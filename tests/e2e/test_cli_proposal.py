import json
import os
import subprocess
from pathlib import Path

from self_nomad.application import SelfNomad


def run(root: Path, state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["XDG_STATE_HOME"] = str(state)
    return subprocess.run(
        ["self-nomad", "--repo", str(root), "--json", *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True, text=True)


def test_cli_propose_validate_review_and_approve(tmp_path: Path) -> None:
    app = SelfNomad.initialize(tmp_path / "agent", name="cli-test")
    root = app.repository.root
    git(root, "config", "user.name", "CLI Test")
    git(root, "config", "user.email", "cli@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
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
    state = tmp_path / "state"

    proposed = run(root, state, "propose", "--reason", "Update preference", "--change", str(change))
    proposal_id = json.loads(proposed.stdout)["result"]["proposal"]["id"]
    validated = run(root, state, "validate", proposal_id)
    reviewed = run(root, state, "review", proposal_id)
    approved = run(root, state, "approve", proposal_id, "--identifier", "owner")

    assert json.loads(validated.stdout)["result"]["status"] == "validated"
    assert json.loads(reviewed.stdout)["result"]["proposal"]["reason"] == "Update preference"
    assert json.loads(approved.stdout)["result"]["status"] == "approved"

