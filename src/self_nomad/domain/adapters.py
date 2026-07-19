from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Fidelity(StrEnum):
    EXACT = "exact"
    ADAPTED = "adapted"
    LOSSY = "lossy"
    UNSUPPORTED = "unsupported"
    RUNTIME_OWNED = "runtime_owned"
    EXCLUDED_SENSITIVE = "excluded_sensitive"


class RuntimeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter: str
    root: Path
    name: str


class DetectionResult(BaseModel):
    adapter: str
    candidates: list[RuntimeRef] = Field(default_factory=list)


class Mapping(BaseModel):
    artifact: str
    source: Path | None = None
    destination: Path | None = None
    fidelity: Fidelity
    action: str
    before_sha256: str | None = None
    reason: str | None = None


class TransferPlan(BaseModel):
    adapter: str
    direction: str
    repository_root: Path
    runtime: RuntimeRef
    mappings: list[Mapping] = Field(default_factory=list)
    exclusions: list[Mapping] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(item.action != "identical" for item in self.mappings)


class ApplyResult(BaseModel):
    adapter: str
    written: list[Path] = Field(default_factory=list)
    backup_root: Path | None = None
    hashes: dict[str, str] = Field(default_factory=dict)
