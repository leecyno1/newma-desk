import asyncio
from dataclasses import dataclass
from typing import cast

from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.adapters.base import AgentAdapter
from vibe_visualization_api.agent_gateway.event_bus import TaskEventBus
from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTask,
    AgentTaskCreate,
    TaskEvent,
)
from vibe_visualization_api.ai_context.market_explain import (
    build_market_explain_prompt,
)
from vibe_visualization_api.ai_context.finance_capabilities import (
    FinanceCapabilityContextEnricher,
)
from vibe_visualization_api.ai_context.light_research import (
    LightResearchContextEnricher,
)
from vibe_visualization_api.agent_gateway.registry import AgentAdapterRegistry
from vibe_visualization_api.agent_gateway.preferences import AgentPreferenceStore
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskStore,
)
from vibe_visualization_api.control_plane.context_store import ModContextStore
from vibe_visualization_api.snapshots.store import (
    SnapshotNotFoundError,
    SnapshotStore,
)


TERMINAL_EVENT_TYPES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class ActiveTask:
    adapter: AgentAdapter
    handle: asyncio.Task[None]


class AgentTaskService:
    def __init__(
        self,
        store: TaskStore,
        event_bus: TaskEventBus,
        registry: AgentAdapterRegistry,
        snapshot_store: SnapshotStore | None = None,
        preference_store: AgentPreferenceStore | None = None,
        context_store: ModContextStore | None = None,
        research_enricher: LightResearchContextEnricher | None = None,
        finance_capability_enricher: (
            FinanceCapabilityContextEnricher | None
        ) = None,
    ):
        self._store = store
        self._event_bus = event_bus
        self._registry = registry
        self._snapshot_store = snapshot_store
        self._preference_store = preference_store
        self._context_store = context_store
        self._research_enricher = research_enricher
        self._finance_capability_enricher = finance_capability_enricher
        self._active: dict[str, ActiveTask] = {}
        self._cancel_lock = asyncio.Lock()

    async def create(
        self,
        request: AgentTaskCreate,
        *,
        workspace_id: str = "local-workspace",
    ) -> AgentTask:
        adapter_id = request.adapter
        if adapter_id is None and self._preference_store is not None:
            adapter_id = await run_in_threadpool(
                self._preference_store.resolve_profile,
                request.user_id,
                request.module_id,
                request.profile,
                self._registry.default_id,
            )
        adapter = self._registry.get(adapter_id)
        request = request.model_copy(update={"adapter": adapter.id})
        request = await self._attach_mod_context(request, workspace_id)
        prepared_request = await self._prepare_request(request)
        task = await run_in_threadpool(self._store.create, prepared_request)
        handle = asyncio.create_task(
            self._run_adapter(task.id, prepared_request, adapter),
            name=f"agent-task:{task.id}",
        )
        self._active[task.id] = ActiveTask(adapter=adapter, handle=handle)
        return task

    async def _attach_mod_context(
        self,
        request: AgentTaskCreate,
        workspace_id: str,
    ) -> AgentTaskCreate:
        if request.module_id is None or self._context_store is None:
            return request
        stored = await run_in_threadpool(
            self._context_store.get,
            user_id=request.user_id,
            workspace_id=workspace_id,
            module_id=request.module_id,
        )
        if stored is None:
            return request
        existing_context = dict(request.context)
        existing_vibedesk = existing_context.get("vibedesk")
        vibedesk_context = (
            dict(existing_vibedesk)
            if isinstance(existing_vibedesk, dict)
            else {}
        )
        vibedesk_context.update(
            {
                "mod": {
                    "id": request.module_id,
                    "revision": stored["revision"],
                },
                "workspace": {"id": workspace_id},
                "page": stored["context"],
                "contextUpdatedAt": stored["updatedAt"],
            }
        )
        existing_context["vibedesk"] = vibedesk_context
        return request.model_copy(update={"context": existing_context})

    async def _prepare_request(self, request: AgentTaskCreate) -> AgentTaskCreate:
        if request.capability != "market.explain":
            return request
        if request.module_id is None or self._snapshot_store is None:
            raise SnapshotNotFoundError("module snapshot was not found")
        snapshot = await run_in_threadpool(
            self._snapshot_store.latest_success,
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
            }
        )

    async def get(self, task_id: str) -> AgentTask:
        return await run_in_threadpool(self._store.get, task_id)

    async def list_events(self, task_id: str, after: int = 0) -> list[TaskEvent]:
        return await run_in_threadpool(self._store.list_events, task_id, after)

    async def subscribe(self, task_id: str) -> asyncio.Queue[TaskEvent]:
        return await self._event_bus.subscribe(task_id)

    async def unsubscribe(
        self,
        task_id: str,
        queue: asyncio.Queue[TaskEvent],
    ) -> None:
        await self._event_bus.unsubscribe(task_id, queue)

    async def describe_adapters(self) -> list[dict[str, object]]:
        return await self._registry.describe()

    async def get_preferences(self, user_id: str):
        if self._preference_store is None:
            raise RuntimeError("Agent preferences are unavailable")
        return await run_in_threadpool(
            self._preference_store.get,
            user_id,
            self._registry.default_id,
        )

    async def set_preferences(
        self,
        user_id: str,
        default_adapter: str,
        module_overrides: dict[str, str],
        profile_targets: dict[str, str],
        module_profile_overrides: dict[str, dict[str, str]],
    ):
        self._registry.get(default_adapter)
        for adapter_id in module_overrides.values():
            self._registry.get(adapter_id)
        for profile, adapter_id in profile_targets.items():
            if profile != "quick":
                self._registry.get(adapter_id)
        for targets in module_profile_overrides.values():
            for profile, adapter_id in targets.items():
                if profile != "quick":
                    self._registry.get(adapter_id)
        if self._preference_store is None:
            raise RuntimeError("Agent preferences are unavailable")
        return await run_in_threadpool(
            self._preference_store.set,
            user_id,
            default_adapter,
            module_overrides,
            profile_targets,
            module_profile_overrides,
        )

    async def cancel(self, task_id: str) -> AgentTask:
        async with self._cancel_lock:
            before = await self.get(task_id)
            cancelled = await run_in_threadpool(self._store.cancel, task_id)
            if before.status == "cancelled":
                return cancelled

            events = await self.list_events(task_id)
            cancellation_event = events[-1]
            await self._event_bus.publish(cancellation_event)

            active = self._active.get(task_id)
            if active is not None:
                try:
                    await asyncio.wait_for(active.adapter.cancel(task_id), timeout=5.0)
                except Exception:
                    pass
                active.handle.cancel()
            return cancelled

    async def shutdown(self) -> None:
        active_task_ids = list(self._active)
        for task_id in active_task_ids:
            try:
                await self.cancel(task_id)
            except Exception:
                active = self._active.get(task_id)
                if active is not None:
                    active.handle.cancel()
        handles = [active.handle for active in self._active.values()]
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)
        self._active.clear()

    async def _run_adapter(
        self,
        task_id: str,
        request: AgentTaskCreate,
        adapter: AgentAdapter,
    ) -> None:
        terminal_seen = False
        try:
            if self._finance_capability_enricher is not None:
                request = await self._finance_capability_enricher.enrich(request)
            if self._research_enricher is not None:
                request = await self._research_enricher.enrich(request)
            async for adapter_event in adapter.run(task_id, request):
                event = await self._persist_event(task_id, adapter_event)
                await self._event_bus.publish(event)
                if event.type in TERMINAL_EVENT_TYPES:
                    terminal_seen = True
                    break
            if not terminal_seen:
                event = await self._persist_event(
                    task_id,
                    AdapterEvent(
                        type="failed",
                        data={
                            "code": "adapter_incomplete",
                            "error": "Agent adapter ended without a result",
                        },
                    ),
                )
                await self._event_bus.publish(event)
        except asyncio.CancelledError:
            raise
        except InvalidTaskStateError:
            return
        except Exception:
            try:
                event = await self._persist_event(
                    task_id,
                    AdapterEvent(
                        type="failed",
                        data={
                            "code": "adapter_error",
                            "error": "Agent adapter failed",
                        },
                    ),
                )
            except InvalidTaskStateError:
                return
            except Exception:
                return
            await self._event_bus.publish(event)
        finally:
            current = asyncio.current_task()
            active = self._active.get(task_id)
            if active is not None and active.handle is current:
                self._active.pop(task_id, None)

    async def _persist_event(
        self,
        task_id: str,
        adapter_event: AdapterEvent,
    ) -> TaskEvent:
        data = cast(dict[str, object], adapter_event.data)
        return await run_in_threadpool(
            self._store.append_event,
            task_id,
            adapter_event.type,
            data,
        )
