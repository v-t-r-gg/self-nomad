"""Thin workspace wrappers. They compose agents-md; they do not copy its map."""

from __future__ import annotations

from pathlib import Path

from self_nomad.adapters.agents_md import AgentsMdAdapter
from self_nomad.adapters.kit import has_portable_content, map_pair
from self_nomad.domain import (
    DetectionResult,
    Fidelity,
    Mapping,
    RuntimeRef,
    TransferPlan,
)
from self_nomad.repository import SelfRepository

_COPILOT_FILE = ".github/copilot-instructions.md"
_COPILOT_REASON = (
    "copilot-instructions.md is an adapted mapping of identity/instructions.md "
    "because AGENTS.md is absent"
)
_COPILOT_UNMERGED = "AGENTS.md takes precedence; copilot-instructions.md is not merged"


def _candidate(name: str, root: Path) -> DetectionResult:
    return DetectionResult(
        adapter=name,
        candidates=[RuntimeRef(adapter=name, root=root.resolve(), name=root.name)],
    )


def _empty(name: str) -> DetectionResult:
    return DetectionResult(adapter=name, candidates=[])


class CodexAdapter(AgentsMdAdapter):
    """agents-md plus .codex/ detection. Instruction files are not added."""

    name = "codex"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        if hint is None or not hint.is_dir():
            return _empty(self.name)
        if (hint / "AGENTS.md").is_file() or (hint / ".codex").is_dir():
            return _candidate(self.name, hint)
        return _empty(self.name)

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        exclusions = super()._exclusions(runtime, repository)
        auth = runtime.root / ".codex" / "auth.json"
        exclusions.append(
            Mapping(
                artifact="codex_auth",
                source=auth if auth.is_file() else None,
                fidelity=Fidelity.EXCLUDED_SENSITIVE,
                action="exclude",
                reason="Codex auth.json is not portable",
            )
        )
        return exclusions


class CursorAdapter(AgentsMdAdapter):
    """agents-md plus .cursor/rules. Rule files are lossy and not merged."""

    name = "cursor"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        if hint is None or not hint.is_dir():
            return _empty(self.name)
        rules = hint / ".cursor" / "rules"
        if (hint / "AGENTS.md").is_file() or rules.is_dir():
            return _candidate(self.name, hint)
        return _empty(self.name)

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        exclusions = super()._exclusions(runtime, repository)
        rules = runtime.root / ".cursor" / "rules"
        if rules.is_dir():
            for path in sorted(rules.glob("*.mdc")):
                exclusions.append(
                    Mapping(
                        artifact="cursor_rule",
                        source=path,
                        fidelity=Fidelity.LOSSY,
                        action="exclude",
                        reason=(
                            "Cursor .mdc rules are lossy and are not merged into instructions"
                        ),
                    )
                )
        for relative, reason in (
            (".cursor/auth.json", "Cursor auth is not portable"),
            (".cursor/mcp.json", "Cursor mcp.json is not portable"),
        ):
            path = runtime.root / relative
            exclusions.append(
                Mapping(
                    artifact="cursor_secret",
                    source=path if path.is_file() else None,
                    fidelity=Fidelity.EXCLUDED_SENSITIVE,
                    action="exclude",
                    reason=reason,
                )
            )
        return exclusions


class CopilotAdapter(AgentsMdAdapter):
    """agents-md. Copilot instructions are used only when AGENTS.md is absent."""

    name = "copilot"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        if hint is None or not hint.is_dir():
            return _empty(self.name)
        if (hint / "AGENTS.md").is_file() or (hint / _COPILOT_FILE).is_file():
            return _candidate(self.name, hint)
        return _empty(self.name)

    def _map_present(
        self,
        *,
        direction: str,
        repository: SelfRepository,
        runtime: RuntimeRef,
    ) -> list[Mapping]:
        mappings = super()._map_present(
            direction=direction, repository=repository, runtime=runtime
        )
        if direction != "import":
            return mappings
        agents = runtime.root / "AGENTS.md"
        copilot = runtime.root / _COPILOT_FILE
        if agents.is_file() or not copilot.is_file():
            return mappings
        content = repository.load_manifest().content
        canonical = content.instructions or ""
        if not canonical or not has_portable_content(copilot):
            return mappings
        kept = [item for item in mappings if item.artifact != "instructions"]
        action, before = self.mapping_action(copilot, repository.root / canonical)
        kept.insert(
            0,
            map_pair(
                artifact="instructions",
                source=copilot,
                destination=Path(canonical),
                fidelity=Fidelity.ADAPTED,
                action=action,
                before_sha256=before,
                reason=_COPILOT_REASON,
            ),
        )
        return kept

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        exclusions = super()._exclusions(runtime, repository)
        copilot = runtime.root / _COPILOT_FILE
        if (runtime.root / "AGENTS.md").is_file() and copilot.is_file():
            exclusions.append(
                Mapping(
                    artifact="copilot_instructions",
                    source=copilot,
                    fidelity=Fidelity.UNSUPPORTED,
                    action="exclude",
                    reason=_COPILOT_UNMERGED,
                )
            )
        return exclusions

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        plan = super().plan_import(runtime, repository)
        return plan.model_copy(update={"adapter": self.name})
