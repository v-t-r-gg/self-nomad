from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_portable_path(value: str) -> str:
    if not value or "\x00" in value or "\\" in value:
        raise ValueError("must be a non-empty repository-relative POSIX path")
    raw_parts = value.split("/")
    if "." in raw_parts or ".." in raw_parts or "" in raw_parts:
        raise ValueError("must not contain empty, '.' or '..' components")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("must not be absolute or contain '.' or '..'")
    return value


class SelfIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)


class ContentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str | None = None
    persona: str | None = None
    identity: str | None = None
    user_profile: str | None = None
    long_term_memory: str | None = None
    daily_memory: str | None = None
    knowledge: str | None = None
    skills: str | None = None
    tool_notes: str | None = None
    workflows: str | None = None
    evaluations: str | None = None

    @field_validator("*", mode="after")
    @classmethod
    def portable_paths(cls, value: str | None) -> str | None:
        return validate_portable_path(value) if value is not None else None


class AdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    self: SelfIdentity
    content: ContentManifest
    skill_format: str = "agent-skills"
    policy: str = "policy/policy.yaml"
    adapters: dict[str, AdapterConfig] = Field(default_factory=dict)

    @field_validator("policy")
    @classmethod
    def policy_path(cls, value: str) -> str:
        return validate_portable_path(value)

    @model_validator(mode="after")
    def supported_version(self) -> "Manifest":
        if self.schema_version != 1:
            raise ValueError("only schema_version 1 is supported")
        return self

    def authoritative_paths(self) -> list[str]:
        data: dict[str, Any] = self.content.model_dump()
        return [path for path in data.values() if path is not None] + [self.policy]
