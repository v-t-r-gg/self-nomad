import os
from pathlib import Path

from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.domain import (
    DetectionResult,
    Fidelity,
    Finding,
    Mapping,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.manifest.loader import load_yaml
from self_nomad.repository import SelfRepository


class HermesAdapter(RuntimeAdapter):
    name = "hermes"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        base = hint or Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        candidates: list[Path] = []
        if self._compatible(base):
            candidates.append(base)
        profiles = base / "profiles"
        if profiles.is_dir():
            candidates.extend(item for item in sorted(profiles.iterdir()) if self._compatible(item))
        unique = list(dict.fromkeys(item.resolve() for item in candidates))
        return DetectionResult(
            adapter=self.name,
            candidates=[
                RuntimeRef(adapter=self.name, root=item, name=item.name) for item in unique
            ],
        )

    @staticmethod
    def _compatible(path: Path) -> bool:
        return path.is_dir() and any(
            (path / marker).exists() for marker in ("SOUL.md", "config.yaml", "memories", "skills")
        )

    def _pairs(self, repository: SelfRepository) -> list[tuple[str, str, str, Fidelity]]:
        content = repository.load_manifest().content
        return [
            ("persona", "SOUL.md", content.persona or "", Fidelity.EXACT),
            (
                "long_term_memory",
                "memories/MEMORY.md",
                content.long_term_memory or "",
                Fidelity.EXACT,
            ),
            ("user_profile", "memories/USER.md", content.user_profile or "", Fidelity.EXACT),
            ("skills", "skills", content.skills or "", Fidelity.EXACT),
        ]

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity in self._pairs(repository):
            source = runtime.root / runtime_path
            if not canonical or not source.exists():
                continue
            target = repository.root / canonical
            action, before = self.mapping_action(source, target)
            mappings.append(
                Mapping(
                    artifact=artifact,
                    source=source,
                    destination=Path(canonical),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                )
            )
        exclusions = self._exclusions(runtime)
        return TransferPlan(
            adapter=self.name,
            direction="import",
            repository_root=repository.root,
            runtime=runtime,
            mappings=mappings,
            exclusions=exclusions,
        )

    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity in self._pairs(repository):
            source = repository.root / canonical
            if not canonical or not source.exists():
                continue
            target = runtime.root / runtime_path
            action, before = self.mapping_action(source, target)
            mappings.append(
                Mapping(
                    artifact=artifact,
                    source=source,
                    destination=Path(runtime_path),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                )
            )
        exclusions = self._exclusions(runtime)
        content = repository.load_manifest().content
        for artifact, relative in (
            ("instructions", content.instructions),
            ("identity", content.identity),
            ("daily_memory", content.daily_memory),
            ("knowledge", content.knowledge),
            ("tool_notes", content.tool_notes),
            ("workflows", content.workflows),
            ("evaluations", content.evaluations),
        ):
            if relative and self._has_content(repository.root / relative):
                exclusions.append(
                    Mapping(
                        artifact=artifact,
                        source=repository.root / relative,
                        fidelity=Fidelity.UNSUPPORTED,
                        action="exclude",
                        reason="Hermes v0.1 mapping is not defined",
                    )
                )
        return TransferPlan(
            adapter=self.name,
            direction="restore",
            repository_root=repository.root,
            runtime=runtime,
            mappings=mappings,
            exclusions=exclusions,
        )

    @staticmethod
    def _has_content(path: Path) -> bool:
        return path.is_file() or (
            path.is_dir()
            and any(item.is_file() and item.name != ".gitkeep" for item in path.rglob("*"))
        )

    def _exclusions(self, runtime: RuntimeRef) -> list[Mapping]:
        known = (
            ("credentials", ".env", Fidelity.EXCLUDED_SENSITIVE),
            ("sessions", "state.db", Fidelity.RUNTIME_OWNED),
            ("configuration", "config.yaml", Fidelity.RUNTIME_OWNED),
            ("cron_jobs", "cron", Fidelity.RUNTIME_OWNED),
            ("plugins", "plugins", Fidelity.RUNTIME_OWNED),
            ("checkpoints", "checkpoints", Fidelity.RUNTIME_OWNED),
            ("backups", "backups", Fidelity.RUNTIME_OWNED),
            ("state_snapshots", "state-snapshots", Fidelity.RUNTIME_OWNED),
            ("logs", "logs", Fidelity.RUNTIME_OWNED),
            ("gateway_state", "gateway", Fidelity.RUNTIME_OWNED),
        )
        return [
            Mapping(
                artifact=artifact,
                source=(runtime.root / relative) if (runtime.root / relative).exists() else None,
                fidelity=fidelity,
                action="exclude",
                reason="known Hermes operational state is not portable",
            )
            for artifact, relative, fidelity in known
        ]

    def validate(
        self, repository: SelfRepository, runtime: RuntimeRef | None = None
    ) -> ValidationResult:
        base = repository.validate(strict=True)
        findings = list(base.findings)
        limits = {"long_term_memory": 2200, "user_profile": 1375}
        if runtime and (runtime.root / "config.yaml").is_file():
            raw = load_yaml(runtime.root / "config.yaml") or {}
            memory = raw.get("memory", {}) if isinstance(raw, dict) else {}
            if isinstance(memory, dict):
                limits["long_term_memory"] = int(memory.get("memory_char_limit", 2200))
                limits["user_profile"] = int(memory.get("user_char_limit", 1375))
        content = repository.load_manifest().content
        for artifact, relative in (
            ("long_term_memory", content.long_term_memory),
            ("user_profile", content.user_profile),
        ):
            if relative and (repository.root / relative).is_file():
                count = len((repository.root / relative).read_text(encoding="utf-8"))
                if count > limits[artifact]:
                    findings.append(
                        Finding(
                            severity="error",
                            code="SN3101",
                            message=f"Hermes character limit exceeded ({count}/{limits[artifact]})",
                            path=relative,
                        )
                    )
        if content.skills:
            findings.extend(self.skill_findings(repository.root / content.skills))
        return ValidationResult(
            valid=not any(item.severity in {"error", "blocker"} for item in findings),
            findings=findings,
            validator_versions={**base.validator_versions, "hermes": self.version},
            content_digest=base.content_digest,
        )
