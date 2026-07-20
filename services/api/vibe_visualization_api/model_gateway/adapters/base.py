from typing import Protocol

from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)


class ModelAdapter(Protocol):
    id: str

    async def capabilities(self) -> list[str]: ...

    async def complete(self, request: ModelResponseCreate) -> ModelResponse: ...
