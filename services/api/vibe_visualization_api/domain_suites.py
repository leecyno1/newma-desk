"""In-process hosting for the first-party Research and Trading suites.

The upstream projects remain source packages under ``mod-projects`` but no
longer need their own API or frontend processes.  Newma-Desk loads their ASGI
applications into its API process and serves their compiled frontend bundles
from the Newma-Desk API origin.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import site
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from vibe_visualization_api.config import Settings


logger = logging.getLogger(__name__)


class SpaStaticFiles(StaticFiles):
    """Serve a Vite SPA with index.html fallback for nested Mod routes."""

    async def get_response(self, path: str, scope: dict[str, Any]):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


class ResearchApiAdapter:
    """Expose Research's historical ``/api/*`` routes under one Desk prefix."""

    def __init__(self, application: Any):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            path = scope.get("path", "/")
            root_path = scope.get("root_path", "")
            if root_path and path.startswith(root_path):
                path = path[len(root_path):] or "/"
                scope["root_path"] = ""
            if path != "/api" and not path.startswith("/api/"):
                path = f"/api{path if path.startswith('/') else f'/{path}'}"
            scope["path"] = path
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, bytes):
                scope["raw_path"] = scope["path"].encode("utf-8")
        await self.application(scope, receive, send)


class TradingApiAdapter:
    """Authenticate the explicitly exposed Trading research surface.

    Vibe-Trading intentionally rejects non-loopback clients unless an API key
    is supplied. In an integrated deployment the browser talks to Desk, not to
    Vibe-Trading directly, so Desk adds the server-held credential only for the
    Alpha research endpoints used by first-party Factor Lab Mods. Session,
    settings, live-trading, and shell-capable endpoints keep Vibe-Trading's own
    authentication boundary. The key is never exposed to the Mod iframe.
    """

    _TRUSTED_PREFIXES = ("/alpha",)

    def __init__(self, application: Any, api_key: str):
        self.application = application
        self._authorization = f"Bearer {api_key}".encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"} and self._is_trusted_path(scope):
            scope = dict(scope)
            headers = [
                (name, value)
                for name, value in scope.get("headers", [])
                if name.lower() != b"authorization"
            ]
            headers.append((b"authorization", self._authorization))
            scope["headers"] = headers
        await self.application(scope, receive, send)

    @classmethod
    def _is_trusted_path(cls, scope: dict[str, Any]) -> bool:
        path = scope.get("path", "/")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path):] or "/"
        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in cls._TRUSTED_PREFIXES
        )


def _venv_site_packages(root: Path) -> list[Path]:
    lib = root / ".venv" / "lib"
    if not lib.is_dir():
        return []
    return sorted(path for path in lib.glob("python*/site-packages") if path.is_dir())


def _add_import_path(path: Path) -> None:
    value = str(path.resolve())
    if value not in sys.path:
        sys.path.insert(0, value)


def _add_site_packages(root: Path) -> None:
    for path in _venv_site_packages(root):
        site.addsitedir(str(path.resolve()))


def _set_trading_api_key(api_key: str) -> None:
    if api_key:
        os.environ["API_AUTH_KEY"] = api_key
    else:
        os.environ.pop("API_AUTH_KEY", None)


def _load_module(name: str, path: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load domain suite module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


async def _run_handlers(handlers: list[Any]) -> None:
    for handler in handlers:
        result = handler()
        if inspect.isawaitable(result):
            await result


@dataclass
class DomainSuiteRuntime:
    applications: list[FastAPI] = field(default_factory=list)
    mounted: dict[str, bool] = field(default_factory=dict)
    _started: bool = False

    async def startup(self) -> None:
        if self._started:
            return
        for application in self.applications:
            await _run_handlers(list(application.router.on_startup))
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        for application in reversed(self.applications):
            await _run_handlers(list(application.router.on_shutdown))
        self._started = False


def mount_domain_suites(
    application: FastAPI,
    settings: Settings,
) -> DomainSuiteRuntime:
    """Mount available first-party domain suites into ``application``."""
    runtime = DomainSuiteRuntime(mounted={"research": False, "trading": False})
    if not settings.enable_domain_suites:
        return runtime

    research_root = settings.investment_workspace.expanduser().resolve()
    trading_root = settings.trading_workspace.expanduser().resolve()

    research_app_path = research_root / "backend" / "app.py"
    if research_app_path.is_file():
        _add_site_packages(research_root / "backend")
        _add_import_path(research_root / "backend")
        research_module = _load_module(
            "vibedesk_integrated_research_app",
            research_app_path,
        )
        research_app = research_module.app
        application.mount("/api/research", ResearchApiAdapter(research_app))
        runtime.applications.append(research_app)
        runtime.mounted["research"] = True
        research_dist = research_root / "frontend" / "dist"
        if research_dist.is_dir():
            application.mount(
                "/mod-runtime/research",
                SpaStaticFiles(directory=str(research_dist), html=True),
                name="research-mod-runtime",
            )
        else:
            logger.warning("Research frontend build is missing: %s", research_dist)
    else:
        logger.warning("Research suite is unavailable: %s", research_app_path)

    trading_app_path = trading_root / "agent" / "api_server.py"
    if trading_app_path.is_file():
        trading_api_key = settings.trading_api_key.get_secret_value()
        _set_trading_api_key(trading_api_key)
        _add_site_packages(trading_root)
        _add_import_path(trading_root / "agent")
        from src.config.accessor import reset_env_config

        reset_env_config()
        trading_module = _load_module(
            "api_server",
            trading_app_path,
        )
        trading_app = trading_module.app
        mounted_trading_app = (
            TradingApiAdapter(trading_app, trading_api_key)
            if trading_api_key
            else trading_app
        )
        application.mount("/api/trading", mounted_trading_app)
        runtime.applications.append(trading_app)
        runtime.mounted["trading"] = True
        trading_dist = trading_root / "frontend" / "dist"
        if trading_dist.is_dir():
            application.mount(
                "/mod-runtime/trading",
                SpaStaticFiles(directory=str(trading_dist), html=True),
                name="trading-mod-runtime",
            )
        else:
            logger.warning("Trading frontend build is missing: %s", trading_dist)
    else:
        logger.warning("Trading suite is unavailable: %s", trading_app_path)

    @application.get("/api/domain-suites", include_in_schema=False)
    def domain_suite_status() -> dict[str, object]:
        return {"ok": all(runtime.mounted.values()), "suites": runtime.mounted}

    return runtime
