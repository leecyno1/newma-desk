from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vibe_visualization_api.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(title="vibe-visualization API", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.origin_list(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
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
