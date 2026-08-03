"""MCP transport-boundary errors and public exception mapping."""

from __future__ import annotations

import logging

from self_nomad.errors import (
    GitOperationError,
    IntakeContentTooLargeError,
    IntakeContentUnsafeError,
    IntakeDuplicateKeyError,
    IntakeError,
    IntakeIdConflictError,
    IntakeInvalidJsonError,
    IntakeInvalidUtf8Error,
    IntakePolicyRejectedError,
    IntakeRequestTooLargeError,
    IntakeSchemaInvalidError,
    IntakeSchemaUnsupportedError,
    IntakeSubmissionFailedError,
    IntakeTargetMovedError,
    PolicyDeniedError,
    ProposalNotFoundError,
    ProposalStaleError,
    ProposalStateError,
    SelfNomadError,
    ValidationFailedError,
)

logger = logging.getLogger("self_nomad.mcp")

# Public codes for MCP clients. Messages are fixed; never derive them from str(exc).
PUBLIC_MESSAGES: dict[str, str] = {
    "PROPOSAL_NOT_FOUND": "proposal not found",
    "PROPOSAL_STATE": "proposal is not in a valid state for this operation",
    "PROPOSAL_STALE": "proposal is stale relative to the target branch or content",
    "VALIDATION_FAILED": "proposal validation failed",
    "INTAKE_ID_CONFLICT": "request_id was reused with a different payload",
    "INTAKE_TARGET_MOVED": "target branch moved since the request was frozen",
    "INTAKE_POLICY_REJECTED": "request rejected by repository policy",
    "INTAKE_SCHEMA_UNSUPPORTED": "unsupported proposal request schema version",
    "INTAKE_SCHEMA_INVALID": "proposal request failed schema validation",
    "INTAKE_CONTENT_UNSAFE": "proposal content rejected by safety checks",
    "INTAKE_CONTENT_TOO_LARGE": "proposal content exceeds configured limits",
    "INTAKE_REQUEST_TOO_LARGE": "proposal request exceeds configured limits",
    "INTAKE_INVALID_UTF8": "proposal request is not valid UTF-8",
    "INTAKE_INVALID_JSON": "proposal request is not valid JSON",
    "INTAKE_DUPLICATE_KEY": "proposal request contains duplicate JSON keys",
    "INTAKE_SUBMISSION_FAILED": "intake submission failed",
    "POLICY_DENIED": "operation denied by repository policy",
    "MCP_INVALID_ARGUMENT": "invalid tool arguments",
    "MCP_CONFIGURATION_ERROR": "MCP server configuration error",
    "MCP_REPOSITORY_UNAVAILABLE": "configured repository is unavailable",
    "MCP_INTERNAL_ERROR": "an internal error occurred",
}


class McpServerError(Exception):
    """Error raised inside an MCP tool with a stable public code."""

    code: str = "MCP_INTERNAL_ERROR"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        default = PUBLIC_MESSAGES["MCP_INTERNAL_ERROR"]
        public = message if message is not None else PUBLIC_MESSAGES.get(self.code, default)
        super().__init__(public)


class McpConfigurationError(McpServerError):
    code = "MCP_CONFIGURATION_ERROR"


class McpRepositoryUnavailableError(McpServerError):
    code = "MCP_REPOSITORY_UNAVAILABLE"


class McpInvalidArgumentError(McpServerError):
    code = "MCP_INVALID_ARGUMENT"

    def __init__(
        self,
        message: str = PUBLIC_MESSAGES["MCP_INVALID_ARGUMENT"],
        *,
        path: str | None = None,
    ) -> None:
        super().__init__(message, code="MCP_INVALID_ARGUMENT")
        self.path = path


def map_exception(exc: BaseException) -> tuple[str, str, str | None]:
    """Map known exceptions to (code, safe_message, path).

    Never returns ``str(exc)`` for infrastructure or untrusted exception text.
    Logs internal details for unexpected failures to stderr via the logging
    subsystem (configured to stderr only).
    """
    if isinstance(exc, McpInvalidArgumentError):
        return exc.code, str(exc), exc.path
    if isinstance(exc, McpServerError):
        return exc.code, str(exc), None

    if isinstance(exc, ProposalNotFoundError):
        return "PROPOSAL_NOT_FOUND", PUBLIC_MESSAGES["PROPOSAL_NOT_FOUND"], None
    if isinstance(exc, ProposalStaleError):
        return "PROPOSAL_STALE", PUBLIC_MESSAGES["PROPOSAL_STALE"], None
    if isinstance(exc, ProposalStateError):
        return "PROPOSAL_STATE", PUBLIC_MESSAGES["PROPOSAL_STATE"], None
    if isinstance(exc, ValidationFailedError):
        return "VALIDATION_FAILED", PUBLIC_MESSAGES["VALIDATION_FAILED"], None
    if isinstance(exc, PolicyDeniedError):
        return "POLICY_DENIED", PUBLIC_MESSAGES["POLICY_DENIED"], None

    if isinstance(exc, IntakeIdConflictError):
        return "INTAKE_ID_CONFLICT", PUBLIC_MESSAGES["INTAKE_ID_CONFLICT"], None
    if isinstance(exc, IntakeTargetMovedError):
        return "INTAKE_TARGET_MOVED", PUBLIC_MESSAGES["INTAKE_TARGET_MOVED"], None
    if isinstance(exc, IntakePolicyRejectedError):
        return "INTAKE_POLICY_REJECTED", PUBLIC_MESSAGES["INTAKE_POLICY_REJECTED"], None
    if isinstance(exc, IntakeSchemaUnsupportedError):
        return "INTAKE_SCHEMA_UNSUPPORTED", PUBLIC_MESSAGES["INTAKE_SCHEMA_UNSUPPORTED"], None
    if isinstance(exc, IntakeSchemaInvalidError):
        return "INTAKE_SCHEMA_INVALID", PUBLIC_MESSAGES["INTAKE_SCHEMA_INVALID"], None
    if isinstance(exc, IntakeContentUnsafeError):
        return "INTAKE_CONTENT_UNSAFE", PUBLIC_MESSAGES["INTAKE_CONTENT_UNSAFE"], None
    if isinstance(exc, IntakeContentTooLargeError):
        return "INTAKE_CONTENT_TOO_LARGE", PUBLIC_MESSAGES["INTAKE_CONTENT_TOO_LARGE"], None
    if isinstance(exc, IntakeRequestTooLargeError):
        return "INTAKE_REQUEST_TOO_LARGE", PUBLIC_MESSAGES["INTAKE_REQUEST_TOO_LARGE"], None
    if isinstance(exc, IntakeInvalidUtf8Error):
        return "INTAKE_INVALID_UTF8", PUBLIC_MESSAGES["INTAKE_INVALID_UTF8"], None
    if isinstance(exc, IntakeInvalidJsonError):
        return "INTAKE_INVALID_JSON", PUBLIC_MESSAGES["INTAKE_INVALID_JSON"], None
    if isinstance(exc, IntakeDuplicateKeyError):
        return "INTAKE_DUPLICATE_KEY", PUBLIC_MESSAGES["INTAKE_DUPLICATE_KEY"], None
    if isinstance(exc, IntakeSubmissionFailedError):
        logger.error("intake submission failed: %s: %s", type(exc).__name__, exc)
        return "INTAKE_SUBMISSION_FAILED", PUBLIC_MESSAGES["INTAKE_SUBMISSION_FAILED"], None
    if isinstance(exc, IntakeError):
        # Unknown intake subclass: stable code only, no raw message.
        code = getattr(exc, "code", "INTAKE_SUBMISSION_FAILED") or "INTAKE_SUBMISSION_FAILED"
        message = PUBLIC_MESSAGES.get(code, PUBLIC_MESSAGES["INTAKE_SUBMISSION_FAILED"])
        logger.error("intake error %s: %s: %s", code, type(exc).__name__, exc)
        return code, message, None

    if isinstance(exc, GitOperationError):
        logger.error("git operation error: %s", exc)
        return "MCP_INTERNAL_ERROR", PUBLIC_MESSAGES["MCP_INTERNAL_ERROR"], None

    if isinstance(exc, SelfNomadError):
        logger.error("self-nomad error: %s: %s", type(exc).__name__, exc)
        return "MCP_INTERNAL_ERROR", PUBLIC_MESSAGES["MCP_INTERNAL_ERROR"], None

    logger.error("unexpected error: %s: %s", type(exc).__name__, exc)
    return "MCP_INTERNAL_ERROR", PUBLIC_MESSAGES["MCP_INTERNAL_ERROR"], None
