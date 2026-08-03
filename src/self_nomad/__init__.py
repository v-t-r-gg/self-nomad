"""Public package interface for self-nomad."""

from importlib.metadata import PackageNotFoundError, version

from self_nomad.application import SelfNomad

__all__ = ["SelfNomad", "__version__"]

try:
    __version__ = version("self-nomad")
except PackageNotFoundError:  # pragma: no cover - uninstalled source tree only
    __version__ = "0+unknown"
