from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    severity: Literal["info", "warning", "error", "blocker"]
    code: str
    message: str
    path: str | None = None
    remediation: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    findings: list[Finding] = Field(default_factory=list)
    validator_versions: dict[str, str] = Field(default_factory=dict)
    content_digest: str

