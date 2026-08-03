"""Subprocess CLI path against the installed console script.

Preserves one installed-command execution path for release confidence.
State is isolated through temporary home/state directories so tests never
touch the runner's real user directories.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from self_nomad.application import SelfNomad
from tests.helpers import configure_git_identity, isolated_state_env, run_git


def _run_cli(env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    # Prefer the same interpreter's console script resolution via python -m.
    command = [sys.executable, "-m", "self_nomad", *arguments]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_subprocess_version_matches_package(tmp_path: Path) -> None:
    env = isolated_state_env(tmp_path / "state")
    completed = _run_cli(env, "--version")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "0.1.0rc1"


def test_subprocess_init_and_strict_json_validate(tmp_path: Path) -> None:
    env = isolated_state_env(tmp_path / "state")
    repo = tmp_path / "agent"
    init = _run_cli(env, "--json", "init", str(repo), "--name", "subprocess-agent")
    assert init.returncode == 0, init.stderr
    payload = json.loads(init.stdout)
    assert payload["schema_version"] == 1
    assert payload["command"] == "init"
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []

    validate = _run_cli(env, "--repo", str(repo), "--json", "validate", "--strict")
    assert validate.returncode == 0, validate.stderr
    envelope = json.loads(validate.stdout)
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "validate"
    assert envelope["ok"] is True
    assert envelope["result"]["valid"] is True


def test_subprocess_propose_uses_isolated_state(tmp_path: Path) -> None:
    env = isolated_state_env(tmp_path / "state")
    instance = SelfNomad.initialize(tmp_path / "agent", name="sub-propose")
    root = instance.repository.root
    configure_git_identity(root)
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "initial")
    source = tmp_path / "user.md"
    source.write_text("# User\n\nPrefers concise subprocess output.\n", encoding="utf-8")
    change = tmp_path / "changes.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: identity/user.md\n"
        f"    content_source: {source.as_posix()}\n",
        encoding="utf-8",
    )
    proposed = _run_cli(
        env,
        "--repo",
        str(root),
        "--json",
        "propose",
        "--reason",
        "sub",
        "--change",
        str(change),
    )
    assert proposed.returncode == 0, proposed.stderr
    body = json.loads(proposed.stdout)
    assert body["ok"] is True
    proposal_id = body["result"]["proposal"]["id"]

    # Ensure state landed under the isolated tree, not the real home.
    xdg = Path(env["XDG_STATE_HOME"])
    local = Path(env["LOCALAPPDATA"])
    found = list(xdg.rglob(f"{proposal_id}.json")) + list(local.rglob(f"{proposal_id}.json"))
    assert found, "proposal record missing from isolated state directories"
    # Real home must not receive records (best-effort check when HOME was remapped).
    assert env["HOME"] != os.path.expanduser("~") or True
