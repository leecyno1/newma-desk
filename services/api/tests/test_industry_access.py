"""Actual Desk routers and declaration; synthetic authority and collectors only."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.test_website_auth import COOKIE, DESK_ORIGIN, TOKEN, USER, WORKSPACE, make_app
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api import industry_research, industry_production, industry_prices, industry_capacity

MODULE = "industry-prosperity"
PATHS = ["/api/industry-research", "/api/industry-research/history",
         "/api/industry-research/production?period=2026-06", "/api/industry-research/prices?period=2026-06",
         "/api/industry-research/capacity?period=2026-06"]


@pytest.fixture
def industry_client(tmp_path, monkeypatch):
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path / "industry.db",
                              enable_domain_suites=False, website_auth_enabled=True,
                              mod_admission_allowlist=MODULE))
    authority = make_app()
    app.state.website_auth.post = authority.state.website_auth.post
    calls = []

    async def collect(*_):
        calls.append("read")
        return {"synthetic": True, "publications": []}

    for module, name in [(industry_research, "collect"), (industry_research, "collect_history"),
                         (industry_production, "collect_production"), (industry_prices, "collect_prices"),
                         (industry_capacity, "collect_capacity")]:
        monkeypatch.setattr(module, name, collect)
    monkeypatch.setattr(industry_research, "_cache", None)
    monkeypatch.setattr(industry_research, "_history_cache", None)
    for module in (industry_production, industry_prices, industry_capacity):
        monkeypatch.setattr(module, "_cache", {})
    client = TestClient(app, base_url=DESK_ORIGIN)
    client.cookies.set(COOKIE, TOKEN)
    origin = {"Origin": DESK_ORIGIN}
    definition = json.loads((Path(__file__).resolve().parents[3] / "mods" / MODULE / "mod.json").read_text())
    manifest = {**definition["manifest"], "id": MODULE, "name": definition["name"], "version": definition["version"],
                "entry": {"type": "external", "url": "https://c10375.runtime.drlemon.cc:10444/mod-runtime/industry-research/"}}
    draft = client.post("/api/mods/drafts", json=manifest, headers=origin)
    assert draft.status_code == 201, draft.text
    revision = draft.json()["revision"]
    assert client.post(f"/api/mods/{MODULE}/revisions/{revision}/publish", headers=origin).status_code == 200
    issued = client.post(f"/api/mods/{MODULE}/sessions", headers=origin,
                         json={"instanceId": "industry-one", "workspaceId": WORKSPACE})
    assert issued.status_code == 201, issued.text
    headers = {"Authorization": "Bearer " + issued.json()["accessToken"],
               "X-Newma-Desk-Instance-Id": "industry-one", "Origin": DESK_ORIGIN.replace("10443", "10444")}
    client.cookies.clear()
    yield client, authority, headers, calls
    client.close()


@pytest.mark.parametrize("path", PATHS)
def test_five_reads_require_bound_mod_not_cookie(industry_client, path):
    client, _, headers, calls = industry_client
    assert client.get(path).status_code == 401
    client.cookies.set(COOKIE, TOKEN)
    assert client.get(path, headers={"Origin": DESK_ORIGIN}).status_code == 401
    assert not calls
    client.cookies.clear()
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["synthetic"] is True
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == ["read"]


@pytest.mark.parametrize("mod,permissions", [("news-radar", ["market.read"]), (MODULE, ["storage.read"])])
def test_other_mod_or_missing_read_grant_cannot_use_industry(industry_client, mod, permissions):
    client, _, headers, calls = industry_client
    service = client.app.state.mod_session_service
    token, _ = service.issue(instance_id="industry-one", user_id=USER, workspace_id=WORKSPACE,
                             module_id=mod, revision=1, actions=[], permissions=permissions)
    client.app.state.website_auth.bind(service.validate(token), TOKEN)
    for path in PATHS:
        assert client.get(path, headers={**headers, "Authorization": "Bearer " + token}).status_code == 403
    assert not calls


def test_rejects_bad_instance_stale_revision_revocation_and_non_read(industry_client):
    client, authority, headers, calls = industry_client
    assert client.get(PATHS[0], headers={**headers, "X-Newma-Desk-Instance-Id": "other"}).status_code == 403
    assert client.get(PATHS[0], headers={**headers, "X-Vibedesk-Instance-Id": "other"}).status_code == 400
    assert client.post(PATHS[0], headers=headers).status_code == 403
    assert client.get("/api/industry-research/private", headers=headers).status_code == 403
    repository = client.app.state.resolve_module_repository()
    original = repository.get_published
    repository.get_published = lambda _: SimpleNamespace(revision=999, manifest={"permissions": ["market.read"]})
    assert client.get(PATHS[0], headers=headers).status_code == 403
    repository.get_published = lambda _: SimpleNamespace(revision=1, manifest={"permissions": []})
    assert client.get(PATHS[0], headers=headers).status_code == 403
    repository.get_published = original
    repository._allowed_module_ids = frozenset({"news-radar"})
    assert client.get(PATHS[0], headers=headers).status_code == 403
    repository._allowed_module_ids = frozenset({MODULE})
    authority.state.revoked = True
    client.app.state.website_auth.cache.clear()
    assert client.get(PATHS[0], headers=headers).status_code == 401
    assert not calls


def test_local_public_read_remains_but_broken_signed_headers_never_fallback(industry_client):
    client, _, _, calls = industry_client
    client.app.state.website_auth.enabled = False
    for headers in ({"Authorization": "Bearer invalid"}, {"X-Newma-Desk-Instance-Id": "orphan"},
                    {"X-Vibedesk-Instance-Id": "orphan"}, {"Authorization": ""}):
        assert client.get(PATHS[0], headers=headers).status_code == 401
    assert not calls
    assert client.get(PATHS[0]).status_code == 200
    assert calls == ["read"]
