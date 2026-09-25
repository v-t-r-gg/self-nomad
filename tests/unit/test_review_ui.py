"""Interactive review helpers (no apply)."""

from __future__ import annotations

from self_nomad.review_ui import _ACTIONS, _normalize_action


def test_action_aliases() -> None:
    assert _normalize_action("A") == "approve"
    assert _normalize_action(" reject ") == "reject"
    assert _normalize_action("q") == "quit"
    assert _normalize_action("nope") == "nope"
    assert set(_ACTIONS) == {"approve", "reject", "quit"}
    assert "apply" not in _ACTIONS
