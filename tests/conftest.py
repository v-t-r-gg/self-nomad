"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import isolated_state_env


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect platformdirs and home-based paths into tmp_path for the test process."""
    state_root = tmp_path / "isolated-state"
    env = isolated_state_env(state_root)
    for key in (
        "HOME",
        "USERPROFILE",
        "XDG_STATE_HOME",
        "LOCALAPPDATA",
        "APPDATA",
        "GIT_TERMINAL_PROMPT",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
    ):
        monkeypatch.setenv(key, env[key])
    return state_root
