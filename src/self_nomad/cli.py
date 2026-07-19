import json
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer
import yaml
from pydantic import TypeAdapter, ValidationError
from rich.console import Console

from self_nomad import __version__
from self_nomad.adapters import default_registry
from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation, RuntimeRef
from self_nomad.errors import AmbiguousRuntimeError, RepositoryNotFoundError, SelfNomadError

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()


class Context:
    repo: Path | None = None
    json_output: bool = False


def emit(command: str, ok: bool, result: object, warnings: list[object] | None = None) -> None:
    payload = {
        "schema_version": 1,
        "command": command,
        "ok": ok,
        "result": result,
        "warnings": warnings or [],
        "errors": [],
    }
    if state.json_output:
        typer.echo(json.dumps(payload, default=str, sort_keys=True))


def fail(command: str, exc: Exception, code: int = 2) -> NoReturn:
    if state.json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": 1,
                    "command": command,
                    "ok": False,
                    "result": {},
                    "warnings": [],
                    "errors": [str(exc)],
                },
                sort_keys=True,
            )
        )
    else:
        console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(code) from exc


state = Context()


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def callback(
    repo: Annotated[Path | None, typer.Option("--repo")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    version: Annotated[
        bool | None, typer.Option("--version", callback=version_callback, is_eager=True)
    ] = None,
) -> None:
    """Manage a portable agent self repository."""
    state.repo = repo
    state.json_output = json_output


@app.command()
def init(
    path: Path,
    name: Annotated[str, typer.Option("--name")],
    description: Annotated[str | None, typer.Option("--description")] = None,
    git: Annotated[bool, typer.Option("--git/--no-git")] = True,
) -> None:
    """Create a conservative self repository."""
    try:
        instance = SelfNomad.initialize(
            path, name=name, description=description, initialize_git=git
        )
    except (SelfNomadError, OSError, ValueError) as exc:
        fail("init", exc)
    result = {"repository": str(instance.repository.root)}
    emit("init", True, result)
    if not state.json_output:
        console.print(f"Initialized self repository at [bold]{instance.repository.root}[/bold]")


@app.command()
def validate(
    proposal_id: Annotated[UUID | None, typer.Argument()] = None,
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Validate repository structure and referenced artifacts."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        if proposal_id is not None:
            record = instance.proposals().validate(proposal_id)
            emit("validate", True, record.model_dump(mode="json"))
            if not state.json_output:
                console.print(f"Proposal {proposal_id} is valid.")
            return
        result = instance.repository.validate(strict=strict)
    except SelfNomadError as exc:
        fail("validate", exc, 3)
    emit("validate", result.valid, result.model_dump(mode="json"))
    if not state.json_output:
        for finding in result.findings:
            console.print(f"{finding.severity.upper()} {finding.code}: {finding.message}")
        console.print("Repository is valid." if result.valid else "Repository is invalid.")
    if not result.valid:
        raise typer.Exit(3)


@app.command()
def status() -> None:
    """Report repository identity and validation status."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        manifest = instance.repository.load_manifest()
        validation = instance.repository.validate()
    except SelfNomadError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc
    result = {
        "repository": str(instance.repository.root),
        "self": manifest.self.model_dump(mode="json"),
        "valid": validation.valid,
        "proposals": [
            {"id": str(record.proposal.id), "status": record.status}
            for record in instance.proposals().store.list()
        ],
    }
    emit("status", validation.valid, result)
    if not state.json_output:
        console.print(f"{manifest.self.name}: {'valid' if validation.valid else 'invalid'}")


def runtime_for(adapter_name: str, path: Path | None) -> RuntimeRef:
    adapter = default_registry().get(adapter_name)
    detection = adapter.detect(path)
    if not detection.candidates:
        raise RepositoryNotFoundError(f"no {adapter_name} runtime found")
    if len(detection.candidates) > 1:
        raise AmbiguousRuntimeError(
            f"multiple {adapter_name} runtimes found; select one with --path/--from"
        )
    return detection.candidates[0]


@app.command()
def detect(
    adapter_name: Annotated[str, typer.Option("--adapter")] = "hermes",
    path: Annotated[Path | None, typer.Option("--path")] = None,
) -> None:
    """Detect compatible runtime instances without mutation."""
    try:
        result = default_registry().get(adapter_name).detect(path)
    except SelfNomadError as exc:
        fail("detect", exc)
    emit("detect", True, result.model_dump(mode="json"))
    if not state.json_output:
        for candidate in result.candidates:
            console.print(f"{candidate.name}: {candidate.root}")


@app.command("diff")
def diff_runtime(
    adapter_name: Annotated[str, typer.Option("--adapter")],
    direction: Annotated[str, typer.Option("--direction")],
    path: Annotated[Path | None, typer.Option("--path")] = None,
) -> None:
    """Show deterministic import or restore drift without writes."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        adapter = default_registry().get(adapter_name)
        runtime = runtime_for(adapter_name, path)
        plan = (
            adapter.plan_import(runtime, instance.repository)
            if direction == "import"
            else adapter.plan_restore(instance.repository, runtime)
        )
        if direction not in {"import", "restore"}:
            raise ValueError("direction must be import or restore")
    except (SelfNomadError, ValueError) as exc:
        fail("diff", exc)
    emit("diff", True, plan.model_dump(mode="json"))
    if not state.json_output:
        for mapping in plan.mappings:
            console.print(
                f"{mapping.fidelity.value.upper():10} {mapping.action:9} {mapping.artifact}"
            )
        for excluded in plan.exclusions:
            console.print(f"{excluded.fidelity.value.upper():18} {excluded.artifact}")


@app.command("import")
def import_runtime(
    adapter_name: Annotated[str, typer.Option("--adapter")],
    source_path: Annotated[Path | None, typer.Option("--from")] = None,
    reason: Annotated[str, typer.Option("--reason")] = "Import durable runtime state",
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Plan an import and optionally create an isolated proposal."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        adapter = default_registry().get(adapter_name)
        plan = adapter.plan_import(runtime_for(adapter_name, source_path), instance.repository)
        if not yes:
            emit("import", True, {"applied": False, "plan": plan.model_dump(mode="json")})
            if not state.json_output:
                console.print("Import plan only; pass --yes to create a proposal.")
            return
        record = instance.create_import_proposal(plan, reason=reason)
    except SelfNomadError as exc:
        fail("import", exc)
    emit("import", True, {"applied": True, "proposal": record.model_dump(mode="json")})
    if not state.json_output:
        console.print(f"Created import proposal {record.proposal.id}.")


@app.command()
def restore(
    adapter_name: Annotated[str, typer.Option("--adapter")],
    target: Annotated[Path, typer.Option("--to")],
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Plan a restore and apply only with explicit confirmation."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        adapter = default_registry().get(adapter_name)
        runtime = RuntimeRef(adapter=adapter_name, root=target, name=target.name)
        plan = adapter.plan_restore(instance.repository, runtime)
        validation = adapter.validate(instance.repository, runtime)
        if not validation.valid:
            raise ValueError("adapter validation failed")
        if not yes:
            emit("restore", True, {"applied": False, "plan": plan.model_dump(mode="json")})
            if not state.json_output:
                console.print("Restore plan only; pass --yes to apply it.")
            return
        result = adapter.apply_restore(plan)
    except (SelfNomadError, ValueError) as exc:
        fail("restore", exc)
    emit("restore", True, {"applied": True, "result": result.model_dump(mode="json")})
    if not state.json_output:
        console.print(f"Restored {len(result.written)} files; backup: {result.backup_root}")


@app.command()
def propose(
    reason: Annotated[str, typer.Option("--reason")],
    change: Annotated[Path, typer.Option("--change", exists=True, dir_okay=False)],
    target_branch: Annotated[str | None, typer.Option("--target-branch")] = None,
) -> None:
    """Materialize a typed change document in an isolated worktree."""
    try:
        raw = yaml.safe_load(change.read_text(encoding="utf-8"))
        operations_raw = raw.get("operations") if isinstance(raw, dict) else raw
        operations = TypeAdapter(list[FileOperation]).validate_python(operations_raw)
        instance = SelfNomad.open(state.repo or Path.cwd())
        record = instance.proposals().create(
            reason=reason, operations=operations, target_branch=target_branch
        )
    except (SelfNomadError, OSError, UnicodeError, yaml.YAMLError, ValidationError) as exc:
        fail("propose", exc)
    emit("propose", True, record.model_dump(mode="json"))
    if not state.json_output:
        console.print(f"Materialized proposal [bold]{record.proposal.id}[/bold]")


@app.command()
def review(proposal_id: UUID) -> None:
    """Show proposal provenance, operations, and state."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        record = instance.proposals().store.load(proposal_id)
    except SelfNomadError as exc:
        fail("review", exc)
    emit("review", True, record.model_dump(mode="json"))
    if not state.json_output:
        console.print(f"Proposal {proposal_id}: {record.status}")
        console.print(f"Reason: {record.proposal.reason}")
        for operation in record.proposal.operations:
            console.print(f"  {operation.kind.upper():7} {operation.path}")


@app.command()
def approve(
    proposal_id: UUID,
    identifier: Annotated[str | None, typer.Option("--identifier")] = None,
) -> None:
    """Record approval for a validated proposal."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        record = instance.proposals().approve(proposal_id, identifier)
    except SelfNomadError as exc:
        fail("approve", exc)
    emit("approve", True, record.model_dump(mode="json"))
    if not state.json_output:
        console.print(f"Approved proposal {proposal_id}.")


@app.command("apply")
def apply_proposal(proposal_id: UUID) -> None:
    """Atomically advance the target ref to an approved proposal."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        record = instance.proposals().apply(proposal_id)
    except SelfNomadError as exc:
        fail("apply", exc, 4)
    emit("apply", True, record.model_dump(mode="json"))
    if not state.json_output:
        console.print(f"Applied proposal {proposal_id} at {record.applied_commit}.")


@app.command()
def reject(
    proposal_id: UUID,
    reason: Annotated[str, typer.Option("--reason")],
) -> None:
    """Reject a pending proposal."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        record = instance.proposals().reject(proposal_id, reason)
    except SelfNomadError as exc:
        fail("reject", exc)
    emit("reject", True, record.model_dump(mode="json"))
    if not state.json_output:
        console.print(f"Rejected proposal {proposal_id}.")


def main() -> None:
    app()
