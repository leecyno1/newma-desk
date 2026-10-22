"""Synthetic Website responses only; never calls a real account or entitlement API."""
import base64
import asyncio
from datetime import UTC, datetime
import hashlib
import json
from types import SimpleNamespace
import time
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.testclient import TestClient
import pytest
import httpx

from vibe_visualization_api.control_plane.routes import create_mod_session, _validate_session
from vibe_visualization_api.control_plane.sessions import ModSessionService
from vibe_visualization_api.website_auth import (
    AUTHORITY, COOKIE, DESK_ORIGIN, FLOW_COOKIE, WebsiteAuth, install_website_auth,
)

USER = "synthetic-user"
WORKSPACE = "newma-synthetic-user-c10375"
TOKEN = "synthetic-desk-token"
CODE = "c" * 43


def identity(**changes):
    return {"ok": True, "userId": USER, "workspaceId": WORKSPACE, "serverName": "c10375",
            "expiresAt": datetime.fromtimestamp(time.time() + 600, UTC).isoformat(), **changes}


def make_app(enabled=True):
    app = FastAPI()
    install_website_auth(app, SimpleNamespace(website_auth_enabled=enabled))
    app.state.mod_session_service = ModSessionService("synthetic-test-signing-secret")
    app.state.resolve_module_repository = lambda: SimpleNamespace(get_published=lambda module_id: SimpleNamespace(
        module_id=module_id, revision=1, manifest={"schemaVersion": "1.1", "permissions": ["analysis.read"], "actions": {}},
    ))
    app.post("/api/mods/{module_id}/sessions")(create_mod_session)

    @app.api_route("/api/private", methods=["GET", "POST", "PUT"])
    @app.api_route("/api/mods/cycle/context", methods=["GET", "PUT"])
    async def private(request: Request):
        return {"userId": request.headers.get("x-user-id"), "workspaceId": request.headers.get("x-workspace-id")}

    @app.post("/api/mods/runtime/instock-scope")
    async def stock_scope(request: Request, authorization: str | None = Header(default=None),
                          instance: str | None = Header(default=None, alias="X-Newma-Desk-Instance-Id")):
        claims = _validate_session(request, authorization, instance)
        return {"userId": claims.user_id, "workspaceId": claims.workspace_id}

    app.state.verifications = []

    async def post(route, payload):
        app.state.verifications.append(route)
        if route.endswith("/exchange"):
            if payload["code"] != CODE or getattr(app.state, "used", False):
                raise HTTPException(401, "synthetic rejected code")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(payload["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            if challenge != app.state.challenge:
                raise HTTPException(401, "synthetic rejected challenge")
            app.state.used = True
            return identity(token=TOKEN)
        if payload["token"] != TOKEN or getattr(app.state, "revoked", False):
            raise HTTPException(401, "synthetic revoked")
        return identity()

    app.state.website_auth.post = post
    return app


@pytest.fixture
def client():
    app = make_app()
    with TestClient(app, base_url=DESK_ORIGIN) as client:
        yield client


def login(client, target="/?mod=seven-cycle-research"):
    start = client.get("/api/auth/website/start", params={"returnTo": target}, follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert urlsplit(start.headers["location"]).netloc == "newma.uk"
    client.app.state.challenge = query["code_challenge"][0]
    callback = client.post("/api/auth/website/callback", headers={"Origin": AUTHORITY},
                           data={"state": query["state"][0], "code": CODE}, follow_redirects=False)
    return start, callback, query


def mod_headers(client):
    result = client.post("/api/mods/cycle/sessions", headers={"Origin": DESK_ORIGIN}, json={
        "instanceId": "instance-one", "workspaceId": WORKSPACE,
    })
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["accessToken"], "X-Newma-Desk-Instance-Id": "instance-one"}


def test_complete_flow_cookie_security_and_authoritative_identity(client):
    start, callback, query = login(client)
    assert callback.status_code == 303
    assert callback.headers["location"] == "/?mod=seven-cycle-research"
    assert len(query["state"][0]) == len(query["code_challenge"][0]) == 43
    for response in (start, callback):
        cookies = response.headers.get_list("set-cookie")
        assert any("HttpOnly" in item and "Secure" in item and "SameSite=none" in item and "Path=/" in item for item in cookies)
        assert all("Domain=" not in item for item in cookies)
        assert response.headers["cache-control"] == "no-store"
        assert TOKEN not in response.headers["location"]
    session = client.get("/api/auth/session", headers={"X-User-Id": "not-authoritative"})
    assert session.json()["userId"] == USER
    assert session.json()["workspaceId"] == WORKSPACE
    assert TOKEN not in session.text
    private = client.get("/api/private")
    assert private.json() == {"userId": USER, "workspaceId": WORKSPACE}
    assert client.app.state.verifications == ["/api/desk-auth/exchange", "/api/desk-auth/verify"]


@pytest.mark.parametrize("path", ["/api/private", "/api/auth/session", "/api/mods/cycle/sessions"])
def test_anonymous_is_not_authenticated_by_identity_headers(client, path):
    method = client.post if path.endswith("sessions") else client.get
    assert method(path, headers={"Origin": DESK_ORIGIN, "X-User-Id": USER, "X-Workspace-Id": WORKSPACE}).status_code == 401


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", "https://newma.uk", DESK_ORIGIN + ".evil"])
def test_cookie_is_not_sufficient_for_cross_site_writes(client, origin):
    login(client)
    assert client.post("/api/private", headers={"Origin": origin} if origin else {}, json={}).status_code == 403


@pytest.mark.parametrize("origin", [DESK_ORIGIN, DESK_ORIGIN.replace("10443", "10444"), DESK_ORIGIN.replace("10443", "10445")])
def test_only_exact_three_origins_can_write(client, origin):
    login(client)
    headers = mod_headers(client)
    assert client.put("/api/mods/cycle/context", headers={**headers, "Origin": origin}, json={}).status_code == 200


@pytest.mark.parametrize("origin", [DESK_ORIGIN.replace("10443", "10444"), DESK_ORIGIN.replace("10443", "10445")])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_sibling_plugin_origin_cannot_use_shared_cookie_as_shell_authority(client, origin, method):
    login(client)
    assert client.request(method, "/api/private", headers={"Origin": origin}).status_code == 401


@pytest.mark.parametrize("path", ["/api/research/portfolio", "/api/research/myreports", "/api/research/radar/refresh",
                                  "/api/data-services/market-data/invoke/research.news-snapshot"])
def test_account_cookie_does_not_unlock_native_data_or_unscoped_provider_invocation(client, path):
    login(client)
    method = "POST" if "invoke" in path or "refresh" in path else "GET"
    rejected = client.request(method, path, headers={"Origin": DESK_ORIGIN})
    assert rejected.status_code == 401
    assert "set-cookie" not in rejected.headers
    assert client.get("/api/auth/session").status_code == 200


@pytest.mark.parametrize("name", ["userId", "workspaceId", "user_id", "workspace_id"])
def test_foreign_scope_rejected_in_query_and_json_including_missing_content_type(client, name):
    login(client)
    assert client.get("/api/private", params={name: "forged"}).status_code == 403
    for media in (None, "application/json", "application/problem+json"):
        headers = {"Origin": DESK_ORIGIN, **({"Content-Type": media} if media else {})}
        assert client.post("/api/private", headers=headers, content=json.dumps({name: "forged"})).status_code == 403
    assert client.post("/api/private", headers={"Origin": DESK_ORIGIN}, json={"scope": {name: "forged"}}).status_code == 403


def test_forged_headers_and_body_cannot_issue_a_mod_session(client):
    login(client)
    for headers in ({"X-User-Id": "wrong"}, {"X-Workspace-Id": "wrong"}):
        assert client.get("/api/private", headers=headers).status_code == 403
    response = client.post("/api/mods/cycle/sessions", headers={"Origin": DESK_ORIGIN}, json={
        "instanceId": "instance-one", "workspaceId": "old-local-workspace",
    })
    assert response.status_code == 403


def test_bound_mod_without_cookie_remains_scoped_and_revocation_is_checked(client):
    login(client)
    headers = mod_headers(client)
    client.cookies.clear()
    assert client.get("/api/mods/cycle/context", headers=headers).json()["workspaceId"] == WORKSPACE
    assert client.get("/api/mods/cycle/context", headers={**headers, "X-User-Id": "forged"}).status_code == 403
    assert client.get("/api/mods/cycle/context", headers={**headers, "X-Newma-Desk-Instance-Id": "other"}).status_code == 403
    client.app.state.revoked = True
    client.app.state.website_auth.cache.clear()  # Simulate the at-most-five-second verification TTL.
    assert client.get("/api/mods/cycle/context", headers=headers).status_code == 401


@pytest.mark.parametrize("path", ["/api/models/providers", "/api/agent/preferences", "/api/mods/drafts",
    "/api/mods/other/context", "/api/mods/cycle/sessions", "/api/data-services/other/invoke/admin",
    "/api/research/portfolio", "/api/trading/runs/quick"])
def test_plugin_token_cannot_be_used_as_full_account_authority(client, path):
    login(client)
    headers = mod_headers(client)
    # Including a valid Cookie must not upgrade a plugin bearer credential either.
    assert client.post(path, headers={**headers, "Origin": DESK_ORIGIN}, json={}).status_code == 403
    client.cookies.clear()
    assert client.post(path, headers={**headers, "Origin": DESK_ORIGIN}, json={}).status_code == 403


def test_old_anonymous_mod_token_and_different_cookie_cannot_cross_identity(client):
    login(client)
    old, _ = client.app.state.mod_session_service.issue(instance_id="instance-one", user_id=USER, workspace_id=WORKSPACE,
        module_id="cycle", revision=1, permissions=["analysis.read"], actions=[])
    assert client.get("/api/private", headers={"Authorization": "Bearer " + old,
        "X-Newma-Desk-Instance-Id": "instance-one"}).status_code == 401
    # A new valid login is needed after the invalid session clears the browser cookie.
    client.cookies.set(COOKIE, TOKEN)
    headers = mod_headers(client)
    client.cookies.clear()
    client.cookies.set(COOKIE, "different-website-token")
    assert client.get("/api/private", headers=headers).status_code == 403


def test_stock_callback_needs_bound_signature_and_instance_even_on_loopback():
    with TestClient(make_app(), base_url=DESK_ORIGIN, client=("127.0.0.1", 1234)) as client:
        login(client)
        headers = mod_headers(client)
        assert client.post("/api/mods/runtime/instock-scope", json={}).status_code == 401
        client.cookies.clear()
        result = client.post("/api/mods/runtime/instock-scope", headers=headers, json={"method": "GET", "path": "/api/v1/example"})
        assert result.status_code == 200
        assert result.json()["workspaceId"] == WORKSPACE


@pytest.mark.parametrize("target", ["https://evil.test/", "//evil.test/", "/%2fevil.test", "/\\evil.test", "/%0d%0aevil"])
def test_login_cannot_redirect_outside_desk(client, target):
    assert client.get("/api/auth/website/start", params={"returnTo": target}, follow_redirects=False).status_code == 400


def test_callback_rejects_wrong_origin_state_cookie_and_replay(client):
    start = client.get("/api/auth/website/start", follow_redirects=False)
    query = parse_qs(urlsplit(start.headers["location"]).query)
    client.app.state.challenge = query["code_challenge"][0]
    data = {"state": query["state"][0], "code": CODE}
    assert client.post("/api/auth/website/callback", data=data, headers={"Origin": DESK_ORIGIN}).status_code == 403
    assert client.post("/api/auth/website/callback", data={**data, "state": "w" * 43}, headers={"Origin": AUTHORITY}).status_code == 401
    good = client.post("/api/auth/website/callback", data=data, headers={"Origin": AUTHORITY}, follow_redirects=False)
    assert good.status_code == 303
    assert client.post("/api/auth/website/callback", data=data, headers={"Origin": AUTHORITY}).status_code == 401
    assert client.app.state.verifications.count("/api/desk-auth/exchange") == 1


@pytest.mark.parametrize("failure", ["expired", "missing-cookie", "wrong-challenge"])
def test_callback_flow_failures_never_set_an_identity(client, failure):
    response = client.get("/api/auth/website/start", follow_redirects=False)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    flow = client.cookies.get(FLOW_COOKIE)
    client.app.state.challenge = "wrong" if failure == "wrong-challenge" else query["code_challenge"][0]
    if failure == "expired":
        saved = client.app.state.website_auth.flows[flow]
        client.app.state.website_auth.flows[flow] = (*saved[:3], time.monotonic() - 1)
    if failure == "missing-cookie":
        client.cookies.clear()
    result = client.post("/api/auth/website/callback", data={"state": query["state"][0], "code": CODE}, headers={"Origin": AUTHORITY})
    assert result.status_code == 401
    assert not client.cookies.get(COOKIE)


@pytest.mark.parametrize("changes", [{"ok": False}, {"serverName": "other"}, {"workspaceId": "other"},
    {"expiresAt": time.time() - 1}, {"expiresAt": "2026-10-22T10:00:00"}, {"expiresAt": time.time() + 9 * 3600}, {"userId": "bad\nuser"}])
def test_invalid_authority_identity_is_not_accepted(changes):
    with pytest.raises(HTTPException):
        WebsiteAuth.identity(identity(**changes))


def test_authority_outage_and_revocation_clear_session_without_local_fallback(client):
    login(client)
    client.app.state.website_auth.cache.clear()
    client.app.state.revoked = True
    result = client.get("/api/auth/session")
    assert result.status_code == 401
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert not client.cookies.get(COOKIE)


def test_logout_removes_cookie_and_bound_plugin_sessions(client):
    login(client)
    headers = mod_headers(client)
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": DESK_ORIGIN}).status_code == 200
    assert not client.cookies.get(COOKIE)
    assert client.get("/api/private", headers=headers).status_code == 401


def test_forward_auth_requires_loopback_cookie_forwarded_request_and_write_origin(client):
    login(client)
    headers = {"X-Forwarded-Method": "GET", "X-Forwarded-Uri": "/api/example"}
    assert client.get("/api/auth/verify", headers=headers).status_code == 403
    with TestClient(make_app(), base_url=DESK_ORIGIN, client=("127.0.0.1", 1234)) as internal:
        login(internal)
        assert internal.get("/api/auth/verify").status_code == 403
        assert internal.get("/api/auth/verify", headers=headers).status_code == 200
        assert internal.get("/api/auth/verify", headers={**headers, "X-Forwarded-Uri": "//evil.test"}).status_code == 400
        post = {**headers, "X-Forwarded-Method": "POST"}
        assert internal.get("/api/auth/verify", headers=post).status_code == 403
        assert internal.get("/api/auth/verify", headers={**post, "Origin": DESK_ORIGIN}).status_code == 200
        internal.cookies.clear()
        assert internal.get("/api/auth/verify", headers=headers).status_code == 401


def test_disabled_mode_preserves_local_usage():
    with TestClient(make_app(False)) as client:
        assert client.get("/api/auth/session").json() == {"mode": "local"}
        assert client.get("/api/private", headers={"X-User-Id": "local-user"}).json()["userId"] == "local-user"
        assert client.get("/api/auth/website/start").status_code == 404


def test_verification_cache_checks_revocation_after_five_seconds(client, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr("vibe_visualization_api.website_auth.time.monotonic", lambda: clock[0])
    login(client)
    client.app.state.revoked = True
    clock[0] += 4.9
    assert client.get("/api/auth/session").status_code == 200
    clock[0] += 0.2
    assert client.get("/api/auth/session").status_code == 401


@pytest.mark.parametrize("failure", ["timeout", "redirect", "non-json", "wrong-shape", "rejected"])
def test_authority_transport_fails_closed_without_following_redirects(monkeypatch, failure):
    real_client = httpx.AsyncClient

    def transport(request):
        assert str(request.url) == AUTHORITY + "/api/desk-auth/verify"
        if failure == "timeout":
            raise httpx.ConnectTimeout("synthetic unavailable")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.test/"})
        if failure == "non-json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json=[] if failure == "wrong-shape" else {"ok": False})

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return real_client(**kwargs, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    with pytest.raises(HTTPException) as error:
        asyncio.run(WebsiteAuth(True).verify(TOKEN))
    assert error.value.status_code == 401


def test_cloud_app_routes_and_cors_use_the_same_authority(tmp_path):
    from vibe_visualization_api.config import Settings
    from vibe_visualization_api.main import create_app

    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "cloud-test.db",
                              enable_domain_suites=False, website_auth_enabled=True))
    app.state.website_auth.post = make_app().state.website_auth.post
    # No lifespan/background collection: only exercise the real HTTP route graph.
    client = TestClient(app, base_url=DESK_ORIGIN)
    assert client.get("/api/mods").status_code == 401
    assert client.get("/api/auth/session").status_code == 401
    client.cookies.set(COOKIE, TOKEN)
    assert client.get("/api/auth/session").json()["workspaceId"] == WORKSPACE
    assert client.get("/api/mods", headers={"X-Workspace-Id": "forged"}).status_code == 403
    good = client.options("/api/mods", headers={"Origin": DESK_ORIGIN, "Access-Control-Request-Method": "POST"})
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == DESK_ORIGIN
    assert good.headers["access-control-allow-credentials"] == "true"
    bad = client.options("/api/mods", headers={"Origin": AUTHORITY, "Access-Control-Request-Method": "POST"})
    assert bad.status_code == 400


@pytest.mark.parametrize("module_id", ["macro-monitor", "news-radar"])
def test_crucix_declared_action_works_through_real_cloud_routes_without_account_cookie(tmp_path, module_id):
    from pathlib import Path
    from unittest.mock import AsyncMock
    from vibe_visualization_api.config import Settings
    from vibe_visualization_api.main import create_app
    from tests.mod_storage.test_routes import _manifest

    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "crucix-auth.db",
                              enable_domain_suites=False, website_auth_enabled=True))
    app.state.website_auth.post = make_app().state.website_auth.post
    client = TestClient(app, base_url=DESK_ORIGIN)
    client.cookies.set(COOKIE, TOKEN)
    origin = {"Origin": DESK_ORIGIN}
    root = Path(__file__).resolve().parents[3]
    definition = json.loads((root / "mods" / module_id / "mod.json").read_text())["manifest"]
    manifest = _manifest(module_id)
    manifest.pop("storage")
    for key in ("permissions", "dataServices", "actions"):
        manifest[key] = definition[key]
    draft = client.post("/api/mods/drafts", json=manifest, headers=origin)
    assert draft.status_code == 201, draft.text
    revision = draft.json()["revision"]
    assert client.post(f"/api/mods/{module_id}/revisions/{revision}/publish", headers=origin).status_code == 200
    issued = client.post(f"/api/mods/{module_id}/sessions", headers=origin,
                         json={"instanceId": "crucix-one", "workspaceId": WORKSPACE})
    assert issued.status_code == 201, issued.text
    headers = {"Origin": DESK_ORIGIN.replace("10443", "10444"),
               "Authorization": "Bearer " + issued.json()["accessToken"], "X-Newma-Desk-Instance-Id": "crucix-one"}
    client.cookies.clear()
    payload = {"contract": "newma-desk.crucix-intelligence.v1", "freshness": {"status": "stale"},
               "sourceHealth": {"ok": 0}, "news": [], "macro": {}, "global": {}}
    provider = AsyncMock(return_value=payload)
    app.state.data_service_client.invoke = provider
    result = client.post(f"/api/mods/{module_id}/actions/crucix.snapshot", json={}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json() == payload
    assert provider.call_args.args[0].id == "crucix"
    assert provider.call_args.args[1:] == ("crucix.snapshot", {})
    assert client.post("/api/mods/another-module/actions/crucix.snapshot", json={}, headers=headers).status_code == 403
    assert client.get("/api/crucix/snapshot", headers=headers).status_code == 403
    assert provider.call_count == 1


@pytest.mark.parametrize("module_id,action_id,input_data,upstream_path", [
    ("macro-monitor", "research.macro-monitor", {"days": 7}, "macro-monitor"),
    ("catalyst-calendar", "research.catalysts", {
        "symbols": "600519", "concepts": "半导体", "days": 90,
        "include_cycles": False, "include_macro": False,
    }, "catalysts"),
    ("news-radar", "research.news-snapshot", {}, "radar/snapshot"),
    ("news-radar", "research.news-topics", {
        "q": "增长", "industry": "all", "signal": "risk", "sort": "latest", "offset": 80, "limit": 40,
    }, "radar/topics"),
])
def test_cloud_data_action_dispatches_in_process_without_bypassing_browser_auth(
    tmp_path, monkeypatch, module_id, action_id, input_data, upstream_path,
):
    from pathlib import Path
    from vibe_visualization_api.config import Settings
    from vibe_visualization_api.main import create_app
    from vibe_visualization_api.domain_suites import ResearchApiAdapter
    from tests.mod_storage.test_routes import _manifest
    from tests.data_services.test_internal_research import upstream

    research = upstream()

    def mount(application, settings):
        application.state.internal_research.bind(research, "synthetic-internal-key")
        application.mount("/api/research", ResearchApiAdapter(research))
        return SimpleNamespace(mounted={"research": True})

    monkeypatch.setattr("vibe_visualization_api.main.mount_domain_suites", mount)
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "internal-auth.db",
                              enable_domain_suites=True, website_auth_enabled=True))
    app.state.website_auth.post = make_app().state.website_auth.post
    client = TestClient(app, base_url=DESK_ORIGIN)
    client.cookies.set(COOKIE, TOKEN)
    origin = {"Origin": DESK_ORIGIN}
    definition = json.loads((Path(__file__).resolve().parents[3] / "mods" / module_id / "mod.json").read_text())["manifest"]
    manifest = _manifest(module_id)
    manifest.pop("storage")
    for key in ("permissions", "dataServices", "actions", "storage"):
        if key in definition:
            manifest[key] = definition[key]
    draft = client.post("/api/mods/drafts", json=manifest, headers=origin)
    assert draft.status_code == 201, draft.text
    revision = draft.json()["revision"]
    assert client.post(f"/api/mods/{module_id}/revisions/{revision}/publish", headers=origin).status_code == 200
    issued = client.post(f"/api/mods/{module_id}/sessions", headers=origin,
                         json={"instanceId": "internal-one", "workspaceId": WORKSPACE})
    assert issued.status_code == 201, issued.text
    headers = {"Origin": DESK_ORIGIN.replace("10443", "10444"),
               "Authorization": "Bearer " + issued.json()["accessToken"], "X-Newma-Desk-Instance-Id": "internal-one"}
    client.cookies.clear()
    endpoint = f"/api/mods/{module_id}/actions/{action_id}"
    result = client.post(endpoint, json=input_data, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json() == {"data": {"synthetic": True} if upstream_path == "macro-monitor" else {}}
    assert research.state.calls == [("GET", upstream_path, {
        key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in input_data.items()
    })]
    assert client.post(endpoint, json={**input_data, "days": 99999}, headers=headers).status_code == 422
    assert client.post(endpoint, json={**input_data, "arbitrary_path": "/portfolio"}, headers=headers).status_code == 422
    assert client.get("/api/research/macro-monitor").status_code == 401
    assert client.get("/api/research/macro-monitor", headers=headers).status_code == 403
    assert client.get("/api/research/portfolio", headers=headers).status_code == 403
    assert client.post("/api/research/radar/refresh", headers=headers).status_code == 403
    assert client.post(f"/api/mods/{module_id}/actions/research.news-collect", json={}, headers=headers).status_code == 403
    assert client.post(f"/api/mods/other/actions/{action_id}", json={}, headers=headers).status_code == 403
    assert len(research.state.calls) == 1


def global_cloud_client(tmp_path):
    from vibe_visualization_api.config import Settings
    from vibe_visualization_api.main import create_app
    from tests.mod_storage.test_routes import _manifest
    from tests.global_intel.test_routes import FakeGlobalIntelClient

    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "global-auth.db",
                              enable_domain_suites=False, website_auth_enabled=True))
    authority = make_app()
    app.state.website_auth.post = authority.state.website_auth.post
    app.state.global_intel_client = FakeGlobalIntelClient()
    client = TestClient(app, base_url=DESK_ORIGIN)
    client.cookies.set(COOKIE, TOKEN)
    headers = {"Origin": DESK_ORIGIN}
    manifest = _manifest("global-situation")
    manifest.pop("storage")
    manifest["permissions"] = ["market.read"]
    draft = client.post("/api/mods/drafts", json=manifest, headers=headers)
    assert draft.status_code == 201, draft.text
    assert client.post(f"/api/mods/global-situation/revisions/{draft.json()['revision']}/publish", headers=headers).status_code == 200
    issued = client.post("/api/mods/global-situation/sessions", headers=headers,
                         json={"instanceId": "global-one", "workspaceId": WORKSPACE})
    assert issued.status_code == 201, issued.text
    client.cookies.clear()
    return client, authority, {
        "Origin": DESK_ORIGIN.replace("10443", "10444"),
        "Authorization": "Bearer " + issued.json()["accessToken"], "X-Newma-Desk-Instance-Id": "global-one",
    }


def test_global_stream_and_snapshots_require_bound_published_read_grant(tmp_path):
    client, _, headers = global_cloud_client(tmp_path)
    for path in ("/api/global-intel/static", "/api/global-intel/overview", "/api/global-intel/health"):
        assert client.get(path, headers=headers).status_code == 200
        assert client.get(path).status_code == 401
    response = client.get("/api/global-intel/stream", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"timestamp"' in response.text
    assert client.get("/api/global-intel/stream", headers={**headers, "X-Newma-Desk-Instance-Id": "wrong"}).status_code == 403
    assert client.get("/api/global-topics/fed-rates", headers=headers).status_code == 403
    assert client.post("/api/global-intel/overview", headers=headers).status_code == 403
    for module_id, permissions in [("news-radar", ["market.read"]), ("global-situation", [])]:
        sessions = client.app.state.mod_session_service
        token, _ = sessions.issue(instance_id="global-one", user_id=USER, workspace_id=WORKSPACE,
                                  module_id=module_id, revision=1, actions=[], permissions=permissions)
        client.app.state.website_auth.bind(sessions.validate(token), TOKEN)
        assert client.get("/api/global-intel/stream", headers={**headers, "Authorization": "Bearer " + token}).status_code == 403
    # A valid login Cookie is not a substitute for this endpoint's Mod grant.
    client.cookies.set(COOKIE, TOKEN)
    assert client.get("/api/global-intel/stream", headers={"Origin": DESK_ORIGIN}).status_code == 401
    client.cookies.clear()
    repository = client.app.state.resolve_module_repository()
    original = repository.get_published
    repository.get_published = lambda module_id: SimpleNamespace(revision=99, manifest={"permissions": ["market.read"]})
    try:
        assert client.get("/api/global-intel/static", headers=headers).status_code == 403
    finally:
        repository.get_published = original


@pytest.mark.asyncio
async def test_global_stream_revocation_stops_silent_upstream_and_cleans_up(tmp_path):
    from vibe_visualization_api.global_intelligence_adapter import guard_global_stream

    client, authority, headers = global_cloud_client(tmp_path)
    request = Request({"type": "http", "method": "GET", "scheme": "https", "server": ("c10375.runtime.drlemon.cc", 10443),
                       "path": "/api/global-intel/stream", "query_string": b"", "app": client.app,
                       "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})
    closed = asyncio.Event()

    async def source():
        try:
            yield b'data: {"first":true}\n\n'
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = guard_global_stream(request, source(), interval=0.01)
    assert b'"first":true' in await anext(stream)
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    terminal = await asyncio.wait_for(anext(stream), timeout=1)
    assert b'event: error' in terminal and b'"unauthorized"' in terminal
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_global_stream_over_real_http_is_progressive_and_revocable(tmp_path):
    import socket
    import uvicorn
    from vibe_visualization_api.global_intelligence_adapter import guard_global_stream

    client, authority, headers = global_cloud_client(tmp_path)
    closed = asyncio.Event()

    class Source:
        async def stream(self, path):
            try:
                yield b'data: {"step":1,"synthetic":true}\n\n'
                await asyncio.Event().wait()  # A real open connection, not an aggregated response.
            finally:
                closed.set()

    client.app.state.global_intel_client = Source()
    client.app.state.global_stream_guard = lambda request, chunks: guard_global_stream(request, chunks, interval=0.02)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, lifespan="off", log_level="critical", access_log=False, proxy_headers=False))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if serving.done():
                    await serving
                    raise AssertionError("isolated HTTP server exited before listening")
                await asyncio.sleep(0.01)
            async with httpx.AsyncClient(trust_env=False, timeout=2) as transport:
                async with transport.stream("GET", f"http://127.0.0.1:{port}/api/global-intel/stream", headers=headers) as response:
                    assert response.status_code == 200
                    lines = response.aiter_lines()
                    assert await anext(lines) == 'data: {"step":1,"synthetic":true}'
                    assert not closed.is_set()
                    authority.state.revoked = True
                    client.app.state.website_auth.cache.clear()
                    remaining = [line async for line in lines]
                    assert "event: error" in remaining
                    assert any('"unauthorized"' in line for line in remaining)
            await asyncio.wait_for(closed.wait(), timeout=1)
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=3)
        listener.close()


@pytest.mark.parametrize("topic,module_id,factor", [
    ("fed-rates", "fed-rates", "inflation"),
    ("hormuz", "hormuz-conflict", "shipping"),
    ("us-china-trade", "us-china-trade", "controls"),
])
def test_global_topic_reads_and_forecasts_bind_to_authoritative_workspace(tmp_path, topic, module_id, factor):
    import sqlite3
    from pathlib import Path
    from tests.mod_storage.test_routes import _manifest
    from vibe_visualization_api.global_topics.store import GlobalTopicStore

    client, _, _ = global_cloud_client(tmp_path)
    app = client.app

    async def verify(route, payload):
        user = {"synthetic-a": "a", "synthetic-b": "b"}.get(payload["token"])
        if user is None:
            raise HTTPException(401)
        return identity(userId=user, workspaceId=f"newma-{user}-c10375")

    async def snapshot(_topic):
        return {}  # No provider/network calls; public evidence intentionally unavailable.

    app.state.website_auth.post = verify
    app.state.global_topic_sources = SimpleNamespace(snapshot=snapshot)
    client.cookies.set(COOKIE, "synthetic-a")
    origin = {"Origin": DESK_ORIGIN}
    definition = json.loads((Path(__file__).resolve().parents[3] / "mods" / module_id / "mod.json").read_text())
    manifest = _manifest(module_id)
    manifest.pop("storage")
    manifest["version"] = definition["version"]
    manifest["permissions"] = definition["manifest"]["permissions"]
    manifest["actions"] = definition["manifest"]["actions"]
    draft = client.post("/api/mods/drafts", headers=origin, json=manifest)
    assert draft.status_code == 201, draft.text
    assert client.post(f"/api/mods/{module_id}/revisions/{draft.json()['revision']}/publish", headers=origin).status_code == 200
    database = app.state.global_intelligence_settings.database_path
    GlobalTopicStore(database).save_forecast(topic, "old-local", {}, {"legacy": True})
    endpoint = f"/api/global-topics/{topic}"
    for user, value in (("a", 25), ("b", 75)):
        client.cookies.set(COOKIE, f"synthetic-{user}")
        issued = client.post(f"/api/mods/{module_id}/sessions", headers=origin,
                             json={"instanceId": f"topic-{user}", "workspaceId": f"newma-{user}-c10375"})
        assert issued.status_code == 201, issued.text
        client.cookies.clear()
        headers = {"Origin": DESK_ORIGIN.replace("10443", "10444"),
                   "Authorization": "Bearer " + issued.json()["accessToken"], "X-Newma-Desk-Instance-Id": f"topic-{user}"}
        assert client.get(endpoint, headers=headers).status_code == 200
        result = client.post(endpoint + "/forecast", json={"factors": {factor: value}}, headers=headers)
        assert result.status_code == 200, result.text
        assert "不代表真实发生概率" in result.json()["disclaimer"]
        assert client.get(endpoint).status_code == 401
        assert client.post(endpoint + "/forecast", json={"factors": {}, "workspaceId": "forged"}, headers=headers).status_code == 403
        assert client.post(endpoint + "/forecast", json={"factors": {"unknown": 10}}, headers=headers).status_code == 422
        for invalid in (-1, 101, True, "50"):
            assert client.post(endpoint + "/forecast", json={"factors": {factor: invalid}}, headers=headers).status_code == 422
        other = "hormuz" if topic != "hormuz" else "fed-rates"
        assert client.get(f"/api/global-topics/{other}", headers=headers).status_code == 403
        assert client.post(f"/api/global-topics/{other}/forecast", json={"factors": {}}, headers=headers).status_code == 403
        # A correctly bound, read-only grant can view but cannot save a forecast.
        sessions = app.state.mod_session_service
        token, _ = sessions.issue(instance_id=f"topic-{user}", user_id=user, workspace_id=f"newma-{user}-c10375",
                                  module_id=module_id, revision=draft.json()["revision"], actions=[], permissions=["market.read"])
        app.state.website_auth.bind(sessions.validate(token), f"synthetic-{user}")
        read_only = {**headers, "Authorization": "Bearer " + token}
        assert client.get(endpoint, headers=read_only).status_code == 200
        assert client.post(endpoint + "/forecast", json={"factors": {}}, headers=read_only).status_code == 403
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT topic_id, created_at FROM global_topic_forecasts").fetchall() == [(topic, "old-local")]
        rows = connection.execute("SELECT user_id, workspace_id, topic_id, factors_json FROM global_topic_scoped_forecasts ORDER BY id").fetchall()
    assert [(row[0], row[1], row[2]) for row in rows] == [("a", "newma-a-c10375", topic), ("b", "newma-b-c10375", topic)]
    assert [json.loads(row[3])[factor] for row in rows] == [25, 75]
    assert all(len(json.loads(row[3])) == 3 for row in rows)  # Include actual default assumptions for reproducibility.
