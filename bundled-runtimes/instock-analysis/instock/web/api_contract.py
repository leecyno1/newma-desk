#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared HTTP contract for the decoupled analysis surfaces.

Legacy endpoints keep their historical ``{ok, data/error}`` response shape.
Versioned endpoints use a stable error object and attach contract metadata so
future Web/Newma-Desk clients can depend on them without importing InStock code.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterable, Tuple
from urllib.parse import urlparse

import tornado.web

from instock.web.runtime_metrics import get_api_metrics_registry


API_VERSION = "1.0"
BRIDGE_PROTOCOL = "1.0"


def exact_http_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _configured_origins(names: Iterable[str]) -> Tuple[str, ...]:
    origins = []
    for name in names:
        raw = os.environ.get(name, "")
        for value in raw.split(","):
            origin = exact_http_origin(value)
            if origin and origin not in origins:
                origins.append(origin)
    return tuple(origins)


def cors_origins() -> Tuple[str, ...]:
    """Return exact origins allowed to call analysis APIs from a browser."""

    return _configured_origins(("INSTOCK_CORS_ORIGINS", "INSTOCK_CORS_ORIGIN"))


def embed_origins() -> Tuple[str, ...]:
    """Return exact origins allowed to frame the two Mod pages."""

    return _configured_origins((
        "INSTOCK_EMBED_ORIGINS",
        "NEWMA_DESK_PARENT_ORIGIN",
        "NEWMA_DOCK_PARENT_ORIGIN",
        "VIBEDESK_PARENT_ORIGIN",
    ))


def apply_security_headers(handler: tornado.web.RequestHandler, *, api: bool = False) -> None:
    """Apply conservative defaults without preventing configured Desk embeds."""

    handler.set_header("X-Content-Type-Options", "nosniff")
    handler.set_header("Referrer-Policy", "strict-origin-when-cross-origin")
    handler.set_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if api:
        handler.set_header("Cache-Control", "no-store")
        return

    origins = embed_origins()
    frame_ancestors = " ".join(("'self'", *origins))
    handler.set_header("Content-Security-Policy", f"frame-ancestors {frame_ancestors}")
    if not origins:
        handler.set_header("X-Frame-Options", "SAMEORIGIN")


def apply_cors_headers(handler: tornado.web.RequestHandler) -> None:
    allowed = cors_origins()
    if not allowed:
        return
    request_origin = handler.request.headers.get("Origin", "").rstrip("/")
    # Returning the first configured origin for non-CORS requests preserves
    # compatibility with existing API checks while browser calls still require
    # an exact match.
    selected = request_origin if request_origin in allowed else (allowed[0] if not request_origin else "")
    if selected:
        handler.set_header("Access-Control-Allow-Origin", selected)
        handler.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        handler.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        handler.set_header("Vary", "Origin")


class AnalysisApiHandler(tornado.web.RequestHandler):
    """Base handler supporting both the legacy and v1 response contracts."""

    @property
    def is_v1(self) -> bool:
        return self.request.path.startswith("/api/v1/")

    @property
    def request_id(self) -> str:
        value = getattr(self, "_request_id", "")
        if not value:
            value = uuid.uuid4().hex
            self._request_id = value
        return value

    def set_default_headers(self) -> None:
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.set_header("X-Request-Id", self.request_id)
        apply_security_headers(self, api=True)
        apply_cors_headers(self)

    def prepare(self) -> None:
        if self.is_v1:
            self._metrics_started_at = get_api_metrics_registry().start()

    def on_finish(self) -> None:
        started_at = getattr(self, "_metrics_started_at", None)
        if started_at is not None:
            get_api_metrics_registry().record(
                self.request.method,
                self.request.path,
                self.get_status(),
                started_at,
            )

    def options(self) -> None:
        self.set_status(204)
        self.finish()

    def write_success(self, data, *, meta=None) -> None:
        payload = {"ok": True, "data": data}
        if self.is_v1:
            payload["meta"] = {
                "api_version": API_VERSION,
                "request_id": self.request_id,
                **(meta or {}),
            }
        self.write(payload)

    def write_analysis_success(
        self,
        data,
        *,
        module_id: str,
        title: str,
        parameters=None,
        record_type: str = "analysis",
        meta=None,
    ) -> None:
        """Append a browsable result version, then return the normal API body."""

        from instock.core.analysis_history import get_analysis_history_registry

        history = get_analysis_history_registry().register(
            module_id=module_id,
            payload=data,
            title=title,
            parameters=parameters,
            record_type=record_type,
        )
        self.write_success(data, meta={**(meta or {}), "history": history})

    def write_error(self, status: int, code: str, message: str, *, details=None) -> None:
        self.set_status(status)
        if not self.is_v1:
            self.write({"ok": False, "error": message})
            return
        error = {"code": code, "message": message}
        if details is not None:
            error["details"] = details
        self.write({
            "ok": False,
            "error": error,
            "meta": {"api_version": API_VERSION, "request_id": self.request_id},
        })
