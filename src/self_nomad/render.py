"""Rich renderers for human CLI output. Never used on the ``--json`` path."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from self_nomad.branding import COMPACT_MARK, TAGLINE, print_wordmark, should_show_wordmark
from self_nomad.snapshot.models import PackSummary

if TYPE_CHECKING:
    from pathlib import Path

    from self_nomad.domain.adapters import DetectionResult, TransferPlan
    from self_nomad.domain.proposals import ProposalRecord
    from self_nomad.domain.results import Finding, ValidationResult
    from self_nomad.intake.service import IntakeSubmitResult


def _severity_style(severity: str) -> str:
    return {
        "info": "cyan",
        "warning": "yellow",
        "error": "red",
        "blocker": "bold red",
    }.get(severity, "white")


def _status_style(status: str) -> str:
    return {
        "materialized": "cyan",
        "validated": "blue",
        "approved": "green",
        "applied": "bold green",
        "rejected": "red",
        "stale": "yellow",
        "failed": "bold red",
        "draft": "dim",
    }.get(status, "white")


def render_init(console: Console, repository: Path) -> None:
    if should_show_wordmark(console):
        print_wordmark(console)
        console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]{repository}[/bold]\n[dim]{TAGLINE}[/dim]"
            ),
            title=f"{COMPACT_MARK} init",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def render_about(console: Console, version: str) -> None:
    print_wordmark(console)
    console.print()
    table = Table.grid(padding=(0, 2))
    table.add_row("version", Text(version, style="bold"))
    table.add_row("role", "local-first portability and change governance")
    table.add_row("not", "a runtime, a model host, or a public registry")
    console.print(Panel(table, border_style="cyan", title=COMPACT_MARK, padding=(0, 1)))


def render_status(
    console: Console,
    *,
    name: str,
    self_id: str,
    repository: Path,
    valid: bool,
    proposals: Sequence[dict[str, str]],
) -> None:
    verdict = Text("valid", style="bold green") if valid else Text("invalid", style="bold red")
    header = Table.grid(padding=(0, 2))
    header.add_row("self", Text(name, style="bold"))
    header.add_row("id", Text(self_id, style="dim"))
    header.add_row("path", str(repository))
    header.add_row("state", verdict)
    console.print(
        Panel(header, title=f"{COMPACT_MARK} status", border_style="cyan", padding=(0, 1))
    )
    if not proposals:
        console.print("[dim]No pending proposals in local state.[/dim]")
        return
    table = Table(title="Proposals", box=None, show_header=True, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("status")
    for item in proposals:
        status = item.get("status", "")
        table.add_row(item.get("id", ""), Text(status, style=_status_style(status)))
    console.print(table)


def render_validation(console: Console, result: ValidationResult) -> None:
    if result.findings:
        table = Table(box=None, show_header=True, pad_edge=False)
        table.add_column("sev", width=8)
        table.add_column("code", style="bold")
        table.add_column("path", style="dim")
        table.add_column("message")
        for finding in result.findings:
            table.add_row(
                Text(finding.severity, style=_severity_style(finding.severity)),
                finding.code,
                finding.path or "—",
                finding.message,
            )
        console.print(table)
    if result.valid:
        console.print(
            Panel(
                f"Repository is valid\n[dim]digest {result.content_digest[:12]}…[/dim]",
                border_style="green",
                title="validate",
                padding=(0, 1),
            )
        )
    else:
        console.print(
            Panel("Repository is invalid", border_style="red", title="validate", padding=(0, 1))
        )


def render_proposal_valid(console: Console, proposal_id: object, status: str) -> None:
    console.print(
        Panel(
            f"Proposal [bold]{proposal_id}[/bold] is [bold]{status}[/bold]",
            border_style="green",
            title="validate",
            padding=(0, 1),
        )
    )


DIFF_LINE_LIMIT = 240


def _styled_diff_line(line: str) -> Text:
    if line.startswith("+++") or line.startswith("---"):
        return Text(line, style="bold")
    if line.startswith("@@"):
        return Text(line, style="cyan")
    if line.startswith("+"):
        return Text(line, style="green")
    if line.startswith("-"):
        return Text(line, style="red")
    return Text(line, style="dim")


def render_unified_diff(console: Console, diff: str) -> None:
    if not diff.strip():
        console.print(
            "[dim]No textual diff (not materialized, or the tree is identical).[/dim]"
        )
        return
    lines = diff.splitlines()
    shown = lines[:DIFF_LINE_LIMIT]
    for line in shown:
        console.print(_styled_diff_line(line))
    omitted = len(lines) - len(shown)
    if omitted > 0:
        console.print(f"[dim]… {omitted} more diff lines omitted[/dim]")


def render_review(
    console: Console,
    record: ProposalRecord,
    *,
    diff: str | None = None,
    interactive_hint: bool = False,
) -> None:
    proposal = record.proposal
    meta = Table.grid(padding=(0, 2))
    meta.add_row("id", Text(str(proposal.id), style="dim"))
    meta.add_row("status", Text(str(record.status), style=_status_style(str(record.status))))
    meta.add_row("risk", str(proposal.risk))
    meta.add_row("target", proposal.target_branch)
    meta.add_row("base", Text(proposal.base_commit[:12], style="dim"))
    meta.add_row("reason", proposal.reason)
    console.print(Panel(meta, title="proposal", border_style="cyan", padding=(0, 1)))
    table = Table(box=None, show_header=True, pad_edge=False)
    table.add_column("op", width=8)
    table.add_column("path")
    for operation in proposal.operations:
        table.add_row(operation.kind.upper(), operation.path)
    console.print(table)
    if diff is not None:
        console.print()
        render_unified_diff(console, diff)
    if interactive_hint:
        console.print()
        console.print(
            "[dim]approve records an identifier and does not apply. "
            "Apply remains a separate command.[/dim]"
        )


def render_plan(console: Console, plan: TransferPlan, *, preview_note: str | None = None) -> None:
    table = Table(
        title=f"{plan.adapter} {plan.direction}",
        box=None,
        show_header=True,
        pad_edge=False,
    )
    table.add_column("fidelity", width=18)
    table.add_column("action", width=10)
    table.add_column("artifact")
    for mapping in plan.mappings:
        table.add_row(mapping.fidelity.value, mapping.action, mapping.artifact)
    for excluded in plan.exclusions:
        table.add_row(excluded.fidelity.value, "exclude", excluded.artifact)
    console.print(table)
    if preview_note:
        console.print(f"[dim]{preview_note}[/dim]")


def render_detection(console: Console, result: DetectionResult) -> None:
    if not result.candidates:
        console.print(f"[yellow]No {result.adapter} runtimes found.[/yellow]")
        return
    table = Table(title=f"{result.adapter} runtimes", box=None, show_header=True, pad_edge=False)
    table.add_column("name")
    table.add_column("path", style="dim")
    for candidate in result.candidates:
        table.add_row(candidate.name, str(candidate.root))
    console.print(table)


def render_intake_preview(
    console: Console,
    *,
    eligible: bool,
    risk: str,
    operations: int,
    next_actions: Sequence[str],
    findings: Sequence[Finding],
) -> None:
    status = Text("eligible", style="green") if eligible else Text("not eligible", style="red")
    body = Table.grid(padding=(0, 2))
    body.add_row("preview", status)
    body.add_row("risk", risk)
    body.add_row("operations", str(operations))
    body.add_row("next", ", ".join(next_actions) or "none")
    console.print(Panel(body, title="intake", border_style="cyan", padding=(0, 1)))
    for finding in findings:
        console.print(
            f"[{_severity_style(finding.severity)}]{finding.severity.upper()}[/] "
            f"{finding.code}: {finding.message}"
        )


def render_intake_submit(console: Console, result: IntakeSubmitResult) -> None:
    verb = "Reused" if result.reused else "Submitted"
    console.print(
        Panel(
            f"{verb} proposal [bold]{result.proposal_id}[/bold] ({result.status})\n"
            f"[dim]next: {', '.join(result.suggested_next) or 'none'}[/dim]",
            title="intake",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def render_proposals(console: Console, rows: Sequence[dict[str, str]]) -> None:
    if not rows:
        console.print("[dim]No proposals in local state.[/dim]")
        return
    table = Table(title="proposals", box=None, show_header=True, pad_edge=False)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("status")
    table.add_column("risk", width=8)
    table.add_column("reason")
    for item in rows:
        status = item.get("status", "")
        table.add_row(
            item.get("id", ""),
            Text(status, style=_status_style(status)),
            item.get("risk", ""),
            item.get("reason", ""),
        )
    console.print(table)


def render_log(console: Console, rows: Sequence[dict[str, str]]) -> None:
    if not rows:
        console.print("[dim]No applied self-nomad commits on this branch.[/dim]")
        return
    table = Table(title="applied history", box=None, show_header=True, pad_edge=False)
    table.add_column("commit", style="dim", no_wrap=True)
    table.add_column("subject")
    for item in rows:
        table.add_row(item.get("commit", "")[:12], item.get("subject", ""))
    console.print(table)


def render_install(console: Console, *, path: Path, summary: PackSummary) -> None:
    omitted = ", ".join(summary.omitted) or "none"
    body = Table.grid(padding=(0, 2))
    body.add_row("repository", str(path))
    body.add_row("profile", summary.profile)
    body.add_row("self", summary.self.name)
    body.add_row("digest", Text(summary.content_digest, style="dim"))
    body.add_row("omitted", omitted)
    console.print(Panel(body, title="install", border_style="cyan", padding=(0, 1)))


def render_pack(console: Console, *, path: Path, summary: PackSummary) -> None:
    omitted = ", ".join(summary.omitted) or "none"
    skills = ", ".join(summary.skills) or "none"
    body = Table.grid(padding=(0, 2))
    body.add_row("file", str(path))
    body.add_row("profile", summary.profile)
    body.add_row("digest", Text(summary.content_digest, style="dim"))
    body.add_row("skills", skills)
    body.add_row("omitted", omitted)
    console.print(Panel(body, title="pack", border_style="cyan", padding=(0, 1)))


def render_simple(console: Console, title: str, message: str, *, ok: bool = True) -> None:
    console.print(
        Panel(
            message,
            title=title,
            border_style="green" if ok else "red",
            padding=(0, 1),
        )
    )
