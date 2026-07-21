import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.agent_gateway.models import (
    AgentPreferences,
    AgentPreferencesUpdate,
    AgentTask,
    AgentTaskCreate,
)
from vibe_visualization_api.agent_gateway.service import AgentTaskService
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository


router = APIRouter(tags=["agent-gateway"])
TERMINAL_EVENT_TYPES = {"completed", "failed", "cancelled"}


async def get_agent_task_service(request: Request) -> AgentTaskService:
    service = request.app.state.agent_task_service
    if service is not None:
        return service
    async with request.app.state.agent_task_service_lock:
        service = request.app.state.agent_task_service
        if service is None:
            service = await run_in_threadpool(
                request.app.state.agent_task_service_factory
            )
            request.app.state.agent_task_service = service
    return service


@router.get("/api/capabilities")
async def capabilities(
    service: AgentTaskService = Depends(get_agent_task_service),
    repository: ModuleRepository = Depends(get_repository),
) -> dict[str, object]:
    published = await run_in_threadpool(repository.list_published)
    module_actions: list[dict[str, object]] = []
    for module in published:
        declared = module.manifest.get("agentCapabilities", [])
        if isinstance(declared, list) and all(
            isinstance(capability, str) for capability in declared
        ):
            module_actions.append(
                {
                    "moduleId": module.module_id,
                    "capabilities": declared,
                }
            )
    return {
        "adapters": await service.describe_adapters(),
        "moduleActions": module_actions,
    }


@router.post("/api/agent/tasks", status_code=202, response_model=AgentTask)
async def create_task(
    task_request: AgentTaskCreate,
    user_id: str = Header(
        default="local-user",
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    service: AgentTaskService = Depends(get_agent_task_service),
) -> AgentTask:
    return await service.create(
        task_request.model_copy(update={"user_id": user_id})
    )


@router.get("/api/agent/preferences", response_model=AgentPreferences)
async def agent_preferences(
    user_id: str = Header(
        default="local-user",
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    service: AgentTaskService = Depends(get_agent_task_service),
) -> AgentPreferences:
    return await service.get_preferences(user_id)


@router.put("/api/agent/preferences", response_model=AgentPreferences)
async def update_agent_preferences(
    update: AgentPreferencesUpdate,
    user_id: str = Header(
        default="local-user",
        alias="X-User-Id",
        min_length=1,
        max_length=128,
    ),
    service: AgentTaskService = Depends(get_agent_task_service),
) -> AgentPreferences:
    return await service.set_preferences(
        user_id,
        update.default_adapter,
        update.module_overrides,
    )


@router.get("/api/agent/tasks/{task_id}", response_model=AgentTask)
async def get_task(
    task_id: str,
    service: AgentTaskService = Depends(get_agent_task_service),
) -> AgentTask:
    return await service.get(task_id)


@router.get("/api/agent/tasks/{task_id}/events")
async def task_events(
    task_id: str,
    after: int = Query(default=0, ge=0),
    service: AgentTaskService = Depends(get_agent_task_service),
) -> StreamingResponse:
    await service.get(task_id)

    async def event_stream() -> AsyncIterator[str]:
        queue = await service.subscribe(task_id)
        last_sequence = after
        try:
            replayed = await service.list_events(task_id, after=after)
            for event in replayed:
                if event.sequence <= last_sequence:
                    continue
                yield _sse_record(event.sequence, event.type, event.data)
                last_sequence = event.sequence
                if event.type in TERMINAL_EVENT_TYPES:
                    return

            current = await service.get(task_id)
            if current.status in TERMINAL_EVENT_TYPES:
                catchup = await service.list_events(task_id, after=last_sequence)
                for event in catchup:
                    yield _sse_record(event.sequence, event.type, event.data)
                    last_sequence = event.sequence
                return

            while True:
                event = await queue.get()
                queue.task_done()
                if event.sequence <= last_sequence:
                    if event.type in TERMINAL_EVENT_TYPES:
                        return
                    continue
                yield _sse_record(event.sequence, event.type, event.data)
                last_sequence = event.sequence
                if event.type in TERMINAL_EVENT_TYPES:
                    return
        except asyncio.CancelledError:
            raise
        finally:
            await service.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/agent/tasks/{task_id}/cancel", response_model=AgentTask)
async def cancel_task(
    task_id: str,
    service: AgentTaskService = Depends(get_agent_task_service),
) -> AgentTask:
    return await service.cancel(task_id)


def _sse_record(sequence: int, event_type: str, data: dict[str, object]) -> str:
    serialized = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {sequence}\nevent: {event_type}\ndata: {serialized}\n\n"
