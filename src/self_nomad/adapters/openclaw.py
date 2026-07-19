import os
from pathlib import Path

from self_nomad.adapters.base import RuntimeAdapter
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
            mappings.append(
                Mapping(
                    artifact=artifact,
                    source=source,
                    destination=Path(canonical if direction == "import" else runtime_path),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                )
            )
        known = (
            ("heartbeat", "HEARTBEAT.md", Fidelity.LOSSY),
            ("startup", "BOOT.md", Fidelity.RUNTIME_OWNED),
            ("bootstrap", "BOOTSTRAP.md", Fidelity.RUNTIME_OWNED),
            ("canvas", "canvas", Fidelity.UNSUPPORTED),
        )
        exclusions = [
            Mapping(
                artifact=artifact,
                source=(runtime.root / relative) if (runtime.root / relative).exists() else None,
                fidelity=fidelity,
                action="exclude",
                reason="known OpenClaw workspace artifact has no canonical v0.1 mapping",
            )
            for artifact, relative, fidelity in known
        ]
        exclusions.extend(
            [
                Mapping(
                    artifact=artifact,
                    fidelity=Fidelity.RUNTIME_OWNED,
                    action="exclude",
                    reason="OpenClaw state directory is outside the portable workspace boundary",
                )
                for artifact in ("configuration", "credentials", "sessions", "agent_databases")
            ]
        )
        content = repository.load_manifest().content
        for artifact, relative, fidelity in (
            ("knowledge", content.knowledge, Fidelity.UNSUPPORTED),
            ("workflows", content.workflows, Fidelity.LOSSY),
            ("evaluations", content.evaluations, Fidelity.UNSUPPORTED),
        ):
            path = repository.root / relative if relative else None
            has_content = path and (
                path.is_file()
                or (
                    path.is_dir()
                    and any(item.is_file() and item.name != ".gitkeep" for item in path.rglob("*"))
                )
            )
            if path and has_content:
                exclusions.append(
                    Mapping(
                        artifact=artifact,
                        source=path,
                        fidelity=fidelity,
                        action="exclude",
                        reason="no portable OpenClaw mapping is defined",
                    )
                )
        return TransferPlan(
            adapter=self.name,
            direction=direction,
            repository_root=repository.root,
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
