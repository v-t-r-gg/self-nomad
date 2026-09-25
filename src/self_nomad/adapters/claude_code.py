"""Claude Code workspace adapter. CLAUDE.md wins over AGENTS.md. Not merged.

Detection matches Claude Code 2.1.277: CLAUDE.md, otherwise AGENTS.md, and a
.claude/ directory alone is still a candidate.
"""

from __future__ import annotations

from pathlib import Path

from self_nomad.adapters.agents_md import AgentsMdAdapter
from self_nomad.adapters.kit import has_portable_content, map_pair
from self_nomad.domain import DetectionResult, Fidelity, Mapping, RuntimeRef, TransferPlan
from self_nomad.repository import SelfRepository

_CLAUDE_REASON = "CLAUDE.md is an adapted mapping of identity/instructions.md"
_AGENTS_FALLBACK = (
    "AGENTS.md is an adapted mapping of identity/instructions.md because CLAUDE.md is absent"
)
_BOTH_NOTE = "CLAUDE.md takes precedence over AGENTS.md; the files are not merged"
_NONE_NOTE = "no CLAUDE.md or AGENTS.md; .claude/ state is not instructions"


def is_claude_workspace(root: Path) -> bool:
    if not root.is_dir():
        return False
    return (
        (root / "CLAUDE.md").is_file()
        or (root / "AGENTS.md").is_file()
        or (root / ".claude").is_dir()
    )


def instruction_file(root: Path) -> str | None:
    if (root / "CLAUDE.md").is_file():
        return "CLAUDE.md"
    if (root / "AGENTS.md").is_file():
        return "AGENTS.md"
    return None


class ClaudeCodeAdapter(AgentsMdAdapter):
    """Separate from agents-md. Instructions are adapted and never merged."""

    name = "claude-code"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        candidates: list[RuntimeRef] = []
        if hint is not None and is_claude_workspace(hint):
            candidates.append(
                RuntimeRef(adapter=self.name, root=hint.resolve(), name=hint.name)
            )
        return DetectionResult(adapter=self.name, candidates=candidates)

    def _instruction_mapping(
        self,
        *,
        direction: str,
        repository: SelfRepository,
        runtime: RuntimeRef,
    ) -> Mapping | None:
        content = repository.load_manifest().content
        canonical = content.instructions or ""
        if not canonical:
            return None
        if direction == "import":
            chosen = instruction_file(runtime.root)
            if chosen is None or not has_portable_content(runtime.root / chosen):
                return None
            source = runtime.root / chosen
            target = repository.root / canonical
            destination = Path(canonical)
            reason = _CLAUDE_REASON if chosen == "CLAUDE.md" else _AGENTS_FALLBACK
        else:
            source = repository.root / canonical
            if not has_portable_content(source):
                return None
            destination = Path("CLAUDE.md")
            target = runtime.root / "CLAUDE.md"
            reason = _CLAUDE_REASON
        action, before = self.mapping_action(source, target)
        return map_pair(
            artifact="instructions",
            source=source,
            destination=destination,
            fidelity=Fidelity.ADAPTED,
            action=action,
            before_sha256=before,
            reason=reason,
        )

    def _map_present(
        self,
        *,
        direction: str,
        repository: SelfRepository,
        runtime: RuntimeRef,
    ) -> list[Mapping]:
        mappings = [
            item
            for item in super()._map_present(
                direction=direction, repository=repository, runtime=runtime
            )
            if item.artifact != "instructions"
        ]
        instructions = self._instruction_mapping(
            direction=direction, repository=repository, runtime=runtime
        )
        if instructions is not None:
            mappings.insert(0, instructions)
        return mappings

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        exclusions = super()._exclusions(runtime, repository)
        if (runtime.root / "CLAUDE.md").is_file() and (runtime.root / "AGENTS.md").is_file():
            exclusions.append(
                Mapping(
                    artifact="agents_md",
                    source=runtime.root / "AGENTS.md",
                    fidelity=Fidelity.UNSUPPORTED,
                    action="exclude",
                    reason=_BOTH_NOTE,
                )
            )
        elif instruction_file(runtime.root) is None:
            content = repository.load_manifest().content
            exclusions.append(
                Mapping(
                    artifact="instructions",
                    source=repository.root / content.instructions if content.instructions else None,
                    fidelity=Fidelity.UNSUPPORTED,
                    action="exclude",
                    reason=_NONE_NOTE,
                )
            )
        return exclusions

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        plan = super().plan_import(runtime, repository)
        return plan.model_copy(update={"adapter": self.name})

    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan:
        plan = super().plan_restore(repository, runtime)
        return plan.model_copy(update={"adapter": self.name})
