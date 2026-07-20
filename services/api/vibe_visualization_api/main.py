import asyncio
import sqlite3
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vibe_visualization_api.agent_gateway.adapters.base import AgentAdapter
from vibe_visualization_api.agent_gateway.adapters.openai_compatible import (
    OpenAICompatibleAdapter,
)
from vibe_visualization_api.agent_gateway.event_bus import TaskEventBus
from vibe_visualization_api.agent_gateway.registry import (
    AgentAdapterRegistry,
    UnknownAgentAdapterError,
)
from vibe_visualization_api.agent_gateway.routes import router as agent_router
from vibe_visualization_api.agent_gateway.service import AgentTaskService
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskNotFoundError,
    TaskStore,
)
from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.repository import (
    InvalidModuleStateError,
    ModuleNotFoundError,
)
from vibe_visualization_api.control_plane.routes import router as modules_router
from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    MissingServiceSecret,
    UnknownServiceCapability,
    UnsafeServiceUrl,
    UnsupportedServiceTransport,
    UpstreamServiceError,
)
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import (
    DataServiceNotFoundError,
    DataServiceRegistry,
)
from vibe_visualization_api.data_services.routes import router as data_services_router


def create_app(
    settings: Settings | None = None,
    *,
    agent_adapters: Sequence[AgentAdapter] | None = None,
    data_services: Sequence[DataServiceDescriptor] | None = None,
    data_service_client: DataServiceClient | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configured_adapters = (
        list(agent_adapters)
        if agent_adapters is not None
        else [OpenAICompatibleAdapter(app_settings)]
    )
    adapter_registry = AgentAdapterRegistry(
        configured_adapters,
        default_id=app_settings.agent_default_adapter,
    )
    application = FastAPI(title="vibe-visualization API", version="0.1.0")
    application.dependency_overrides[get_settings] = lambda: app_settings
    application.state.agent_task_service = None
    application.state.agent_task_service_lock = asyncio.Lock()

    def create_agent_task_service() -> AgentTaskService:
        return AgentTaskService(
            TaskStore(app_settings.database_path),
            TaskEventBus(),
            adapter_registry,
        )

    application.state.agent_task_service_factory = create_agent_task_service
    application.state.data_service_registry = DataServiceRegistry(
        list(data_services or [])
    )
    application.state.data_service_client = data_service_client or DataServiceClient(
        public_mode=app_settings.data_service_public_mode
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.origin_list(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(modules_router)
    application.include_router(agent_router)
    application.include_router(data_services_router)

    @application.exception_handler(ModuleNotFoundError)
    async def module_not_found(
        request: Request, error: ModuleNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "module revision not found"}
        )

    @application.exception_handler(InvalidModuleStateError)
    async def invalid_module_state(
        request: Request, error: InvalidModuleStateError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "invalid module state"})

    @application.exception_handler(sqlite3.Error)
    async def database_error(request: Request, error: sqlite3.Error) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "database unavailable"},
        )

    @application.exception_handler(TaskNotFoundError)
    async def agent_task_not_found(
        request: Request, error: TaskNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "agent task not found"})

    @application.exception_handler(InvalidTaskStateError)
    async def invalid_agent_task_state(
        request: Request, error: InvalidTaskStateError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "invalid task state"})

    @application.exception_handler(UnknownAgentAdapterError)
    async def unknown_agent_adapter(
        request: Request, error: UnknownAgentAdapterError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "unknown agent adapter"},
        )

    @application.exception_handler(DataServiceNotFoundError)
    async def data_service_not_found(
        request: Request, error: DataServiceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "data service not found"}
        )

    @application.exception_handler(UnknownServiceCapability)
    async def data_service_capability_not_found(
        request: Request, error: UnknownServiceCapability
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "data service capability not found"},
        )

    @application.exception_handler(UnsafeServiceUrl)
    async def unsafe_data_service_url(
        request: Request, error: UnsafeServiceUrl
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "unsafe data service URL"},
        )

    @application.exception_handler(UnsupportedServiceTransport)
    async def unsupported_data_service_transport(
        request: Request, error: UnsupportedServiceTransport
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "unsupported data service transport"},
        )

    @application.exception_handler(MissingServiceSecret)
    async def missing_data_service_secret(
        request: Request, error: MissingServiceSecret
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "data service unavailable"},
        )

    @application.exception_handler(UpstreamServiceError)
    async def data_service_upstream_error(
        request: Request, error: UpstreamServiceError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": "data service upstream failed"},
        )

    async def shutdown_agent_gateway() -> None:
        service = application.state.agent_task_service
        if service is not None:
            await service.shutdown()

    application.router.add_event_handler("shutdown", shutdown_agent_gateway)

    @application.get("/api/health")
    def health() -> dict[str, bool | str]:
        return {
            "ok": True,
            "service": "vibe-visualization-api",
            "version": "0.1.0",
        }

    return application


app = create_app()
