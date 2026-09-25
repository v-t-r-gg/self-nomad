"""Stdlib HTML skin over TuiSession. No second validator and no display required."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from uuid import UUID

from self_nomad.branding import TAGLINE, wordmark_lines
from self_nomad.domain import TransferPlan
from self_nomad.errors import SelfNomadError
from self_nomad.tui.session import TuiSession, format_plan

_NAV = (
    ("/", "Status"),
    ("/detect", "Detect"),
    ("/import", "Import"),
    ("/review", "Review"),
    ("/apply", "Apply"),
    ("/pack", "Pack"),
    ("/check", "Check"),
    ("/restore", "Restore"),
)


class GuiApp:
    """Request handler the local server and the tests both call."""

    def __init__(self, repo: Path) -> None:
        self.gate = TuiSession(repo)
        self._import_plan: TransferPlan | None = None
        self._restore_plan: TransferPlan | None = None

    def handle(self, method: str, path: str, form: dict[str, str] | None = None) -> str:
        fields = form or {}
        route = path.split("?", 1)[0]
        try:
            body = self._route(method.upper(), route, fields)
        except (SelfNomadError, OSError, ValueError) as exc:
            body = f"<p class='err'>{escape(str(exc))}</p>"
        return _page(body)

    def _route(self, method: str, route: str, form: dict[str, str]) -> str:
        if route in {"", "/"}:
            return self._status()
        if route == "/detect":
            hint = Path(form["path"]) if form.get("path") else None
            lines = self.gate.detect_lines(hint)
            listed = "".join(f"<li>{escape(line)}</li>" for line in lines)
            return (
                "<form method='get' action='/detect'>"
                "<input name='path' placeholder='runtime hint'>"
                "<button>Detect</button></form>"
                f"<ul>{listed}</ul>"
            )
        if route == "/import":
            return self._import(method, form)
        if route == "/review":
            return self._review(method, form)
        if route == "/apply":
            return self._apply(method, form)
        if route == "/pack":
            return self._pack(method, form)
        if route == "/check":
            return self._check(method, form)
        if route == "/restore":
            return self._restore(method, form)
        raise SelfNomadError(f"unknown page: {route}")

    def _status(self) -> str:
        status = self.gate.home_status()
        mark = "\n".join(wordmark_lines(width=80))
        return (
            f"<pre class='mark'>{escape(mark)}</pre>"
            f"<p>{escape(TAGLINE)}</p>"
            f"<p>repo {escape(status['root'])}</p>"
            f"<p>valid {escape(status['valid'])}</p>"
            f"<p>digest {escape(status['digest'])}</p>"
            f"<p>{escape(status['hint'])}</p>"
        )

    def _import(self, method: str, form: dict[str, str]) -> str:
        form_html = (
            "<form method='post' action='/import'>"
            "<input name='adapter' value='hermes'>"
            "<input name='path' placeholder='runtime directory'>"
            "<button name='action' value='preview'>Preview</button>"
            "<button name='action' value='confirm'>Create proposal</button>"
            "</form>"
        )
        if method != "POST":
            return form_html + "<p>Import creates a proposal. It does not apply.</p>"
        if form.get("action") == "preview":
            plan = self.gate.preview_import(form.get("adapter", ""), Path(form.get("path", "")))
            self._import_plan = plan
            return form_html + f"<pre>{escape(format_plan(plan))}</pre><p>preview only</p>"
        if self._import_plan is None:
            raise SelfNomadError("preview the import before creating a proposal")
        record = self.gate.confirm_import(self._import_plan)
        ident = escape(str(record.proposal.id))
        state = escape(str(record.status))
        return form_html + f"<p>proposal {ident} {state}</p>"

    def _review(self, method: str, form: dict[str, str]) -> str:
        options = "".join(
            f"<option value='{escape(value)}'>{escape(label)}</option>"
            for label, value in self.gate.proposal_lines()
        )
        form_html = (
            "<form method='post' action='/review'>"
            f"<select name='proposal'>{options}</select>"
            "<input name='identifier' placeholder='identifier or reason'>"
            "<button name='action' value='diff'>Show diff</button>"
            "<button name='action' value='approve'>Approve</button>"
            "<button name='action' value='reject'>Reject</button>"
            "</form><p>Review never applies.</p>"
        )
        if method != "POST" or not form.get("proposal"):
            return form_html
        proposal_id = UUID(form["proposal"])
        action = form.get("action")
        if action == "diff":
            return form_html + f"<pre>{escape(self.gate.diff(proposal_id))}</pre>"
        if action == "approve":
            record = self.gate.approve(proposal_id, form.get("identifier", ""))
        elif action == "reject":
            record = self.gate.reject(proposal_id, form.get("identifier", ""))
        else:
            raise SelfNomadError("unknown review action")
        return form_html + f"<p>{escape(str(record.proposal.id))} {escape(str(record.status))}</p>"

    def _apply(self, method: str, form: dict[str, str]) -> str:
        options = "".join(
            f"<option value='{escape(value)}'>{escape(label)}</option>"
            for label, value in self.gate.proposal_lines()
        )
        form_html = (
            "<form method='post' action='/apply'>"
            f"<select name='proposal'>{options}</select>"
            "<button>Apply</button></form>"
            "<p>A dirty worktree is refused.</p>"
        )
        if method != "POST" or not form.get("proposal"):
            return form_html
        record = self.gate.apply(UUID(form["proposal"]))
        return form_html + f"<p>{escape(str(record.proposal.id))} {escape(str(record.status))}</p>"

    def _pack(self, method: str, form: dict[str, str]) -> str:
        form_html = (
            "<form method='post' action='/pack'>"
            "<input name='profile' value='specialist'>"
            "<input name='out' placeholder='output .snpack'>"
            "<label><input type='checkbox' name='ltm' value='1'> Include memory/PUBLISH.md</label>"
            "<button>Pack</button></form>"
        )
        if method != "POST":
            return form_html
        summary = self.gate.pack(
            Path(form.get("out", "")),
            profile=form.get("profile") or "specialist",
            include_long_term=form.get("ltm") == "1",
        )
        omitted = ", ".join(summary.omitted)
        return form_html + (
            f"<p>packed {escape(summary.profile)} {escape(summary.content_digest)} "
            f"omitted {escape(omitted)}</p>"
        )

    def _check(self, method: str, form: dict[str, str]) -> str:
        form_html = (
            "<form method='post' action='/check'>"
            "<input name='archive' placeholder='.snpack path'>"
            "<input name='dest' placeholder='empty destination'>"
            "<button name='action' value='check'>Check</button>"
            "<button name='action' value='install'>Install</button>"
            "</form>"
        )
        if method != "POST":
            return form_html
        archive = Path(form.get("archive", ""))
        if form.get("action") == "install":
            summary = self.gate.install_pack(archive, Path(form.get("dest", "")))
            return form_html + f"<p>installed {escape(summary.content_digest)}</p>"
        summary = self.gate.check_pack(archive)
        omitted = ", ".join(summary.omitted)
        skills = ", ".join(summary.skills)
        return form_html + (
            f"<p>profile {escape(summary.profile)}</p>"
            f"<p>omitted {escape(omitted)}</p>"
            f"<p>digest {escape(summary.content_digest)}</p>"
            f"<p>skills {escape(skills)}</p>"
        )

    def _restore(self, method: str, form: dict[str, str]) -> str:
        form_html = (
            "<form method='post' action='/restore'>"
            "<input name='adapter' value='openclaw'>"
            "<input name='target' placeholder='target directory'>"
            "<button name='action' value='preview'>Preview</button>"
            "<button name='action' value='confirm'>Restore</button>"
            "</form>"
        )
        if method != "POST":
            return form_html
        if form.get("action") == "preview":
            plan = self.gate.preview_restore(form.get("adapter", ""), Path(form.get("target", "")))
            self._restore_plan = plan
            return form_html + f"<pre>{escape(format_plan(plan))}</pre>"
        if self._restore_plan is None:
            raise SelfNomadError("preview the restore before writing")
        written = self.gate.apply_restore(self._restore_plan)
        return form_html + f"<p>restored {escape(', '.join(written) or 'no new files')}</p>"


def _page(body: str) -> str:
    color = "" if os.environ.get("NO_COLOR") else "color:#9cf;"
    links = " ".join(f"<a href='{href}'>{escape(label)}</a>" for href, label in _NAV)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>self-nomad</title>"
        f"<style>body{{font-family:ui-monospace,monospace}} .mark{{{color}}}</style>"
        f"</head><body><nav>{links}</nav>{body}</body></html>"
    )
