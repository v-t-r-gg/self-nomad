"""Template adapter for a fictional files runtime. Not in the default registry.

Copy this module when adding a third runtime. Contract tests import it.
"""

from __future__ import annotations

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
    Mapping,
    RuntimeRef,
    TransferPlan,
    ValidationResult,
)
from self_nomad.repository import SelfRepository


class ExampleFilesAdapter(RuntimeAdapter):
    """Maps persona to PERSONA.md. Excludes .env. Authoring-kit sample only."""

    name = "example-files"

    def detect(self, hint: Path | None = None) -> DetectionResult:
        candidates = []
        if hint is not None and (hint / "PERSONA.md").is_file():
            candidates.append(RuntimeRef(adapter=self.name, root=hint.resolve(), name=hint.name))
        return DetectionResult(adapter=self.name, candidates=candidates)

    def _pairs(self, repository: SelfRepository) -> list[tuple[str, str, str, Fidelity]]:
        content = repository.load_manifest().content
        return [("persona", "PERSONA.md", content.persona or "", Fidelity.EXACT)]

    def _exclusions(self, runtime: RuntimeRef, repository: SelfRepository) -> list[Mapping]:
        content = repository.load_manifest().content
        return [
            *runtime_exclusions(
                runtime.root,
                (
                    (
                        "credentials",
                        ".env",
                        Fidelity.EXCLUDED_SENSITIVE,
                        "example-files credentials are not portable",
                    ),
                ),
            ),
            *unmapped_exclusions(
                repository,
                (
                    (
                        "instructions",
                        content.instructions,
                        Fidelity.UNSUPPORTED,
                        "example-files has no instructions mapping",
                    ),
                    (
                        "knowledge",
                        content.knowledge,
                        Fidelity.UNSUPPORTED,
                        "example-files has no knowledge mapping",
                    ),
                    (
                        "workflows",
                        content.workflows,
                        Fidelity.UNSUPPORTED,
                        "example-files has no workflows mapping",
                    ),
                    (
                        "evaluations",
                        content.evaluations,
                        Fidelity.UNSUPPORTED,
                        "example-files has no evaluations mapping",
                    ),
                ),
            ),
        ]

    def plan_import(self, runtime: RuntimeRef, repository: SelfRepository) -> TransferPlan:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity in self._pairs(repository):
            source = runtime.root / runtime_path
            if not canonical or not has_portable_content(source):
                continue
            action, before = self.mapping_action(source, repository.root / canonical)
            mappings.append(
                map_pair(
                    artifact=artifact,
                    source=source,
                    destination=Path(canonical),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                )
            )
        return transfer_plan(
            adapter=self.name,
            direction="import",
            repository=repository,
            runtime=runtime,
            mappings=mappings,
            exclusions=self._exclusions(runtime, repository),
        )

    def plan_restore(self, repository: SelfRepository, runtime: RuntimeRef) -> TransferPlan:
        mappings: list[Mapping] = []
        for artifact, runtime_path, canonical, fidelity in self._pairs(repository):
            source = repository.root / canonical
            if not canonical or not has_portable_content(source):
                continue
            action, before = self.mapping_action(source, runtime.root / runtime_path)
            mappings.append(
                map_pair(
                    artifact=artifact,
                    source=source,
                    destination=Path(runtime_path),
                    fidelity=fidelity,
                    action=action,
                    before_sha256=before,
                )
            )
        return transfer_plan(
            adapter=self.name,
            direction="restore",
            repository=repository,
            runtime=runtime,
            mappings=mappings,
            exclusions=self._exclusions(runtime, repository),
        )

    def validate(
        self, repository: SelfRepository, runtime: RuntimeRef | None = None
    ) -> ValidationResult:
        base = repository.validate(strict=True)
        return ValidationResult(
            valid=base.valid,
            findings=list(base.findings),
            validator_versions={**base.validator_versions, self.name: self.version},
            content_digest=base.content_digest,
        )
