import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.public_demo.app import MODULE_IDS, create_app


@pytest.fixture
def public_client():
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("module_id", sorted(MODULE_IDS))
def test_five_pages_have_distinct_readonly_content(public_client, module_id):
    page = public_client.get("/demo/", params={"mod": module_id})
    assert page.status_code == 200
    assert "/demo/assets/demo.js" in page.text
    result = public_client.get(f"/demo/api/modules/{module_id}")
    payload = result.json()
    assert result.status_code == 200
    assert payload["moduleId"] == module_id
    assert payload["mode"] == "public-readonly"
    if module_id in {"instock-industry-chain", "orchestra-committee"}:
        assert payload["dataKind"] == "illustrative" and payload["asOf"] is None
        assert payload["ready"] is False
    else:
        assert payload["dataKind"] in {"public-snapshot", "research-snapshot"}
        assert payload["asOf"] and payload["content"]["provenance"]
    assert payload["content"]["notice"]
    assert len(payload["content"]["chart"]["labels"]) == len(payload["content"]["chart"]["values"])
    assert payload["content"]["sections"] and payload["content"]["sources"]
    assert "set-cookie" not in result.headers


def test_no_account_or_workspace_is_used(public_client):
    endpoint = "/demo/api/modules/orchestra-committee"
    expected = public_client.get(endpoint).json()
    result = public_client.get(endpoint + "?workspaceId=private&userId=owner", headers={
        "Cookie": "__Host-newma_desk_session=synthetic-private-token",
        "Authorization": "Bearer synthetic-admin-token",
        "X-User-Id": "owner", "X-Workspace-Id": "private",
    })
    assert result.json() == expected
    assert "synthetic-private" not in result.text
    assert "set-cookie" not in result.headers
    assert not hasattr(public_client.app.state, "website_auth")
    assert not hasattr(public_client.app.state, "resolve_module_repository")


def test_public_snapshots_keep_original_dates_and_limits(public_client):
    market = public_client.get("/demo/api/modules/market-daily").json()
    assert market["asOf"] == "2026-09" and market["live"] is False
    assert market["content"]["chart"]["labels"][-1] == "2026-09"
    assert "2026-10" not in market["content"]["chart"]["labels"]
    cycle = public_client.get("/demo/api/modules/seven-cycle-research").json()
    assert cycle["asOf"] == "2026-08" and cycle["dataKind"] == "research-snapshot"
    assert cycle["content"]["chart"]["values"][-1] == -0.06944
    assert "真实历史发布版本" in cycle["content"]["notice"]
    world = public_client.get("/demo/api/modules/global-situation").json()
    assert world["asOf"] == "2026-10-22T12:09:05Z"
    assert world["content"]["chart"]["values"] == [4.9, 4.6, 4.5, 4.6, 4.8]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_server_rejects_execution_and_writes(public_client, method):
    for endpoint in ("/demo/api/modules/market-daily", "/demo/api/actions/run", "/api/agents/tasks", "/api/mods/sessions"):
        response = public_client.request(method, endpoint, json={"prompt": "do not execute"})
        assert response.status_code == 405
        assert response.headers["allow"] == "GET, HEAD"


@pytest.mark.parametrize("path", [
    "/demo/?mod=portfolio-risk", "/demo/?mod=unknown", "/demo/api/modules/portfolio-risk",
    "/demo/api/modules/market-daily/execute", "/demo/api/research/myreports",
    "/api/auth/session", "/api/mods", "/api/research/myreports", "/api/orchestra/history",
    "/demo/assets/content.json", "/demo/assets/app.py", "/docs", "/openapi.json", "/",
])
def test_no_fallback_or_private_routes(public_client, path):
    assert public_client.get(path).status_code == 404


def test_page_rejects_scope_and_duplicate_module_selection(public_client):
    assert public_client.get("/demo/?mod=market-daily&workspaceId=private").status_code == 400
    assert public_client.get("/demo/?mod=market-daily&mod=orchestra-committee").status_code == 400


def test_status_contract_and_exact_material_origin(public_client):
    status = public_client.get("/demo/status.json", headers={"Origin": "http://127.0.0.1:8766"})
    assert status.json()["contract"] == "newma-desk.public-demo.v1"
    assert status.json()["mode"] == "readonly"
    assert {row["id"] for row in status.json()["modules"]} == MODULE_IDS
    for row in status.json()["modules"]:
        if row["ready"]:
            assert row["dataKind"] in {"public-snapshot", "research-snapshot"} and row["asOf"]
        if row["dataKind"] == "illustrative":
            assert row["ready"] is False
    assert status.headers["access-control-allow-origin"] == "http://127.0.0.1:8766"
    assert "access-control-allow-credentials" not in status.headers
    for origin in ("null", "https://evil.invalid", "http://127.0.0.1:87660"):
        response = public_client.get("/demo/status.json", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in public_client.get("/demo/api/modules/market-daily", headers={"Origin": "http://127.0.0.1:8766"}).headers


def test_static_assets_and_security_headers(public_client):
    for path, media in (("/demo/", "text/html"), ("/demo/assets/demo.js", "text/javascript"), ("/demo/assets/demo.css", "text/css")):
        response = public_client.get(path)
        assert response.status_code == 200
        assert media in response.headers["content-type"]
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'self' http://127.0.0.1:8766" in response.headers["content-security-policy"]
        assert "unsafe-inline" not in response.headers["content-security-policy"]
        assert "set-cookie" not in response.headers
    script = public_client.get("/demo/assets/demo.js").text
    assert 'credentials: "omit"' in script
    assert "innerHTML" not in script
    assert "localStorage" not in script and "postMessage" not in script
    assert public_client.head("/demo/status.json").status_code == 200
    assert public_client.head("/demo/status.json").content == b""
