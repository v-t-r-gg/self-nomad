import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from self_nomad import __version__
from self_nomad.application import SelfNomad
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
        if state.json_output:
            typer.echo(json.dumps({"schema_version": 1, "command": "init", "ok": False,
                                   "result": {}, "warnings": [], "errors": [str(exc)]}))
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc
    result = {"repository": str(instance.repository.root)}
    emit("init", True, result)
    if not state.json_output:
        console.print(f"Initialized self repository at [bold]{instance.repository.root}[/bold]")


@app.command()
def validate(
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    """Validate repository structure and referenced artifacts."""
    try:
        instance = SelfNomad.open(state.repo or Path.cwd())
        result = instance.repository.validate(strict=strict)
    except SelfNomadError as exc:
        if state.json_output:
            typer.echo(json.dumps({"schema_version": 1, "command": "validate", "ok": False,
                                   "result": {}, "warnings": [], "errors": [str(exc)]}))
        else:
            console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc
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
    }
    emit("status", validation.valid, result)
    if not state.json_output:
        console.print(f"{manifest.self.name}: {'valid' if validation.valid else 'invalid'}")


def main() -> None:
    app()

