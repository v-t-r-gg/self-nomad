import os
from pathlib import Path

from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.adapters.kit import runtime_exclusions, transfer_plan, unmapped_exclusions
from self_nomad.domain import (
    DetectionResult,
    Fidelity,
    Mapping,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.repository import SelfRepository


class OpenClawAdapter(RuntimeAdapter):
    name = "openclaw"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        profile = os.environ.get("OPENCLAW_PROFILE", "default")
        default_name = "workspace" if profile == "default" else f"workspace-{profile}"
        workspace = hint or Path(
            os.environ.get("OPENCLAW_WORKSPACE_DIR", Path.home() / ".openclaw" / default_name)
        )
        candidates = []
        if workspace.is_dir() and any((workspace / name).exists() for name in self._markers()):
            candidates.append(
                RuntimeRef(adapter=self.name, root=workspace.resolve(), name=workspace.name)
            )
        return DetectionResult(adapter=self.name, candidates=candidates)

    @staticmethod
    def _markers() -> tuple[str, ...]:
        return ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "skills")

    def _pairs(self, repository: SelfRepository) -> list[tuple[str, str, str, Fidelity]]:
        content = repository.load_manifest().content
        return [
            ("instructions", "AGENTS.md", content.instructions or "", Fidelity.ADAPTED),
            ("persona", "SOUL.md", content.persona or "", Fidelity.EXACT),
            ("identity", "IDENTITY.md", content.identity or "", Fidelity.EXACT),
            ("user_profile", "USER.md", content.user_profile or "", Fidelity.EXACT),
            ("tool_notes", "TOOLS.md", content.tool_notes or "", Fidelity.EXACT),
            ("long_term_memory", "MEMORY.md", content.long_term_memory or "", Fidelity.EXACT),
            ("daily_memory", "memory", content.daily_memory or "", Fidelity.EXACT),
            ("skills", "skills", content.skills or "", Fidelity.EXACT),
        ]

    def _plan(
        self, direction: str, repository: SelfRepository, runtime: RuntimeRef
    ) -> TransferPlan:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity in self._pairs(repository):
            if not canonical:
                continue
            source = (
                runtime.root / runtime_path
                if direction == "import"
                else repository.root / canonical
            )
            target = (
                repository.root / canonical
                if direction == "import"
                else runtime.root / runtime_path
            )
            if not source.exists():
                continue
            action, before = self.mapping_action(source, target)
            reason = None
            if artifact == "instructions":
                reason = "OpenClaw AGENTS.md is an adapted mapping of identity/instructions.md"
            mappings.append(
                Mapping(
                    artifact=artifact,
                    source=source,
                    destination=Path(canonical if direction == "import" else runtime_path),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                    reason=reason,
                )
            )
        content = repository.load_manifest().content
        exclusions = [
            *runtime_exclusions(
                runtime.root,
                (
                    (
                        "heartbeat",
                        "HEARTBEAT.md",
                        Fidelity.LOSSY,
                        "OpenClaw HEARTBEAT.md has no canonical mapping",
                    ),
                    (
                        "startup",
                        "BOOT.md",
                        Fidelity.RUNTIME_OWNED,
                        "OpenClaw BOOT.md is runtime-owned",
                    ),
                    (
                        "bootstrap",
                        "BOOTSTRAP.md",
                        Fidelity.RUNTIME_OWNED,
                        "OpenClaw BOOTSTRAP.md is runtime-owned",
                    ),
                    (
                        "canvas",
                        "canvas",
                        Fidelity.UNSUPPORTED,
                        "OpenClaw canvas has no canonical mapping",
                    ),
                ),
            ),
            *[
                Mapping(
                    artifact=artifact,
                    fidelity=Fidelity.RUNTIME_OWNED,
                    action="exclude",
                    reason="OpenClaw state directory is outside the portable workspace boundary",
                )
                for artifact in ("configuration", "credentials", "sessions", "agent_databases")
            ],
            *unmapped_exclusions(
                repository,
                (
                    (
                        "knowledge",
                        content.knowledge,
                        Fidelity.UNSUPPORTED,
                        "OpenClaw has no knowledge mapping",
                    ),
                    (
                        "workflows",
                        content.workflows,
                        Fidelity.LOSSY,
                        "OpenClaw workflows have no lossless portable mapping",
                    ),
                    (
                        "evaluations",
                        content.evaluations,
                        Fidelity.UNSUPPORTED,
                        "OpenClaw has no evaluations mapping",
                    ),
                ),
            ),
        ]
        return transfer_plan(
            adapter=self.name,
            direction=direction,
            repository=repository,
            runtime=runtime,
            mappings=mappings,
            exclusions=exclusions,
        )

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        return self._plan("import", repository, runtime)

    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan:
        return self._plan("restore", repository, runtime)

    def validate(
        self, repository: SelfRepository, runtime: RuntimeRef | None = None
    ) -> ValidationResult:
        base = repository.validate(strict=True)
        content = repository.load_manifest().content
        findings = list(base.findings)
        if content.skills:
            findings.extend(self.skill_findings(repository.root / content.skills))
        return ValidationResult(
            valid=not any(item.severity in {"error", "blocker"} for item in findings),
            findings=findings,
            validator_versions={**base.validator_versions, "openclaw": self.version},
            content_digest=base.content_digest,
        )
