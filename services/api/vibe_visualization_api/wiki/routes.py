from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.data_services.client import DataServiceClient
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.wiki.models import (
    WikiHandoffCreate,
    WikiHandoffResponse,
    WikiLinkResolutionRequest,
    WikiLinkResolutionResponse,
    WikiModProfileResponse,
    WikiSubjectMatch,
)
from vibe_visualization_api.wiki.service import (
    WikiEntrypointUnavailableError,
    WikiModuleNotFoundError,
    WikiService,
)
from vibe_visualization_api.wiki.store import (
    WikiHandoffNotFoundError,
    WikiHandoffStore,
    WikiSubjectStore,
)


router = APIRouter(prefix="/api/wiki", tags=["wiki"])
HandoffId = Annotated[str, Path(pattern=r"^hf_[A-Za-z0-9_-]{8,120}$")]


def get_repository(request: Request) -> ModuleRepository:
    return request.app.state.resolve_module_repository()


def get_data_registry(request: Request) -> DataServiceRegistry:
    return request.app.state.data_service_registry


def get_data_client(request: Request) -> DataServiceClient:
    return request.app.state.data_service_client


def get_handoff_store(request: Request) -> WikiHandoffStore:
    return request.app.state.wiki_handoff_store


def get_subject_store(request: Request) -> WikiSubjectStore:
    return request.app.state.wiki_subject_store


def get_wiki_service(
    repository: ModuleRepository = Depends(get_repository),
    data_registry: DataServiceRegistry = Depends(get_data_registry),
    data_client: DataServiceClient = Depends(get_data_client),
    handoff_store: WikiHandoffStore = Depends(get_handoff_store),
    subject_store: WikiSubjectStore = Depends(get_subject_store),
) -> WikiService:
    return WikiService(
        repository,
        data_registry,
        data_client,
        handoff_store,
        subject_store,
    )


@router.get("/subjects", response_model=list[WikiSubjectMatch])
async def search_subjects(
    query: str = Query(min_length=1, max_length=80),
    subject_type: str | None = Query(
        default=None,
        alias="type",
        pattern="^(security|etf|fund|company|industry|concept|event|topic)$",
    ),
    market: str | None = Query(default=None, pattern="^(CN|HK|US)$"),
    limit: int = Query(default=12, ge=1, le=30),
    service: WikiService = Depends(get_wiki_service),
) -> list[WikiSubjectMatch]:
    return await service.search_subjects(
        query,
        subject_type=subject_type,
        market=market,
        limit=limit,
    )


@router.get("/mod-profiles", response_model=list[WikiModProfileResponse])
async def list_mod_profiles(
    service: WikiService = Depends(get_wiki_service),
) -> list[WikiModProfileResponse]:
    return await run_in_threadpool(service.list_mod_profiles)


@router.post(
    "/link-resolutions",
    response_model=WikiLinkResolutionResponse,
)
async def resolve_links(
    resolution: WikiLinkResolutionRequest,
    service: WikiService = Depends(get_wiki_service),
) -> WikiLinkResolutionResponse:
    try:
        return await run_in_threadpool(service.resolve_links, resolution)
    except WikiModuleNotFoundError as error:
        raise HTTPException(404, "source Mod is not available") from error


@router.post(
    "/handoffs",
    status_code=201,
    response_model=WikiHandoffResponse,
    response_model_exclude_none=True,
)
async def create_handoff(
    handoff: WikiHandoffCreate,
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(default="local-workspace", alias="X-Workspace-Id"),
    service: WikiService = Depends(get_wiki_service),
) -> dict[str, object]:
    try:
        created = await run_in_threadpool(
            service.create_handoff,
            user_id=user_id,
            workspace_id=workspace_id,
            request=handoff,
        )
    except WikiModuleNotFoundError as error:
        raise HTTPException(404, "source or target Mod is not available") from error
    except WikiEntrypointUnavailableError as error:
        raise HTTPException(422, str(error)) from error
    return created.model_dump(by_alias=True, mode="json")


@router.get(
    "/handoffs/{handoff_id}",
    response_model=WikiHandoffResponse,
    response_model_exclude_none=True,
)
async def get_handoff(
    handoff_id: HandoffId,
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(default="local-workspace", alias="X-Workspace-Id"),
    store: WikiHandoffStore = Depends(get_handoff_store),
) -> dict[str, object]:
    try:
        handoff = await run_in_threadpool(
            store.get,
            handoff_id=handoff_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WikiHandoffNotFoundError as error:
        raise HTTPException(404, "Wiki handoff is not available") from error
    return handoff.model_dump(by_alias=True, mode="json")


@router.delete("/handoffs/{handoff_id}", status_code=204)
async def delete_handoff(
    handoff_id: HandoffId,
    user_id: str = Header(default="local-user", alias="X-User-Id"),
    workspace_id: str = Header(default="local-workspace", alias="X-Workspace-Id"),
    store: WikiHandoffStore = Depends(get_handoff_store),
) -> Response:
    try:
        await run_in_threadpool(
            store.delete,
            handoff_id=handoff_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    except WikiHandoffNotFoundError as error:
        raise HTTPException(404, "Wiki handoff is not available") from error
    return Response(status_code=204)
