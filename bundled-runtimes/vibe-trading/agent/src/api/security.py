"""Auth dependencies, CORS parsing, DNS-rebinding guard, and shell-tools gating."""

from __future__ import annotations

import hmac
import ipaddress
import urllib.parse
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, Query, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api._compat import host_attr as _host_attr
from src.config.accessor import get_env_config


# ============================================================================
# Constants
# ============================================================================

_DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
)

_DEFAULT_LOOPBACK_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "[::1]",
    "testserver",
})

_SAFE_BROWSER_METHODS = {"GET", "HEAD", "OPTIONS"}


# ============================================================================
# CORS / host parsing
# ============================================================================


def _parse_cors_origins(raw: Optional[str]) -> List[str]:
    """Parse CORS origins and reject credentialed wildcard configuration."""
    if raw is None or not raw.strip():
        return list(_DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError(
            "CORS_ORIGINS='*' is not allowed while credentials are enabled; "
            "configure explicit Web UI origins instead."
        )
    return origins


def _parse_extra_loopback_hosts(raw: Optional[str]) -> set[str]:
    """Return additional trusted Host names for loopback API traffic."""
    if raw is None or not raw.strip():
        return set()
    return {host.strip().lower().rstrip(".") for host in raw.split(",") if host.strip()}


def _get_extra_loopback_hosts() -> set[str]:
    from src.config.accessor import get_env_config
    return _parse_extra_loopback_hosts(get_env_config().api.api_allowed_hosts or None)


def _host_without_port(host: str) -> str:
    """Normalize a Host header to a lowercase hostname without a port."""
    value = host.strip().lower().rstrip(".")
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            return value[: end + 1]
        return value
    if value.count(":") == 1:
        return value.rsplit(":", 1)[0]
    return value


def _is_allowed_loopback_host(host: str) -> bool:
    """Return whether *host* is allowed for loopback-trusted API requests."""
    normalized = _host_without_port(host)
    return normalized in _DEFAULT_LOOPBACK_HOSTS or normalized in _get_extra_loopback_hosts()


def _is_loopback_bind_host(host: str) -> bool:
    """Return whether *host* resolves to a loopback interface."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _get_cors_origins() -> List[str]:
    from src.config.accessor import get_env_config
    return _parse_cors_origins(get_env_config().api.cors_origins or None)


# ============================================================================
# DNS-rebinding middleware
# ============================================================================


async def _reject_untrusted_loopback_host(request: Request, call_next):
    """Block DNS-rebinding Host headers before loopback auth bypasses run."""
    if _is_local_client(request) and not _is_allowed_loopback_host(request.headers.get("host", "")):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Untrusted local API host"},
        )
    return await call_next(request)


# ============================================================================
# API Key Authentication
# ============================================================================

_security = HTTPBearer(auto_error=False)


def _get_api_key() -> str:
    from src.config.accessor import get_env_config
    return get_env_config().api.api_auth_key


def _configured_api_key() -> str:
    """Return the current API auth key, if configured.

    Resolves the ``VIBE_TRADING_API_KEY`` alias server-side via
    :func:`get_env_config` so both ``API_AUTH_KEY`` and the legacy
    alias produce the same key.
    """
    return (
        get_env_config().api.api_auth_key
        or _host_attr("_API_KEY", _get_api_key())
        or ""
    )


def _auth_credential_from_header_or_query(
    cred: Optional[HTTPAuthorizationCredentials],
    query_api_key: Optional[str],
    *,
    allow_query: bool,
) -> str:
    """Return the supplied API credential from the permitted source."""
    if cred and cred.credentials:
        return cred.credentials
    if allow_query and query_api_key:
        return query_api_key
    return ""


def _is_loopback_origin(origin: str) -> bool:
    """Return whether a browser Origin header names a loopback web UI."""
    try:
        parsed = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _origin_matches_request_host(origin: str, request: Request) -> bool:
    """Return whether *origin* is the same site serving this request."""
    try:
        parsed = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    origin_host = parsed.hostname.rstrip(".").lower()
    origin_port = parsed.port
    request_host = _host_without_port(request.headers.get("host", ""))
    if origin_host != request_host:
        return False

    if origin_port is None:
        origin_port = 443 if parsed.scheme == "https" else 80
    request_port = request.url.port
    if request_port is None:
        request_port = 443 if request.url.scheme == "https" else 80
    return origin_port == request_port


def _reject_cross_site_browser_request(request: Request) -> None:
    """Reject unsafe browser requests from untrusted cross-site origins."""
    sec_fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if sec_fetch_site == "cross-site":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request denied")

    origin = request.headers.get("origin")
    if origin and not (_is_loopback_origin(origin) or _origin_matches_request_host(origin, request)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request denied")


def _require_shutdown_authorization(
    *,
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials],
) -> None:
    """Authorize the local shutdown control-plane action."""
    _reject_cross_site_browser_request(request)
    api_key = _configured_api_key()
    if api_key:
        token = _auth_credential_from_header_or_query(cred, None, allow_query=False)
        if not token or not hmac.compare_digest(token, api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return
    if not _is_local_client(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API_AUTH_KEY is required for non-local API access",
        )


def _validate_api_auth(
    *,
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials],
    query_api_key: Optional[str] = None,
    allow_query: bool = False,
) -> None:
    """Validate configured auth, preserving loopback-only dev mode."""
    if request.method.upper() not in _SAFE_BROWSER_METHODS:
        _reject_cross_site_browser_request(request)

    if _is_local_client(request):
        return

    api_key = _configured_api_key()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API_AUTH_KEY is required for non-local API access",
        )

    token = _auth_credential_from_header_or_query(cred, query_api_key, allow_query=allow_query)
    if not token or not hmac.compare_digest(token, api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _is_local_client(request: Request) -> bool:
    """Return whether the request originates from a loopback client."""
    host = request.client.host if request.client else ""
    if host in {"localhost", "testclient"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    return _trusted_docker_loopback_ip(ip)


# ============================================================================
# Docker / shell helpers
# ============================================================================


def _default_gateway_ips() -> set[ipaddress.IPv4Address]:
    """Return IPv4 default gateway addresses from Linux procfs."""
    gateways: set[ipaddress.IPv4Address] = set()
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()
    except OSError:
        return gateways

    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 3 or fields[1] != "00000000":
            continue
        try:
            raw = int(fields[2], 16).to_bytes(4, byteorder="little")
            gateways.add(ipaddress.IPv4Address(raw))
        except ValueError:
            continue
    return gateways


def _trusted_docker_loopback_ip(ip: ipaddress._BaseAddress) -> bool:
    """Return whether an IP is the trusted Docker host gateway."""
    if not isinstance(ip, ipaddress.IPv4Address):
        return False
    if not get_env_config().api.vibe_trading_trust_docker_loopback:
        return False
    gateway_fn = _host_attr("_default_gateway_ips", _default_gateway_ips)
    return ip in gateway_fn()


def _env_shell_tools_enabled() -> bool:
    """Return whether server-side shell tools are explicitly enabled."""
    return get_env_config().api.vibe_trading_enable_shell_tools


def _shell_tools_enabled_for_request(request: Request) -> bool:
    """Return whether this API request may expose shell tools to the agent."""
    return _env_shell_tools_enabled()


# ============================================================================
# Auth dependencies (FastAPI Depends)
# ============================================================================


async def require_auth(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> None:
    """Validate Bearer token for sensitive API endpoints."""
    _validate_api_auth(request=request, cred=cred)


async def require_event_stream_auth(
    request: Request,
    api_key: Optional[str] = Query(None),
    cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> None:
    """Validate auth for browser EventSource streams."""
    _validate_api_auth(request=request, cred=cred, query_api_key=api_key, allow_query=True)


async def require_local_or_auth(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> None:
    """Protect settings access when dev-mode auth is disabled."""
    if _configured_api_key():
        await require_auth(request, cred)
        return
    if not _is_local_client(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Settings access requires API_AUTH_KEY or a local loopback client",
        )


async def require_settings_write_auth(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
) -> None:
    """Require explicit authorization before changing credential-routing settings."""
    api_key = _configured_api_key()
    if api_key:
        token = _auth_credential_from_header_or_query(cred, None, allow_query=False)
        if not token or not hmac.compare_digest(token, api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return

    if not _is_local_client(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Settings writes require API_AUTH_KEY or a local loopback client",
        )


_LEGACY_LAZY_NAMES = {
    "_API_KEY": _get_api_key,
    "_CORS_ORIGINS": _get_cors_origins,
    "_EXTRA_LOOPBACK_HOSTS": _get_extra_loopback_hosts,
}


def __getattr__(name: str):
    if name in _LEGACY_LAZY_NAMES:
        return _LEGACY_LAZY_NAMES[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
