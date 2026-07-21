from vibe_visualization_api.agent_gateway.adapters.base import AgentAdapter


class AgentAdapterRegistryError(Exception):
    """Base error for Agent adapter discovery and routing."""


class UnknownAgentAdapterError(AgentAdapterRegistryError):
    """Raised when a requested Agent adapter is not registered."""


class AgentAdapterRegistry:
    def __init__(self, adapters: list[AgentAdapter], default_id: str):
        self._adapters: dict[str, AgentAdapter] = {}
        for adapter in adapters:
            if adapter.id in self._adapters:
                raise ValueError(f"duplicate Agent adapter {adapter.id!r}")
            self._adapters[adapter.id] = adapter
        if default_id not in self._adapters:
            raise ValueError(f"default Agent adapter {default_id!r} is not registered")
        self._default_id = default_id

    def get(self, adapter_id: str | None = None) -> AgentAdapter:
        resolved_id = adapter_id or self._default_id
        try:
            return self._adapters[resolved_id]
        except KeyError as error:
            raise UnknownAgentAdapterError(
                f"Agent adapter {resolved_id!r} is not registered"
            ) from error

    @property
    def default_id(self) -> str:
        return self._default_id

    async def describe(self) -> list[dict[str, object]]:
        descriptions: list[dict[str, object]] = []
        for adapter in self._adapters.values():
            description: dict[str, object] = {
                "id": adapter.id,
                "capabilities": await adapter.capabilities(),
                "default": adapter.id == self._default_id,
            }
            describe = getattr(adapter, "describe", None)
            if callable(describe):
                extra = await describe()
                if isinstance(extra, dict):
                    description.update(extra)
            descriptions.append(description)
        return descriptions
