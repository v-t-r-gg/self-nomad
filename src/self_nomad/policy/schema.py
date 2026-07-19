from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: Literal["required", "allowed"] = "required"
    protected_paths: list[str] = Field(default_factory=list)


class LimitsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_file_bytes: int = Field(default=1_048_576, gt=0)
    maximum_proposal_files: int = Field(default=100, gt=0)


class ValidationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict_schema: bool = True
    reject_symlinks: bool = True
    scan_for_secrets: bool = True
    execute_repository_tests: bool = False


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    approval: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    limits: LimitsPolicy = Field(default_factory=LimitsPolicy)
    validation: ValidationPolicy = Field(default_factory=ValidationPolicy)

    @model_validator(mode="after")
    def supported_and_safe(self) -> "Policy":
        if self.schema_version != 1:
            raise ValueError("only schema_version 1 is supported")
        if self.validation.execute_repository_tests:
            raise ValueError("repository test execution is unsupported")
        return self
