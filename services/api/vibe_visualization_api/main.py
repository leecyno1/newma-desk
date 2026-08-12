import asyncio
import sqlite3
from collections.abc import Sequence
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vibe_visualization_api.artifacts.archify import (
    ArchifyRenderer,
    ArtifactRenderError,
)
from vibe_visualization_api.artifacts.routes import router as artifacts_router
from vibe_visualization_api.artifacts.store import (
    ArtifactNotFoundError,
    ArtifactStore,
    CorruptArtifactError,
)
from vibe_visualization_api.agent_gateway.adapters.base import AgentAdapter
from vibe_visualization_api.agent_gateway.adapters.hermes_webui import (
    HermesWebUIAdapter,
)
from vibe_visualization_api.agent_gateway.adapters.local_cli import (
    LocalCliAgentAdapter,
)
from vibe_visualization_api.agent_gateway.conversation_store import (
    AgentConversationStore,
)
from vibe_visualization_api.agent_gateway.event_bus import TaskEventBus
from vibe_visualization_api.agent_gateway.registry import (
    AgentAdapterRegistry,
    UnknownAgentAdapterError,
)
from vibe_visualization_api.agent_gateway.routes import router as agent_router
from vibe_visualization_api.agent_gateway.preferences import AgentPreferenceStore
from vibe_visualization_api.agent_gateway.service import AgentTaskService
from vibe_visualization_api.agent_gateway.session_store import (
    AgentModuleSessionStore,
)
from vibe_visualization_api.ai_context.finance_capabilities import (
    FinanceCapabilityContextEnricher,
)
from vibe_visualization_api.ai_context.light_research import (
    LightResearchContextEnricher,
)
from vibe_visualization_api.agent_gateway.store import (
    InvalidTaskStateError,
    TaskNotFoundError,
    TaskStore,
)
from vibe_visualization_api.config import (
    Settings,
    get_settings,
    resolve_database_path,
)
from vibe_visualization_api.model_gateway.adapters.base import ModelAdapter
from vibe_visualization_api.model_gateway.adapters.anthropic import (
    AnthropicModelAdapter,
)
from vibe_visualization_api.model_gateway.adapters.openai_compatible import (
    OpenAICompatibleModelAdapter,
)
from vibe_visualization_api.model_gateway.errors import ModelGatewayError
from vibe_visualization_api.model_gateway.registry import (
    ModelAdapterRegistry,
    UnknownModelAdapterError,
)
from vibe_visualization_api.model_gateway.routes import router as model_router
from vibe_visualization_api.model_gateway.service import ModelGatewayService
from vibe_visualization_api.market_alerts.routes import router as market_alerts_router
from vibe_visualization_api.market_alerts.store import (
    MarketAlertLimitError,
    MarketAlertNotFoundError,
    MarketAlertStore,
)
from vibe_visualization_api.mod_store.routes import router as mod_store_router
from vibe_visualization_api.mod_store.service import (
    DescriptorFetcher,
    ModStoreService,
)
from vibe_visualization_api.mod_storage.routes import router as mod_storage_router
from vibe_visualization_api.mod_storage.store import (
    ModStorageConflictError,
    ModStorageCorruptError,
    ModStorageNotFoundError,
    ModStorageQuotaError,
    ModStorageStore,
)
from vibe_visualization_api.portfolio_center.quotes import (
    PortfolioQuoteProvider,
    ResearchPortfolioQuoteProvider,
)
from vibe_visualization_api.portfolio_center.history import (
    DataServicePortfolioHistoryProvider,
)
from vibe_visualization_api.portfolio_center.routes import (
    router as portfolio_center_router,
)
from vibe_visualization_api.portfolio_center.service import PortfolioCenterService
from vibe_visualization_api.research_archive.routes import (
    router as research_archive_router,
)
from vibe_visualization_api.research_archive.service import ResearchArchiveService
from vibe_visualization_api.portfolio_center.store import (
    PortfolioConflictError,
    PortfolioNotFoundError,
    PortfolioStore,
)
from vibe_visualization_api.control_plane.repository import (
    InvalidModuleStateError,
    ModuleRepository,
    ModuleNotFoundError,
)
from vibe_visualization_api.control_plane.routes import router as mods_router
from vibe_visualization_api.control_plane.actions import TradeConfirmationService
from vibe_visualization_api.control_plane.context_store import ModContextStore
from vibe_visualization_api.control_plane.sessions import ModSessionService
from vibe_visualization_api.data_services.client import (
    DataServiceClient,
    MissingServiceSecret,
    UnknownServiceCapability,
    UnsafeServiceUrl,
    UnsupportedServiceTransport,
    UpstreamServiceError,
)
from vibe_visualization_api.data_services.discovery import discover_data_services
from vibe_visualization_api.data_services.models import DataServiceDescriptor
from vibe_visualization_api.data_services.registry import (
    DataCapabilityNotFoundError,
    DataServiceNotFoundError,
    DataServiceRegistry,
    PreferredDataServiceUnavailable,
)
from vibe_visualization_api.data_services.preferences import DataServicePreferenceStore
from vibe_visualization_api.domain_suites import SpaStaticFiles, mount_domain_suites
from vibe_visualization_api.data_services.market import VibeResearchMarketClient
from vibe_visualization_api.data_services.routes import router as data_services_router
from vibe_visualization_api.finance_pilots.adapters import (
    DailyStockAnalysisAdapter,
    PilotPayloadError,
    QuantDingerAdapter,
)
from vibe_visualization_api.finance_pilots.policy import FinancePilotPolicy
from vibe_visualization_api.finance_pilots.routes import router as finance_pilots_router
from vibe_visualization_api.finance_pilots.service import (
    FinancePilotActivationError,
    FinancePilotNotFoundError,
    FinancePilotService,
)
from vibe_visualization_api.global_intel.client import GlobalIntelClient
from vibe_visualization_api.global_intel.routes import router as global_intel_router
from vibe_visualization_api.scheduler.service import (
    RefreshSchedulerService,
    SchedulerLifecycle,
)
from vibe_visualization_api.scheduler.store import SchedulerStore
from vibe_visualization_api.snapshots.routes import router as mod_snapshots_router
from vibe_visualization_api.snapshots.store import SnapshotNotFoundError, SnapshotStore
from vibe_visualization_api.schema_validation import JsonContractError
from vibe_visualization_api.watchlists.routes import router as watchlists_router
from vibe_visualization_api.watchlists.store import (
    WatchlistConflictError,
    WatchlistNotFoundError,
    WatchlistStore,
)


def create_app(
    settings: Settings | None = None,
    *,
    agent_adapters: Sequence[AgentAdapter] | None = None,
    model_adapters: Sequence[ModelAdapter] | None = None,
    data_services: Sequence[DataServiceDescriptor] | None = None,
    data_service_client: DataServiceClient | None = None,
    scheduler_service: SchedulerLifecycle | None = None,
    mod_store_fetcher: DescriptorFetcher | None = None,
    portfolio_quote_provider: PortfolioQuoteProvider | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    resolved_database_path = resolve_database_path(app_settings.database_path)
    if resolved_database_path != app_settings.database_path:
        app_settings = app_settings.model_copy(
            update={"database_path": resolved_database_path}
        )
    agent_session_store = AgentModuleSessionStore(app_settings.database_path)
    agent_conversation_store = AgentConversationStore(app_settings.database_path)
    agent_preference_store = AgentPreferenceStore(app_settings.database_path)
    mod_context_store = ModContextStore(app_settings.database_path)
    mod_storage_store = ModStorageStore(app_settings.database_path)
    mod_store_service = ModStoreService(
        app_settings,
        descriptor_fetcher=mod_store_fetcher,
    )
    configured_adapters = (
        list(agent_adapters)
        if agent_adapters is not None
        else [
            LocalCliAgentAdapter(
                "codex",
                app_settings,
                agent_conversation_store,
                workspace_resolver=mod_store_service.resolve_agent_workspace,
            ),
            LocalCliAgentAdapter(
                "claude",
                app_settings,
                agent_conversation_store,
                workspace_resolver=mod_store_service.resolve_agent_workspace,
            ),
            LocalCliAgentAdapter(
                "gemini",
                app_settings,
                agent_conversation_store,
                workspace_resolver=mod_store_service.resolve_agent_workspace,
            ),
            HermesWebUIAdapter(
                app_settings,
                agent_session_store,
            )
        ]
    )
    adapter_registry = AgentAdapterRegistry(
        configured_adapters,
        default_id=app_settings.agent_default_adapter,
    )
    configured_model_adapters = (
        list(model_adapters)
        if model_adapters is not None
        else [
            OpenAICompatibleModelAdapter(app_settings),
            AnthropicModelAdapter(app_settings),
        ]
    )
    model_adapter_registry = ModelAdapterRegistry(
        configured_model_adapters,
        default_id=app_settings.model_default_adapter,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        domain_suites = application.state.domain_suites
        await domain_suites.startup()
        active_scheduler = application.state.scheduler_service
        if app_settings.enable_scheduler:
            if active_scheduler is None:
                active_scheduler = application.state.scheduler_service_factory()
                application.state.scheduler_service = active_scheduler
            await active_scheduler.start()
        try:
            yield
        finally:
            if app_settings.enable_scheduler and active_scheduler is not None:
                await active_scheduler.stop()
            agent_service = application.state.agent_task_service
            if agent_service is not None:
                await agent_service.shutdown()
            await domain_suites.shutdown()

    application = FastAPI(
        title="Newma-Desk API",
        description=(
            "Data, Mod, Model Gateway and Agent Gateway services for Newma-Desk."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    application.dependency_overrides[get_settings] = lambda: app_settings
    application.state.agent_task_service = None
    application.state.agent_task_service_lock = asyncio.Lock()
    application.state.domain_suites = None
    application.state.module_repository = None
    application.state.module_repository_lock = Lock()

    def resolve_module_repository() -> ModuleRepository:
        repository = application.state.module_repository
        if repository is not None:
            return repository
        with application.state.module_repository_lock:
            repository = application.state.module_repository
            if repository is None:
                repository = ModuleRepository(app_settings.database_path)
                application.state.module_repository = repository
        return repository

    application.state.resolve_module_repository = resolve_module_repository

    def create_agent_task_service() -> AgentTaskService:
        return AgentTaskService(
            TaskStore(app_settings.database_path),
            TaskEventBus(),
            adapter_registry,
            SnapshotStore(
                app_settings.runtime_dir,
                app_settings.database_path,
            ),
            agent_preference_store,
            mod_context_store,
            research_enricher=LightResearchContextEnricher(
                application.state.data_service_registry,
                application.state.data_service_client,
            ),
            finance_capability_enricher=FinanceCapabilityContextEnricher(
                app_settings.finance_project_intake_descriptor,
                resolve_module_repository,
            ),
        )

    application.state.agent_task_service_factory = create_agent_task_service
    application.state.model_gateway_service = ModelGatewayService(
        model_adapter_registry,
        snapshot_store_factory=lambda: SnapshotStore(
            app_settings.runtime_dir,
            app_settings.database_path,
        ),
    )
    application.state.scheduler_service = scheduler_service
    application.state.scheduler_service_lock = asyncio.Lock()

    def create_scheduler_service() -> RefreshSchedulerService:
        return RefreshSchedulerService(
            store=SchedulerStore(app_settings.database_path),
            repository=resolve_module_repository(),
            snapshot_store=SnapshotStore(
                app_settings.runtime_dir,
                app_settings.database_path,
            ),
            market_client=VibeResearchMarketClient(
                app_settings.research_base_url,
                api_key=app_settings.research_api_key.get_secret_value(),
            ),
            poll_seconds=app_settings.scheduler_poll_seconds,
        )

    application.state.scheduler_service_factory = create_scheduler_service
    configured_data_services = (
        list(data_services)
        if data_services is not None
        else discover_data_services(
            app_settings.data_service_paths(),
            base_url_overrides={
                "market-data": app_settings.research_base_url,
                "instock-analysis": f"{app_settings.instock_web_url}/api/v1",
                "world-intel": app_settings.world_intel_url,
            },
        )
    )
    data_service_registry = DataServiceRegistry(configured_data_services)
    resolved_data_service_client = data_service_client or DataServiceClient(
        public_mode=app_settings.data_service_public_mode
    )
    application.state.data_service_registry = data_service_registry
    application.state.data_service_client = resolved_data_service_client
    application.state.global_intel_client = GlobalIntelClient(
        app_settings.world_intel_url
    )
    application.state.data_service_preference_store = DataServicePreferenceStore(
        app_settings.database_path
    )
    application.state.trade_confirmation_service = TradeConfirmationService(
        app_settings.trade_confirmation_secret.get_secret_value()
    )
    application.state.mod_session_service = ModSessionService(
        app_settings.mod_session_secret.get_secret_value(),
        ttl_seconds=app_settings.mod_session_ttl_seconds,
    )
    application.state.mod_context_store = mod_context_store
    application.state.mod_storage_store = mod_storage_store
    application.state.mod_store_service = mod_store_service
    application.state.artifact_store = ArtifactStore(app_settings.runtime_dir)
    application.state.archify_renderer = ArchifyRenderer(
        app_settings.archify_root,
        node_binary=app_settings.node_binary,
    )
    application.state.watchlist_store = WatchlistStore(
        app_settings.database_path,
    )
    application.state.market_alert_store = MarketAlertStore(
        app_settings.database_path,
    )
    application.state.research_archive_service = ResearchArchiveService(
        mod_storage_store,
    )
    application.state.finance_pilot_service = FinancePilotService(
        FinancePilotPolicy(
            app_settings.external_finance_pilot_descriptor,
            project_root=app_settings.workspace_root,
        ),
        [DailyStockAnalysisAdapter(), QuantDingerAdapter()],
    )
    application.state.portfolio_center_service = PortfolioCenterService(
        PortfolioStore(app_settings.database_path),
        quote_provider=(
            portfolio_quote_provider
            or ResearchPortfolioQuoteProvider(
                app_settings.research_base_url,
                api_key=app_settings.research_api_key.get_secret_value(),
                timeout_seconds=app_settings.portfolio_quote_timeout_seconds,
            )
        ),
        history_provider=DataServicePortfolioHistoryProvider(
            data_service_registry,
            resolved_data_service_client,
        ),
        legacy_portfolio_path=app_settings.legacy_portfolio_path,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.origin_list(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-User-Id",
            "X-Workspace-Id",
            "X-Newma-Desk-Instance-Id",
            "X-Newma-Desk-Mod-Session",
            "X-Newma-Dock-Instance-Id",
        ],
    )
    application.include_router(mods_router, prefix="/api/mods")
    application.include_router(
        mods_router,
        prefix="/api/modules",
        include_in_schema=False,
    )
    application.include_router(mod_storage_router, prefix="/api/mods")
    application.include_router(
        mod_storage_router,
        prefix="/api/modules",
        include_in_schema=False,
    )
    application.include_router(agent_router)
    application.include_router(mod_store_router)
    application.include_router(model_router)
    application.include_router(data_services_router)
    application.include_router(artifacts_router)
    application.include_router(watchlists_router)
    application.include_router(market_alerts_router)
    application.include_router(research_archive_router)
    application.include_router(portfolio_center_router)
    application.include_router(finance_pilots_router)
    application.include_router(global_intel_router)
    application.include_router(mod_snapshots_router, prefix="/api/mods")
    application.include_router(
        mod_snapshots_router,
        prefix="/api/modules",
        include_in_schema=False,
    )

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

    @application.exception_handler(ModStorageNotFoundError)
    async def mod_storage_not_found(
        request: Request,
        error: ModStorageNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "Mod storage document not found"},
        )

    @application.exception_handler(ModStorageConflictError)
    async def mod_storage_conflict(
        request: Request,
        error: ModStorageConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Mod storage revision conflict"},
        )

    @application.exception_handler(ModStorageQuotaError)
    async def mod_storage_quota(
        request: Request,
        error: ModStorageQuotaError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"detail": "Mod storage quota exceeded"},
        )

    @application.exception_handler(ModStorageCorruptError)
    async def mod_storage_corrupt(
        request: Request,
        error: ModStorageCorruptError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Mod storage document is corrupt"},
        )

    @application.exception_handler(SnapshotNotFoundError)
    async def snapshot_not_found(
        request: Request, error: SnapshotNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "module snapshot not found"},
        )

    @application.exception_handler(ArtifactNotFoundError)
    async def artifact_not_found(
        request: Request, error: ArtifactNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "artifact not found"})

    @application.exception_handler(CorruptArtifactError)
    async def corrupt_artifact(
        request: Request, error: CorruptArtifactError
    ) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "artifact is corrupt"})

    @application.exception_handler(ArtifactRenderError)
    async def artifact_render_failed(
        request: Request, error: ArtifactRenderError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": str(error)},
        )

    @application.exception_handler(WatchlistConflictError)
    async def watchlist_conflict(
        request: Request,
        error: WatchlistConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(WatchlistNotFoundError)
    async def watchlist_not_found(
        request: Request,
        error: WatchlistNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(MarketAlertNotFoundError)
    async def market_alert_not_found(
        request: Request,
        error: MarketAlertNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(MarketAlertLimitError)
    async def market_alert_limit(
        request: Request,
        error: MarketAlertLimitError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(PortfolioConflictError)
    async def portfolio_conflict(
        request: Request,
        error: PortfolioConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(PortfolioNotFoundError)
    async def portfolio_not_found(
        request: Request,
        error: PortfolioNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(FinancePilotNotFoundError)
    async def finance_pilot_not_found(
        request: Request,
        error: FinancePilotNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "finance pilot not found"},
        )

    @application.exception_handler(FinancePilotActivationError)
    async def finance_pilot_activation_blocked(
        request: Request,
        error: FinancePilotActivationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "finance_pilot_activation_blocked",
                    "message": "finance pilot activation is blocked",
                    "pilotId": error.pilot_id,
                    "reasons": error.reasons,
                }
            },
        )

    @application.exception_handler(PilotPayloadError)
    async def invalid_finance_pilot_payload(
        request: Request,
        error: PilotPayloadError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": str(error)},
        )

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

    @application.exception_handler(UnknownModelAdapterError)
    async def unknown_model_adapter(
        request: Request, error: UnknownModelAdapterError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "unknown model adapter"},
        )

    @application.exception_handler(ModelGatewayError)
    async def model_gateway_error(
        request: Request, error: ModelGatewayError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                }
            },
        )

    @application.exception_handler(DataServiceNotFoundError)
    async def data_service_not_found(
        request: Request, error: DataServiceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "data service not found"}
        )

    @application.exception_handler(DataCapabilityNotFoundError)
    async def data_capability_not_found(
        request: Request, error: DataCapabilityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "data capability not found"},
        )

    @application.exception_handler(PreferredDataServiceUnavailable)
    async def preferred_data_service_unavailable(
        request: Request, error: PreferredDataServiceUnavailable
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "preferred data provider is unavailable"},
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

    @application.exception_handler(JsonContractError)
    async def json_contract_error(
        request: Request, error: JsonContractError
    ) -> JSONResponse:
        status_code = 422 if error.direction == "input" else 502
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": f"schema_{error.direction}_invalid",
                    "message": str(error),
                }
            },
        )

    @application.get("/api/health")
    def health() -> dict[str, bool | str]:
        return {
            "ok": True,
            "service": "newma-desk-api",
            "version": "0.1.0",
        }

    portfolio_center_dist = app_settings.portfolio_center_dist.expanduser().resolve()
    if portfolio_center_dist.is_dir():
        application.mount(
            "/mod-runtime/portfolio-center",
            SpaStaticFiles(directory=str(portfolio_center_dist), html=True),
            name="portfolio-center-mod-runtime",
        )

    application.state.domain_suites = mount_domain_suites(
        application,
        app_settings,
    )

    return application


app = create_app()
