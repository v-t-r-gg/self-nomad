"""Start the TUI without importing Textual until it is actually launched."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MISSING_TUI_MESSAGE = (
    "error: the TUI requires the optional dependency; "
    "install with: pip install 'self-nomad[tui]'"
)


def textual_available() -> bool:
    try:
        return importlib.util.find_spec("textual") is not None
    except (ImportError, ValueError):
        return False


def is_missing_textual(exc: BaseException) -> bool:
    """True only when the optional textual package itself is absent.

    Classification uses ``ModuleNotFoundError.name`` and ``find_spec``.
    Message text is not consulted.
    """
    if not isinstance(exc, ModuleNotFoundError):
        return False
    name = getattr(exc, "name", None)
    if not isinstance(name, str) or not name:
        return False
    root = name.split(".", 1)[0]
    if root != "textual":
        return False
    try:
        return importlib.util.find_spec(root) is None
    except (ImportError, ValueError, ModuleNotFoundError):
        return True


def launch_tui(repo: Path) -> None:
    from self_nomad.tui.app import SelfNomadApp

    SelfNomadApp(repo).run()
