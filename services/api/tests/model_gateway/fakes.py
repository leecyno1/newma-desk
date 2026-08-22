from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)


class FakeModelAdapter:
    id = "fake-model"

    def __init__(self) -> None:
        self.requests: list[ModelResponseCreate] = []

    async def capabilities(self) -> list[str]:
        return ["chat", "module.explain"]

    async def describe(self) -> dict[str, object]:
        return {"name": "Fake Model", "available": True}

    async def complete(self, request: ModelResponseCreate) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            answer=f"fake model: {request.prompt or request.capability}",
            adapter=self.id,
            model=request.model or "fake-default",
        )
