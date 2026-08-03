"""Stable application error categories."""


class SelfNomadError(Exception):
    """Base class for expected self-nomad failures."""


class RepositoryNotFoundError(SelfNomadError):
    """A self repository could not be discovered."""


class ManifestError(SelfNomadError):
    """A manifest could not be safely loaded or validated."""


class UnsupportedSchemaError(ManifestError):
    """A document uses an unsupported schema version."""


class ConflictError(SelfNomadError):
    """An operation conflicts with existing state."""


class GitOperationError(SelfNomadError):
    """A Git command failed."""


class ProposalNotFoundError(SelfNomadError):
    """A proposal does not exist in local control state."""


class ProposalStateError(SelfNomadError):
    """A proposal operation is invalid in its current state."""


class ProposalStaleError(SelfNomadError):
    """The target branch or expected file contents changed."""


class ValidationFailedError(SelfNomadError):
    """A proposal failed required validation."""


class PolicyDeniedError(SelfNomadError):
    """Policy does not authorize an operation."""


class AdapterNotFoundError(SelfNomadError):
    """A requested runtime adapter is unavailable."""


class AmbiguousRuntimeError(SelfNomadError):
    """Runtime detection returned multiple candidates."""


class RestoreVerificationError(SelfNomadError):
    """Restored content did not match its planned source."""


class RecoveryRequiredError(SelfNomadError):
    """Automatic rollback failed and manual recovery is required."""


class IntakeError(SelfNomadError):
    """Base class for agent proposal intake failures."""

    code: str = "INTAKE_SUBMISSION_FAILED"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class IntakeRequestTooLargeError(IntakeError):
    code = "INTAKE_REQUEST_TOO_LARGE"


class IntakeInvalidUtf8Error(IntakeError):
    code = "INTAKE_INVALID_UTF8"


class IntakeInvalidJsonError(IntakeError):
    code = "INTAKE_INVALID_JSON"


class IntakeDuplicateKeyError(IntakeError):
    code = "INTAKE_DUPLICATE_KEY"


class IntakeSchemaUnsupportedError(IntakeError):
    code = "INTAKE_SCHEMA_UNSUPPORTED"


class IntakeSchemaInvalidError(IntakeError):
    code = "INTAKE_SCHEMA_INVALID"


class IntakeContentTooLargeError(IntakeError):
    code = "INTAKE_CONTENT_TOO_LARGE"


class IntakeContentUnsafeError(IntakeError):
    code = "INTAKE_CONTENT_UNSAFE"


class IntakeIdConflictError(IntakeError):
    code = "INTAKE_ID_CONFLICT"


class IntakeTargetMovedError(IntakeError):
    code = "INTAKE_TARGET_MOVED"


class IntakePolicyRejectedError(IntakeError):
    code = "INTAKE_POLICY_REJECTED"


class IntakeSubmissionFailedError(IntakeError):
    code = "INTAKE_SUBMISSION_FAILED"
