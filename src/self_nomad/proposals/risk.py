"""Shared proposal risk classification for materialization and intake preview."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any, Literal


def classify_proposal_risk(
    operations: Iterable[Any],
) -> Literal["low", "medium", "high", "critical"]:
    items = list(operations)
    paths = [str(operation.path) for operation in items]
    if any(
        path.startswith("policy/")
        or path == "self-nomad.yaml"
        or PurePosixPath(path).suffix in {".py", ".sh", ".js", ".exe"}
        for path in paths
    ):
        return "critical"
    if any(
        str(operation.kind) == "delete" or str(operation.path).startswith("identity/")
        for operation in items
    ):
        return "high"
    if any(path.startswith("skills/") for path in paths):
        return "medium"
    return "low"
