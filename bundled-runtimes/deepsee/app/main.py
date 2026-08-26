from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response, JSONResponse
from .db import init_db
from .background import start_background_loops, stop_background_loops
from .routers import health, messages, chats, contacts, ai, send, hooks, configs, sync, reports, compat, market, email, extensions, news, folo, minutes, tools, media, mp_rss, tasks, recorder, admin, invitations, agent_api, contact_scoring, wechat_gateway, collector_api
from .db import SessionLocal
from .models import Message
from .config import settings
import orjson
import os


VIBEDESK_EMBED_MODULES = frozenset(
    {
        "dashboard",
        "ai-summary",
        "news-agg",
        "message-list",
        "email-messages",
        "minutes-agg",
        "folo-agg",
        "mp-agg",
        "send-management",
        "contact-management",
        "function-settings",
    }
)


def _api_token_auth_enabled() -> bool:
    # Deepsee is now deployed as a private workspace app without a project-level
    # login gate by default. Cloud deployments can enable API_TOKEN protection
    # with API_AUTH_REQUIRED=true while keeping local desktop use frictionless.
    return bool(getattr(settings, "API_AUTH_REQUIRED", False))


def _configured_api_tokens() -> set[str]:
    token = str(getattr(settings, "API_TOKEN", "") or "").strip()
    return {token} if token else set()


def _extract_api_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.headers.get("x-api-token") or "").strip()


def _is_api_auth_exempt_path(path: str) -> bool:
    if not path.startswith("/api"):
        return True
    if path in {"/api/health", "/api/ready", "/api/access/verify", "/api/wechat-gateway/callback"}:
        return True
    if path.startswith("/api/agent"):
        return True
    return False


def _cors_options() -> dict | None:
    env = str(getattr(settings, "APP_ENV", "development") or "development").strip().lower()
    raw_origins = str(getattr(settings, "CORS_ALLOW_ORIGINS", "") or "").strip()
    if env in {"dev", "development", "local", "test", "testing"}:
        return {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    if not origins:
        return None
    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "X-API-Token"],
    }


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    try:
        await start_background_loops(app)
        yield
    finally:
        await stop_background_loops(app)


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="Deepsee Personal Information Flow API", lifespan=app_lifespan)

    cors = _cors_options()
    if cors:
        app.add_middleware(CORSMiddleware, **cors)
    # Compress large HTML/JSON responses (index.html ~27MB before gzip)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        configured = _configured_api_tokens()
        if _api_token_auth_enabled() and not _is_api_auth_exempt_path(request.url.path):
            if not configured:
                return JSONResponse(
                    {"detail": "API auth is required but API_TOKEN is not configured"},
                    status_code=503,
                )
            provided = _extract_api_token(request)
            if provided not in configured:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(chats.router)
    app.include_router(contacts.router)
    app.include_router(contact_scoring.router)
    app.include_router(ai.router)
    app.include_router(send.router)
    app.include_router(hooks.router)
    app.include_router(configs.router)
    app.include_router(sync.router)
    # NOTE: must be mounted before /api/reports/{report_id} to avoid path shadowing.
    app.include_router(invitations.router)
    app.include_router(reports.router)
    app.include_router(compat.router)
    app.include_router(email.router)
    app.include_router(extensions.router)
    app.include_router(news.router)
    app.include_router(folo.router)
    app.include_router(minutes.router)
    app.include_router(tools.router)
    app.include_router(media.router)
    app.include_router(mp_rss.router)
    app.include_router(tasks.router)
    app.include_router(recorder.router)
    app.include_router(wechat_gateway.router)
    app.include_router(admin.router)
    app.include_router(agent_api.router)
    app.include_router(collector_api.router)
    app.include_router(market.router)

    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    static_dir = os.path.abspath(static_dir)
    if not os.path.exists(static_dir):
        os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        """Serve the unified UI only from static/index.html.
        We intentionally deprecate legacy pages (0811/0801) to avoid confusion.
        """
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            # Avoid stale UI after frequent iterations
            return FileResponse(index_path, headers={"Cache-Control": "no-store"})
        return Response("UI not found", media_type="text/plain", status_code=404)

    @app.get("/embed/{module_id}", include_in_schema=False)
    async def embedded_module(module_id: str):
        """Serve one Deepsee panel as an addressable VibeDesk Mod page."""
        if module_id not in VIBEDESK_EMBED_MODULES:
            return Response("Unknown Deepsee module", media_type="text/plain", status_code=404)
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(
                index_path,
                headers={
                    "Cache-Control": "no-store",
                    "X-VibeDesk-Mod": module_id,
                },
            )
        return Response("UI not found", media_type="text/plain", status_code=404)

    @app.get("/ui/legacy")
    async def legacy_ui():
        # Deprecated permanently to avoid confusion with unified static UI
        return Response("Legacy UI removed", status_code=404)

    return app


app = create_app()
