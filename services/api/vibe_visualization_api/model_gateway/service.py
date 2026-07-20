from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.ai_context.market_explain import (
    build_market_explain_prompt,
)
from vibe_visualization_api.model_gateway.models import (
    ModelResponse,
    ModelResponseCreate,
)
from vibe_visualization_api.model_gateway.registry import ModelAdapterRegistry
from vibe_visualization_api.snapshots.store import (
    SnapshotNotFoundError,
    SnapshotStore,
)


class ModelGatewayService:
    def __init__(
        self,
        registry: ModelAdapterRegistry,
        snapshot_store: SnapshotStore | None = None,
        snapshot_store_factory: Callable[[], SnapshotStore] | None = None,
    ):
        self._registry = registry
        self._snapshot_store = snapshot_store
        self._snapshot_store_factory = snapshot_store_factory

    async def create_response(self, request: ModelResponseCreate) -> ModelResponse:
        prepared = await self._prepare_request(request)
        adapter = self._registry.get(prepared.adapter)
        return await adapter.complete(prepared)

    async def describe_adapters(self) -> list[dict[str, object]]:
        return await self._registry.describe()

    async def _prepare_request(
        self,
        request: ModelResponseCreate,
    ) -> ModelResponseCreate:
        if request.capability != "market.explain":
            return request
        if request.module_id is None:
            raise SnapshotNotFoundError("module snapshot was not found")
        snapshot_store = self._snapshot_store
        if snapshot_store is None and self._snapshot_store_factory is not None:
            snapshot_store = self._snapshot_store_factory()
        if snapshot_store is None:
            raise SnapshotNotFoundError("module snapshot was not found")
        snapshot = await run_in_threadpool(
            snapshot_store.latest_success,
            request.module_id,
        )
        input_prompt = request.input.get("prompt")
        user_prompt = (
            request.prompt
            or (input_prompt if isinstance(input_prompt, str) else "")
        )
        return request.model_copy(
            update={
                "prompt": build_market_explain_prompt(
                    snapshot=snapshot.data,
                    user_prompt=user_prompt,
                ),
                "context": {},
                "input": {},
            }
        )
