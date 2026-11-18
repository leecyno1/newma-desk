import httpx
import pytest
from types import SimpleNamespace

from vibe_visualization_api.config import Settings
from tests.test_website_auth import global_cloud_client, USER, WORKSPACE
from tests.mod_storage.test_routes import _manifest, _publish, _session_headers


@pytest.mark.asyncio
async def test_callback_rechecks_real_website_identity_and_published_grant(tmp_path):
    client, authority, headers = global_cloud_client(tmp_path)
    headers.pop("Origin")
    target = {"method": "GET", "path": "/api/crucix/snapshot"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app, client=("127.0.0.1", 50000)), base_url="http://desk") as callback:
        endpoint = "/api/mods/runtime/global-scope"
        response = await callback.post(endpoint, json=target, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {"userId": USER, "workspaceId": WORKSPACE}
        assert response.headers["cache-control"] == "private, no-store"
        assert (await callback.post(endpoint, json=target)).status_code == 401
        assert (await callback.post(endpoint, json={"method": "GET", "path": "/api/global-topics/fed-rates"}, headers=headers)).status_code == 403
        assert (await callback.post(endpoint, json={"method": "POST", "path": target["path"]}, headers=headers)).status_code == 403
        assert (await callback.post(endpoint, json=target, headers={**headers, "X-Newma-Desk-Instance-Id": "wrong"})).status_code == 403
        repository = client.app.state.resolve_module_repository()
        original = repository.get_published
        repository.get_published = lambda _: SimpleNamespace(revision=99, manifest={"permissions": ["market.read"]})
        assert (await callback.post(endpoint, json=target, headers=headers)).status_code == 403
        repository.get_published = original
        authority.state.revoked = True
        client.app.state.website_auth.cache.clear()
        assert (await callback.post(endpoint, json=target, headers=headers)).status_code == 401


def test_callback_requires_session_even_in_local_desk(client):
    endpoint = "/api/mods/runtime/global-scope"
    target = {"method": "POST", "path": "/api/global-topics/fed-rates/forecast"}
    assert client.post(endpoint, json=target).status_code == 401
    manifest = _manifest("fed-rates")
    manifest.pop("storage")
    manifest["permissions"] = ["market.read", "storage.write"]
    _publish(client, manifest)
    headers = _session_headers(client, module_id="fed-rates")
    assert client.post(endpoint, json=target, headers=headers).json() == {"userId": "user-a", "workspaceId": "workspace-a"}
    readonly, _ = client.app.state.mod_session_service.issue(instance_id="instance-a", user_id="user-a",
        workspace_id="workspace-a", module_id="fed-rates", revision=1, actions=[], permissions=["market.read"])
    assert client.post(endpoint, json=target, headers={**headers, "Authorization": "Bearer " + readonly}).status_code == 403


@pytest.mark.parametrize("value", ["https://example.com", "http://127.0.0.1/api", "http://user@localhost:1", "http://localhost:1?x=y"])
def test_remote_config_cannot_send_sessions_to_external_address(value):
    with pytest.raises(ValueError):
        Settings(global_intelligence_api_url=value)


@pytest.mark.parametrize("status,content,expected", [
    (200, b'{"independent":true}', 200), (200, b'<html>not JSON</html>', 503), (200, b'null', 503),
    (302, b'private upstream address', 503), (401, b'private upstream token', 401),
    (422, b'private validation details', 422), (500, b'private upstream traceback', 503),
])
def test_proxy_uses_only_explicit_service_and_never_falls_back(tmp_path, monkeypatch, status, content, expected):
    from fastapi.testclient import TestClient
    from vibe_visualization_api.main import create_app
    import vibe_visualization_api.global_intelligence_proxy as proxy

    app = create_app(Settings(_env_file=None, runtime_dir=tmp_path, database_path=tmp_path / "desk.db",
                             enable_domain_suites=False, global_intelligence_api_url="http://127.0.0.1:18952"))
    client = TestClient(app)
    manifest = _manifest("fed-rates")
    manifest.pop("storage")
    manifest["permissions"] = ["market.read", "storage.write"]
    _publish(client, manifest)
    headers = _session_headers(client, module_id="fed-rates")
    sent = []

    def upstream(request):
        sent.append(request)
        assert str(request.url) == "http://127.0.0.1:18952/api/global-topics/fed-rates/forecast"
        assert request.headers["authorization"] == headers["Authorization"]
        assert request.headers.get("x-user-id") is None
        assert request.headers.get("cookie") is None
        assert request.content == b'{"factors":{"inflation":20}}'
        return httpx.Response(status, content=content, headers={"Location": "http://outside.invalid/"})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(upstream), **kwargs))
    endpoint = "/api/global-topics/fed-rates/forecast"
    response = client.post(endpoint, headers={**headers, "X-User-Id": "forged", "Cookie": "do-not-forward"},
                           json={"factors": {"inflation": 20}})
    assert response.status_code == expected, response.text
    assert len(sent) == 1
    assert "private" not in response.text
    if expected == 200:
        assert response.json() == {"independent": True}
        assert response.headers["cache-control"] == "no-store"
    assert client.post(endpoint, json={}).status_code == 401
    assert len(sent) == 1
    # Proxy mode did not create a local domain forecast as a substitute.
    import sqlite3
    with sqlite3.connect(tmp_path / "desk.db") as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'global_topic%'").fetchall() == []


def test_proxy_preserves_partial_stream_and_identifies_domain_disconnect(tmp_path, monkeypatch, caplog):
    from fastapi.testclient import TestClient
    from vibe_visualization_api.main import create_app
    import vibe_visualization_api.global_intelligence_proxy as proxy

    app = create_app(Settings(_env_file=None, runtime_dir=tmp_path, database_path=tmp_path / "desk.db",
                             enable_domain_suites=False, global_intelligence_api_url="http://127.0.0.1:18952"))
    client = TestClient(app)
    manifest = _manifest("global-situation")
    manifest.pop("storage")
    manifest["permissions"] = ["market.read"]
    _publish(client, manifest)
    headers = _session_headers(client, module_id="global-situation")

    class BrokenStream(httpx.AsyncByteStream):
        closed = False
        async def __aiter__(self):
            yield b'data: {"_done":1,"_total":48}\n\n'
            raise httpx.RemoteProtocolError("private-token-internal-address")
        async def aclose(self):
            self.closed = True
    body = BrokenStream()
    async_client = httpx.AsyncClient
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kwargs: async_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body, headers={"Content-Type": "text/event-stream"})), **kwargs))
    response = client.get("/api/global-intel/stream", headers=headers)
    assert response.text.startswith('data: {"_done":1')
    assert '"code":"domain_stream_disconnected"' in response.text
    assert '"stage":"desk_proxy"' in response.text
    assert "domain_stream_disconnected" in caplog.text
    assert "private-token-internal-address" not in response.text + caplog.text
    assert body.closed
