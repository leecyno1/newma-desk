from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.preferences import AgentPreferenceStore

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
        preference_store: AgentPreferenceStore | None = None,
    ):
        self._registry = registry
        self._snapshot_store = snapshot_store
        self._snapshot_store_factory = snapshot_store_factory
        self._preference_store = preference_store

    async def create_response(
        self,
        request: ModelResponseCreate,
        *,
        user_id: str = "local-user",
    ) -> ModelResponse:
        prepared = await self._prepare_request(request)
        adapter_id = prepared.adapter
        if adapter_id is None and self._preference_store is not None:
            adapter_id = await run_in_threadpool(
                self._preference_store.resolve_existing_profile,
                user_id,
                prepared.module_id,
                "quick",
                self._registry.default_id,
            )
        adapter = self._registry.get(adapter_id)
        return await adapter.complete(prepared)

    async def describe_adapters(self) -> list[dict[str, object]]:
        return await self._registry.describe()

    def validate_adapter(self, adapter_id: str) -> None:
        self._registry.get(adapter_id)

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
