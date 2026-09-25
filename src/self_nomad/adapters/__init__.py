from self_nomad.adapters.agents_md import AgentsMdAdapter
from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.adapters.claude_code import ClaudeCodeAdapter
from self_nomad.adapters.example import ExampleFilesAdapter
from self_nomad.adapters.hermes import HermesAdapter
from self_nomad.adapters.openclaw import OpenClawAdapter
from self_nomad.adapters.registry import AdapterRegistry


def default_registry() -> AdapterRegistry:
    return AdapterRegistry(
        [HermesAdapter(), OpenClawAdapter(), AgentsMdAdapter(), ClaudeCodeAdapter()]
    )


__all__ = [
    "AdapterRegistry",
    "AgentsMdAdapter",
    "ClaudeCodeAdapter",
    "ExampleFilesAdapter",
    "HermesAdapter",
    "OpenClawAdapter",
    "RuntimeAdapter",
    "default_registry",
]
