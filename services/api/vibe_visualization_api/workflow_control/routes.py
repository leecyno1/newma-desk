from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.workflow_control.models import (
    DelegationGrantCreate,
    NodeAssignmentInput,
    NodeClaimInput,
    NodeDataCreate,
    NodeReviewInput,
    NodeRevisionInput,
    NodeSubmitInput,
    WorkflowArtifactCreate,
    WorkflowPrincipalCreate,
    WorkflowRunCreate,
    WorkflowTemplateCreate,
    WorkflowTemplateRestore,
    WorkflowTemplateVersionCreate,
)
from vibe_visualization_api.workflow_control.service import (
    WorkflowAuthorizationError,
    WorkflowClaimConflictError,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowValidationError,
)


router = APIRouter(prefix="/api/workflows", tags=["workflows"])

UserId = Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)]
WorkspaceId = Annotated[
    str,
    Header(alias="X-Workspace-Id", min_length=1, max_length=128),
]
ActingPrincipalId = Annotated[
    str | None,
    Header(alias="X-Workflow-Principal-Id", max_length=128),
]
WorkflowId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$"),
]
PrincipalPathId = Annotated[
    str,
    Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9:_-]{2,127}$"),
]
VersionId = Annotated[int, Path(ge=1)]


async def execute(call: Callable[[], Any]) -> Any:
    try:
        return await run_in_threadpool(call)
    except WorkflowNotFoundError as error:
        raise HTTPException(404, "Workflow resource not found") from error
    except WorkflowAuthorizationError as error:
        raise HTTPException(403, str(error)) from error
    except (WorkflowConflictError, WorkflowClaimConflictError) as error:
        raise HTTPException(409, str(error)) from error
    except (WorkflowValidationError, ValidationError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


def service(request: Request):
    return request.app.state.workflow_control_service


def actor(
    request: Request,
    *,
    user_id: str,
    workspace_id: str,
    acting_principal_id: str | None,
) -> dict[str, Any]:
    return service(request).identity(
        organization_id=workspace_id,
        user_id=user_id,
        acting_principal_id=acting_principal_id,
    )


@router.get("/overview")
async def overview(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).overview(
            organization_id=workspace_id,
            user_id=user_id,
            acting_principal_id=acting_principal_id,
        )
    )


@router.get("/principals")
async def list_principals(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "principals": (
                service(request).identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                service(request).repository.list_principals(workspace_id),
            )[1]
        }
    )


@router.post("/principals", status_code=status.HTTP_201_CREATED)
async def create_principal(
    payload: WorkflowPrincipalCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).create_principal(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            request=payload,
        )
    )


@router.get("/templates")
async def list_templates(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "templates": (
                service(request).overview(
                    organization_id=workspace_id,
                    user_id=user_id,
                )["templates"]
            )
        }
    )


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: WorkflowTemplateCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).create_template(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            request=payload,
        )
    )


@router.get("/templates/{template_id}")
async def get_template(
    template_id: WorkflowId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: (
            service(request).identity(
                organization_id=workspace_id,
                user_id=user_id,
            ),
            service(request).repository.get_template(workspace_id, template_id),
        )[1]
    )


@router.post("/templates/{template_id}/versions")
async def create_template_version(
    template_id: WorkflowId,
    payload: WorkflowTemplateVersionCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).add_template_version(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            template_id=template_id,
            request=payload,
        )
    )


@router.get("/templates/{template_id}/versions")
async def list_template_versions(
    template_id: WorkflowId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: {
            "versions": service(request).list_template_versions(
                organization_id=workspace_id,
                actor_principal_id=actor(
                    request,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    acting_principal_id=acting_principal_id,
                )["id"],
                template_id=template_id,
            )
        }
    )


@router.post("/templates/{template_id}/versions/{source_version}/restore")
async def restore_template_version(
    template_id: WorkflowId,
    source_version: VersionId,
    payload: WorkflowTemplateRestore,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).restore_template_version(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            template_id=template_id,
            source_version=source_version,
            request=payload,
        )
    )


@router.get("/runs")
async def list_runs(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "runs": (
                service(request).identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                service(request).repository.list_runs(workspace_id),
            )[1]
        }
    )


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: WorkflowRunCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).create_run(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            request=payload,
        )
    )


@router.get("/runs/{run_id}")
async def get_run(
    run_id: WorkflowId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: (
            service(request).identity(
                organization_id=workspace_id,
                user_id=user_id,
            ),
            service(request).run_snapshot(workspace_id, run_id),
        )[1]
    )


@router.post("/runs/{run_id}/nodes/{node_id}/claim")
async def claim_node(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeClaimInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).claim_node(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.post("/runs/{run_id}/nodes/{node_id}/release")
async def release_node(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeRevisionInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).release_node(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            expected_revision=payload.expected_revision,
        )
    )


@router.post("/runs/{run_id}/nodes/{node_id}/data")
async def save_node_data(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeDataCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).save_node_data(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.post("/runs/{run_id}/nodes/{node_id}/artifacts")
async def save_artifact(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: WorkflowArtifactCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).save_artifact(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.post("/runs/{run_id}/nodes/{node_id}/submit")
async def submit_node(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeSubmitInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).submit_node(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.post("/runs/{run_id}/nodes/{node_id}/review")
async def review_node(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeReviewInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).review_node(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.put("/runs/{run_id}/nodes/{node_id}/assignment")
async def assign_node(
    run_id: WorkflowId,
    node_id: WorkflowId,
    payload: NodeAssignmentInput,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).assign_node(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            run_id=run_id,
            node_id=node_id,
            request=payload,
        )
    )


@router.get("/grants")
async def list_grants(
    request: Request,
    principal_id: Annotated[str | None, Query(alias="principalId")] = None,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "grants": (
                service(request).identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                service(request).repository.list_grants(
                    workspace_id, principal_id=principal_id
                ),
            )[1]
        }
    )


@router.post("/grants", status_code=status.HTTP_201_CREATED)
async def create_grant(
    payload: DelegationGrantCreate,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).create_grant(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            request=payload,
        )
    )


@router.delete("/grants/{grant_id}")
async def revoke_grant(
    grant_id: WorkflowId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
    acting_principal_id: ActingPrincipalId = None,
):
    return await execute(
        lambda: service(request).revoke_grant(
            organization_id=workspace_id,
            actor_principal_id=actor(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                acting_principal_id=acting_principal_id,
            )["id"],
            grant_id=grant_id,
        )
    )


@router.get("/authority/{principal_id}")
async def effective_authority(
    principal_id: PrincipalPathId,
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: (
            service(request).identity(
                organization_id=workspace_id,
                user_id=user_id,
            ),
            service(request).effective_authority(
                organization_id=workspace_id,
                principal_id=principal_id,
            ),
        )[1]
    )


@router.get("/artifacts")
async def list_artifacts(
    request: Request,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "artifacts": (
                service(request).identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                service(request).artifacts(workspace_id),
            )[1]
        }
    )


@router.get("/events")
async def list_events(
    request: Request,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    user_id: UserId = "local-user",
    workspace_id: WorkspaceId = "local-workspace",
):
    return await execute(
        lambda: {
            "events": (
                service(request).identity(
                    organization_id=workspace_id,
                    user_id=user_id,
                ),
                service(request).events(
                    workspace_id,
                    run_id=run_id,
                    limit=limit,
                ),
            )[1]
        }
    )
