import json
import os
import shutil
import subprocess
from pathlib import Path

from self_nomad.application import SelfNomad

FIXTURES = Path(__file__).parents[1] / "fixtures"


def command(root: Path, state: Path, *arguments: str) -> dict[str, object]:
    environment = os.environ.copy()
    environment["XDG_STATE_HOME"] = str(state)
    completed = subprocess.run(
        ["self-nomad", "--repo", str(root), "--json", *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def committed_repository(tmp_path: Path) -> SelfNomad:
    app = SelfNomad.initialize(tmp_path / "self", name="adapter-e2e")
    git(app.repository.root, "config", "user.name", "Adapter Test")
    git(app.repository.root, "config", "user.email", "adapter@example.invalid")
    git(app.repository.root, "add", ".")
    git(app.repository.root, "commit", "-m", "initial")
    return app


def test_cli_hermes_import_creates_isolated_proposal(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    runtime = tmp_path / "hermes"
    shutil.copytree(FIXTURES / "hermes/minimal", runtime)
    original = git(app.repository.root, "rev-parse", "HEAD")
    payload = command(
        app.repository.root,
        tmp_path / "state",
        "import",
        "--adapter",
        "hermes",
        "--from",
        str(runtime),
        "--yes",
    )
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["proposal"]["status"] == "materialized"  # type: ignore[index]
    assert git(app.repository.root, "rev-parse", "HEAD") == original
    assert (app.repository.root / "identity/persona.md").read_text() == "# Persona\n"


def test_cli_openclaw_restore_preview_then_apply(tmp_path: Path) -> None:
    app = committed_repository(tmp_path)
    target = tmp_path / "workspace"
    preview = command(
        app.repository.root,
        tmp_path / "state",
        "restore",
        "--adapter",
        "openclaw",
        "--to",
        str(target),
    )
    assert not target.exists()
    assert preview["result"]["applied"] is False  # type: ignore[index]
    applied = command(
        app.repository.root,
        tmp_path / "state",
        "restore",
        "--adapter",
        "openclaw",
        "--to",
        str(target),
        "--yes",
    )
    assert applied["result"]["applied"] is True  # type: ignore[index]
    assert (target / "AGENTS.md").is_file()
    assert not (target / "BOOTSTRAP.md").exists()
