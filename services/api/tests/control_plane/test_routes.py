from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "市场行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/mods/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def _path_snapshot(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def test_module_must_be_published_before_sidebar_listing(
    client: TestClient,
) -> None:
    draft_response = client.post("/api/modules/drafts", json=MANIFEST)

    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert client.get("/api/modules").json() == []

    response = client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )

    assert response.status_code == 200
    assert client.get("/api/modules").json()[0]["manifest"]["id"] == (
        "market-daily"
    )


def test_mod_api_is_canonical_and_legacy_module_routes_remain_compatible(
    client: TestClient,
) -> None:
    draft = client.post("/api/mods/drafts", json=MANIFEST).json()
    published = client.post(
        f"/api/mods/market-daily/revisions/{draft['revision']}/publish"
    )

    assert published.status_code == 200
    assert client.get("/api/mods").json() == client.get("/api/modules").json()


def test_app_factory_settings_drive_repository_dependency(
    tmp_path: Path,
) -> None:
    default_database_path = Path("runtime/vibe-visualization.db")
    default_database_before = _path_snapshot(default_database_path)
    database_path = tmp_path / "factory-settings.db"
    application = create_app(
        Settings(runtime_dir=tmp_path, database_path=database_path)
    )

    try:
        with TestClient(application) as client:
            response = client.post("/api/modules/drafts", json=MANIFEST)
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 201
    assert database_path.exists()
    assert _path_snapshot(default_database_path) == default_database_before


def test_parallel_registry_reads_and_writes_do_not_lock_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "parallel-registry.db"
    application = create_app(
        Settings(runtime_dir=tmp_path, database_path=database_path)
    )

    def request(client: TestClient, index: int) -> int:
        if index % 3:
            return client.get("/api/mods").status_code
        manifest = {
            **MANIFEST,
            "id": f"parallel-mod-{index}",
            "name": f"Parallel Mod {index}",
        }
        return client.post("/api/mods/drafts", json=manifest).status_code

    with TestClient(application) as client:
        with ThreadPoolExecutor(max_workers=12) as executor:
            statuses = list(
                executor.map(lambda index: request(client, index), range(60))
            )

    assert set(statuses) <= {200, 201}
    assert database_path.exists()


def test_get_exact_revision_preserves_camel_case_manifest(
    client: TestClient,
) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()

    response = client.get(
        f"/api/modules/market-daily/revisions/{draft['revision']}"
    )

    assert response.status_code == 200
    assert response.json() == draft
    assert response.json()["moduleId"] == "market-daily"
    assert response.json()["manifest"]["schemaVersion"] == "1.0"
    assert response.json()["manifest"]["dataServices"] == ["market-data"]
    assert response.json()["manifest"]["agentCapabilities"] == []
    assert "schema_version" not in response.json()["manifest"]


def test_navigation_metadata_survives_draft_storage(client: TestClient) -> None:
    navigation = {
        "groupLabel": "市场",
        "groupOrder": 20,
        "itemOrder": 10,
        "label": "行情",
        "directory": {
            "id": "market-suite",
            "label": "市场工具",
            "order": 5,
        },
        "icon": "market",
    }

    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "navigation": navigation},
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["navigation"] == navigation


@pytest.mark.parametrize("icon", ["today", "trading", "settings"])
def test_first_party_navigation_icons_are_accepted(
    client: TestClient, icon: str
) -> None:
    response = client.post(
        "/api/mods/drafts",
        json={
            **MANIFEST,
            "id": f"{icon}-workspace",
            "navigation": {
                "groupLabel": "工作区",
                "groupOrder": 10,
                "itemOrder": 10,
                "icon": icon,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["navigation"]["icon"] == icon


def test_disable_removes_module_from_sidebar_listing(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert client.get("/api/modules").json() == []


def test_rollback_republishes_disabled_prior_revision(
    client: TestClient,
) -> None:
    first = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/publish"
    )
    second = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "version": "0.2.0"},
    ).json()
    client.post(
        f"/api/modules/market-daily/revisions/{second['revision']}/publish"
    )

    response = client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/rollback"
    )

    assert response.status_code == 200
    assert response.json()["revision"] == first["revision"]
    assert response.json()["status"] == "published"
    assert client.get("/api/modules").json()[0]["revision"] == first["revision"]


def test_rollback_recovers_module_after_disable(client: TestClient) -> None:
    first = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/publish"
    )
    second = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "version": "0.2.0"},
    ).json()
    client.post(
        f"/api/modules/market-daily/revisions/{second['revision']}/publish"
    )
    client.post("/api/modules/market-daily/disable")

    response = client.post(
        f"/api/modules/market-daily/revisions/{first['revision']}/rollback"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["revision"] == first["revision"]
    assert client.get("/api/modules").json() == [response.json()]


def test_missing_revision_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/modules/missing/revisions/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_publish_missing_target_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/revisions/999/publish")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_disable_missing_module_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/disable")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_rollback_missing_target_returns_not_found(client: TestClient) -> None:
    response = client.post("/api/modules/missing/revisions/999/rollback")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_invalid_publish_state_returns_conflict(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    url = (
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )
    client.post(url)

    response = client.post(url)

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_invalid_disable_state_returns_conflict(client: TestClient) -> None:
    client.post("/api/modules/drafts", json=MANIFEST)

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_disabled_module_cannot_be_disabled_again(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
    )
    client.post("/api/modules/market-daily/disable")

    response = client.post("/api/modules/market-daily/disable")

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


def test_invalid_rollback_state_returns_conflict(client: TestClient) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()

    response = client.post(
        f"/api/modules/market-daily/revisions/{draft['revision']}/rollback"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "invalid module state"}


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("version", "1.0"),
        ("entry", {"type": "static", "url": "../secret"}),
        ("entry", {"type": "static", "url": "//evil.example/app"}),
        ("entry", {"type": "static", "url": "/%2e%2e/secret"}),
        ("entry", {"type": "static", "url": "/%252e%252e/secret"}),
        ("entry", {"type": "static", "url": "/%ZZ"}),
        ("entry", {"type": "external", "url": "ftp://example.com/app"}),
        ("entry", {"type": "external", "url": "http://exa mple.com"}),
        ("events", {"emits": ["selected"], "accepts": []}),
        ("refresh", {"mode": "schedule"}),
        ("refresh", {"mode": "manual", "cron": "* * * * *"}),
        ("icon", None),
        ("refresh", None),
        (
            "entry",
            {
                "type": "structured",
                "url": "/modules/market-daily/",
                "sandbox": False,
            },
        ),
    ],
    ids=[
        "semantic-version",
        "relative-url",
        "network-path-url",
        "encoded-traversal-url",
        "repeatedly-encoded-traversal-url",
        "malformed-encoded-url",
        "non-http-external-url",
        "malformed-external-url",
        "unnamespaced-event",
        "scheduled-refresh-without-cron",
        "manual-refresh-with-cron",
        "null-icon",
        "null-refresh",
        "unknown-nested-field",
    ],
)
def test_invalid_manifest_returns_unprocessable_entity(
    client: TestClient,
    change: str,
    value: object,
) -> None:
    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, change: value},
    )

    assert response.status_code == 422


def test_unknown_top_level_manifest_field_returns_unprocessable_entity(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/modules/drafts",
        json={**MANIFEST, "unexpected": True},
    )

    assert response.status_code == 422


def test_python_field_names_are_not_accepted_as_json_aliases(
    client: TestClient,
) -> None:
    manifest = {
        key: value for key, value in MANIFEST.items() if key != "schemaVersion"
    }
    manifest["schema_version"] = "1.0"

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 422


def test_manifest_defaults_are_returned_with_camel_case_aliases(
    client: TestClient,
) -> None:
    minimal_manifest = {
        key: value
        for key, value in MANIFEST.items()
        if key
        not in {"permissions", "dataServices", "agentCapabilities", "events"}
    }

    response = client.post("/api/modules/drafts", json=minimal_manifest)

    assert response.status_code == 201
    assert response.json()["manifest"] == {
        **minimal_manifest,
        "permissions": [],
        "dataServices": [],
        "agentCapabilities": [],
        "events": {"emits": [], "accepts": []},
    }
    assert "refresh" not in response.json()["manifest"]


def test_manifest_1_1_accepts_explicit_action_bindings(
    client: TestClient,
) -> None:
    manifest = {
        "schemaVersion": "1.1",
        "id": "factor-lab",
        "name": "因子实验室",
        "version": "1.0.0",
        "category": "quant",
        "entry": {"type": "external", "url": "https://quant.example/mod"},
        "compatibility": {
            "level": 2,
            "bridgeProtocol": "1.0",
            "sdkVersion": "^0.2.0",
        },
        "permissions": ["quant.execute", "research.read"],
        "dataServices": ["vibe-trading"],
        "actions": {
            "factor.backtest": {
                "binding": {
                    "type": "data",
                    "service": "vibe-trading",
                },
                "execution": "task",
                "permission": "quant.execute",
            },
            "research.explain": {
                "binding": {
                    "type": "agent",
                    "memoryScope": "user-agent-mod",
                },
                "execution": "task",
                "permission": "research.read",
            },
        },
    }

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 201
    stored = response.json()["manifest"]
    assert stored["schemaVersion"] == "1.1"
    assert "agentCapabilities" not in stored
    assert stored["actions"]["research.explain"]["confirmation"] == "none"


@pytest.mark.parametrize(
    "update",
    [
        {
            "compatibility": {
                "level": 3,
                "bridgeProtocol": "1.0",
            }
        },
        {"permissions": []},
        {"dataServices": []},
        {"agentCapabilities": ["research.explain"]},
    ],
)
def test_manifest_1_1_rejects_incomplete_or_legacy_declarations(
    client: TestClient,
    update: dict[str, object],
) -> None:
    manifest = {
        "schemaVersion": "1.1",
        "id": "factor-lab",
        "name": "因子实验室",
        "version": "1.0.0",
        "category": "quant",
        "entry": {"type": "external", "url": "https://quant.example/mod"},
        "compatibility": {
            "level": 3,
            "bridgeProtocol": "1.0",
            "viewSpecVersion": "1.0",
        },
        "permissions": ["quant.execute"],
        "dataServices": ["vibe-trading"],
        "actions": {
            "factor.backtest": {
                "binding": {
                    "type": "data",
                    "service": "vibe-trading",
                },
                "execution": "task",
                "permission": "quant.execute",
            }
        },
        **update,
    }

    response = client.post("/api/modules/drafts", json=manifest)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "structured", "url": "/modules/market-daily/"},
        {"type": "static", "url": "/modules/market-daily/index.html"},
        {"type": "external", "url": "https://example.com/module"},
        {"type": "external", "url": "http:example.com"},
    ],
)
def test_supported_entry_types_are_accepted(
    client: TestClient, entry: dict[str, str]
) -> None:
    response = client.post(
        "/api/modules/drafts", json={**MANIFEST, "entry": entry}
    )

    assert response.status_code == 201
    assert response.json()["manifest"]["entry"] == entry
