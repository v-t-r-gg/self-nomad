#!/usr/bin/env python3
"""Operator acceptance on an installed (non-editable) wheel.

Installs ``dist/self_nomad-*.whl`` into a fresh venv and exercises the
operator loop: init, validate, propose, approve, apply, intake, restore
preview, and validation of the frozen first-RC schema fixture.

Optional ``--previous-wheel`` installs that artifact first, creates a repo,
then upgrades to the current wheel and re-validates (upgrade-path check).

Network: pip bootstrap and runtime dependency resolve, same as
``scripts/release_smoke.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_meta import project_version  # noqa: E402
from scripts.release_smoke import (  # noqa: E402
    SmokeError,
    find_artifacts,
    isolated_env,
    run,
    venv_python,
    venv_self_nomad,
    version_from_artifact_name,
)

UPGRADE_FIXTURE = ROOT / "tests" / "fixtures" / "upgrade" / "v0_1_schema1"


class AcceptanceError(SmokeError):
    """Raised when an operator-acceptance step fails."""


def _json(cli: Path, env: dict[str, str], *arguments: str) -> dict[str, object]:
    completed = run(
        [str(cli), "--json", *arguments],
        artifact="operator-acceptance",
        step=" ".join(arguments[:3]) or "cli",
        env=env,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"not JSON: {completed.stdout!r}") from exc
    if payload.get("ok") is not True:
        raise AcceptanceError(f"command failed: {payload!r}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AcceptanceError(f"result is not an object: {payload!r}")
    return result


def _git(repo: Path, env: dict[str, str], *arguments: str) -> None:
    run(
        ["git", "-C", str(repo), *arguments],
        artifact="operator-acceptance",
        step=f"git {' '.join(arguments[:2])}",
        env=env,
    )


def install_wheel(python: Path, wheel: Path, env: dict[str, str]) -> None:
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        artifact=wheel.name,
        step="upgrade pip",
        env=env,
    )
    run(
        [str(python), "-m", "pip", "install", str(wheel.resolve())],
        artifact=wheel.name,
        step="install wheel",
        env=env,
    )


def select_current_wheel(dist_dir: Path, expected_version: str) -> Path:
    wheels = [path for path in find_artifacts(dist_dir) if path.suffix == ".whl"]
    if not wheels:
        raise AcceptanceError(f"no wheel under {dist_dir}")
    for wheel in wheels:
        if version_from_artifact_name(wheel) == expected_version:
            return wheel
    raise AcceptanceError(
        f"no wheel for {expected_version}; found {[path.name for path in wheels]}"
    )


def configure_repo_git(repo: Path, env: dict[str, str]) -> None:
    _git(repo, env, "config", "user.name", "Operator Acceptance")
    _git(repo, env, "config", "user.email", "operator@example.invalid")


def commit_if_needed(repo: Path, env: dict[str, str], message: str) -> None:
    configure_repo_git(repo, env)
    _git(repo, env, "add", ".")
    completed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--quiet"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode == 1:
        _git(repo, env, "commit", "-m", message)
    elif completed.returncode != 0:
        raise AcceptanceError(completed.stderr or "git diff --cached failed")


def operator_loop(cli: Path, work: Path, env: dict[str, str]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    repo = work / "agent"
    _json(cli, env, "init", str(repo), "--name", "acceptance")
    validated = _json(cli, env, "--repo", str(repo), "validate", "--strict")
    if validated.get("valid") is not True:
        raise AcceptanceError(f"fresh repo invalid: {validated!r}")
    commit_if_needed(repo, env, "initial self")

    memory = work / "memory.md"
    memory.write_text("# Memory\n\n- Operator acceptance recorded this fact.\n", encoding="utf-8")
    change = work / "change.yaml"
    change.write_text(
        "operations:\n"
        "  - kind: replace\n"
        "    path: memory/MEMORY.md\n"
        f"    content_source: {memory.as_posix()}\n",
        encoding="utf-8",
    )
    proposed = _json(
        cli,
        env,
        "--repo",
        str(repo),
        "propose",
        "--reason",
        "Record acceptance fact",
        "--change",
        str(change),
    )
    proposal = proposed.get("proposal")
    if not isinstance(proposal, dict) or "id" not in proposal:
        raise AcceptanceError(f"propose missing id: {proposed!r}")
    proposal_id = str(proposal["id"])
    _json(cli, env, "--repo", str(repo), "validate", proposal_id)
    _json(cli, env, "--repo", str(repo), "approve", proposal_id, "--identifier", "operator")
    applied = _json(cli, env, "--repo", str(repo), "apply", proposal_id)
    if applied.get("status") != "applied":
        raise AcceptanceError(f"apply status: {applied!r}")
    text = (repo / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    if "Operator acceptance recorded this fact" not in text:
        raise AcceptanceError("applied tree missing proposed memory")

    request = work / "intake.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "request_id": "acceptance:memory:1",
                "reason": "Record a second acceptance fact via intake.",
                "source": {
                    "runtime": "openclaw",
                    "agent_identifier": "acceptance",
                    "correlation_id": "rc1",
                },
                "operations": [
                    {
                        "kind": "replace",
                        "path": "memory/MEMORY.md",
                        "content": (
                            "# Memory\n\n"
                            "- Operator acceptance recorded this fact.\n"
                            "- Intake updated the same repository.\n"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    preview = _json(cli, env, "--repo", str(repo), "intake", "--request", str(request))
    if preview.get("eligible") is not True:
        raise AcceptanceError(f"intake preview not eligible: {preview!r}")
    submitted = _json(
        cli, env, "--repo", str(repo), "intake", "--request", str(request), "--submit"
    )
    if submitted.get("status") != "materialized":
        raise AcceptanceError(f"intake submit: {submitted!r}")

    target = work / "openclaw-workspace"
    restore = _json(
        cli,
        env,
        "--repo",
        str(repo),
        "restore",
        "--adapter",
        "openclaw",
        "--to",
        str(target),
    )
    if restore.get("applied") is not False:
        raise AcceptanceError(f"restore preview should not apply: {restore!r}")
    if target.exists():
        raise AcceptanceError("restore preview wrote the runtime tree")

    archive = work / "acceptance.snpack"
    packed = _json(
        cli, env, "--repo", str(repo), "pack", "--out", str(archive), "--profile", "specialist"
    )
    if packed.get("profile") != "specialist":
        raise AcceptanceError(f"pack profile: {packed!r}")
    installed_root = work / "installed"
    installed = _json(cli, env, "install", str(archive), "--to", str(installed_root))
    if not installed_root.is_dir():
        raise AcceptanceError(f"install missing dest: {installed!r}")
    installed_valid = _json(
        cli, env, "--repo", str(installed_root), "validate", "--strict"
    )
    if installed_valid.get("valid") is not True:
        raise AcceptanceError(f"installed repo invalid: {installed_valid!r}")
    installed_restore = _json(
        cli,
        env,
        "--repo",
        str(installed_root),
        "restore",
        "--adapter",
        "openclaw",
        "--to",
        str(work / "installed-openclaw"),
    )
    if installed_restore.get("applied") is not False:
        raise AcceptanceError(f"installed restore preview applied: {installed_restore!r}")


def validate_upgrade_fixture(cli: Path, work: Path, env: dict[str, str]) -> None:
    if not (UPGRADE_FIXTURE / "self-nomad.yaml").is_file():
        raise AcceptanceError(f"missing upgrade fixture: {UPGRADE_FIXTURE}")
    work.mkdir(parents=True, exist_ok=True)
    dest = work / "v01-repo"
    shutil.copytree(UPGRADE_FIXTURE, dest)
    _git(dest, env, "init", "--initial-branch=main")
    commit_if_needed(dest, env, "imported first-rc schema tree")
    result = _json(cli, env, "--repo", str(dest), "validate", "--strict")
    if result.get("valid") is not True:
        raise AcceptanceError(f"upgrade fixture invalid under current CLI: {result!r}")


def upgrade_from_previous(
    python: Path,
    cli_lookup: Path,
    env: dict[str, str],
    work: Path,
    previous: Path,
    current: Path,
) -> None:
    install_wheel(python, previous, env)
    previous_cli = venv_self_nomad(cli_lookup)
    repo = work / "upgraded"
    _json(previous_cli, env, "init", str(repo), "--name", "from-previous")
    commit_if_needed(repo, env, "created on previous release")
    install_wheel(python, current, env)
    current_cli = venv_self_nomad(cli_lookup)
    result = _json(current_cli, env, "--repo", str(repo), "validate", "--strict")
    if result.get("valid") is not True:
        raise AcceptanceError(f"repo from previous release invalid after upgrade: {result!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--previous-wheel", type=Path, default=None)
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args(argv)
    expected = project_version(ROOT)
    work_root = Path(tempfile.mkdtemp(prefix="self-nomad-accept-"))
    try:
        wheel = select_current_wheel(args.dist.resolve(), expected)
        venv_dir = work_root / "venv"
        state = work_root / "state"
        state.mkdir()
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(venv_dir)
        python = venv_python(venv_dir)
        env = isolated_env(state)
        install_wheel(python, wheel, env)
        cli = venv_self_nomad(venv_dir)
        if not cli.is_file():
            raise AcceptanceError(f"missing console script: {cli}")
        version = run(
            [str(cli), "--version"],
            artifact=wheel.name,
            step="version",
            env=env,
        ).stdout.strip()
        if version != expected:
            raise AcceptanceError(f"CLI version {version!r} != {expected!r}")
        operator_loop(cli, work_root / "loop", env)
        validate_upgrade_fixture(cli, work_root / "upgrade", env)
        if args.previous_wheel is not None:
            upgrade_from_previous(
                python,
                venv_dir,
                env,
                work_root / "from-prev",
                args.previous_wheel,
                wheel,
            )
        print(f"OK  operator acceptance  version={expected}  wheel={wheel.name}")
        return 0
    except (SmokeError, OSError, ValueError) as exc:
        print(f"FAIL operator acceptance: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.keep_workdir:
            print(f"workdir retained: {work_root}")
        else:
            shutil.rmtree(work_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
