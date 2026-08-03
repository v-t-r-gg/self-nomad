"""Shared test helpers (importable from test modules)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def isolated_state_env(state_root: Path) -> dict[str, str]:
    """Build an environment that isolates platformdirs state on all OSes.

    Sets XDG_STATE_HOME (Linux/macOS when honored), LOCALAPPDATA (Windows),
    and HOME/USERPROFILE so home-relative defaults cannot leak into the
    runner account.

    Path segments are kept short so Windows Git worktrees under pytest
    temporary roots stay within path-length limits.
    """
    # Single-letter segments minimize path length on Windows runners.
    home = state_root / "h"
    home.mkdir(parents=True, exist_ok=True)
    xdg_state = state_root / "s"
    xdg_state.mkdir(parents=True, exist_ok=True)
    local_appdata = state_root / "l"
    local_appdata.mkdir(parents=True, exist_ok=True)
    appdata = state_root / "a"
    appdata.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    environment["XDG_STATE_HOME"] = str(xdg_state)
    environment["LOCALAPPDATA"] = str(local_appdata)
    environment["APPDATA"] = str(appdata)
    # Prefer short temp roots when tools honor these variables.
    environment["TMP"] = str(state_root / "t")
    environment["TEMP"] = str(state_root / "t")
    environment["TMPDIR"] = str(state_root / "t")
    (state_root / "t").mkdir(parents=True, exist_ok=True)
    environment.setdefault("GIT_TERMINAL_PROMPT", "0")
    environment.setdefault("GIT_CONFIG_NOSYSTEM", "1")
    gitconfig = home / ".gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text("", encoding="utf-8")
    environment["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    return environment


def run_git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed.stdout.strip()


def configure_git_identity(
    root: Path,
    *,
    name: str = "Test User",
    email: str = "test@example.invalid",
) -> None:
    run_git(root, "config", "user.name", name)
    run_git(root, "config", "user.email", email)
