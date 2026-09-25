"""In-process Typer CLI tests so CLI lines contribute to coverage.

Subprocess installed-command coverage remains in test_cli_subprocess.py and
the release smoke harness.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from self_nomad import __version__
from self_nomad.application import SelfNomad
from self_nomad.cli import app
from tests.helpers import ensure_initial_commit, run_git

FIXTURES = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _json_invoke(args: list[str]) -> dict[str, object]:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def test_cli_version_and_help_inprocess() -> None:
    version = runner.invoke(app, ["--version"], catch_exceptions=False)
    assert version.exit_code == 0
    assert version.stdout.strip() == project_version()
    assert version.stdout.strip() == __version__
    help_result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert help_result.exit_code == 0
    assert "Manage a portable agent self repository" in help_result.stdout
    assert "self-nomad" in help_result.stdout
    assert "untethered" in help_result.stdout


def test_cli_about_human_and_json() -> None:
    human = runner.invoke(app, ["about"], catch_exceptions=False)
    assert human.exit_code == 0
    assert "self-nomad" in human.stdout
    assert "untethered" in human.stdout
    assert "not" in human.stdout.lower()
    payload = _json_invoke(["--json", "about"])
    assert payload["ok"] is True
    assert payload["command"] == "about"
    assert payload["result"]["version"] == project_version()  # type: ignore[index]
    assert payload["schema_version"] == 1


def test_cli_init_and_strict_validate_human(isolated_env: Path, tmp_path: Path) -> None:
    repo = tmp_path / "pretty"
    init = runner.invoke(
        app, ["init", str(repo), "--name", "pretty-agent"], catch_exceptions=False
    )
    assert init.exit_code == 0, init.stdout + init.stderr
    assert "pretty" in init.stdout
    validated = runner.invoke(
        app, ["--repo", str(repo), "validate", "--strict"], catch_exceptions=False
    )
    assert validated.exit_code == 0, validated.stdout
    assert "valid" in validated.stdout.lower()


def test_cli_init_and_strict_validate_json(isolated_env: Path, tmp_path: Path) -> None:
    repo = tmp_path / "agent"
    init = _json_invoke(["--json", "init", str(repo), "--name", "inprocess"])
    assert init["ok"] is True
    assert init["schema_version"] == 1
    assert init["command"] == "init"
    assert "errors" in init and init["errors"] == []
    assert run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    validated = _json_invoke(["--repo", str(repo), "--json", "validate", "--strict"])
    assert validated["ok"] is True
    assert validated["schema_version"] == 1
    assert validated["command"] == "validate"
    result = validated["result"]
    assert isinstance(result, dict)
    assert result.get("valid") is True


def test_cli_propose_validate_review_and_approve(isolated_env: Path, tmp_path: Path) -> None:
    app_instance = SelfNomad.initialize(tmp_path / "agent", name="cli-test")
    root = app_instance.repository.root
    ensure_initial_commit(root)
    source = tmp_path / "user.md"
    source.write_text("# User\n\nPrefers concise output.\n", encoding="utf-8")
    change = tmp_path / "changes.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: identity/user.md\n"
        f"    content_source: {source}\n",
        encoding="utf-8",
    )

    proposed = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "propose",
            "--reason",
            "Update preference",
            "--change",
            str(change),
        ]
    )
    proposal = proposed["result"]
    assert isinstance(proposal, dict)
    proposal_id = proposal["proposal"]["id"]  # type: ignore[index]

    validated = _json_invoke(["--repo", str(root), "--json", "validate", str(proposal_id)])
    reviewed = _json_invoke(["--repo", str(root), "--json", "review", str(proposal_id)])
    approved = _json_invoke(
        ["--repo", str(root), "--json", "approve", str(proposal_id), "--identifier", "owner"]
    )

    assert validated["result"]["status"] == "validated"  # type: ignore[index]
    assert reviewed["result"]["proposal"]["reason"] == "Update preference"  # type: ignore[index]
    assert "unified_diff" in reviewed["result"]
    assert "identity/user.md" in str(reviewed["result"]["unified_diff"])
    assert approved["result"]["status"] == "approved"  # type: ignore[index]


def test_cli_hermes_import_creates_isolated_proposal(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "self", name="adapter-e2e")
    root = instance.repository.root
    ensure_initial_commit(root)
    runtime = tmp_path / "hermes"
    shutil.copytree(FIXTURES / "hermes/minimal", runtime)
    original = run_git(root, "rev-parse", "HEAD")

    payload = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "import",
            "--adapter",
            "hermes",
            "--from",
            str(runtime),
            "--yes",
        ]
    )
    result = payload["result"]
    assert isinstance(result, dict)
    assert result["proposal"]["status"] == "materialized"  # type: ignore[index]
    assert run_git(root, "rev-parse", "HEAD") == original
    assert (root / "identity/persona.md").read_text() == "# Persona\n"


def test_cli_openclaw_restore_preview_then_apply(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "self", name="adapter-e2e")
    root = instance.repository.root
    ensure_initial_commit(root)
    target = tmp_path / "workspace"

    preview = _json_invoke(
        ["--repo", str(root), "--json", "restore", "--adapter", "openclaw", "--to", str(target)]
    )
    assert not target.exists()
    assert preview["result"]["applied"] is False  # type: ignore[index]

    applied = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "restore",
            "--adapter",
            "openclaw",
            "--to",
            str(target),
            "--yes",
        ]
    )
    assert applied["result"]["applied"] is True  # type: ignore[index]
    assert (target / "AGENTS.md").is_file()
    assert not (target / "BOOTSTRAP.md").exists()


def test_cli_status_detect_diff_and_import_preview(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "self", name="status-agent")
    root = instance.repository.root
    ensure_initial_commit(root)
    runtime = tmp_path / "hermes"
    shutil.copytree(FIXTURES / "hermes/minimal", runtime)

    status = _json_invoke(["--repo", str(root), "--json", "status"])
    assert status["ok"] is True
    assert status["result"]["self"]["name"] == "status-agent"  # type: ignore[index]
    human_status = runner.invoke(app, ["--repo", str(root), "status"], catch_exceptions=False)
    assert human_status.exit_code == 0
    assert "status-agent" in human_status.stdout
    assert "valid" in human_status.stdout

    detect = _json_invoke(
        ["--json", "detect", "--adapter", "hermes", "--path", str(runtime)]
    )
    assert detect["ok"] is True
    assert len(detect["result"]["candidates"]) == 1  # type: ignore[index]

    diff = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "diff",
            "--adapter",
            "hermes",
            "--direction",
            "import",
            "--path",
            str(runtime),
        ]
    )
    assert diff["ok"] is True
    assert "mappings" in diff["result"]  # type: ignore[index]

    preview = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "import",
            "--adapter",
            "hermes",
            "--from",
            str(runtime),
        ]
    )
    assert preview["result"]["applied"] is False  # type: ignore[index]


def test_cli_reject_and_human_output(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "agent", name="reject-agent")
    root = instance.repository.root
    ensure_initial_commit(root)
    source = tmp_path / "user.md"
    source.write_text("# User\n\nReject path content.\n", encoding="utf-8")
    change = tmp_path / "changes.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: identity/user.md\n"
        f"    content_source: {source}\n",
        encoding="utf-8",
    )
    proposed = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "propose",
            "--reason",
            "will reject",
            "--change",
            str(change),
        ]
    )
    proposal_id = proposed["result"]["proposal"]["id"]  # type: ignore[index]

    human_review = runner.invoke(
        app, ["--repo", str(root), "review", str(proposal_id)], catch_exceptions=False
    )
    assert human_review.exit_code == 0
    assert "will reject" in human_review.stdout
    assert "REPLACE" in human_review.stdout
    assert "identity/user.md" in human_review.stdout
    assert any(
        token in human_review.stdout
        for token in ("Reject path content", "@@", "identity/user.md")
    )

    rejected = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "reject",
            str(proposal_id),
            "--reason",
            "not wanted",
        ]
    )
    assert rejected["result"]["status"] == "rejected"  # type: ignore[index]


def test_cli_fail_json_envelope_on_missing_repo(isolated_env: Path, tmp_path: Path) -> None:
    missing = tmp_path / "no-such-repo"
    result = runner.invoke(
        app,
        ["--repo", str(missing), "--json", "validate", "--strict"],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["schema_version"] == 1
    assert payload["command"] == "validate"
    assert payload["errors"]


def test_cli_apply_on_checked_out_main(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "agent", name="apply-agent")
    root = instance.repository.root
    ensure_initial_commit(root)
    source = tmp_path / "user.md"
    source.write_text("# User\n\nApply me.\n", encoding="utf-8")
    change = tmp_path / "changes.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: identity/user.md\n"
        f"    content_source: {source}\n",
        encoding="utf-8",
    )
    proposed = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "propose",
            "--reason",
            "apply path",
            "--change",
            str(change),
        ]
    )
    proposal_id = proposed["result"]["proposal"]["id"]  # type: ignore[index]
    _json_invoke(["--repo", str(root), "--json", "validate", str(proposal_id)])
    _json_invoke(
        ["--repo", str(root), "--json", "approve", str(proposal_id), "--identifier", "owner"]
    )
    applied = _json_invoke(["--repo", str(root), "--json", "apply", str(proposal_id)])
    assert applied["ok"] is True
    assert applied["result"]["status"] == "applied"  # type: ignore[index]
    assert "Apply me." in (root / "identity" / "user.md").read_text(encoding="utf-8")
    assert run_git(root, "symbolic-ref", "--short", "HEAD") == "main"

    listed = _json_invoke(["--repo", str(root), "--json", "proposals"])
    assert listed["ok"] is True
    assert listed["result"]["proposals"][0]["status"] == "applied"  # type: ignore[index]
    history = _json_invoke(["--repo", str(root), "--json", "log"])
    assert history["ok"] is True
    subjects = [item["subject"] for item in history["result"]["commits"]]  # type: ignore[index]
    assert any("audit" in str(subject) for subject in subjects)


def test_cli_pack_and_check(isolated_env: Path, tmp_path: Path) -> None:
    repo = tmp_path / "packed-agent"
    _json_invoke(["--json", "init", str(repo), "--name", "packed-agent"])
    archive = tmp_path / "packed-agent.snpack"
    packed = _json_invoke(
        ["--repo", str(repo), "--json", "pack", "--out", str(archive), "--profile", "specialist"]
    )
    assert packed["ok"] is True
    assert packed["command"] == "pack"
    assert packed["result"]["profile"] == "specialist"
    assert archive.is_file()
    assert "user_profile" in packed["result"]["summary"]["omitted"]  # type: ignore[index]
    checked = _json_invoke(["--json", "pack", "--check", str(archive)])
    assert checked["ok"] is True
    assert checked["result"]["valid"] is True
    human = runner.invoke(app, ["pack", "--check", str(archive)], catch_exceptions=False)
    assert human.exit_code == 0
    assert "specialist" in human.stdout
    dest = tmp_path / "from-pack"
    installed = _json_invoke(
        ["--json", "install", str(archive), "--to", str(dest)]
    )
    assert installed["ok"] is True
    assert installed["command"] == "install"
    assert dest.is_dir()
    validated = _json_invoke(["--repo", str(dest), "--json", "validate", "--strict"])
    assert validated["result"]["valid"] is True
    restore = _json_invoke(
        [
            "--repo",
            str(dest),
            "--json",
            "restore",
            "--adapter",
            "openclaw",
            "--to",
            str(tmp_path / "workspace"),
        ]
    )
    assert restore["result"]["applied"] is False


def _materialized_proposal(tmp_path: Path, name: str, body: str) -> tuple[Path, str]:
    instance = SelfNomad.initialize(tmp_path / name, name=name)
    root = instance.repository.root
    ensure_initial_commit(root)
    source = tmp_path / f"{name}-user.md"
    source.write_text(f"# User\n\n{body}\n", encoding="utf-8")
    change = tmp_path / f"{name}-change.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: identity/user.md\n"
        f"    content_source: {source}\n",
        encoding="utf-8",
    )
    proposed = _json_invoke(
        [
            "--repo",
            str(root),
            "--json",
            "propose",
            "--reason",
            body,
            "--change",
            str(change),
        ]
    )
    proposal_id = proposed["result"]["proposal"]["id"]  # type: ignore[index]
    return root, str(proposal_id)


def test_cli_review_interactive_quit(isolated_env: Path, tmp_path: Path) -> None:
    root, proposal_id = _materialized_proposal(tmp_path, "quit-agent", "quit path")
    result = runner.invoke(
        app,
        ["--repo", str(root), "review", proposal_id, "--interactive"],
        input="quit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "No change" in result.stdout
    status = _json_invoke(["--repo", str(root), "--json", "status"])
    assert status["result"]["proposals"][0]["status"] == "materialized"  # type: ignore[index]


def test_cli_review_interactive_approve_does_not_apply(
    isolated_env: Path, tmp_path: Path
) -> None:
    root, proposal_id = _materialized_proposal(tmp_path, "ia-agent", "interactive approve")
    before = run_git(root, "rev-parse", "HEAD")
    result = runner.invoke(
        app,
        ["--repo", str(root), "review", proposal_id, "--interactive", "--identifier", "owner"],
        input="approve\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Approved proposal" in result.stdout
    assert "separate command" in result.stdout
    reviewed = _json_invoke(["--repo", str(root), "--json", "review", proposal_id])
    assert reviewed["result"]["status"] == "approved"  # type: ignore[index]
    assert run_git(root, "rev-parse", "HEAD") == before
    assert (root / "identity" / "user.md").read_text(encoding="utf-8") == "# User\n"


def test_cli_review_interactive_reject(isolated_env: Path, tmp_path: Path) -> None:
    root, proposal_id = _materialized_proposal(tmp_path, "ir-agent", "interactive reject")
    result = runner.invoke(
        app,
        ["--repo", str(root), "review", proposal_id, "--interactive"],
        input="reject\nnot wanted interactively\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Rejected" in result.stdout
    reviewed = _json_invoke(["--repo", str(root), "--json", "review", proposal_id])
    assert reviewed["result"]["status"] == "rejected"  # type: ignore[index]
    assert reviewed["result"]["rejection_reason"] == "not wanted interactively"


def test_cli_review_interactive_rejects_json_combo(isolated_env: Path, tmp_path: Path) -> None:
    root, proposal_id = _materialized_proposal(tmp_path, "ij-agent", "json combo")
    result = runner.invoke(
        app,
        ["--repo", str(root), "--json", "review", proposal_id, "--interactive"],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "review"
    assert any("interactive" in item for item in payload["errors"])
