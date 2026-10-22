"""Standalone global intelligence API; engines are explicitly configured services."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vibe_visualization_api.crucix.client import CrucixClient
from vibe_visualization_api.crucix.routes import router as crucix_router
from vibe_visualization_api.global_topics.routes import router as topics_router
from vibe_visualization_api.global_topics.sources import TopicSources
from .client import GlobalIntelClient, GlobalIntelUnavailable
from .routes import router
from .runtime import Settings


def create_app(settings: Settings | None = None, frontend_dist: str | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Global Intelligence", version="0.1.0")
    app.state.global_intelligence_settings = settings
    if settings.world_intel_url:
        app.state.global_intel_client = GlobalIntelClient(settings.world_intel_url)
    crucix = CrucixClient(settings.crucix_url)
    app.state.crucix_reader = crucix.read

    async def crucix_snapshot():
        return await crucix.read("crucix.snapshot")

    async def maritime_snapshot():
        client = getattr(app.state, "global_intel_client", None)
        if client is None:
            raise GlobalIntelUnavailable("World Intelligence 数据源未配置")
        return await client.get_json("/api/maritime/warnings", timeout_seconds=15)

    app.state.global_topic_sources = TopicSources(
        tushare_token=settings.tushare_token.get_secret_value(),
        crucix_snapshot=crucix_snapshot,
        maritime_snapshot=maritime_snapshot,
    )
    for routes in (router, topics_router, crucix_router):
        app.include_router(routes)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "project": "global-intelligence", "agent": "host-only",
                "sources": {"worldIntelConfigured": bool(settings.world_intel_url), "crucixConfigured": bool(settings.crucix_url)}}

    if frontend_dist:
        directory = Path(frontend_dist).resolve(strict=True)
        if not (directory / "index.html").is_file():
            raise ValueError("frontend_dist must contain a built index.html")
        app.mount("/mods/global-intelligence", StaticFiles(directory=directory, html=True), name="desk-frontend")
        app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    return app


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Independent global intelligence runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18952)
    parser.add_argument("--frontend-dist")
    args = parser.parse_args()
    uvicorn.run(create_app(frontend_dist=args.frontend_dist), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
