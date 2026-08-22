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
import secrets
import site
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.sessions import (
    ModSessionError,
    ModSessionService,
)


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
    """Authorize the integrated Trading capability surface with Mod sessions.

    The browser receives a short-lived Desk Mod session, never the internal
    Vibe-Trading credential.  This adapter validates the session and its
    permission before replacing it with the server-held credential.  Native
    Trading Agent, channel, upload, shutdown, and live-mutation routes stay
    outside the integrated surface.
    """

    _MODULE_IDS = frozenset(
        {
            "quant-overview",
            "alpha-lab",
            "backtest-lab",
            "factor-correlation",
            "trade-desk",
            "trading-settings",
        }
    )
    _NATIVE_AGENT_PREFIXES = (
        "/sessions",
        "/swarm",
        "/scheduled-runs",
        "/channels",
        "/upload",
        "/shadow-reports",
        "/settings/llm",
        "/skills",
        "/api",
        "/system/shutdown",
    )
    _LIVE_MUTATION_PREFIXES = ("/live", "/mandate")
    _SESSION_HEADER = b"x-newma-desk-mod-session"
    _INSTANCE_HEADER = b"x-newma-desk-instance-id"
    _LEGACY_INSTANCE_HEADER = b"x-newma-dock-instance-id"

    def __init__(
        self,
        application: Any,
        api_key: str,
        session_service: ModSessionService,
    ):
        self.application = application
        self._authorization = (
            f"Bearer {api_key}".encode("utf-8") if api_key else None
        )
        self._session_service = session_service

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return

        path = self._request_path(scope)
        method = str(scope.get("method", "GET")).upper()
        if method == "OPTIONS":
            await self.application(scope, receive, send)
            return

        required_permission = self._required_permission(path, method)
        if required_permission is not None:
            if self._authorization is None:
                await self._reject(
                    scope,
                    receive,
                    send,
                    503,
                    "Trading integration credential is not configured",
                )
                return
            error = self._authorize_mod_session(scope, required_permission)
            if error is not None:
                status_code, detail = error
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code,
                    detail,
                )
                return
            scope = self._credential_scope(scope)
        else:
            blocked = self._blocked_reason(path, method)
            if blocked is not None:
                await self._reject(scope, receive, send, 403, blocked)
                return
        await self.application(scope, receive, send)

    def _authorize_mod_session(
        self,
        scope: dict[str, Any],
        required_permission: str,
    ) -> tuple[int, str] | None:
        token = self._header(scope, self._SESSION_HEADER)
        instance_id = self._header(scope, self._INSTANCE_HEADER)
        if instance_id is None:
            instance_id = self._header(scope, self._LEGACY_INSTANCE_HEADER)
        if token is None or instance_id is None:
            return 401, "A scoped Newma-Desk Mod session is required"
        try:
            claims = self._session_service.validate(token.decode("utf-8"))
        except (ModSessionError, UnicodeDecodeError):
            return 401, "The Newma-Desk Mod session is invalid or expired"
        if claims.instance_id != instance_id.decode("utf-8", errors="ignore"):
            return 403, "The Mod session does not grant this iframe instance"
        if claims.module_id not in self._MODULE_IDS:
            return 403, "The Mod session does not grant Trading capabilities"
        if required_permission not in claims.permissions:
            return 403, f"The Mod session requires {required_permission}"
        return None

    def _credential_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        authorized = dict(scope)
        headers = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower()
            not in {
                b"authorization",
                self._SESSION_HEADER,
                self._INSTANCE_HEADER,
                self._LEGACY_INSTANCE_HEADER,
            }
        ]
        if self._authorization is not None:
            headers.append((b"authorization", self._authorization))
        authorized["headers"] = headers
        return authorized

    @staticmethod
    def _header(scope: dict[str, Any], expected: bytes) -> bytes | None:
        for name, value in scope.get("headers", []):
            if name.lower() == expected:
                return value
        return None

    @staticmethod
    def _request_path(scope: dict[str, Any]) -> str:
        path = scope.get("path", "/")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path):] or "/"
        return str(path)

    @staticmethod
    def _matches_prefix(path: str, prefix: str) -> bool:
        return path == prefix or path.startswith(f"{prefix}/")

    @classmethod
    def _required_permission(cls, path: str, method: str) -> str | None:
        if method == "GET" and path == "/correlation":
            return "trading.compute"
        if cls._matches_prefix(path, "/alpha/bench") or cls._matches_prefix(
            path, "/alpha/compare"
        ):
            if method in {"GET", "POST"}:
                return "trading.compute"
        if method == "GET" and cls._matches_prefix(path, "/alpha"):
            return "trading.read"
        if method == "POST" and path == "/runs/quick":
            return "trading.compute"
        if method == "POST":
            run_parts = path.strip("/").split("/")
            if (
                len(run_parts) == 3
                and run_parts[0] == "runs"
                and run_parts[1]
                and run_parts[2] == "cancel"
            ):
                return "trading.compute"
        if method == "GET" and cls._matches_prefix(path, "/runs"):
            return "trading.read"
        if path == "/live/status" and method == "GET":
            return "trading.runtime"
        if path == "/settings/data-sources" and method in {"GET", "PUT"}:
            return "trading.settings"
        if path == "/qveris/config" and method in {"GET", "PUT"}:
            return "trading.settings"
        if path == "/qveris/status" and method == "GET":
            return "trading.settings"
        return None

    @classmethod
    def _blocked_reason(cls, path: str, method: str) -> str | None:
        if any(cls._matches_prefix(path, prefix) for prefix in cls._NATIVE_AGENT_PREFIXES):
            return "This native Trading capability is replaced by Newma-Desk"
        if method != "GET" and any(
            cls._matches_prefix(path, prefix)
            for prefix in cls._LIVE_MUTATION_PREFIXES
        ):
            return "Live Trading changes require the Newma-Desk confirmation flow"
        return None

    @staticmethod
    async def _reject(
        scope: dict[str, Any],
        receive,
        send,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, receive, send)


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


def _set_trading_api_key(api_key: str) -> str:
    """Configure the private in-process credential used by Trading.

    A standalone Trading deployment may provide its own key.  Integrated mode
    does not require another operator-managed secret: Desk validates the scoped
    Mod session first, then uses this process-local credential only for the
    in-process call into Trading.
    """

    resolved = api_key or secrets.token_urlsafe(32)
    os.environ["API_AUTH_KEY"] = resolved
    return resolved


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

    # The reduced route graph is an invariant of the Integrated Domain
    # Runtime, regardless of whether Desk starts through Docker or uvicorn.
    os.environ["NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"
    os.environ["VIBEDESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"

    research_root = settings.investment_workspace.expanduser().resolve()
    trading_root = settings.trading_workspace.expanduser().resolve()

    research_app_path = research_root / "backend" / "app.py"
    if research_app_path.is_file():
        if settings.domain_suite_workspace_venvs:
            logger.warning(
                "Using Research workspace .venv compatibility mode; "
                "production deployments should install one unified dependency set"
            )
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
        trading_api_key = _set_trading_api_key(
            settings.trading_api_key.get_secret_value()
        )
        # The Trading app is loaded in-process, so its path-safety defaults can
        # resolve against the Desk process instead of the Trading workspace.
        # Explicitly register the workspace run root before importing it; this
        # keeps integrated quick backtests subject to the same sandbox as the
        # standalone service.
        configured_run_roots = [
            item.strip()
            for item in os.environ.get("VIBE_TRADING_ALLOWED_RUN_ROOTS", "").split(",")
            if item.strip()
        ]
        trading_run_root = str((trading_root / "agent" / "runs").resolve())
        os.environ["VIBE_TRADING_ALLOWED_RUN_ROOTS"] = ",".join(
            dict.fromkeys([trading_run_root, *configured_run_roots])
        )
        if settings.domain_suite_workspace_venvs:
            logger.warning(
                "Using Trading workspace .venv compatibility mode; "
                "production deployments should install one unified dependency set"
            )
            _add_site_packages(trading_root)
        _add_import_path(trading_root / "agent")
        from src.config.accessor import reset_env_config

        reset_env_config()
        trading_module = _load_module(
            "api_server",
            trading_app_path,
        )
        trading_app = trading_module.app
        mounted_trading_app = TradingApiAdapter(
            trading_app,
            trading_api_key,
            application.state.mod_session_service,
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
