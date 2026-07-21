import json
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.mod_store.service import ModStoreSourceError


DESCRIPTOR = {
    "schemaVersion": "1.0",
    "id": "daily-review",
    "name": "每日复盘",
    "description": "把每天的市场变化整理成可持续复用的复盘页面。",
    "version": "0.1.0",
    "publisher": "VibeDesk",
    "upstream": "https://github.com/simonlin1212/Vibe-Research",
    "tags": ["投研", "复盘"],
    "runtime": {
        "type": "external",
        "baseUrlEnv": "VIBEDESK_INVESTMENT_WEB_URL",
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


def _write_store(root: Path) -> Path:
    store_dir = root / "mods"
    descriptor_path = store_dir / "daily-review" / "mod.json"
    descriptor_path.parent.mkdir(parents=True)
    descriptor_path.write_text(
        json.dumps(DESCRIPTOR, ensure_ascii=False),
        encoding="utf-8",
    )
    (store_dir / "store.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "id": "vibedesk-official",
                "name": "VibeDesk 官方 Mod 商店",
                "git": {
                    "repository": "https://github.com/leecyno1/vibedesk",
                    "ref": "main",
                    "pathPrefix": "mods",
                    "mirrors": ["https://gitee.com/leecyno1/vibedesk"],
                    "rawBaseUrls": [
                        "https://raw.githubusercontent.com/leecyno1/vibedesk/main/mods",
                        "https://gitee.com/leecyno1/vibedesk/raw/main/mods",
                    ],
                },
                "mods": [
                    {
                        "id": "daily-review",
                        "path": "daily-review/mod.json",
                        "defaultInstall": True,
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
        ("https://github.com/leecyno1/vibedesk", "daily-review/mod.json"),
        ("https://github.com/leecyno1/vibedesk", "daily-review/mod.json"),
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
