"""Helpers for RuntimeAdapter authors. Adapters must not run Git or approve."""

from __future__ import annotations

from pathlib import Path

from self_nomad.domain import Fidelity, Mapping, RuntimeRef, TransferPlan
from self_nomad.repository import SelfRepository


def has_portable_content(path: Path) -> bool:
    """True when a file exists or a directory has a non-.gitkeep file."""
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    return any(item.is_file() and item.name != ".gitkeep" for item in path.rglob("*"))


def map_pair(
    *,
    artifact: str,
    source: Path,
    destination: Path,
    fidelity: Fidelity,
    action: str,
    before_sha256: str | None,
    reason: str | None = None,
) -> Mapping:
    return Mapping(
        artifact=artifact,
        source=source,
        destination=destination,
        fidelity=fidelity,
        action=action,
        before_sha256=before_sha256,
        reason=reason,
    )


def unmapped_exclusions(
    repository: SelfRepository,
    classes: tuple[tuple[str, str | None, Fidelity, str], ...],
) -> list[Mapping]:
    """Always report each class. Never silently drop knowledge/workflows/evals."""
    exclusions: list[Mapping] = []
    for artifact, relative, fidelity, reason in classes:
        path = repository.root / relative if relative else None
        exclusions.append(
            Mapping(
                artifact=artifact,
                source=path if path and path.exists() else None,
                fidelity=fidelity,
                action="exclude",
                reason=reason,
            )
        )
    return exclusions


def runtime_exclusions(
    runtime_root: Path,
    classes: tuple[tuple[str, str, Fidelity, str], ...],
) -> list[Mapping]:
    return [
        Mapping(
            artifact=artifact,
            source=(runtime_root / relative) if (runtime_root / relative).exists() else None,
            fidelity=fidelity,
            action="exclude",
            reason=reason,
        )
        for artifact, relative, fidelity, reason in classes
    ]


def transfer_plan(
    *,
    adapter: str,
    direction: str,
    repository: SelfRepository,
    runtime: RuntimeRef,
    mappings: list[Mapping],
    exclusions: list[Mapping],
) -> TransferPlan:
    return TransferPlan(
        adapter=adapter,
        direction=direction,
        repository_root=repository.root,
        runtime=runtime,
        mappings=mappings,
        exclusions=exclusions,
    )
