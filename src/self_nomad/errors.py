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
