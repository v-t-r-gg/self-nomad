"""Wordmark and banner gating."""

from __future__ import annotations

import pytest
from rich.console import Console

from self_nomad.branding import (
    COMPACT_MARK,
    TAGLINE,
    WORDMARK_LINES,
    print_help_identity,
    print_wordmark,
    should_show_wordmark,
    wordmark_lines,
)


def test_wide_wordmark_is_ascii_and_mentions_self() -> None:
    blob = "\n".join(WORDMARK_LINES)
    assert blob.isascii()
    assert "___" in blob
    assert all(len(line) <= 76 for line in WORDMARK_LINES)


def test_wordmark_falls_back_when_narrow() -> None:
    assert wordmark_lines(width=40) == (COMPACT_MARK,)
    assert wordmark_lines(width=80) == WORDMARK_LINES


def test_wordmark_hidden_for_json_and_nocolor(monkeypatch: pytest.MonkeyPatch) -> None:
    assert should_show_wordmark(Console(force_terminal=True), json_output=True) is False
    monkeypatch.setenv("SELF_NOMAD_BANNER", "0")
    assert should_show_wordmark(Console(force_terminal=True)) is False


def test_wordmark_forced_even_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELF_NOMAD_BANNER", "1")
    console = Console(force_terminal=False)
    assert should_show_wordmark(console) is True


def test_tagline_is_stable() -> None:
    assert "untethered" in TAGLINE


def test_print_wordmark_and_help_identity() -> None:
    wide = Console(record=True, width=80, force_terminal=True)
    print_wordmark(wide)
    exported = wide.export_text()
    assert TAGLINE in exported
    assert any("__" in line for line in exported.splitlines())
    help_console = Console(record=True, width=40, force_terminal=False)
    print_help_identity(help_console)
    assert COMPACT_MARK in help_console.export_text()
    silent = Console(record=True)
    print_help_identity(silent, json_output=True)
    assert silent.export_text().strip() == ""
