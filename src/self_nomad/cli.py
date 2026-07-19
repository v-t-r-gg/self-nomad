import json
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer
import yaml
from pydantic import TypeAdapter, ValidationError
from rich.console import Console

from self_nomad import __version__
from self_nomad.application import SelfNomad
from self_nomad.domain import FileOperation
from self_nomad.errors import SelfNomadError

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
