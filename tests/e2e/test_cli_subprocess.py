"""Subprocess CLI path against the installed console script.

Preserves one installed-command execution path for release confidence.
State is isolated through temporary home/state directories so tests never
touch the runner's real user directories.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from self_nomad import __version__
from self_nomad.application import SelfNomad
from tests.helpers import ensure_initial_commit, isolated_state_env

ROOT = Path(__file__).resolve().parents[2]


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


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
    assert completed.stdout.strip() == project_version()
    assert completed.stdout.strip() == __version__


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
    ensure_initial_commit(root)
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
    # Records are stored as compact UUID hex filenames under platformdirs.
    compact = proposal_id.replace("-", "")
    state_root = tmp_path / "state"
    found = list(state_root.rglob(f"{compact}.json"))
    assert found, (
        f"proposal record missing from isolated state directories under {state_root}; "
        f"LOCALAPPDATA={env.get('LOCALAPPDATA')!r} XDG_STATE_HOME={env.get('XDG_STATE_HOME')!r}"
    )
