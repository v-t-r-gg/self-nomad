"""MCP transport-boundary errors and mapping of self-nomad exceptions."""

from __future__ import annotations

from self_nomad.errors import (
    IntakeError,
    ProposalNotFoundError,
    ProposalStaleError,
    ProposalStateError,
    SelfNomadError,
    ValidationFailedError,
)


class McpServerError(Exception):
    """Error raised inside an MCP tool with a stable code for clients."""

    code: str = "MCP_INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class McpConfigurationError(McpServerError):
    code = "MCP_CONFIGURATION_ERROR"


class McpRepositoryUnavailableError(McpServerError):
    code = "MCP_REPOSITORY_UNAVAILABLE"


class McpInvalidArgumentError(McpServerError):
    code = "MCP_INVALID_ARGUMENT"


def map_exception(exc: BaseException) -> tuple[str, str]:
    """Map known exceptions to (code, safe_message) without local paths."""
    if isinstance(exc, McpServerError):
        return exc.code, str(exc)
    if isinstance(exc, IntakeError):
        return exc.code, str(exc)
    if isinstance(exc, ProposalNotFoundError):
        return "PROPOSAL_NOT_FOUND", str(exc)
    if isinstance(exc, ProposalStaleError):
        return "PROPOSAL_STALE", str(exc)
    if isinstance(exc, ProposalStateError):
        return "PROPOSAL_STATE", str(exc)
    if isinstance(exc, ValidationFailedError):
        return "VALIDATION_FAILED", str(exc)
    if isinstance(exc, SelfNomadError):
        return "SELF_NOMAD_ERROR", str(exc)
    return "MCP_INTERNAL_ERROR", "an internal error occurred"
