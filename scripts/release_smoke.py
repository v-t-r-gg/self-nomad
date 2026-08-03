#!/usr/bin/env python3
"""Smoke-test built wheel and sdist artifacts from dist/.

Creates a fresh virtual environment per artifact, installs without editable
mode, and exercises import, version, CLI help, init, and strict JSON validate.

Network behavior: each smoke run upgrades pip and installs the artifact plus
its declared runtime dependencies from the configured package index (typically
PyPI). The local artifact path is installed from disk; dependency resolution
still requires network access unless the environment already has a populated
pip cache or mirror. This harness does not implement an offline wheelhouse.

Usage (from repository root, after ``uv build``)::

    python scripts/release_smoke.py
    # or
    uv run python scripts/release_smoke.py

Exit status is non-zero when any artifact fails; failures name the artifact
and the command that failed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SmokeError(RuntimeError):
    """Raised when a smoke step fails; message includes artifact and command."""


def run(
    command: list[str],
    *,
    artifact: str,
    step: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SmokeError(
            f"[{artifact}] {step} failed (exit {completed.returncode}): "
            f"{' '.join(command)}\n{detail}"
        )
    return completed


def find_artifacts(dist_dir: Path) -> list[Path]:
    wheels = sorted(dist_dir.glob("self_nomad-*.whl"))
    sdists = sorted(dist_dir.glob("self_nomad-*.tar.gz"))
    artifacts = [*wheels, *sdists]
    if not artifacts:
        raise SmokeError(f"no self_nomad wheel or sdist found under {dist_dir}")
    return artifacts


def version_from_artifact_name(artifact: Path) -> str:
    """Derive the packaged version from a wheel or sdist filename."""
    name = artifact.name
    if name.endswith(".whl"):
        # self_nomad-<version>-py3-none-any.whl
        match = re.fullmatch(r"self_nomad-(.+)-py3-none-any\.whl", name)
        if match:
            return match.group(1)
    elif name.endswith(".tar.gz"):
        match = re.fullmatch(r"self_nomad-(.+)\.tar\.gz", name)
        if match:
            return match.group(1)
    raise SmokeError(f"[{name}] cannot parse version from artifact filename")


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_self_nomad(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "self-nomad.exe"
    return venv_dir / "bin" / "self-nomad"


def isolated_env(state_root: Path) -> dict[str, str]:
    home = state_root / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["XDG_STATE_HOME"] = str(state_root / "xdg-state")
    env["LOCALAPPDATA"] = str(state_root / "localappdata")
    env["APPDATA"] = str(state_root / "appdata")
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = str(home / ".gitconfig")
    return env


def smoke_artifact(artifact: Path, work_root: Path) -> None:
    name = artifact.name
    expected_version = version_from_artifact_name(artifact)
    venv_dir = work_root / f"venv-{artifact.stem.replace('.', '_')}"
    state_root = work_root / f"state-{artifact.stem.replace('.', '_')}"
    repo = work_root / f"repo-{artifact.stem.replace('.', '_')}"
    state_root.mkdir(parents=True, exist_ok=True)

    builder = venv.EnvBuilder(with_pip=True, clear=True)
    builder.create(venv_dir)
    python = venv_python(venv_dir)
    env = isolated_env(state_root)

    # Bootstrap pip tooling (network), then install the local artifact.
    # Dependency wheels are resolved from the package index (network).
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        artifact=name,
        step="upgrade pip",
        env=env,
    )
    run(
        [str(python), "-m", "pip", "install", str(artifact.resolve())],
        artifact=name,
        step="install artifact",
        env=env,
    )

    # Import and version: public attribute, installed metadata, artifact name.
    completed = run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m, self_nomad; "
            "print(self_nomad.__version__); "
            "print(m.version('self-nomad'))",
        ],
        artifact=name,
        step="import and metadata version",
        env=env,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise SmokeError(f"[{name}] unexpected version output: {lines!r}")
    imported, metadata = lines
    if imported != metadata:
        raise SmokeError(
            f"[{name}] import version {imported!r} != metadata version {metadata!r}"
        )
    if imported != expected_version:
        raise SmokeError(
            f"[{name}] installed version {imported!r} != artifact name version "
            f"{expected_version!r}"
        )
    if imported in {"", "0+unknown"}:
        raise SmokeError(f"[{name}] installed version must not be the source-tree sentinel")

    # py.typed must be present in the installed distribution.
    run(
        [
            str(python),
            "-c",
            "import self_nomad, pathlib; "
            "p = pathlib.Path(self_nomad.__file__).with_name('py.typed'); "
            "assert p.is_file(), p; print(p)",
        ],
        artifact=name,
        step="check py.typed",
        env=env,
    )

    cli = venv_self_nomad(venv_dir)
    if not cli.is_file():
        raise SmokeError(f"[{name}] console script missing after install: {cli}")

    version_out = run(
        [str(cli), "--version"],
        artifact=name,
        step="self-nomad --version",
        env=env,
    )
    if version_out.stdout.strip() != expected_version:
        raise SmokeError(
            f"[{name}] CLI version {version_out.stdout.strip()!r} != {expected_version!r}"
        )

    run([str(cli), "--help"], artifact=name, step="self-nomad --help", env=env)

    run(
        [str(cli), "--json", "init", str(repo), "--name", "smoke-agent"],
        artifact=name,
        step="self-nomad init",
        env=env,
    )
    validate = run(
        [str(cli), "--repo", str(repo), "--json", "validate", "--strict"],
        artifact=name,
        step="self-nomad validate --strict --json",
        env=env,
    )
    try:
        envelope = json.loads(validate.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"[{name}] validate output is not JSON: {validate.stdout!r}") from exc

    expected_keys = {"schema_version", "command", "ok", "result", "warnings", "errors"}
    if set(envelope) != expected_keys and not expected_keys.issubset(set(envelope)):
        raise SmokeError(f"[{name}] validate envelope keys unexpected: {sorted(envelope)}")
    if envelope.get("schema_version") != 1:
        raise SmokeError(f"[{name}] schema_version != 1: {envelope.get('schema_version')!r}")
    if envelope.get("command") != "validate":
        raise SmokeError(f"[{name}] command != validate: {envelope.get('command')!r}")
    if envelope.get("ok") is not True:
        raise SmokeError(f"[{name}] validate ok is not True: {envelope!r}")
    if envelope.get("errors") not in ([], None):
        raise SmokeError(f"[{name}] validate errors not empty: {envelope.get('errors')!r}")
    result = envelope.get("result")
    if not isinstance(result, dict) or result.get("valid") is not True:
        raise SmokeError(f"[{name}] validate result not successful: {result!r}")

    print(f"OK  {name}  version={expected_version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        default=ROOT / "dist",
        help="directory containing built wheel and sdist (default: ./dist)",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="retain temporary virtualenvs for debugging",
    )
    args = parser.parse_args(argv)

    dist_dir = args.dist.resolve()
    if not dist_dir.is_dir():
        print(f"ERROR: dist directory not found: {dist_dir}", file=sys.stderr)
        return 2

    try:
        artifacts = find_artifacts(dist_dir)
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    work_root = Path(tempfile.mkdtemp(prefix="self-nomad-smoke-"))
    failures: list[str] = []
    try:
        for artifact in artifacts:
            try:
                smoke_artifact(artifact, work_root)
            except SmokeError as exc:
                failures.append(str(exc))
                print(f"FAIL {artifact.name}: {exc}", file=sys.stderr)
    finally:
        if args.keep_workdir:
            print(f"workdir retained: {work_root}")
        else:
            shutil.rmtree(work_root, ignore_errors=True)

    if failures:
        print(f"{len(failures)} artifact smoke failure(s)", file=sys.stderr)
        return 1
    print(f"All {len(artifacts)} artifact(s) passed smoke tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
