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

