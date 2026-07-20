from vibe_visualization_api.model_gateway.adapters.base import ModelAdapter


class ModelAdapterRegistryError(Exception):
    """Base error for Model adapter discovery and routing."""


class UnknownModelAdapterError(ModelAdapterRegistryError):
    """Raised when a requested Model adapter is not registered."""


class ModelAdapterRegistry:
    def __init__(self, adapters: list[ModelAdapter], default_id: str):
        self._adapters: dict[str, ModelAdapter] = {}
        for adapter in adapters:
            if adapter.id in self._adapters:
                raise ValueError(f"duplicate Model adapter {adapter.id!r}")
            self._adapters[adapter.id] = adapter
        if default_id not in self._adapters:
            raise ValueError(f"default Model adapter {default_id!r} is not registered")
        self._default_id = default_id

    def get(self, adapter_id: str | None = None) -> ModelAdapter:
        resolved_id = adapter_id or self._default_id
        try:
            return self._adapters[resolved_id]
        except KeyError as error:
            raise UnknownModelAdapterError(
                f"Model adapter {resolved_id!r} is not registered"
            ) from error

    async def describe(self) -> list[dict[str, object]]:
        return [
            {
                "id": adapter.id,
                "capabilities": await adapter.capabilities(),
                "default": adapter.id == self._default_id,
            }
            for adapter in self._adapters.values()
        ]
