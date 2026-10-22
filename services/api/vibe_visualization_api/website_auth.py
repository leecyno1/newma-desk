"""Optional c10375 identity adapter. Website owns accounts and entitlement checks."""
import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
import secrets
import time
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import httpx

from vibe_visualization_api.control_plane.sessions import ModSessionError, bearer_token

AUTHORITY = "https://newma.uk"
DESK_ORIGIN = "https://c10375.runtime.drlemon.cc:10443"
WRITE_ORIGINS = frozenset(f"https://c10375.runtime.drlemon.cc:{port}" for port in (10443, 10444, 10445))
COOKIE = "__Host-newma_desk_session"
FLOW_COOKIE = "__Host-newma_desk_flow"
SCOPE_PATHS = frozenset(("/api/mods/runtime/instock-scope", "/api/modules/runtime/instock-scope",
                       "/api/mods/runtime/cycle-scope", "/api/modules/runtime/cycle-scope"))
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
CODE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))


def denied(status=401):
    return HTTPException(status, "请通过 Newma 登录后重试" if status == 401 else "当前身份或请求来源未获授权")


def local_request(request):
    return request.client is not None and request.client.host in {"127.0.0.1", "::1"}


def relative_page(value):
    decoded = unquote(value)
    if (len(value) > 2048 or not decoded.startswith("/") or decoded.startswith("//")
            or "\\" in decoded or any(ord(char) < 32 for char in decoded)
            or urlsplit(decoded).netloc or urlsplit(decoded).scheme):
        raise denied(400)
    return value


def check_origin(request, method=None):
    if (method or request.method) not in SAFE_METHODS and request.headers.get("origin") not in WRITE_ORIGINS:
        raise denied(403)


def check_mod_boundary(request, claims):
    """A plugin credential is not an account credential, even with a valid login."""
    path = request.url.path.rstrip("/")
    from vibe_visualization_api.watchlists.access import storage_permission
    permission = storage_permission(path, request.method, claims.module_id)
    if permission and permission in claims.permissions:
        return  # Storage dependency rechecks revision and derives the owner from claims.
    if path.startswith("/api/global-topics/"):
        from vibe_visualization_api.global_intelligence_adapter import topic_access
        access = topic_access(path, request.method)
        if access and access[0] == claims.module_id and access[1] in claims.permissions:
            return  # Domain dependency rechecks published permissions and binds record ownership.
    if request.method == "GET" and claims.module_id == "global-situation" and "market.read" in claims.permissions:
        from vibe_visualization_api.global_intelligence_adapter import GLOBAL_READ_PATHS
        if path in GLOBAL_READ_PATHS:
            return  # Endpoint dependency also validates the published revision.
    if path in SCOPE_PATHS:
        return
    if request.method == "GET" and claims.module_id == "industry-prosperity" and "market.read" in claims.permissions:
        from vibe_visualization_api.industry_access import INDUSTRY_READ_PATHS
        if path in INDUSTRY_READ_PATHS:
            return  # The dependency requires a bound Mod session and current published revision.
    match = re.fullmatch(r"/api/(?:mods|modules)/([^/]+)/(.+)", path)
    if match:
        module_id, resource = match.groups()
        if module_id == claims.module_id and (
            resource in {"context", "visual-context", "visual-context/capture", "industry-map-inputs"}
            or resource.startswith(("actions/", "storage/", "sources/", "research-origins/"))
        ):
            return  # Each downstream route still checks its action/storage grants.
        raise denied(403)
    # Only the Research file adapter enforces Mod scope; the whole native API
    # must not be treated as a signed capability surface.
    if (path in {"/api/research-archive", "/api/research/myreports"}
            or path.startswith(("/api/research-archive/", "/api/research/myreports/",
            "/api/data-services/instock-analysis/invoke/"))):
        return
    if path.startswith("/api/trading/"):
        from vibe_visualization_api.domain_suites import TradingApiAdapter
        permission = TradingApiAdapter._required_permission(path.removeprefix("/api/trading"), request.method)
        if permission and permission in claims.permissions and claims.module_id in TradingApiAdapter._MODULE_IDS:
            return  # The adapter additionally verifies its signed-session header.
    raise denied(403)


@dataclass(frozen=True)
class Identity:
    user_id: str
    workspace_id: str
    expires_at: float

    def public(self):
        return {"mode": "website", "userId": self.user_id, "workspaceId": self.workspace_id,
                "expiresAt": datetime.fromtimestamp(self.expires_at, UTC).isoformat()}


class WebsiteAuth:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.flows = OrderedDict()
        self.cache = OrderedDict()
        self.bindings = OrderedDict()

    @staticmethod
    def bounded_put(store, key, value, limit):
        store[key] = value
        store.move_to_end(key)
        while len(store) > limit:
            store.popitem(last=False)

    async def post(self, route, payload):
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
                response = await client.post(AUTHORITY + route, json=payload)
            if response.status_code != 200:
                raise denied()
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise denied()
            return result
        except (httpx.HTTPError, ValueError) as error:
            raise denied() from error

    @staticmethod
    def identity(result):
        user = result.get("userId")
        if isinstance(user, int) and not isinstance(user, bool):
            user = str(user)
        workspace = result.get("workspaceId")
        expires = result.get("expiresAt")
        try:
            if isinstance(expires, str):
                parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("timezone required")
                expires = parsed.timestamp()
            if (not isinstance(expires, (float, int)) or isinstance(expires, bool)
                    or not time.time() < expires <= time.time() + 8 * 3600 + 30):
                raise ValueError("invalid expiry")
        except (ValueError, TypeError, OverflowError) as error:
            raise denied() from error
        if (result.get("ok") is not True or result.get("serverName") != "c10375"
                or not isinstance(user, str) or not ID.fullmatch(user)
                or workspace != f"newma-{user}-c10375" or len(workspace) > 128):
            raise denied()
        return Identity(user, workspace, expires)

    async def verify(self, token):
        if not token or not isinstance(token, str) or len(token) > 16384 or not re.fullmatch(r"[A-Za-z0-9_.-]+", token):
            raise denied()
        key = hashlib.sha256(token.encode()).hexdigest()
        cached = self.cache.get(key)
        if cached and cached[0] > time.monotonic() and cached[1].expires_at > time.time():
            return cached[1]
        self.cache.pop(key, None)
        identity = self.identity(await self.post("/api/desk-auth/verify", {"token": token}))
        self.bounded_put(self.cache, key, (time.monotonic() + 5, identity), 2048)
        return identity

    def bind(self, claims, token):
        self.bounded_put(self.bindings, claims.session_id, (token, claims.expires_at), 2048)

    def forget(self, token):
        self.cache.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        for sid, (bound, _) in list(self.bindings.items()):
            if secrets.compare_digest(bound, token):
                self.bindings.pop(sid, None)

    async def authenticate(self, request, *, cookie_only=False, require_mod=False):
        token = request.cookies.get(COOKIE)
        claims = None
        authorization = request.headers.get("authorization")
        mod_header = request.headers.get("x-newma-desk-mod-session")
        if not cookie_only and (authorization or mod_header):
            try:
                mod_token = bearer_token(authorization) if authorization else mod_header
                if mod_header and mod_token != mod_header:
                    raise ModSessionError("conflicting tokens")
                claims = request.app.state.mod_session_service.validate(mod_token)
            except ModSessionError as error:
                raise denied() from error
            instance = request.headers.get("x-newma-desk-instance-id")
            legacy = request.headers.get("x-newma-dock-instance-id")
            if not (instance or legacy) or (instance and legacy and instance != legacy) or (instance or legacy) != claims.instance_id:
                raise denied(403)
            binding = self.bindings.get(claims.session_id)
            if binding is None or binding[1] <= time.time():
                self.bindings.pop(claims.session_id, None)
                raise denied()
            if token and not secrets.compare_digest(token, binding[0]):
                raise denied(403)
            token = binding[0]
        if require_mod and claims is None:
            raise denied()
        identity = await self.verify(token)
        if claims and (claims.user_id != identity.user_id or claims.workspace_id != identity.workspace_id):
            raise denied(403)
        if claims:
            check_mod_boundary(request, claims)
        return identity, token


def check_scope(values, identity):
    expected = {"userId": identity.user_id, "user_id": identity.user_id,
                "workspaceId": identity.workspace_id, "workspace_id": identity.workspace_id}
    for key, value in values:
        if key in expected and value != expected[key]:
            raise denied(403)


class WebsiteIdentityMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (not self.auth.enabled or scope["type"] != "http"
                or not (path == "/api" or path.startswith("/api/")) or path.startswith("/api/auth/")):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        try:
            internal = path in SCOPE_PATHS and local_request(request) and not request.headers.get("origin")
            # Sibling ports share this host's Cookie. Their plugins must not gain
            # Shell account-management authority by omitting their Mod bearer.
            plugin_origin = request.headers.get("origin") in WRITE_ORIGINS - {DESK_ORIGIN}
            # Website login is not ownership of the native single-user store.
            # Research files require their scoped adapter; public data goes via
            # declared Actions. Never expose legacy portfolios with only a Cookie.
            native_resource = path.startswith("/api/research/") or bool(re.fullmatch(
                r"/api/data-services/[^/]+/invoke/[^/]+", path.rstrip("/")))
            identity, token = await self.auth.authenticate(request, require_mod=internal or plugin_origin or native_resource)
            if not internal:
                check_origin(request)
            for name, expected in (("x-user-id", identity.user_id), ("x-workspace-id", identity.workspace_id)):
                if any(value != expected for value in request.headers.getlist(name)):
                    raise denied(403)
            check_scope(request.query_params.multi_items(), identity)
            media = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if not media or media == "application/json" or media.endswith("+json"):
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise HTTPException(413, "请求内容过大")
                    chunks.append(chunk)
                body = b"".join(chunks)
                try:
                    value = json.loads(body) if body else None
                except (ValueError, UnicodeDecodeError) as error:
                    raise HTTPException(400, "请求格式错误") from error
                if isinstance(value, dict):
                    check_scope(value.items(), identity)
                    if isinstance(value.get("scope"), dict):
                        check_scope(value["scope"].items(), identity)
                original_receive = receive
                pending = True

                async def replay():
                    nonlocal pending
                    if pending:
                        pending = False
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await original_receive()

                receive = replay
            headers = [(key, value) for key, value in scope["headers"] if key.lower() not in (b"x-user-id", b"x-workspace-id")]
            headers.extend(((b"x-user-id", identity.user_id.encode()), (b"x-workspace-id", identity.workspace_id.encode())))
            scope["headers"] = headers
            scope.setdefault("state", {}).update(website_identity=identity, website_token=token)
        except HTTPException as error:
            response = JSONResponse({"detail": error.detail}, status_code=error.status_code, headers={"Cache-Control": "no-store"})
            # A rejected plugin/native request must not log out a valid Shell
            # session. Only the session check and explicit logout clear Cookies.
            return await response(scope, receive, send)
        await self.app(scope, receive, send)


router = APIRouter(prefix="/api/auth", tags=["website-auth"])


def service(request):
    auth = request.app.state.website_auth
    if not auth.enabled:
        raise HTTPException(404, "云端登录未启用")
    return auth


@router.get("/website/start")
async def start(request: Request, returnTo: str = "/"):
    auth = service(request)
    target = relative_page(returnTo)
    flow, state, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    auth.bounded_put(auth.flows, flow, (state, verifier, target, time.monotonic() + 180), 256)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    response = RedirectResponse(AUTHORITY + "/console.html?" + urlencode({
        "newma_desk_login": "1", "state": state, "code_challenge": challenge,
    }), status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.set_cookie(FLOW_COOKIE, flow, max_age=180, secure=True, httponly=True, samesite="none")
    return response


@router.post("/website/callback")
async def callback(request: Request):
    auth = service(request)
    if request.headers.get("origin") != AUTHORITY:
        raise denied(403)
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
        raise denied(400)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 8192:
            raise denied(400)
        chunks.append(chunk)
    body = b"".join(chunks)
    try:
        form = parse_qs(body.decode(), strict_parsing=True)
    except (ValueError, UnicodeDecodeError) as error:
        raise denied(400) from error
    if set(form) != {"state", "code"} or any(len(v) != 1 or not CODE.fullmatch(v[0]) for v in form.values()):
        raise denied(400)
    flow = request.cookies.get(FLOW_COOKIE)
    saved = auth.flows.get(flow)
    if not saved or saved[3] <= time.monotonic() or not secrets.compare_digest(saved[0], form["state"][0]):
        raise denied()
    auth.flows.pop(flow)
    result = await auth.post("/api/desk-auth/exchange", {"code": form["code"][0], "code_verifier": saved[1]})
    identity = auth.identity(result)
    token = result.get("token")
    # Re-verify before accepting the exchange, including current binding/revocation.
    verified = await auth.verify(token)
    if (verified.user_id, verified.workspace_id) != (identity.user_id, identity.workspace_id):
        raise denied()
    response = RedirectResponse(saved[2], status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite="none")
    response.set_cookie(COOKIE, token, max_age=max(1, int(min(identity.expires_at, verified.expires_at) - time.time())),
                        secure=True, httponly=True, samesite="none")
    return response


@router.get("/session")
async def session(request: Request):
    auth = request.app.state.website_auth
    if not auth.enabled:
        return JSONResponse({"mode": "local"}, headers={"Cache-Control": "no-store"})
    try:
        identity, _ = await auth.authenticate(request, cookie_only=True)
    except HTTPException as error:
        response = JSONResponse({"detail": error.detail}, status_code=error.status_code, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="none")
        return response
    return JSONResponse(identity.public(), headers={"Cache-Control": "no-store"})


@router.post("/logout")
async def logout(request: Request):
    auth = service(request)
    check_origin(request)
    token = request.cookies.get(COOKIE)
    if token:
        auth.forget(token)
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="none")
    return response


@router.get("/verify")
async def forward_auth(request: Request):
    auth = service(request)
    if not local_request(request):
        raise denied(403)
    method = request.headers.get("x-forwarded-method", "")
    uri = request.headers.get("x-forwarded-uri", "")
    if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
        raise denied(403)
    relative_page(uri)
    check_origin(request, method)
    identity, _ = await auth.authenticate(request, cookie_only=True)
    check_scope(parse_qsl(urlsplit(uri).query, keep_blank_values=True), identity)
    for name, expected in (("x-user-id", identity.user_id), ("x-workspace-id", identity.workspace_id)):
        if any(value != expected for value in request.headers.getlist(name)):
            raise denied(403)
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


def install_website_auth(application, settings):
    auth = WebsiteAuth(settings.website_auth_enabled)
    application.state.website_auth = auth
    application.add_middleware(WebsiteIdentityMiddleware, auth=auth)
    application.include_router(router)
