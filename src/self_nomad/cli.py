import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn
from uuid import UUID

import typer
import yaml
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from typer.core import TyperGroup

from self_nomad import __version__
from self_nomad.adapters import default_registry
from self_nomad.application import SelfNomad
from self_nomad.branding import print_help_identity
from self_nomad.domain import FileOperation, RuntimeRef
from self_nomad.errors import (
    AmbiguousRuntimeError,
    ConflictError,
    IntakeError,
    RepositoryNotFoundError,
    SelfNomadError,
)
from self_nomad.filesystem import contained_path
from self_nomad.intake import (
    load_proposal_request_from_path,
    load_proposal_request_from_stream,
)
from self_nomad.manifest.loader import load_yaml
from self_nomad.policy import Policy
from self_nomad.render import (
    render_about,
    render_detection,
    render_init,
    render_install,
    render_intake_preview,
    render_intake_submit,
    render_log,
    render_pack,
    render_plan,
    render_proposal_valid,
    render_proposals,
    render_review,
    render_simple,
    render_status,
    render_validation,
)
from self_nomad.review_ui import review_record, run_interactive_review


class BrandedGroup(TyperGroup):
    def format_help(self, ctx: Any, formatter: Any) -> None:
        print_help_identity(console)
        super().format_help(ctx, formatter)


app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    cls=BrandedGroup,
    rich_markup_mode="rich",
)
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
        render_init(console, instance.repository.root)


@app.command()
def about() -> None:
    """Show the self-nomad wordmark and what this tool is (and is not)."""
    if state.json_output:
        emit(
            "about",
            True,
            {
                "name": "self-nomad",
                "version": __version__,
                "tagline": "an agent's self, untethered from its runtime",
            },
        )
        return
    render_about(console, __version__)


@app.command("intake")
def intake_command(
    request: Annotated[
        Path,
        typer.Option("--request", exists=False, dir_okay=False, readable=False),
    ],
    submit: Annotated[bool, typer.Option("--submit")] = False,
) -> None:
    """Preview or submit an agent proposal request (preview is default)."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        manifest = instance.repository.load_manifest()
        policy = Policy.model_validate(
            load_yaml(
                contained_path(instance.repository.root, manifest.policy, must_exist=True)
            )
        )
        max_bytes = policy.limits.maximum_request_bytes
        if str(request) == "-":
            loaded = load_proposal_request_from_stream(
                sys.stdin.buffer, maximum_request_bytes=max_bytes
            )
        else:
            loaded = load_proposal_request_from_path(request, maximum_request_bytes=max_bytes)
        service = instance.intake()
        if submit:
            result = service.submit(loaded)
            payload = result.model_dump(mode="json")
            emit("intake", True, payload)
            if not state.json_output:
                render_intake_submit(console, result)
            return
        preview = service.preview(loaded)
        payload = preview.model_dump(mode="json")
        emit("intake", preview.eligible, payload)
        if not state.json_output:
            render_intake_preview(
                console,
                eligible=preview.eligible,
                risk=preview.risk,
                operations=len(preview.operations),
                next_actions=preview.suggested_next,
                findings=preview.findings,
            )
        if not preview.eligible:
            raise typer.Exit(3)
    except IntakeError as exc:
        if state.json_output:
            typer.echo(
                json.dumps(
                    {
                        "schema_version": 1,
                        "command": "intake",
                        "ok": False,
                        "result": {"code": exc.code},
                        "warnings": [],
                        "errors": [f"{exc.code}: {exc}"],
                    },
                    sort_keys=True,
                )
            )
        else:
            console.print(f"[red]{exc.code}:[/red] {exc}")
        raise typer.Exit(2) from exc
    except (SelfNomadError, OSError, ValueError) as exc:
        fail("intake", exc)


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
                render_proposal_valid(console, proposal_id, str(record.status))
            return
        result = instance.repository.validate(strict=strict)
    except SelfNomadError as exc:
        fail("validate", exc, 3)
    emit("validate", result.valid, result.model_dump(mode="json"))
    if not state.json_output:
        render_validation(console, result)
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
        fail("status", exc)
    proposals = [
        {"id": str(record.proposal.id), "status": str(record.status)}
        for record in instance.proposals().store.list()
    ]
    result = {
        "repository": str(instance.repository.root),
        "self": manifest.self.model_dump(mode="json"),
        "valid": validation.valid,
        "proposals": proposals,
    }
    emit("status", validation.valid, result)
    if not state.json_output:
        render_status(
            console,
            name=manifest.self.name,
            self_id=str(manifest.self.id),
            repository=instance.repository.root,
            valid=validation.valid,
            proposals=proposals,
        )


@app.command()
def proposals() -> None:
    """List local proposal records (newest first)."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        records = instance.proposals().list_records()
    except SelfNomadError as exc:
        fail("proposals", exc)
    rows = [
        {
            "id": str(record.proposal.id),
            "status": str(record.status),
            "reason": record.proposal.reason,
            "risk": str(record.proposal.risk),
            "target_branch": record.proposal.target_branch,
        }
        for record in records
    ]
    emit("proposals", True, {"proposals": rows})
    if not state.json_output:
        render_proposals(console, rows)


@app.command()
def pack(
    output: Annotated[Path | None, typer.Option("--out")] = None,
    profile: Annotated[str, typer.Option("--profile")] = "specialist",
    include_long_term_memory: Annotated[
        bool, typer.Option("--include-long-term-memory")
    ] = False,
    check: Annotated[Path | None, typer.Option("--check")] = None,
    list_archive: Annotated[Path | None, typer.Option("--list")] = None,
) -> None:
    """Write or verify a history-free snapshot pack."""
    try:
        if check is not None and list_archive is not None:
            raise ConflictError("pass only one of --check or --list")
        if list_archive is not None:
            summary, names = SelfNomad.list_pack(list_archive)
            payload: dict[str, object] = {
                "path": str(list_archive.resolve()),
                "profile": summary.profile,
                "omitted": summary.omitted,
                "content_digest": summary.content_digest,
                "skills": summary.skills,
                "packer_version": summary.packer_version,
                "members": names,
                "summary": summary.model_dump(mode="json"),
            }
            emit("pack", True, payload)
            if not state.json_output:
                render_pack(console, path=list_archive, summary=summary)
            return
        if check is not None:
            summary = SelfNomad.check_pack(check, profile=profile)
            payload = {
                "valid": True,
                "path": str(check.resolve()),
                "profile": summary.profile,
                "omitted": summary.omitted,
                "content_digest": summary.content_digest,
                "skills": summary.skills,
                "packer_version": summary.packer_version,
                "summary": summary.model_dump(mode="json"),
            }
            emit("pack", True, payload)
            if not state.json_output:
                render_pack(console, path=check, summary=summary)
            return
        instance = SelfNomad.open(state.repo or Path.cwd())
        destination = output
        if destination is None:
            name = instance.repository.load_manifest().self.name
            destination = Path(f"{name}-{profile}.snpack")
        summary = instance.pack(
            destination,
            profile=profile,
            include_long_term_memory=include_long_term_memory,
        )
    except (SelfNomadError, OSError, ValueError) as exc:
        fail("pack", exc)
    payload = {
        "path": str(destination.resolve()),
        "profile": summary.profile,
        "content_digest": summary.content_digest,
        "summary": summary.model_dump(mode="json"),
    }
    emit("pack", True, payload)
    if not state.json_output:
        render_pack(console, path=destination, summary=summary)


@app.command()
def install(
    archive: Path,
    destination: Annotated[Path, typer.Option("--to")],
    git: Annotated[bool, typer.Option("--git/--no-git")] = True,
) -> None:
    """Install a snapshot pack into a new local repository after validation."""
    try:
        instance, summary = SelfNomad.install_pack(
            archive, destination, initialize_git=git
        )
    except (SelfNomadError, OSError, ValueError) as exc:
        fail("install", exc)
    payload = {
        "repository": str(instance.repository.root),
        "content_digest": summary.content_digest,
        "summary": summary.model_dump(mode="json"),
    }
    emit("install", True, payload)
    if not state.json_output:
        render_install(console, path=instance.repository.root, summary=summary)


@app.command("log")
def history_log(
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
) -> None:
    """Show applied proposal commits from Git history on the current branch."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        entries = instance.proposals().applied_history(limit=limit)
    except SelfNomadError as exc:
        fail("log", exc)
    rows = [{"commit": item.commit, "subject": item.subject} for item in entries]
    emit("log", True, {"commits": rows})
    if not state.json_output:
        render_log(console, rows)


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
        render_detection(console, result)


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
        render_plan(console, plan)


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
                render_plan(
                    console,
                    plan,
                    preview_note="Import plan only; pass --yes to create a proposal.",
                )
            return
        record = instance.create_import_proposal(plan, reason=reason)
    except SelfNomadError as exc:
        fail("import", exc)
    emit("import", True, {"applied": True, "proposal": record.model_dump(mode="json")})
    if not state.json_output:
        render_simple(console, "import", f"Created import proposal {record.proposal.id}.")


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
                render_plan(
                    console,
                    plan,
                    preview_note="Restore plan only; pass --yes to apply it.",
                )
            return
        result = adapter.apply_restore(plan)
    except (SelfNomadError, ValueError) as exc:
        fail("restore", exc)
    emit("restore", True, {"applied": True, "result": result.model_dump(mode="json")})
    if not state.json_output:
        render_simple(
            console,
            "restore",
            f"Restored {len(result.written)} files; backup: {result.backup_root}",
        )


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
        render_simple(console, "propose", f"Materialized proposal {record.proposal.id}")


@app.command()
def review(
    proposal_id: UUID,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            help="Approve or reject from this review. Never applies.",
        ),
    ] = False,
    identifier: Annotated[
        str | None,
        typer.Option("--identifier", help="Approval identifier used with --interactive"),
    ] = None,
) -> None:
    """Show proposal provenance, operations, unified diff, and state."""
    if interactive and state.json_output:
        fail("review", ValueError("--interactive cannot be combined with --json"))
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        service = instance.proposals()
        record, diff = review_record(service, proposal_id)
        if interactive:
            record = run_interactive_review(
                console,
                service,
                record,
                identifier=identifier,
                diff=diff,
            )
    except (SelfNomadError, OSError, ValueError) as exc:
        fail("review", exc)
    payload = record.model_dump(mode="json")
    if diff:
        payload["unified_diff"] = diff
    emit("review", True, payload)
    if not state.json_output and not interactive:
        render_review(console, record, diff=diff)


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
        render_simple(console, "approve", f"Approved proposal {proposal_id}.")


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
        render_simple(
            console,
            "apply",
            f"Applied proposal {proposal_id} at {record.applied_commit}.",
        )


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
        render_simple(console, "reject", f"Rejected proposal {proposal_id}.", ok=False)


def main() -> None:
    app()
