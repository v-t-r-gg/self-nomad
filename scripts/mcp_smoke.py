#!/usr/bin/env python3
"""Smoke-test installed self-nomad[mcp] wheel and sdist artifacts.

Builds are expected under dist/. For each artifact this harness:

1. Creates a fresh virtual environment
2. Installs the artifact with the ``mcp`` extra (``self-nomad[mcp]``)
3. Launches ``self-nomad-mcp`` via the official MCP client transport
4. Lists tools, calls repository status, reads the schema resource
5. Shuts down cleanly

Base install optionality remains proven by ``scripts/release_smoke.py``
(without the MCP extra). Network is used for pip bootstrap and resolving the
``mcp`` dependency from the package index.

Usage (from repository root, after ``uv build``)::

    uv run python scripts/mcp_smoke.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "self_nomad_repository_status",
    "self_nomad_repository_validate",
    "self_nomad_intake_preview",
    "self_nomad_intake_submit",
    "self_nomad_proposal_list",
    "self_nomad_proposal_get",
    "self_nomad_proposal_validate",
}


class SmokeError(RuntimeError):
    """Raised when a smoke step fails."""


def run(
    command: list[str],
    *,
    artifact: str,
    step: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
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
    name = artifact.name
    if name.endswith(".whl"):
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


def venv_self_nomad_mcp(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "self-nomad-mcp.exe"
    return venv_dir / "bin" / "self-nomad-mcp"


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


async def _probe_mcp(
    mcp_bin: Path,
    repo: Path,
    artifact: str,
    env: dict[str, str],
    *,
    expected_version: str,
) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(mcp_bin),
        args=["--repo", str(repo)],
        env=env,
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as client,
    ):
        initialized = await client.initialize()
        server_info = initialized.server_info
        if server_info.name != "self-nomad":
            raise SmokeError(
                f"[{artifact}] server_info.name {server_info.name!r} != 'self-nomad'"
            )
        if server_info.version != expected_version:
            raise SmokeError(
                f"[{artifact}] server_info.version {server_info.version!r} != "
                f"{expected_version!r}"
            )
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        if names != EXPECTED_TOOLS:
            raise SmokeError(
                f"[{artifact}] tool set mismatch: {sorted(names)} != {sorted(EXPECTED_TOOLS)}"
            )
        status = await client.call_tool("self_nomad_repository_status", {})
        if (
            status.is_error
            or not status.structured_content
            or not status.structured_content.get("ok")
        ):
            raise SmokeError(f"[{artifact}] repository_status failed: {status}")
        if status.structured_content["result"]["repository"]["name"] != "mcp-smoke":
            raise SmokeError(
                f"[{artifact}] unexpected repository name: {status.structured_content}"
            )
        package_version = status.structured_content["result"].get("package_version")
        if package_version != expected_version:
            raise SmokeError(
                f"[{artifact}] status package_version {package_version!r} != "
                f"{expected_version!r}"
            )
        resources = await client.list_resources()
        uris = [str(r.uri) for r in resources.resources]
        if "self-nomad://schemas/proposal-request/v1" not in uris:
            raise SmokeError(f"[{artifact}] schema resource missing: {uris}")
        content = await client.read_resource("self-nomad://schemas/proposal-request/v1")
        text = "".join(
            block.text
            for block in content.contents
            if hasattr(block, "text") and block.text
        )
        if "schema_version" not in text:
            raise SmokeError(f"[{artifact}] schema resource empty or unexpected")


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

    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        artifact=name,
        step="upgrade pip",
        env=env,
    )
    # Install with MCP extra. Wheel path needs extras syntax via pip.
    # For a local path: pip install 'path[mcp]' does not work for wheels;
    # install the artifact then install mcp from the extra, or use:
    # pip install package.whl && pip install mcp
    # Prefer: pip install "self-nomad[mcp] @ file://..."
    if name.endswith(".whl"):
        install_target = f"self-nomad[mcp] @ {artifact.resolve().as_uri()}"
    else:
        install_target = f"self-nomad[mcp] @ {artifact.resolve().as_uri()}"
    run(
        [str(python), "-m", "pip", "install", install_target],
        artifact=name,
        step="install artifact with mcp extra",
        env=env,
    )

    # Confirm base CLI still works and MCP entry exists.
    cli = venv_dir / ("Scripts" if os.name == "nt" else "bin") / (
        "self-nomad.exe" if os.name == "nt" else "self-nomad"
    )
    mcp_bin = venv_self_nomad_mcp(venv_dir)
    if not mcp_bin.is_file():
        raise SmokeError(f"[{name}] self-nomad-mcp console script missing after install")

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

    # Init a repository using the base CLI (no MCP import required for CLI).
    run(
        [str(cli), "--json", "init", str(repo), "--name", "mcp-smoke"],
        artifact=name,
        step="self-nomad init",
        env=env,
    )
    # Configure git identity for any subsequent Git use.
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "smoke@example.com"],
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Smoke"],
        check=True,
        capture_output=True,
        env=env,
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        env=env,
    )
    if head.returncode != 0:
        subprocess.run(
            ["git", "-C", str(repo), "add", "."],
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "initial"],
            check=True,
            capture_output=True,
            env=env,
        )

    # Prove base import does not require using MCP; optional dep is present though.
    run(
        [
            str(python),
            "-c",
            "import self_nomad; import importlib.metadata as m; "
            "print(self_nomad.__version__); print(m.version('mcp'))",
        ],
        artifact=name,
        step="import self_nomad and mcp",
        env=env,
    )

    try:
        asyncio.run(
            _probe_mcp(
                mcp_bin,
                repo.resolve(),
                name,
                env,
                expected_version=expected_version,
            )
        )
    except SmokeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SmokeError(f"[{name}] MCP probe failed: {exc}") from exc

    print(f"OK  {name}  version={expected_version}  mcp-extra")


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

    work_root = Path(tempfile.mkdtemp(prefix="self-nomad-mcp-smoke-"))
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
        print(f"{len(failures)} MCP artifact smoke failure(s)", file=sys.stderr)
        return 1
    print(f"All {len(artifacts)} artifact(s) passed MCP smoke tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
