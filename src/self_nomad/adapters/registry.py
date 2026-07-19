from self_nomad.adapters.base import RuntimeAdapter
from self_nomad.errors import AdapterNotFoundError


class AdapterRegistry:
    def __init__(self, adapters: list[RuntimeAdapter] | None = None) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters or []}

    def register(self, adapter: RuntimeAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> RuntimeAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise AdapterNotFoundError(f"adapter not found: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._adapters)
