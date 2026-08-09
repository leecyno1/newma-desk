import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.external_mod_runtimes import resolve_runtime_workspace
from vibe_visualization_api.main import create_app
from vibe_visualization_api.mod_store.schemas import (
    StoreModDescriptor,
    StoreModSuiteDescriptor,
    expand_mod_suite,
)
from vibe_visualization_api.mod_store.service import (
    ModStoreCatalogError,
    ModStoreDiscoveryError,
    ModStoreService,
    ModStoreSourceError,
)

DESCRIPTOR = {
    "schemaVersion": "1.0",
    "id": "daily-review",
    "name": "每日复盘",
    "description": "把每天的市场变化整理成可持续复用的复盘页面。",
    "version": "0.1.0",
    "publisher": "Newma-Desk",
    "upstream": "https://github.com/simonlin1212/Vibe-Research",
    "tags": ["投研", "复盘"],
    "runtime": {
        "type": "external",
        "baseUrlEnv": "NEWMA_DESK_INVESTMENT_WEB_URL",
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
    "publisher": "Newma-Desk",
    "upstream": "https://github.com/leecyno1/newma-dock",
    "tags": ["Suite"],
    "runtime": {
        "type": "external",
        "baseUrlEnv": "NEWMA_DESK_INVESTMENT_WEB_URL",
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
            "project": {
                "id": "fundamentals",
                "name": "宏观面",
                "order": 20,
                "description": "经济数据、宏观指标、行业、产业链与宏观事件。",
                "logo": {"type": "letter", "text": "ER"},
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
            "version": "0.2.0",
            "route": "/overview",
            "navigation": {
                "itemOrder": 10,
                "label": "总览",
            },
            "manifest": {
                "schemaVersion": "1.1",
                "category": "market",
                "compatibility": {
                    "level": 3,
                    "bridgeProtocol": "1.0",
                    "viewSpecVersion": "1.0",
                },
                "permissions": ["research.read"],
                "dataServices": ["market-data"],
                "actions": {},
                "events": {"emits": ["security.selected"], "accepts": []},
            },
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
            "manifest": {
                "category": "system",
                "permissions": ["research.settings"],
            },
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
                "id": "newma-desk-official",
                "name": "Newma-Desk 官方 Mod 商店",
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


def _write_suite_store(
    root: Path,
    descriptor: dict[str, object] = SUITE_DESCRIPTOR,
) -> Path:
    store_dir = root / "mods"
    descriptor_path = store_dir / "example-suite" / "suite.json"
    descriptor_path.parent.mkdir(parents=True)
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False),
        encoding="utf-8",
    )
    (store_dir / "store.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "id": "newma-desk-official",
                "name": "Newma-Desk 官方 Mod 商店",
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
                "id": "newma-desk-http-discovery",
                "name": "Newma-Desk HTTP Discovery Store",
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
                            "baseUrlEnv": "NEWMA_DESK_INVESTMENT_WEB_URL",
                            "defaultBaseUrl": base_url,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return store_dir


def test_suite_expansion_preserves_project_identity_on_every_page() -> None:
    suite = StoreModSuiteDescriptor.model_validate(SUITE_DESCRIPTOR)

    expanded = expand_mod_suite(suite)

    assert len(expanded) == 2
    for descriptor, _ in expanded:
        navigation = descriptor.manifest.navigation
        assert navigation is not None
        assert navigation.project is not None
        assert navigation.project.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        ) == {
            "id": "fundamentals",
            "name": "宏观面",
            "order": 20,
            "description": "经济数据、宏观指标、行业、产业链与宏观事件。",
            "logo": {"type": "letter", "text": "ER"},
        }


def test_suite_expansion_places_legacy_suite_intact_under_other() -> None:
    legacy_descriptor = json.loads(json.dumps(SUITE_DESCRIPTOR))
    del legacy_descriptor["manifest"]["navigation"]["project"]
    suite = StoreModSuiteDescriptor.model_validate(legacy_descriptor)

    expanded = expand_mod_suite(suite)

    for descriptor, _ in expanded:
        navigation = descriptor.manifest.navigation
        assert navigation is not None
        assert navigation.project is not None
        assert navigation.project.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        ) == {
            "id": "other",
            "name": "其他",
            "order": 150,
            "description": "尚未归入核心投研流程的管理工具与扩展能力。",
        }


def test_suite_rejects_pages_split_across_domains() -> None:
    descriptor = json.loads(json.dumps(SUITE_DESCRIPTOR))
    descriptor["pages"][1]["navigation"]["project"] = {
        "id": "policy-intelligence",
        "name": "政策面",
        "order": 50,
    }

    with pytest.raises(ValidationError, match="cannot split pages across investment domains"):
        StoreModSuiteDescriptor.model_validate(descriptor)


def test_suite_rejects_page_moved_into_another_complete_project() -> None:
    descriptor = json.loads(json.dumps(SUITE_DESCRIPTOR))
    descriptor["pages"][1]["navigation"]["directory"] = {
        "id": "detached-suite",
        "label": "另一个项目",
        "order": 20,
    }

    with pytest.raises(ValidationError, match="cannot split pages into another project group"):
        StoreModSuiteDescriptor.model_validate(descriptor)


@pytest.mark.parametrize(
    "logo",
    [
        {"type": "letter", "text": " "},
        {"type": "letter", "text": "LONG"},
        {"type": "image", "src": "javascript:alert(1)"},
        {"type": "image", "src": "/%2e%2e/secret.png"},
        {"type": "icon", "name": "unregistered"},
    ],
)
def test_suite_rejects_unsafe_project_logo(logo: dict[str, str]) -> None:
    descriptor = json.loads(json.dumps(SUITE_DESCRIPTOR))
    descriptor["manifest"]["navigation"]["project"]["logo"] = logo

    with pytest.raises(ValidationError):
        StoreModSuiteDescriptor.model_validate(descriptor)


@pytest.mark.parametrize(
    ("relative_path", "expected_domain"),
    [
        ("mods/research-suite/suite.json", "fundamentals"),
        ("mods/trading-suite/suite.json", "quant-research"),
        ("mods/portfolio-suite/suite.json", "trading-risk-portfolio"),
        ("mods/orchestra-suite/suite.json", "investment-committee"),
        ("mods/calendar-effect-suite/suite.json", "tactical-timing"),
        ("mods/deepsee-suite/suite.json", "other"),
    ],
)
def test_first_party_suite_remains_intact_in_one_investment_domain(
    relative_path: str,
    expected_domain: str,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    suite = StoreModSuiteDescriptor.model_validate_json(
        (repository_root / relative_path).read_text(encoding="utf-8")
    )

    expanded = expand_mod_suite(suite)

    assert expanded
    assert {
        descriptor.manifest.navigation.project.id
        for descriptor, _ in expanded
        if descriptor.manifest.navigation is not None
        and descriptor.manifest.navigation.project is not None
    } == {expected_domain}
    assert all(
        descriptor.manifest.navigation is not None
        and descriptor.manifest.navigation.group_label
        == descriptor.manifest.navigation.project.name
        for descriptor, _ in expanded
    )


@pytest.mark.asyncio
async def test_agent_workspace_resolves_restricted_runtime_reference(
    tmp_path: Path,
) -> None:
    investment = tmp_path / "vibe-research"
    investment.mkdir()
    descriptor = {
        **DESCRIPTOR,
        "agentWorkspace": {
            "type": "runtime",
            "runtimeId": "vibe-research",
            "workspaceName": "source",
        },
    }
    settings = Settings(
        workspace_root=tmp_path,
        investment_workspace=investment,
        mod_store_dir=_write_store(tmp_path, descriptor),
        _env_file=None,
    )
    service = ModStoreService(settings)

    assert await service.resolve_agent_workspace("daily-review") == investment


@pytest.mark.asyncio
async def test_agent_workspace_is_inherited_by_suite_pages(tmp_path: Path) -> None:
    desk = tmp_path / "newma-desk"
    desk.mkdir()
    descriptor = {
        **SUITE_DESCRIPTOR,
        "agentWorkspace": {"type": "desk"},
    }
    settings = Settings(
        workspace_root=desk,
        mod_store_dir=_write_suite_store(tmp_path, descriptor),
        _env_file=None,
    )
    service = ModStoreService(settings)

    assert await service.resolve_agent_workspace("example-overview") == desk
    assert await service.resolve_agent_workspace("example-settings") == desk


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent_workspace",
    [
        {"type": "desk"},
        {
            "type": "runtime",
            "runtimeId": "vibe-research",
            "workspaceName": "source",
        },
    ],
)
async def test_http_discovered_suite_cannot_grant_agent_workspace(
    tmp_path: Path,
    agent_workspace: dict[str, str],
) -> None:
    descriptor = {
        **SUITE_DESCRIPTOR,
        "agentWorkspace": agent_workspace,
    }

    async def fetch_descriptor(catalog, entry):
        return descriptor

    def reject_runtime_resolution(runtime_id: str, workspace_name: str) -> Path:
        raise AssertionError(
            f"remote Suite attempted to resolve {runtime_id}/{workspace_name}"
        )

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        workspace_root=tmp_path / "desk",
        mod_store_dir=_write_http_suite_store(tmp_path),
        _env_file=None,
    )
    service = ModStoreService(
        settings,
        descriptor_fetcher=fetch_descriptor,
        runtime_workspace_resolver=reject_runtime_resolution,
    )

    store = await service.list(ModuleRepository(settings.database_path))

    assert [item.id for item in store.mods] == [
        "example-overview",
        "example-settings",
    ]
    assert await service.resolve_agent_workspace("example-overview") is None


@pytest.mark.asyncio
async def test_relative_runtime_agent_workspace_matches_runtime_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative_workspace = "relative-vibe-research-workspace"
    monkeypatch.setenv(
        "NEWMA_DESK_INVESTMENT_WORKSPACE",
        relative_workspace,
    )
    descriptor = {
        **DESCRIPTOR,
        "agentWorkspace": {
            "type": "runtime",
            "runtimeId": "vibe-research",
            "workspaceName": "source",
        },
    }
    settings = Settings(
        workspace_root=tmp_path / "unrelated-desk-root",
        mod_store_dir=_write_store(tmp_path, descriptor),
        _env_file=None,
    )
    service = ModStoreService(settings)

    expected = resolve_runtime_workspace("vibe-research", "source")

    assert await service.resolve_agent_workspace("daily-review") == expected
    assert expected != (settings.workspace_root / relative_workspace).resolve()


def test_agent_workspace_rejects_arbitrary_paths() -> None:
    descriptor = {
        **DESCRIPTOR,
        "agentWorkspace": {
            "type": "runtime",
            "runtimeId": "../private",
            "workspaceName": "source",
        },
    }

    with pytest.raises(ValidationError):
        StoreModDescriptor.model_validate(descriptor)


@pytest.mark.asyncio
async def test_agent_workspace_rejects_unknown_runtime_workspace(
    tmp_path: Path,
) -> None:
    descriptor = {
        **DESCRIPTOR,
        "agentWorkspace": {
            "type": "runtime",
            "runtimeId": "vibe-research",
            "workspaceName": "missing",
        },
    }
    settings = Settings(
        workspace_root=tmp_path,
        mod_store_dir=_write_store(tmp_path, descriptor),
        _env_file=None,
    )
    service = ModStoreService(settings)

    with pytest.raises(ModStoreCatalogError):
        await service.resolve_agent_workspace("daily-review")


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
    with TestClient(create_app(settings, mod_store_fetcher=fetch_descriptor)) as client:
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
    with TestClient(create_app(settings, mod_store_fetcher=fetch_descriptor)) as client:
        installed = client.post("/api/store/mods/market-daily/install")

    assert installed.status_code == 201
    manifest = installed.json()["mod"]["manifest"]
    assert manifest["schemaVersion"] == "1.1"
    assert "agentCapabilities" not in manifest
    assert manifest["actions"]["market.explain"]["binding"]["type"] == "agent"


def test_store_preserves_desk_managed_storage_declaration(tmp_path: Path) -> None:
    descriptor = {
        **V1_1_DESCRIPTOR,
        "id": "storage-notes",
        "name": "存储笔记",
        "manifest": {
            **V1_1_DESCRIPTOR["manifest"],
            "permissions": ["storage.read", "storage.write"],
            "actions": {},
            "storage": {
                "mode": "desk-managed",
                "namespaces": [
                    {
                        "id": "notes",
                        "schemaVersion": 1,
                        "quotaMb": 5,
                    }
                ],
            },
        },
    }

    async def fetch_descriptor(catalog, entry):
        return descriptor

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path, descriptor),
    )
    with TestClient(create_app(settings, mod_store_fetcher=fetch_descriptor)) as client:
        installed = client.post("/api/store/mods/storage-notes/install")

    assert installed.status_code == 201
    storage = installed.json()["mod"]["manifest"]["storage"]
    assert storage["mode"] == "desk-managed"
    assert storage["namespaces"][0] == {
        "id": "notes",
        "scope": "user-workspace",
        "schemaVersion": 1,
        "quotaMb": 5,
        "maxItemKb": 256,
    }


def test_store_uses_local_descriptor_when_git_download_fails(tmp_path: Path) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreSourceError()

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_store(tmp_path),
    )
    with TestClient(create_app(settings, mod_store_fetcher=failed_fetch)) as client:
        response = client.post("/api/store/mods/daily-review/install")

    assert response.status_code == 201
    assert response.json()["action"] == "installed"
    assert response.json()["descriptorSource"] == "bundled"
    assert response.json()["mod"]["manifest"]["id"] == "daily-review"


def test_store_reports_git_failure_when_local_descriptor_is_missing(
    tmp_path: Path,
) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreSourceError()

    store_dir = _write_store(tmp_path)
    (store_dir / "daily-review" / "mod.json").unlink()
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=store_dir,
    )
    with TestClient(create_app(settings, mod_store_fetcher=failed_fetch)) as client:
        response = client.post("/api/store/mods/daily-review/install")

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to download Mod from Git"}


def test_store_uses_local_suite_page_when_git_download_fails(tmp_path: Path) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreSourceError()

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_suite_store(tmp_path),
        investment_web_url="https://research.example",
    )
    with TestClient(create_app(settings, mod_store_fetcher=failed_fetch)) as client:
        response = client.post("/api/store/mods/example-settings/install")

    assert response.status_code == 201
    assert response.json()["action"] == "installed"
    assert response.json()["descriptorSource"] == "bundled"
    assert response.json()["mod"]["manifest"]["entry"]["url"] == (
        "https://research.example/settings"
    )


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
    with TestClient(create_app(settings, mod_store_fetcher=fetch_descriptor)) as client:
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
    with TestClient(create_app(settings, mod_store_fetcher=fetch_descriptor)) as client:
        available = client.get("/api/store/mods")
        installed = client.post("/api/store/mods/example-overview/install")

    assert available.status_code == 200
    assert [item["id"] for item in available.json()["mods"]] == [
        "example-overview",
        "example-settings",
    ]
    assert available.json()["mods"][0]["sourceUrl"] == (
        "https://research.example/.well-known/newma-desk-suite.json"
    )
    assert installed.status_code == 201
    assert installed.json()["mod"]["manifest"]["entry"]["url"] == (
        "https://research.example/overview"
    )
    assert fetched_sources == [
        (None, "/.well-known/newma-desk-suite.json"),
        (None, "/.well-known/newma-desk-suite.json"),
    ]


def test_store_reports_http_suite_discovery_failure(tmp_path: Path) -> None:
    async def failed_fetch(catalog, entry):
        raise ModStoreDiscoveryError()

    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "store.db",
        mod_store_dir=_write_http_suite_store(tmp_path),
    )
    with TestClient(create_app(settings, mod_store_fetcher=failed_fetch)) as client:
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

    assert response.status_code == 200, requested_paths
    assert [item["id"] for item in response.json()["mods"]] == [
        "example-overview",
        "example-settings",
    ]
    assert response.json()["mods"][0]["sourceUrl"] == (
        f"{base_url}/.well-known/newma-desk-suite.json"
    )
    assert requested_paths == [
        "/.well-known/newma-desk-suite.json",
        "/.well-known/newma-dock-suite.json",
        "/.well-known/vibedesk-suite.json",
    ]
