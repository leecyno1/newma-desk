"""Scoped mode is opt-in; failed Desk verification must never read local products."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from seven_cycle_platform.api.desk_access import install_desk_access, verify_with_desk

SCOPE_URL = "http://127.0.0.1:8911/api/mods/runtime/cycle-scope"
HEADERS = {"Authorization": "Bearer synthetic", "X-Newma-Desk-Instance-Id": "one"}


def make_client(monkeypatch, endpoint=SCOPE_URL):
    monkeypatch.setenv("SEVEN_CYCLE_DESK_SCOPE_URL", endpoint)
    app = FastAPI()
    install_desk_access(app)
    app.state.reads = []
    app.state.checks = []

    def verify(*args):
        app.state.checks.append(args)
        return 200

    app.state.cycle_desk_verifier = verify

    @app.get("/{path:path}")
    async def read(path):
        app.state.reads.append(path)
        return {"synthetic": True}

    return TestClient(app)


def test_attached_runtime_never_uses_cookie_or_anonymous_native_data(monkeypatch):
    client = make_client(monkeypatch)
    for path in ("/data/cycle-research.json", "/v1/assets/a/attribution?horizon=12", "/data/deployment.json"):
        assert client.get(path, headers={"Cookie": "synthetic=logged-in"}).status_code == 401
    assert client.app.state.reads == []
    response = client.get("/data/cycle-research.json", headers={**HEADERS, "Cookie": "private", "X-User-Id": "forged"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert client.app.state.checks == [(SCOPE_URL, "Bearer synthetic", "one", {
        "method": "GET", "path": "/data/cycle-research.json", "query": "",
    })]
    for status in (401, 403, 503):
        client.app.state.cycle_desk_verifier = lambda *_: status
        assert client.get("/data/cycle-research.json", headers=HEADERS).status_code == status
    assert client.app.state.reads == ["data/cycle-research.json"]


def test_only_canonical_page_assets_are_public_and_bad_headers_cannot_fallback(monkeypatch):
    client = make_client(monkeypatch)
    for path in ("/", "/cycles", "/assets/main-test.js", "/circle-mark.svg", "/healthz"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers['x-cycle-access-mode'] == 'desk-required'
    for path in ("/assets/%2e%2e/data/cycle-research.json", "/assets/data.json", "/data//cycle-research.json", "/v1/assets"):
        assert client.get(path).status_code == 401
    assert client.get("/data/cycle-research.json", headers={**HEADERS, "X-Newma-Dock-Instance-Id": "conflict"}).status_code == 401
    local = make_client(monkeypatch, "")
    assert local.get('/healthz').headers['x-cycle-access-mode'] == 'standalone'
    assert local.get("/data/cycle-research.json").status_code == 200
    assert local.get("/data/cycle-research.json", headers=HEADERS).status_code == 503
    assert local.get("/data/cycle-research.json", headers={"Authorization": ""}).status_code == 401


@pytest.mark.parametrize("endpoint", ["https://other.example/api/mods/runtime/cycle-scope", "http://127.0.0.1:8911/api/private", "http://user@localhost/api/mods/runtime/cycle-scope", SCOPE_URL + "?token=x"])
def test_validator_configuration_is_exact_loopback(monkeypatch, endpoint):
    with pytest.raises(ValueError):
        make_client(monkeypatch, endpoint)


def test_verifier_over_http_does_not_forward_cookies_or_follow_redirects():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/unexpected')
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"userId":"a","workspaceId":"b"}')

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    target = {'method': 'GET', 'path': '/data/cycle-research.json', 'query': ''}
    try:
        assert verify_with_desk(base + '/scope', 'Bearer synthetic', 'one', target) == 200
        assert verify_with_desk(base + '/redirect', 'Bearer synthetic', 'one', target) == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert [call[0] for call in calls] == ['/scope', '/redirect']
    assert calls[0][2] == target
    assert not any(key.lower() in {'cookie', 'x-user-id', 'x-workspace-id', 'origin'} for key in calls[0][1])
