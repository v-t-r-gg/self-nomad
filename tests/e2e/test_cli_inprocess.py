"""In-process Typer CLI tests so CLI lines contribute to coverage.

Subprocess installed-command coverage remains in test_cli_subprocess.py and
the release smoke harness.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from self_nomad.application import SelfNomad
from self_nomad.cli import app
from tests.helpers import configure_git_identity, run_git

FIXTURES = Path(__file__).parents[1] / "fixtures"
runner = CliRunner()


def _json_invoke(args: list[str]) -> dict[str, object]:
    result = runner.invoke(app, args, catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def test_cli_version_and_help_inprocess() -> None:
    version = runner.invoke(app, ["--version"], catch_exceptions=False)
    assert version.exit_code == 0
    assert version.stdout.strip() == "0.1.0rc1"
    help_result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert help_result.exit_code == 0
    assert "Manage a portable agent self repository" in help_result.stdout


def test_cli_init_and_strict_validate_json(isolated_env: Path, tmp_path: Path) -> None:
    repo = tmp_path / "agent"
    init = _json_invoke(["--json", "init", str(repo), "--name", "inprocess"])
    assert init["ok"] is True
    assert init["schema_version"] == 1
    assert init["command"] == "init"
    assert "errors" in init and init["errors"] == []

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
    configure_git_identity(root, name="CLI Test", email="cli@example.invalid")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
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
    assert approved["result"]["status"] == "approved"  # type: ignore[index]


def test_cli_hermes_import_creates_isolated_proposal(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "self", name="adapter-e2e")
    root = instance.repository.root
    configure_git_identity(root, name="Adapter Test", email="adapter@example.invalid")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
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
    configure_git_identity(root, name="Adapter Test", email="adapter@example.invalid")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
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
    configure_git_identity(root)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
    runtime = tmp_path / "hermes"
    shutil.copytree(FIXTURES / "hermes/minimal", runtime)

    status = _json_invoke(["--repo", str(root), "--json", "status"])
    assert status["ok"] is True
    assert status["result"]["self"]["name"] == "status-agent"  # type: ignore[index]

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
    configure_git_identity(root)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
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


def test_cli_apply_after_switch_away(isolated_env: Path, tmp_path: Path) -> None:
    instance = SelfNomad.initialize(tmp_path / "agent", name="apply-agent")
    root = instance.repository.root
    configure_git_identity(root)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
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
    # Checked-out-target rule: switch main away before apply.
    run_git(root, "switch", "-c", "review-work")
    applied = _json_invoke(["--repo", str(root), "--json", "apply", str(proposal_id)])
    assert applied["ok"] is True
    assert applied["result"]["status"] == "applied"  # type: ignore[index]
