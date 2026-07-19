from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.adapters.hermes import HermesAdapter
from self_nomad.adapters.openclaw import OpenClawAdapter
from self_nomad.adapters.registry import AdapterRegistry


def default_registry() -> AdapterRegistry:
    return AdapterRegistry([HermesAdapter(), OpenClawAdapter()])


__all__ = [
    "AdapterRegistry",
    "HermesAdapter",
    "OpenClawAdapter",
    "RuntimeAdapter",
    "default_registry",
]
