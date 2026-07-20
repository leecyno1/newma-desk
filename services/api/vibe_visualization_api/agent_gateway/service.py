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
from vibe_visualization_api.agent_gateway.prompts.market_explain import (
    build_market_explain_prompt,
)
from vibe_visualization_api.agent_gateway.registry import AgentAdapterRegistry
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskStore,
)
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
    ):
        self._store = store
        self._event_bus = event_bus
        self._registry = registry
        self._snapshot_store = snapshot_store
        self._active: dict[str, ActiveTask] = {}
        self._cancel_lock = asyncio.Lock()

    async def create(self, request: AgentTaskCreate) -> AgentTask:
        adapter = self._registry.get(request.adapter)
        prepared_request = await self._prepare_request(request)
        task = await run_in_threadpool(self._store.create, prepared_request)
        handle = asyncio.create_task(
            self._run_adapter(task.id, prepared_request, adapter),
            name=f"agent-task:{task.id}",
        )
        self._active[task.id] = ActiveTask(adapter=adapter, handle=handle)
        return task

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
                "context": {},
                "input": {},
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
                active.handle.cancel()
                try:
                    await asyncio.wait_for(active.adapter.cancel(task_id), timeout=5.0)
                except Exception:
                    pass
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
            async for adapter_event in adapter.run(request):
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
