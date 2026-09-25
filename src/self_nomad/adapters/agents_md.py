"""Project-workspace adapter for the AGENTS.md convention.

Not a personal-agent home. A directory is a candidate only when it contains
AGENTS.md or an Agent Skills ``skills/`` tree. Detection does not walk home.
"""

from __future__ import annotations

import re
from pathlib import Path

from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.adapters.kit import (
    has_portable_content,
    map_pair,
    runtime_exclusions,
    transfer_plan,
    unmapped_exclusions,
)
from self_nomad.domain import (
    DetectionResult,
    Fidelity,
    Finding,
    Mapping,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.repository import SelfRepository

_DATE_NOTE = re.compile(r"\d{4}-\d{2}-\d{2}(?:\.md)?")
_SENSITIVE = (
    (
        "credentials",
        ".env",
        Fidelity.EXCLUDED_SENSITIVE,
        "workspace .env is not portable",
    ),
    (
        "claude_state",
        ".claude",
        Fidelity.EXCLUDED_SENSITIVE,
        "Claude Code state is not portable",
    ),
    (
        "codex_state",
        ".codex",
        Fidelity.EXCLUDED_SENSITIVE,
        "Codex state is not portable",
    ),
    (
        "cursor_state",
        ".cursor",
        Fidelity.EXCLUDED_SENSITIVE,
        "Cursor auth and state are not portable",
    ),
    (
        "dependencies",
        "node_modules",
        Fidelity.RUNTIME_OWNED,
        "node_modules is not a portable artifact",
    ),
    (
        "git_metadata",
        ".git",
        Fidelity.RUNTIME_OWNED,
        "Git metadata is not a portable artifact",
    ),
)
_INSTRUCTIONS_REASON = "AGENTS.md is an adapted mapping of identity/instructions.md"


def is_agents_workspace(root: Path) -> bool:
    if not root.is_dir():
        return False
    if (root / "AGENTS.md").is_file():
        return True
    return has_portable_content(root / "skills")


def daily_runtime_relative(root: Path) -> str | None:
    """Return a runtime path only when the directory is clearly daily notes."""
    explicit = root / "memory" / "daily"
    if has_portable_content(explicit):
        return "memory/daily"
    memory = root / "memory"
    if not memory.is_dir():
        return None
    files = [path for path in memory.iterdir() if path.is_file() and not path.name.startswith(".")]
    if files and all(_DATE_NOTE.fullmatch(path.name) for path in files):
        return "memory"
    return None


def _extra_sensitive(root: Path) -> tuple[tuple[str, str, Fidelity, str], ...]:
    found: list[tuple[str, str, Fidelity, str]] = []
    if not root.is_dir():
        return ()
    for path in sorted(root.glob(".env.*")):
        if path.is_file():
            found.append(
                (
                    "credentials",
                    path.name,
                    Fidelity.EXCLUDED_SENSITIVE,
                    "workspace env file is not portable",
                )
            )
    for path in sorted(root.glob("*.db")):
        if path.is_file():
            found.append(
                (
                    "session_db",
                    path.name,
                    Fidelity.RUNTIME_OWNED,
                    "session database is not portable",
                )
            )
    github = root / ".github"
    if github.is_dir():
        for path in github.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if "token" in name or "secret" in name or name.startswith(".env"):
                found.append(
                    (
                        "copilot_tokens",
                        path.relative_to(root).as_posix(),
                        Fidelity.EXCLUDED_SENSITIVE,
                        "GitHub copilot token file is not portable",
                    )
                )
                break
    return tuple(found)


class AgentsMdAdapter(RuntimeAdapter):
    """AGENTS.md workspace. Instructions are adapted, not byte-identical."""

    name = "agents-md"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        candidates: list[RuntimeRef] = []
        if hint is not None and is_agents_workspace(hint):
            candidates.append(
                RuntimeRef(adapter=self.name, root=hint.resolve(), name=hint.name)
            )
        return DetectionResult(adapter=self.name, candidates=candidates)

    def _rows(
        self, repository: SelfRepository
    ) -> list[tuple[str, str, str, Fidelity, str | None]]:
        content = repository.load_manifest().content
        return [
            (
                "instructions",
                "AGENTS.md",
                content.instructions or "",
                Fidelity.ADAPTED,
                _INSTRUCTIONS_REASON,
            ),
            ("persona", "SOUL.md", content.persona or "", Fidelity.EXACT, None),
            ("identity", "IDENTITY.md", content.identity or "", Fidelity.EXACT, None),
            ("user_profile", "USER.md", content.user_profile or "", Fidelity.EXACT, None),
            (
                "long_term_memory",
                "MEMORY.md",
                content.long_term_memory or "",
                Fidelity.EXACT,
                None,
            ),
            ("tool_notes", "TOOLS.md", content.tool_notes or "", Fidelity.EXACT, None),
            ("skills", "skills", content.skills or "", Fidelity.EXACT, None),
        ]

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        content = repository.load_manifest().content
        canonical_daily = content.daily_memory or ""
        repo_daily = (
            has_portable_content(repository.root / canonical_daily) if canonical_daily else False
        )
        classes: list[tuple[str, str | None, Fidelity, str]] = [
            (
                "knowledge",
                content.knowledge,
                Fidelity.UNSUPPORTED,
                "agents-md has no knowledge mapping",
            ),
            (
                "workflows",
                content.workflows,
                Fidelity.UNSUPPORTED,
                "agents-md has no workflows mapping",
            ),
            (
                "evaluations",
                content.evaluations,
                Fidelity.UNSUPPORTED,
                "agents-md has no evaluations mapping",
            ),
        ]
        if daily_runtime_relative(runtime.root) is None and not repo_daily:
            classes.append(
                (
                    "daily_memory",
                    content.daily_memory,
                    Fidelity.UNSUPPORTED,
                    "memory/ is not a clearly daily notes directory",
                )
            )
        return [
            *runtime_exclusions(runtime.root, (*_SENSITIVE, *_extra_sensitive(runtime.root))),
            *unmapped_exclusions(repository, tuple(classes)),
        ]

    def _map_present(
        self,
        *,
        direction: str,
        repository: SelfRepository,
        runtime: RuntimeRef,
    ) -> list[Mapping]:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity, reason in self._rows(repository):
            if not canonical:
                continue
            if direction == "import":
                source = runtime.root / runtime_path
                destination = Path(canonical)
                target = repository.root / canonical
            else:
                source = repository.root / canonical
                destination = Path(runtime_path)
                target = runtime.root / runtime_path
            if not has_portable_content(source):
                continue
            action, before = self.mapping_action(source, target)
            mappings.append(
                map_pair(
                    artifact=artifact,
                    source=source,
                    destination=destination,
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                    reason=reason,
                )
            )
        if direction == "restore":
            content = repository.load_manifest().content
            canonical_daily = content.daily_memory or ""
            source = repository.root / canonical_daily if canonical_daily else Path()
            if canonical_daily and has_portable_content(source):
                target = runtime.root / "memory" / "daily"
                action, before = self.mapping_action(source, target)
                mappings.append(
                    map_pair(
                        artifact="daily_memory",
                        source=source,
                        destination=Path("memory/daily"),
                        fidelity=Fidelity.EXACT,
                        action=action,
                        before_sha256=before,
                    )
                )
        else:
            content = repository.load_manifest().content
            canonical_daily = content.daily_memory or ""
            daily = daily_runtime_relative(runtime.root)
            if daily is None or not canonical_daily:
                return mappings
            source = runtime.root / daily
            if canonical_daily and has_portable_content(source):
                target = repository.root / canonical_daily
                action, before = self.mapping_action(source, target)
                mappings.append(
                    map_pair(
                        artifact="daily_memory",
                        source=source,
                        destination=Path(canonical_daily),
                        fidelity=Fidelity.EXACT,
                        action=action,
                        before_sha256=before,
                    )
                )
        return mappings

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        return transfer_plan(
            adapter=self.name,
            direction="import",
            repository=repository,
            runtime=runtime,
            mappings=self._map_present(direction="import", repository=repository, runtime=runtime),
            exclusions=self._exclusions(runtime, repository),
        )

    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan:
        return transfer_plan(
            adapter=self.name,
            direction="restore",
            repository=repository,
            runtime=runtime,
            mappings=self._map_present(direction="restore", repository=repository, runtime=runtime),
            exclusions=self._exclusions(runtime, repository),
        )

    def validate(
        self, repository: SelfRepository, runtime: RuntimeRef | None = None
    ) -> ValidationResult:
        base = repository.validate(strict=True)
        findings: list[Finding] = list(base.findings)
        skills = repository.load_manifest().content.skills
        if skills:
            findings.extend(self.skill_findings(repository.root / skills))
        return ValidationResult(
            valid=not any(item.severity in {"error", "blocker"} for item in findings),
            findings=findings,
            validator_versions={**base.validator_versions, self.name: self.version},
            content_digest=base.content_digest,
        )
