"""Standalone global intelligence API; engines are explicitly configured services."""
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vibe_visualization_api.crucix.client import CrucixClient
from vibe_visualization_api.crucix.routes import router as crucix_router
from vibe_visualization_api.global_topics.routes import router as topics_router
from vibe_visualization_api.global_topics.sources import TopicSources
from .client import GlobalIntelClient, GlobalIntelUnavailable
from .routes import router
from .runtime import Settings
from .release import process_release
from .access import DeskScopeResolver, guard_stream, reject_desk_session_in_local_mode


_INSTANCE = {"id": str(uuid4()), "started_at": datetime.now(timezone.utc).isoformat()}


def create_app(settings: Settings | None = None, frontend_dist: str | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Global Intelligence", version="0.1.0")
    app.state.global_intelligence_settings = settings
    authorizer = (DeskScopeResolver(settings.desk_scope_url) if settings.access_mode == "desk"
                  else reject_desk_session_in_local_mode)
    app.state.global_read_authorizer = authorizer
    app.state.global_topic_authorizer = authorizer
    app.state.global_stream_guard = lambda request, chunks: guard_stream(request, chunks, authorizer)
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
        return {"ok": True, "service": "newma-global-intelligence", "project": "global-intelligence", "agent": "host-only",
                "accessMode": settings.access_mode,
                "release": process_release(), "runtime": {"instance": dict(_INSTANCE)},
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
    state_mode = parser.add_mutually_exclusive_group()
    state_mode.add_argument("--check-state", action="store_true", help="只读检查显式数据库，不启动服务或初始化")
    state_mode.add_argument("--initialize-state", action="store_true", help="仅创建全新的空独立库；父目录须存在，不覆盖或迁移")
    state_mode.add_argument("--require-existing-state", action="store_true", help="启动前要求完整的独立领域库，不创建空库")
    args = parser.parse_args()
    settings = Settings()
    if args.check_state or args.initialize_state or args.require_existing_state:
        import json
        import sqlite3
        from .state import initialize_state, inspect_state
        if "database_path" not in settings.model_fields_set or not settings.database_path.is_absolute():
            parser.error("必须显式配置 GLOBAL_INTELLIGENCE_DATABASE_PATH 绝对路径")
        if args.initialize_state:
            try:
                initialize_state(settings.database_path)
            except FileExistsError:
                parser.error("目标已存在；不会覆盖、迁移或认领旧记录")
            except (OSError, sqlite3.Error) as error:
                parser.error(f"初始化未完成（{type(error).__name__}）；请检查父目录及写入权限，用 --check-state 核实目标状态")
        state = inspect_state(settings.database_path)
        ready = state["status"] == "ready" and state["dedicated"] is True
        if args.check_state or args.initialize_state:
            print(json.dumps(state, ensure_ascii=False))
            parser.exit(0 if ready else 2)
        if not ready:
            parser.error("业务库缺失、不完整或包含其他项目数据；请先确认归属，未创建或迁移数据库")
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("仅支持本机监听；远程入口须由受控宿主提供")
    uvicorn.run(create_app(settings, frontend_dist=args.frontend_dist), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
