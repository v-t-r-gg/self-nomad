"""Full-screen operator loop. Human only; it never speaks --json."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Select, Static

from self_nomad.branding import TAGLINE, wordmark_lines
from self_nomad.domain import TransferPlan
from self_nomad.errors import SelfNomadError
from self_nomad.snapshot.models import PackSummary
from self_nomad.tui.session import TuiSession, format_plan

_PROFILE = [("specialist", "specialist"), ("personal", "personal")]


def _report(screen: Screen[None], exc: BaseException) -> None:
    screen.query_one("#message", Static).update(str(exc))


def _uuid_from_select(screen: Screen[None], widget_id: str) -> UUID:
    value = screen.query_one(widget_id, Select).value
    if value is Select.BLANK or not isinstance(value, str):
        raise SelfNomadError("choose a proposal")
    return UUID(value)


class HomeScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static(id="wordmark")
        yield Static(id="status")
        yield Static("", id="message")

    def on_mount(self) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        status = gate.home_status()
        mark = "\n".join(wordmark_lines(width=80))
        self.query_one("#wordmark", Static).update(f"{mark}\n{TAGLINE}")
        self.query_one("#status", Static).update(
            f"repo {status['root']}\nvalid {status['valid']}\n"
            f"digest {status['digest']}\n{status['hint']}"
        )


class DetectScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Detect registered adapters. Empty path uses each adapter default.")
        yield Input(placeholder="runtime hint path", id="detect-path")
        yield Button("Detect", id="detect-run")
        yield Static("", id="detect-body")
        yield Static("", id="message")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "detect-run":
            return
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        raw = self.query_one("#detect-path", Input).value.strip()
        hint = Path(raw) if raw else None
        try:
            lines = gate.detect_lines(hint)
        except SelfNomadError as exc:
            _report(self, exc)
            return
        self.query_one("#detect-body", Static).update("\n".join(lines))


class ImportScreen(Screen[None]):
    def __init__(self) -> None:
        super().__init__()
        self._plan: TransferPlan | None = None

    def compose(self) -> ComposeResult:
        yield Static("Import creates a proposal. It does not apply.")
        yield Input(value="hermes", id="import-adapter")
        yield Input(placeholder="runtime directory", id="import-path")
        yield Button("Preview", id="import-preview")
        yield Button("Create proposal", id="import-confirm", disabled=True)
        yield Static("", id="import-plan")
        yield Static("", id="message")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        try:
            if event.button.id == "import-preview":
                plan = gate.preview_import(
                    self.query_one("#import-adapter", Input).value.strip(),
                    Path(self.query_one("#import-path", Input).value.strip()),
                )
                self._plan = plan
                self.query_one("#import-plan", Static).update(format_plan(plan))
                self.query_one("#import-confirm", Button).disabled = False
                self.query_one("#message", Static).update("preview only")
            elif event.button.id == "import-confirm" and self._plan is not None:
                record = gate.confirm_import(self._plan)
                self.query_one("#message", Static).update(
                    f"proposal {record.proposal.id} {record.status}"
                )
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)


class ReviewScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Review can approve or reject. It never applies.")
        yield Select([], prompt="proposal", id="review-id", allow_blank=True)
        yield Button("Show diff", id="review-diff")
        yield Static("", id="review-diff-body")
        yield Input(placeholder="identifier or rejection reason", id="review-identifier")
        yield Button("Approve", id="review-approve")
        yield Button("Reject", id="review-reject")
        yield Static("", id="message")

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        options = gate.proposal_lines()
        select = self.query_one("#review-id", Select)
        if options:
            select.set_options(options)
            select.value = options[0][1]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        try:
            proposal_id = _uuid_from_select(self, "#review-id")
            if event.button.id == "review-diff":
                self.query_one("#review-diff-body", Static).update(gate.diff(proposal_id))
            elif event.button.id == "review-approve":
                record = gate.approve(
                    proposal_id,
                    self.query_one("#review-identifier", Input).value,
                )
                self.query_one("#message", Static).update(f"{record.proposal.id} {record.status}")
            elif event.button.id == "review-reject":
                record = gate.reject(
                    proposal_id,
                    self.query_one("#review-identifier", Input).value,
                )
                self.query_one("#message", Static).update(f"{record.proposal.id} {record.status}")
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)


class ApplyScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Apply only an approved proposal. A dirty worktree is refused.")
        yield Select([], prompt="proposal", id="apply-id", allow_blank=True)
        yield Button("Apply", id="apply-run")
        yield Static("", id="message")

    def on_mount(self) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        options = gate.proposal_lines()
        if options:
            select = self.query_one("#apply-id", Select)
            select.set_options(options)
            select.value = options[0][1]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "apply-run":
            return
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        try:
            record = gate.apply(_uuid_from_select(self, "#apply-id"))
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)
            return
        self.query_one("#message", Static).update(f"{record.proposal.id} {record.status}")


class PackScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Pack. Specialist omits user profile and daily memory.")
        yield Select(_PROFILE, value="specialist", id="pack-profile", allow_blank=False)
        yield Checkbox("Include memory/PUBLISH.md", id="pack-ltm")
        yield Input(placeholder="output .snpack path", id="pack-out")
        yield Button("Pack", id="pack-run")
        yield Static("", id="message")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "pack-run":
            return
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        profile = self.query_one("#pack-profile", Select).value
        if not isinstance(profile, str):
            _report(self, SelfNomadError("choose a profile"))
            return
        try:
            summary = gate.pack(
                Path(self.query_one("#pack-out", Input).value.strip()),
                profile=profile,
                include_long_term=self.query_one("#pack-ltm", Checkbox).value,
            )
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)
            return
        omitted = ", ".join(summary.omitted)
        self.query_one("#message", Static).update(
            f"packed {summary.profile} {summary.content_digest} omitted {omitted}"
        )


class CheckInstallScreen(Screen[None]):
    def __init__(self) -> None:
        super().__init__()
        self._summary: PackSummary | None = None

    def compose(self) -> ComposeResult:
        yield Static("Check a local .snpack, then install into an empty directory.")
        yield Input(placeholder="archive path", id="check-archive")
        yield Button("Check", id="check-run")
        yield Input(placeholder="install destination", id="install-dest")
        yield Button("Install", id="install-run", disabled=True)
        yield Static("", id="check-body")
        yield Static("", id="message")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        archive = Path(self.query_one("#check-archive", Input).value.strip())
        try:
            if event.button.id == "check-run":
                summary = gate.check_pack(archive)
                self._summary = summary
                self.query_one("#install-run", Button).disabled = False
                self.query_one("#check-body", Static).update(
                    f"profile {summary.profile}\n"
                    f"omitted {', '.join(summary.omitted)}\n"
                    f"digest {summary.content_digest}\n"
                    f"skills {', '.join(summary.skills)}"
                )
            elif event.button.id == "install-run":
                destination = Path(self.query_one("#install-dest", Input).value.strip())
                summary = gate.install_pack(archive, destination)
                self.query_one("#message", Static).update(
                    f"installed {destination} {summary.content_digest}"
                )
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)


class RestoreScreen(Screen[None]):
    def __init__(self) -> None:
        super().__init__()
        self._plan: TransferPlan | None = None

    def compose(self) -> ComposeResult:
        yield Static("Restore preview, then write. Adapted classes stay visible.")
        yield Input(value="openclaw", id="restore-adapter")
        yield Input(placeholder="target directory", id="restore-target")
        yield Button("Preview", id="restore-preview")
        yield Button("Restore", id="restore-run", disabled=True)
        yield Static("", id="restore-plan")
        yield Static("", id="message")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        gate: TuiSession = self.app.gate  # type: ignore[attr-defined]
        try:
            if event.button.id == "restore-preview":
                plan = gate.preview_restore(
                    self.query_one("#restore-adapter", Input).value.strip(),
                    Path(self.query_one("#restore-target", Input).value.strip()),
                )
                self._plan = plan
                self.query_one("#restore-plan", Static).update(format_plan(plan))
                self.query_one("#restore-run", Button).disabled = False
            elif event.button.id == "restore-run" and self._plan is not None:
                written = gate.apply_restore(self._plan)
                self.query_one("#message", Static).update(
                    "restored " + (", ".join(written) if written else "no new files")
                )
        except (SelfNomadError, OSError, ValueError) as exc:
            _report(self, exc)


class SelfNomadApp(App[None]):
    """Keyboard-first skin over SelfNomad. Not a second validator."""

    CSS = """
    Screen { layout: vertical; overflow-y: auto; }
    #wordmark { height: auto; color: cyan; }
    #status, #detect-body, #import-plan, #review-diff-body, #check-body, #restore-plan {
        height: auto;
    }
    """
    BINDINGS = [
        Binding("f1", "home", "Home"),
        Binding("f2", "detect", "Detect"),
        Binding("f3", "import", "Import"),
        Binding("f4", "review", "Review"),
        Binding("f5", "apply", "Apply"),
        Binding("f6", "pack", "Pack"),
        Binding("f7", "check", "Check"),
        Binding("f8", "restore", "Restore"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, repo: Path) -> None:
        super().__init__()
        self.gate = TuiSession(repo)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Vertical(id="frame")
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def action_home(self) -> None:
        self.switch_screen(HomeScreen())

    def action_detect(self) -> None:
        self.switch_screen(DetectScreen())

    def action_import(self) -> None:
        self.switch_screen(ImportScreen())

    def action_review(self) -> None:
        self.switch_screen(ReviewScreen())

    def action_apply(self) -> None:
        self.switch_screen(ApplyScreen())

    def action_pack(self) -> None:
        self.switch_screen(PackScreen())

    def action_check(self) -> None:
        self.switch_screen(CheckInstallScreen())

    def action_restore(self) -> None:
        self.switch_screen(RestoreScreen())
