import sqlite3

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.control_plane.repository import (
    InvalidModuleStateError,
    ModuleNotFoundError,
)
from vibe_visualization_api.control_plane.routes import router as modules_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(title="vibe-visualization API", version="0.1.0")
    application.dependency_overrides[get_settings] = lambda: app_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.origin_list(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(modules_router)

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
        return JSONResponse(
            status_code=409, content={"detail": "invalid module state"}
        )

    @application.exception_handler(sqlite3.Error)
    async def module_repository_error(
        request: Request, error: sqlite3.Error
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "module repository unavailable"},
        )

    @application.get("/api/health")
    def health() -> dict[str, bool | str]:
        return {
            "ok": True,
            "service": "vibe-visualization-api",
            "version": "0.1.0",
        }

    return application


app = create_app()
