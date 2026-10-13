from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.workflow_control.errors import (
    WorkflowAuthorizationError,
    WorkflowValidationError,
)
from vibe_visualization_api.workflow_control.repository import (
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from vibe_visualization_api.workflow_runtime.adapters import (
    UnknownNodeExecutionAdapterError,
)
from vibe_visualization_api.workflow_runtime.conditions import ConditionExpressionError
from vibe_visualization_api.workflow_runtime.models import (
    WorkflowRemoteAgentTaskCreate,
    WorkflowRuntimeCommand,
    WorkflowRuntimeEventPublish,
    WorkflowRuntimeStart,
    WorkflowRuntimeTick,
    WorkflowRuntimeTriggerCreate,
    WorkflowRuntimeTriggerState,
    WorkflowTriggerType,
)
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskNotFoundError,
)
from vibe_visualization_api.workflow_runtime.repository import (
    WorkflowRuntimeConflictError,
    WorkflowRuntimeNotFoundError,
)
from vibe_visualization_api.workflow_runtime.signing import WorkflowSignatureError


router = APIRouter(prefix="/api/workflows/runtime", tags=["workflow-runtime"])

UserId = Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
ActingPrincipalId = Annotated[
    str | None,
    Header(alias="X-Workflow-Principal-Id", max_length=128),
]
ResourceId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$"),
]
EventType = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$"),
]
WebhookTimestamp = Annotated[
    str,
    Header(alias="X-Newma-Webhook-Timestamp", pattern=r"^[0-9]{10}$"),
]
WebhookSignature = Annotated[
    str,
    Header(alias="X-Newma-Webhook-Signature", pattern=r"^sha256=[a-f0-9]{64}$"),
]
WebhookWorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
AgentTimestamp = Annotated[
    str,
    Header(alias="X-Newma-Agent-Timestamp", pattern=r"^[0-9]{10}$"),
]
AgentSignature = Annotated[
    str,
    Header(alias="X-Newma-Agent-Signature", pattern=r"^sha256=[a-f0-9]{64}$"),
]
MAX_WEBHOOK_BYTES = 256 * 1024


async def execute(call: Callable[[], Any]) -> Any:
    try:
        return await run_in_threadpool(call)
    except (WorkflowNotFoundError, WorkflowRuntimeNotFoundError) as error:
        raise HTTPException(404, "Workflow runtime resource not found") from error
    except WorkflowAuthorizationError as error:
        raise HTTPException(403, str(error)) from error
    except (WorkflowConflictError, WorkflowRuntimeConflictError) as error:
        raise HTTPException(409, str(error)) from error
    except (
        WorkflowValidationError,
        ConditionExpressionError,
        UnknownNodeExecutionAdapterError,
        ValidationError,
        ValueError,
    ) as error:
        raise HTTPException(422, str(error)) from error


def runtime(request: Request):
    return request.app.state.workflow_runtime_engine


def actor(
    request: Request,
    *,
    user_id: str,
    workspace_id: str,
    acting_principal_id: str | None,
) -> dict[str, Any]:
    return request.app.state.workflow_control_service.identity(
        organization_id=workspace_id,
        user_id=user_id,
        acting_principal_id=acting_principal_id,
    )


def remote_task_workspace(task: Any) -> str | None:
    request = getattr(task, "request", None)
    context = getattr(request, "context", None)
    if not isinstance(context, dict):
        return None
    workflow = context.get("workflow")
    if not isinstance(workflow, dict):
        return None
    workspace_id = workflow.get("organizationId")
    return str(workspace_id) if workspace_id else None


def require_remote_task_workspace(task: Any, workspace_id: str) -> None:
    if remote_task_workspace(task) != workspace_id:
        raise HTTPException(404, "Remote Agent task not found")


@router.get("/executions")
async def list_executions(
    request: Request,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "executions": (
                request.app.state.workflow_control_service.identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                runtime(request).list(workspace_id, run_id),
            )[1]
        }
    )


@router.post(
    "/runs/{run_id}/executions",
    status_code=status.HTTP_201_CREATED,
)
async def start_execution(
    run_id: ResourceId,
    payload: WorkflowRuntimeStart,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    if payload.trigger_type not in {
        WorkflowTriggerType.MANUAL,
        WorkflowTriggerType.API,
    }:
        raise HTTPException(422, "event and schedule executions require a trigger")
    return await execute(
        lambda: runtime(request).start(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            trigger_type=payload.trigger_type.value,
            idempotency_key=payload.idempotency_key,
            input_payload=payload.input,
            user_id=user_id,
            dispatch=False,
        )
    )


@router.get("/triggers")
async def list_triggers(
    request: Request,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "triggers": (
                request.app.state.workflow_control_service.identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                runtime(request).list_triggers(workspace_id, run_id),
            )[1]
        }
    )


@router.post("/runs/{run_id}/triggers", status_code=status.HTTP_201_CREATED)
async def create_trigger(
    run_id: ResourceId,
    payload: WorkflowRuntimeTriggerCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).create_trigger(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            trigger_type=payload.trigger_type.value,
            event_type=payload.event_type,
            interval_seconds=payload.interval_seconds,
            cron_expression=payload.cron_expression,
            timezone=payload.timezone,
            input_payload=payload.input,
            user_id=user_id,
            enabled=payload.enabled,
        )
    )


@router.post("/triggers/{trigger_id}/enabled")
async def set_trigger_enabled(
    trigger_id: ResourceId,
    payload: WorkflowRuntimeTriggerState,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).set_trigger_enabled(
            organization_id=workspace_id,
            trigger_id=trigger_id,
            enabled=payload.enabled,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.post("/events/{event_type}", status_code=status.HTTP_202_ACCEPTED)
async def publish_event(
    event_type: EventType,
    payload: WorkflowRuntimeEventPublish,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "executions": (
                request.app.state.workflow_control_service.identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                runtime(request).emit_event(
                    organization_id=workspace_id,
                    event_type=event_type,
                    idempotency_key=payload.idempotency_key,
                    input_payload=payload.input,
                ),
            )[1]
        }
    )


@router.post(
    "/webhooks/events/{event_type}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_signed_webhook(
    event_type: EventType,
    request: Request,
    workspace_id: WebhookWorkspaceId,
    timestamp: WebhookTimestamp,
    signature: WebhookSignature,
):
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(413, "Webhook payload is too large")
    signer = request.app.state.workflow_request_signer
    if not signer.available:
        raise HTTPException(503, "Workflow webhook signing is not configured")
    try:
        signer.verify(
            timestamp=timestamp,
            signature=signature,
            scope=f"webhook:{workspace_id}:{event_type}",
            body=body,
        )
    except WorkflowSignatureError as error:
        raise HTTPException(401, "Invalid workflow webhook signature") from error
    try:
        payload = WorkflowRuntimeEventPublish.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(422, "Invalid workflow webhook payload") from error
    return await execute(
        lambda: {
            "executions": runtime(request).emit_event(
                organization_id=workspace_id,
                event_type=event_type,
                idempotency_key=payload.idempotency_key,
                input_payload=payload.input,
            )
        }
    )


async def verify_remote_agent_request(
    request: Request,
    *,
    workspace_id: str,
    timestamp: str,
    signature: str,
    method: str,
    path: str,
) -> bytes:
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(413, "Remote Agent payload is too large")
    signer = request.app.state.workflow_server_agent_signer
    if not signer.available:
        raise HTTPException(503, "Remote Server Agent signing is not configured")
    try:
        signer.verify(
            timestamp=timestamp,
            signature=signature,
            scope=f"remote-agent:{workspace_id}:{method}:{path}",
            body=body,
        )
    except WorkflowSignatureError as error:
        raise HTTPException(401, "Invalid Remote Server Agent signature") from error
    return body


@router.post(
    "/remote-agent/tasks",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_remote_agent_task(
    request: Request,
    workspace_id: WebhookWorkspaceId,
    timestamp: AgentTimestamp,
    signature: AgentSignature,
):
    path = "/api/workflows/runtime/remote-agent/tasks"
    body = await verify_remote_agent_request(
        request,
        workspace_id=workspace_id,
        timestamp=timestamp,
        signature=signature,
        method="POST",
        path=path,
    )
    try:
        payload = WorkflowRemoteAgentTaskCreate.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(422, "Invalid Remote Server Agent payload") from error
    if payload.workspace_id != workspace_id:
        raise HTTPException(401, "Invalid Remote Server Agent workspace")
    request_context = dict(payload.request.context)
    workflow_context = request_context.get("workflow")
    workflow_context = (
        dict(workflow_context) if isinstance(workflow_context, dict) else {}
    )
    workflow_context["organizationId"] = workspace_id
    request_context["workflow"] = workflow_context
    task = await request.app.state.resolve_agent_task_service().create(
        payload.request.model_copy(update={"context": request_context}),
        workspace_id=workspace_id,
    )
    return task.model_dump(by_alias=True)


@router.get("/remote-agent/tasks/{task_id}")
async def get_remote_agent_task(
    task_id: ResourceId,
    request: Request,
    workspace_id: WebhookWorkspaceId,
    timestamp: AgentTimestamp,
    signature: AgentSignature,
):
    path = f"/api/workflows/runtime/remote-agent/tasks/{task_id}"
    await verify_remote_agent_request(
        request,
        workspace_id=workspace_id,
        timestamp=timestamp,
        signature=signature,
        method="GET",
        path=path,
    )
    try:
        task = await request.app.state.resolve_agent_task_service().get(task_id)
    except TaskNotFoundError as error:
        raise HTTPException(404, "Remote Agent task not found") from error
    require_remote_task_workspace(task, workspace_id)
    return task.model_dump(by_alias=True)


@router.post("/remote-agent/tasks/{task_id}/cancel")
async def cancel_remote_agent_task(
    task_id: ResourceId,
    request: Request,
    workspace_id: WebhookWorkspaceId,
    timestamp: AgentTimestamp,
    signature: AgentSignature,
):
    path = f"/api/workflows/runtime/remote-agent/tasks/{task_id}/cancel"
    await verify_remote_agent_request(
        request,
        workspace_id=workspace_id,
        timestamp=timestamp,
        signature=signature,
        method="POST",
        path=path,
    )
    try:
        service = request.app.state.resolve_agent_task_service()
        task = await service.get(task_id)
        require_remote_task_workspace(task, workspace_id)
        task = await service.cancel(task_id)
    except TaskNotFoundError as error:
        raise HTTPException(404, "Remote Agent task not found") from error
    except InvalidTaskStateError as error:
        raise HTTPException(409, "Remote Agent task cannot be cancelled") from error
    return task.model_dump(by_alias=True)


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: ResourceId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: (
            request.app.state.workflow_control_service.identity(
                organization_id=workspace_id,
                user_id=user_id,
            ),
            runtime(request).get(workspace_id, execution_id),
        )[1]
    )


@router.post("/executions/{execution_id}/tick")
async def tick_execution(
    execution_id: ResourceId,
    payload: WorkflowRuntimeTick,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).tick(
            organization_id=workspace_id,
            execution_id=execution_id,
            max_jobs=payload.max_jobs,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.post("/executions/{execution_id}/pause")
async def pause_execution(
    execution_id: ResourceId,
    payload: WorkflowRuntimeCommand,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).pause(
            organization_id=workspace_id,
            execution_id=execution_id,
            reason=payload.reason,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: ResourceId,
    payload: WorkflowRuntimeCommand,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).resume(
            organization_id=workspace_id,
            execution_id=execution_id,
            reason=payload.reason,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: ResourceId,
    payload: WorkflowRuntimeCommand,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).cancel(
            organization_id=workspace_id,
            execution_id=execution_id,
            reason=payload.reason,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.post("/executions/{execution_id}/jobs/{job_id}/retry")
async def retry_job(
    execution_id: ResourceId,
    job_id: ResourceId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: runtime(request).retry_job(
            organization_id=workspace_id,
            execution_id=execution_id,
            job_id=job_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
        )
    )


@router.get("/executions/{execution_id}/events")
async def list_runtime_events(
    execution_id: ResourceId,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "events": (
                request.app.state.workflow_control_service.identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                runtime(request).repository.list_events(
                    workspace_id,
                    execution_id,
                    limit,
                ),
            )[1]
        }
    )
