"""Human-facing identity for the self-nomad CLI.

Wordmark and tagline belong on the front door (help, about, init). They never
enter ``--json`` envelopes, MCP, or non-interactive pipes unless the operator
asks via ``SELF_NOMAD_BANNER=1``.
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.text import Text

TAGLINE = "an agent's self, untethered from its runtime"
COMPACT_MARK = "self-nomad"

# smslant-inspired, ASCII only, ~70 columns.
WORDMARK_LINES = (
    r"              __       __                                      __",
    r"   ________  / /_____/ /      ____  ____  ____ ___  ____ _____/ /",
    r"  / ___/ _ \/ / __  / /_____ / __ \/ __ \/ __ `__ \/ __ `/ __  /",
    r" (__  )  __/ / /_/ / /_____// / / / /_/ / / / / / / /_/ / /_/ /",
    r"/____/\___/_/\__,_/_/      /_/ /_/\____/_/ /_/ /_/\__,_/\__,_/",
)

WIDE_WORDMARK_MIN = 70


def banner_forced() -> bool:
    return os.environ.get("SELF_NOMAD_BANNER", "").strip() in {"1", "true", "yes"}


def banner_suppressed() -> bool:
    return os.environ.get("SELF_NOMAD_BANNER", "").strip() in {"0", "false", "no"}


def should_show_wordmark(console: Console, *, json_output: bool = False) -> bool:
    if json_output or banner_suppressed():
        return False
    if banner_forced():
        return True
    return bool(console.is_terminal) and not console.no_color


def wordmark_lines(*, width: int) -> tuple[str, ...]:
    if width >= WIDE_WORDMARK_MIN:
        return WORDMARK_LINES
    return (COMPACT_MARK,)


def print_wordmark(console: Console) -> None:
    width = console.width or 80
    color = "cyan" if not console.no_color else "default"
    for line in wordmark_lines(width=width):
        console.print(Text(line, style=f"bold {color}"))
    console.print(Text(TAGLINE, style="italic dim"))


def print_help_identity(console: Console, *, json_output: bool = False) -> None:
    if should_show_wordmark(console, json_output=json_output):
        print_wordmark(console)
        console.print()
        return
    if json_output or banner_suppressed():
        return
    console.print(Text(f"{COMPACT_MARK}  ·  {TAGLINE}", style="dim"))
