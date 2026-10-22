"""Optional attached-mode adapter. Account and permission decisions remain in Desk."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request as URLRequest, build_opener

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

PUBLIC_PAGES = frozenset(("/", "/cycles", "/assets", "/audit", "/forecast", "/healthz", "/circle-mark.svg",
    "/docs/2026-07-19-seven-cycle-research-system-redesign.md"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def verify_with_desk(endpoint, authorization, instance, target):
    request = URLRequest(endpoint, data=json.dumps(target).encode(), method="POST", headers={
        "Authorization": authorization, "X-Newma-Desk-Instance-Id": instance,
        "Content-Type": "application/json", "Accept": "application/json",
    })
    try:
        # Fixed loopback validator: no browser Cookie, identity headers, redirects or environment proxy.
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=8) as response:
            identity = json.loads(response.read(4097))
        if not isinstance(identity, dict) or not all(isinstance(identity.get(key), str) and identity[key] for key in ("userId", "workspaceId")):
            return 503
        return 200
    except HTTPError as error:
        return error.code if error.code in (401, 403, 422) else 503
    except (URLError, OSError, ValueError):
        return 503


def install_desk_access(app):
    endpoint = os.environ.get("SEVEN_CYCLE_DESK_SCOPE_URL", "").strip()
    if endpoint:
        url = urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
                or url.path != "/api/mods/runtime/cycle-scope" or url.username or url.password or url.query or url.fragment):
            raise ValueError("SEVEN_CYCLE_DESK_SCOPE_URL must select the loopback Desk cycle validator")
    app.state.cycle_desk_verifier = verify_with_desk

    @app.middleware("http")
    async def access(request: Request, call_next):
        path = request.url.path
        # Only canonical build assets/pages are public in attached mode. Alternate
        # static paths must not bypass protection of /data or other API products.
        public = path in PUBLIC_PAGES or bool(re.fullmatch(r"/assets/[A-Za-z0-9_.-]+\.(?:js|css|woff2?|svg|png)", path))
        if public and request.method in {"GET", "HEAD"}:
            response = await call_next(request)
            response.headers["X-Cycle-Access-Mode"] = "desk-required" if endpoint else "standalone"
            return response
        authorization = request.headers.get("authorization")
        instance = request.headers.get("x-newma-desk-instance-id")
        supplied = any(key in request.headers for key in ("authorization", "x-newma-desk-instance-id", "x-newma-dock-instance-id"))
        if not endpoint and not supplied:
            return await call_next(request)  # Explicit local standalone runtime.
        headers = {"Cache-Control": "private, no-store"}
        status = 401
        legacy = request.headers.get("x-newma-dock-instance-id")
        if authorization and authorization.startswith("Bearer ") and instance and len(authorization) <= 16384 and len(instance) <= 128 and (not legacy or legacy == instance):
            status = await run_in_threadpool(app.state.cycle_desk_verifier, endpoint, authorization, instance, {
                "method": request.method, "path": path, "query": request.url.query,
            }) if endpoint else 503
        if status != 200:
            return JSONResponse({"detail": "周期读取未获授权，请从 Desk 重新打开；未回退独立数据。"}, status_code=status, headers=headers)
        response = await call_next(request)
        response.headers["Cache-Control"] = headers["Cache-Control"]
        return response
