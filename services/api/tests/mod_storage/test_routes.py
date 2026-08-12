from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def _manifest(module_id: str = "research-notes", *, max_item_kb: int = 700):
    return {
        "schemaVersion": "1.1",
        "id": module_id,
        "name": "研究笔记",
        "version": "1.0.0",
        "category": "research",
        "entry": {"type": "structured", "url": f"/mods/{module_id}/"},
        "compatibility": {
            "level": 2,
            "bridgeProtocol": "1.0",
            "sdkVersion": "^0.2.0",
        },
        "permissions": ["storage.read", "storage.write"],
        "dataServices": [],
        "storage": {
            "mode": "desk-managed",
            "namespaces": [
                {
                    "id": "settings",
                    "scope": "user-workspace",
                    "schemaVersion": 1,
                    "quotaMb": 1,
                    "maxItemKb": max_item_kb,
                },
                {
                    "id": "notes",
                    "scope": "user-workspace",
                    "schemaVersion": 3,
                    "quotaMb": 2,
                    "maxItemKb": 256,
                },
            ],
        },
        "actions": {},
        "events": {"emits": [], "accepts": []},
    }


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "desk.db",
        enable_domain_suites=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _publish(client: TestClient, manifest: dict):
    draft = client.post("/api/mods/drafts", json=manifest)
    assert draft.status_code == 201, draft.text
    revision = draft.json()["revision"]
    published = client.post(
        f"/api/mods/{manifest['id']}/revisions/{revision}/publish"
    )
    assert published.status_code == 200, published.text


def _session_headers(
    client: TestClient,
    *,
    module_id: str = "research-notes",
    user_id: str = "user-a",
    workspace_id: str = "workspace-a",
    instance_id: str = "instance-a",
):
    response = client.post(
        f"/api/mods/{module_id}/sessions",
        headers={"X-User-Id": user_id},
        json={"instanceId": instance_id, "workspaceId": workspace_id},
    )
    assert response.status_code == 201, response.text
    return {
        "Authorization": f"Bearer {response.json()['accessToken']}",
        "X-Newma-Desk-Instance-Id": instance_id,
    }


def test_storage_crud_pagination_and_revision_conflicts(client: TestClient):
    _publish(client, _manifest())
    headers = _session_headers(client)
    base = "/api/mods/research-notes/storage/notes"

    first = client.put(
        f"{base}/note-1",
        headers=headers,
        json={"expectedRevision": 0, "value": {"title": "第一条"}},
    )
    second = client.put(
        f"{base}/note-2",
        headers=headers,
        json={"expectedRevision": 0, "value": {"title": "第二条"}},
    )

    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert first.json()["schemaVersion"] == 3
    assert second.status_code == 200
    stale = client.put(
        f"{base}/note-1",
        headers=headers,
        json={"expectedRevision": 0, "value": {"title": "覆盖"}},
    )
    assert stale.status_code == 409

    page_one = client.get(f"{base}?limit=1", headers=headers)
    assert [item["key"] for item in page_one.json()["items"]] == ["note-1"]
    assert page_one.json()["nextCursor"] == "note-1"
    page_two = client.get(
        f"{base}?limit=1&cursor=note-1",
        headers=headers,
    )
    assert [item["key"] for item in page_two.json()["items"]] == ["note-2"]
    assert "nextCursor" not in page_two.json()

    updated = client.put(
        f"{base}/note-1",
        headers=headers,
        json={"expectedRevision": 1, "value": {"title": "已更新"}},
    )
    assert updated.json()["revision"] == 2
    assert client.get(f"{base}/note-1", headers=headers).json()["value"] == {
        "title": "已更新"
    }
    assert client.delete(
        f"{base}/note-1?expectedRevision=1",
        headers=headers,
    ).status_code == 409
    assert client.delete(
        f"{base}/note-1?expectedRevision=2",
        headers=headers,
    ).status_code == 204
    assert client.get(f"{base}/note-1", headers=headers).status_code == 404


def test_storage_isolated_by_session_scope_and_declared_namespace(
    client: TestClient,
):
    _publish(client, _manifest())
    workspace_a = _session_headers(client)
    workspace_b = _session_headers(
        client,
        workspace_id="workspace-b",
        instance_id="instance-b",
    )
    endpoint = "/api/mods/research-notes/storage/settings/layout"

    assert client.put(
        endpoint,
        headers=workspace_a,
        json={"expectedRevision": 0, "value": {"density": "compact"}},
    ).status_code == 200
    assert client.get(endpoint, headers=workspace_b).status_code == 404
    assert client.get(
        "/api/mods/research-notes/storage/private/key",
        headers=workspace_a,
    ).status_code == 403
    assert client.get(endpoint).status_code == 401


def test_storage_enforces_item_and_namespace_quota(client: TestClient):
    _publish(client, _manifest())
    headers = _session_headers(client)
    endpoint = "/api/mods/research-notes/storage/settings"
    payload = "x" * 600_000

    assert client.put(
        f"{endpoint}/first",
        headers=headers,
        json={"expectedRevision": 0, "value": payload},
    ).status_code == 200
    assert client.put(
        f"{endpoint}/second",
        headers=headers,
        json={"expectedRevision": 0, "value": payload},
    ).status_code == 413

    _publish(client, _manifest("tiny-storage", max_item_kb=1))
    tiny_headers = _session_headers(client, module_id="tiny-storage")
    assert client.put(
        "/api/mods/tiny-storage/storage/settings/too-large",
        headers=tiny_headers,
        json={"expectedRevision": 0, "value": "x" * 2_000},
    ).status_code == 413
