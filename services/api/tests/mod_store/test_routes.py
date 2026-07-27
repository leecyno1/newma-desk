import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.mod_store.service import (
    ModStoreDiscoveryError,
    ModStoreSourceError,
)


DESCRIPTOR = {
    "schemaVersion": "1.0",
    "id": "daily-review",
    "name": "每日复盘",
    "description": "把每天的市场变化整理成可持续复用的复盘页面。",
    "version": "0.1.0",
    "publisher": "Newma-Dock",
    "upstream": "https://github.com/simonlin1212/Vibe-Research",
    "tags": ["投研", "复盘"],
    "runtime": {
        "type": "external",
        "baseUrlEnv": "NEWMA_DOCK_INVESTMENT_WEB_URL",
        "defaultBaseUrl": "http://127.0.0.1:5899",
        "route": "/daily-review",
    },
    "manifest": {
        "category": "today",
        "navigation": {
            "groupLabel": "今日",
            "groupOrder": 0,
            "itemOrder": 10,
            "icon": "today",
        },
        "permissions": ["investment.read"],
        "dataServices": ["vibe-investment-native"],
        "agentCapabilities": [],
        "events": {"emits": [], "accepts": []},
    },
}

V1_1_DESCRIPTOR = {
    **DESCRIPTOR,
    "id": "market-daily",
    "name": "市场行情",
    "version": "0.2.0",
    "runtime": {
        "type": "direct",
        "entry": {"type": "structured", "url": "/mods/market-daily/"},
    },
    "manifest": {
        "schemaVersion": "1.1",
        "category": "market",
        "compatibility": {
            "level": 3,
            "bridgeProtocol": "1.0",
            "viewSpecVersion": "1.0",
        },
        "permissions": ["market.read"],
        "dataServices": [],
        "actions": {
            "market.explain": {
                "binding": {
                    "type": "agent",
                    "memoryScope": "user-agent-mod",
                },
                "execution": "task",
                "permission": "market.read",
                "confirmation": "none",
            }
        },
        "events": {"emits": [], "accepts": []},
    },
}

SUITE_DESCRIPTOR = {
    "schemaVersion": "1.0",
    "id": "example-suite",
    "name": "示例项目",
    "description": "由一份 Suite 描述自动生成多个 Mod 页面。",
    "version": "0.1.0",
    "publisher": "Newma-Dock",
    "upstream": "https://github.com/leecyno1/newma-dock",
    "tags": ["Suite"],
    "runtime": {
        "type": "external",
        "baseUrlEnv": "NEWMA_DOCK_INVESTMENT_WEB_URL",
        "defaultBaseUrl": "http://127.0.0.1:5899",
    },
    "manifest": {
        "category": "research",
        "navigation": {
            "groupLabel": "研究",
            "groupOrder": 10,
            "itemOrder": 100,
            "directory": {
                "id": "example-suite",
                "label": "示例项目",
                "order": 10,
            },
            "icon": "research",
        },
        "permissions": [],
        "dataServices": [],
        "agentCapabilities": [],
        "events": {"emits": [], "accepts": []},
    },
    "pages": [
        {
            "id": "example-overview",
            "name": "项目总览",
            "description": "示例项目的总览页面。",
            "route": "/overview",
            "navigation": {"itemOrder": 10, "label": "总览"},
            "manifest": {"permissions": ["research.read"]},
            "defaultInstall": True,
        },
        {
            "id": "example-settings",
            "name": "项目设置",
            "description": "示例项目的设置页面。",
            "route": "/settings",
            "navigation": {
                "itemOrder": 20,
                "label": "设置",
                "icon": "settings",
                "role": "settings",
            },
            "manifest": {"permissions": ["research.settings"]},
        },
    ],
}


def _write_store(
    root: Path,
    descriptor: dict[str, object] = DESCRIPTOR,
) -> Path:
    store_dir = root / "mods"
    mod_id = str(descriptor["id"])
    descriptor_path = store_dir / mod_id / "mod.json"
    descriptor_path.parent.mkdir(parents=True)
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False),
        encoding="utf-8",
    )
    (store_dir / "store.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "id": "newma-dock-official",
                "name": "Newma-Dock 官方 Mod 商店",
                "git": {
                    "repository": "https://github.com/leecyno1/newma-dock",
                    "ref": "main",
                    "pathPrefix": "mods",
                    "mirrors": ["https://gitee.com/leecyno1/newma-dock"],
                    "rawBaseUrls": [
                        "https://raw.githubusercontent.com/leecyno1/newma-dock/main/mods",
                        "https://gitee.com/leecyno1/newma-dock/raw/main/mods",
                    ],
                },
                "mods": [
                    {
                        "id": mod_id,
                        "path": f"{mod_id}/mod.json",
                        "defaultInstall": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return store_dir


def _write_suite_store(root: Path) -> Path:
    store_dir = root / "mods"
    descriptor_path = store_dir / "example-suite" / "suite.json"
    descriptor_path.parent.mkdir(parents=True)
    descriptor_path.write_text(
        json.dumps(SUITE_DESCRIPTOR, ensure_ascii=False),
        encoding="utf-8",
    )
    (store_dir / "store.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "id": "newma-dock-official",
                "name": "Newma-Dock 官方 Mod 商店",
                "git": {
                    "repository": "https://github.com/leecyno1/newma-dock",
                    "ref": "main",
                    "pathPrefix": "mods",
                    "mirrors": [],
                    "rawBaseUrls": [
                        "https://raw.githubusercontent.com/leecyno1/newma-dock/main/mods"
                    ],
                },
                "mods": [],
                "suites": [
                    {
                        "id": "example-suite",
                        "path": "example-suite/suite.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return store_dir


def _write_http_suite_store(
    root: Path,
    *,
    base_url: str = "http://127.0.0.1:5899",
) -> Path:
    store_dir = root / "mods"
    store_dir.mkdir(parents=True)
    (store_dir / "store.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "id": "newma-dock-http-discovery",
                "name": "Newma-Dock HTTP Discovery Store",
                "git": {
                    "repository": "https://github.com/leecyno1/newma-dock",
                    "ref": "main",
                    "pathPrefix": "mods",
                    "mirrors": [],
                    "rawBaseUrls": [
                        "https://raw.githubusercontent.com/leecyno1/newma-dock/main/mods"
                    ],
                },
                "mods": [],
                "suites": [
                    {
                        "id": "example-suite",
                        "discovery": {
                            "type": "http",
                            "baseUrlEnv": "NEWMA_DOCK_INVESTMENT_WEB_URL",
                            "defaultBaseUrl": base_url,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return store_dir


def test_store_lists_local_catalog_and_installs_descriptor_from_git(
    tmp_path: Path,
) -> None:
    fetched_sources: list[tuple[str, str]] = []

    async def fetch_descriptor(catalog, entry):
        fetched_sources.append((catalog.git.repository, entry.path))
        return DESCRIPTOR

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path),
        investment_web_url="https://research.example",
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=fetch_descriptor)
    ) as client:
        available = client.get("/api/store/mods")
        installed = client.post("/api/store/mods/daily-review/install")
        unchanged = client.post("/api/store/mods/daily-review/install")
        catalog_after = client.get("/api/store/mods")

    assert available.status_code == 200
    assert available.json()["mods"][0]["installState"] == "available"
    assert available.json()["mods"][0]["defaultInstall"] is True
    assert installed.status_code == 201
    assert installed.json()["action"] == "installed"
    assert installed.json()["mod"]["manifest"]["entry"]["url"] == (
        "https://research.example/daily-review"
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["action"] == "unchanged"
    assert catalog_after.json()["mods"][0]["installState"] == "installed"
    assert fetched_sources == [
        ("https://github.com/leecyno1/newma-dock", "daily-review/mod.json"),
        ("https://github.com/leecyno1/newma-dock", "daily-review/mod.json"),
    ]


def test_store_rejects_unknown_or_invalid_git_mod(tmp_path: Path) -> None:
    async def invalid_descriptor(catalog, entry):
        return {**DESCRIPTOR, "id": "other-mod"}

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path),
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=invalid_descriptor)
    ) as client:
        missing = client.post("/api/store/mods/missing/install")
        invalid = client.post("/api/store/mods/daily-review/install")

    assert missing.status_code == 404
    assert invalid.status_code == 422


def test_store_installs_manifest_1_1_with_explicit_actions(tmp_path: Path) -> None:
    async def fetch_descriptor(catalog, entry):
        return V1_1_DESCRIPTOR

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path, V1_1_DESCRIPTOR),
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=fetch_descriptor)
    ) as client:
        installed = client.post("/api/store/mods/market-daily/install")

    assert installed.status_code == 201
    manifest = installed.json()["mod"]["manifest"]
    assert manifest["schemaVersion"] == "1.1"
    assert "agentCapabilities" not in manifest
    assert manifest["actions"]["market.explain"]["binding"]["type"] == "agent"


def test_store_reports_git_download_failure(tmp_path: Path) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreSourceError()

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path),
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=failed_fetch)
    ) as client:
        response = client.post("/api/store/mods/daily-review/install")

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to download Mod from Git"}


def test_store_discovers_suite_pages_and_installs_one_page(tmp_path: Path) -> None:
    fetched_sources: list[str] = []

    async def fetch_descriptor(catalog, entry):
        fetched_sources.append(entry.path)
        return SUITE_DESCRIPTOR

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_suite_store(tmp_path),
        investment_web_url="https://research.example",
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=fetch_descriptor)
    ) as client:
        available = client.get("/api/store/mods")
        installed = client.post("/api/store/mods/example-settings/install")

    assert available.status_code == 200
    assert [item["id"] for item in available.json()["mods"]] == [
        "example-overview",
        "example-settings",
    ]
    assert available.json()["mods"][0]["defaultInstall"] is True
    assert installed.status_code == 201
    manifest = installed.json()["mod"]["manifest"]
    assert manifest["entry"]["url"] == "https://research.example/settings"
    assert manifest["navigation"]["directory"]["id"] == "example-suite"
    assert manifest["navigation"]["icon"] == "settings"
    assert manifest["navigation"]["role"] == "settings"
    assert fetched_sources == ["example-suite/suite.json"]


def test_store_discovers_suite_from_http_well_known_endpoint(
    tmp_path: Path,
) -> None:
    fetched_sources: list[tuple[str | None, str]] = []

    async def fetch_descriptor(catalog, entry):
        fetched_sources.append((entry.path, entry.discovery.path))
        return SUITE_DESCRIPTOR

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_http_suite_store(tmp_path),
        investment_web_url="https://research.example",
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=fetch_descriptor)
    ) as client:
        available = client.get("/api/store/mods")
        installed = client.post("/api/store/mods/example-overview/install")

    assert available.status_code == 200
    assert [item["id"] for item in available.json()["mods"]] == [
        "example-overview",
        "example-settings",
    ]
    assert available.json()["mods"][0]["sourceUrl"] == (
        "https://research.example/.well-known/newma-dock-suite.json"
    )
    assert installed.status_code == 201
    assert installed.json()["mod"]["manifest"]["entry"]["url"] == (
        "https://research.example/overview"
    )
    assert fetched_sources == [
        (None, "/.well-known/newma-dock-suite.json"),
        (None, "/.well-known/newma-dock-suite.json"),
    ]


def test_store_reports_http_suite_discovery_failure(tmp_path: Path) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreDiscoveryError()

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_http_suite_store(tmp_path),
    )
    with TestClient(
        create_app(settings, mod_store_fetcher=failed_fetch)
    ) as client:
        response = client.get("/api/store/mods")

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to discover Mod Suite"}


def test_default_http_adapter_fetches_well_known_descriptor(tmp_path: Path) -> None:
    body = json.dumps(SUITE_DESCRIPTOR, ensure_ascii=False).encode("utf-8")
    requested_paths: list[str] = []

    class DiscoveryHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requested_paths.append(self.path)
            if self.path != "/.well-known/vibedesk-suite.json":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), DiscoveryHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        settings = Settings(
            runtime_dir=tmp_path,
            database_path=tmp_path / "store.db",
            mod_store_dir=_write_http_suite_store(tmp_path, base_url=base_url),
            investment_web_url=base_url,
        )
        with TestClient(create_app(settings)) as client:
            response = client.get("/api/store/mods")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["mods"]] == [
        "example-overview",
        "example-settings",
    ]
    assert response.json()["mods"][0]["sourceUrl"] == (
        f"{base_url}/.well-known/newma-dock-suite.json"
    )
    assert requested_paths == [
        "/.well-known/newma-dock-suite.json",
        "/.well-known/vibedesk-suite.json",
    ]
