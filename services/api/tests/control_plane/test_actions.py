import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from tests.model_gateway.fakes import FakeModelAdapter
from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.actions import (
    TradeConfirmationService,
    payload_hash,
)
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.main import create_app
from vibe_visualization_api.snapshots.store import SnapshotStore


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "external", "url": "https://example.com/market"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": ["market.explain"],
    "events": {"emits": [], "accepts": []},
}

MANIFEST_V1_1 = {
    "schemaVersion": "1.1",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "1.0.0",
    "category": "market",
    "entry": {"type": "external", "url": "https://example.com/market"},
    "compatibility": {
        "level": 2,
        "bridgeProtocol": "1.0",
    },
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "actions": {
        "market.explain": {
            "binding": {
                "type": "agent",
                "memoryScope": "user-agent-mod",
            },
            "execution": "task",
            "permission": "market.read",
        },
        "market.summarize": {
            "binding": {"type": "model"},
            "execution": "request",
            "permission": "market.read",
        },
        "market.overview": {
            "binding": {
                "type": "data",
                "service": "market-data",
            },
            "execution": "request",
            "permission": "market.read",
        },
    },
    "events": {"emits": [], "accepts": []},
}

MANIFEST_V1_1_UNIFIED = {
    **MANIFEST_V1_1,
    "navigation": {
        "groupLabel": "市场",
        "groupOrder": 10,
        "itemOrder": 10,
        "directory": {
            "id": "market-suite",
            "label": "行情工具",
            "order": 5,
        },
        "icon": "market",
    },
    "dataServices": [],
    "actions": {
        **MANIFEST_V1_1["actions"],
        "market.overview": {
            "binding": {"type": "data"},
            "execution": "request",
            "permission": "market.read",
        },
    },
}


class FakeDataClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, object]:
        self.calls.append((service.id, capability_id, input_data))
        return {"breadth": 0.63}


class FakeRefreshService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def refresh_module(self, module_id: str) -> dict[str, object]:
        self.calls.append(module_id)
        return {
            "id": "snapshot-1",
            "moduleId": module_id,
            "data": {"asOf": "2026-07-20T15:00:00+08:00"},
        }


@pytest.fixture
def fake_adapter() -> FakeAgentAdapter:
    return FakeAgentAdapter()


@pytest.fixture
def fake_model_adapter() -> FakeModelAdapter:
    return FakeModelAdapter()


@pytest.fixture
def fake_data_client() -> FakeDataClient:
    return FakeDataClient()


@pytest.fixture
def fake_refresh_service() -> FakeRefreshService:
    return FakeRefreshService()


@pytest.fixture
def client(
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
    fake_model_adapter: FakeModelAdapter,
    fake_data_client: FakeDataClient,
    fake_refresh_service: FakeRefreshService,
) -> Iterator[TestClient]:
    service = DataServiceDescriptor(
        id="market-data",
        priority=10,
        base_url="http://127.0.0.1:9000/api",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            )
        },
    )
    alternate_service = DataServiceDescriptor(
        id="alternate-market-data",
        priority=20,
        base_url="http://127.0.0.1:9001/api",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.overview": ServiceCapability(
                method="POST",
                path="/overview",
                input_schema="MarketOverviewInput",
                output_schema="MarketOverviewOutput",
                permission="market.read",
            )
        },
    )
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "actions.db",
        agent_default_adapter="fake",
        model_default_adapter="fake-model",
        trade_confirmation_secret="test-confirmation-secret",
    )
    application = create_app(
        settings,
        agent_adapters=[fake_adapter],
        model_adapters=[fake_model_adapter],
        data_services=[service, alternate_service],
        data_service_client=fake_data_client,
        scheduler_service=fake_refresh_service,
    )
    with TestClient(application) as test_client:
        yield test_client


def _publish(client: TestClient, manifest: dict[str, object] = MANIFEST) -> int:
    draft = client.post("/api/modules/drafts", json=manifest).json()
    response = client.post(
        f"/api/modules/{manifest['id']}/revisions/{draft['revision']}/publish"
    )
    assert response.status_code == 200
    return draft["revision"]


def _session_headers(
    client: TestClient,
    *,
    user_id: str = "alice",
    workspace_id: str = "workspace-1",
) -> dict[str, str]:
    response = client.post(
        "/api/modules/market-daily/sessions",
        headers={"X-User-Id": user_id},
        json={"instanceId": "instance-1", "workspaceId": workspace_id},
    )
    assert response.status_code == 201
    assert response.json()["instanceId"] == "instance-1"
    return {
        "Authorization": f"Bearer {response.json()['accessToken']}",
        "X-Newma-Dock-Instance-Id": "instance-1",
    }


def _audit_details(database_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT detail_json FROM audit_events "
            "WHERE event_type = 'module_action' ORDER BY id"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def test_published_module_can_call_declared_agent_capability(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
) -> None:
    _publish(client)
    SnapshotStore(tmp_path, tmp_path / "actions.db").write_success(
        "market-daily",
        {
            "asOf": "2026-07-20T15:00:00+08:00",
            "breadth": {"up": 3000, "down": 1800, "flat": 100},
            "indices": [],
            "globalIndices": [],
            "leaders": [],
        },
    )

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        headers={"X-User-Id": "alice"},
        json={"prompt": "解释市场异动"},
    )

    assert response.status_code == 202
    assert response.json()["request"]["moduleId"] == "market-daily"
    assert response.json()["request"]["capability"] == "market.explain"
    deadline = time.monotonic() + 1
    while not fake_adapter.requests and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fake_adapter.requests[0].input == {}
    assert "解释市场异动" in fake_adapter.requests[0].prompt
    assert "breadth" in fake_adapter.requests[0].prompt
    audit = _audit_details(tmp_path / "actions.db")[-1]
    assert audit["decision"] == "allowed"
    assert audit["user_id"] == "alice"
    assert audit["task_id"].startswith("task-")


def test_model_mode_does_not_create_agent_task_or_session(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
    fake_model_adapter: FakeModelAdapter,
) -> None:
    _publish(client)
    SnapshotStore(tmp_path, tmp_path / "actions.db").write_success(
        "market-daily",
        {
            "asOf": "2026-07-20T15:00:00+08:00",
            "breadth": {"up": 3000, "down": 1800, "flat": 100},
            "indices": [],
            "globalIndices": [],
            "leaders": [],
        },
    )

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        headers={"X-User-Id": "alice"},
        json={
            "gatewayMode": "model",
            "prompt": "解释市场异动",
            "model": "chosen-model",
        },
    )

    assert response.status_code == 200
    assert response.json()["adapter"] == "fake-model"
    assert response.json()["model"] == "chosen-model"
    assert fake_adapter.requests == []
    assert len(fake_model_adapter.requests) == 1
    with sqlite3.connect(tmp_path / "actions.db") as connection:
        session_table = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'agent_module_sessions'
            """
        ).fetchone()[0]
        agent_task_table = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'agent_tasks'
            """
        ).fetchone()[0]
    assert session_table == 0
    assert agent_task_table == 0


def test_manifest_1_1_agent_binding_cannot_be_changed_by_payload(
    client: TestClient,
    fake_adapter: FakeAgentAdapter,
    fake_model_adapter: FakeModelAdapter,
) -> None:
    _publish(client, MANIFEST_V1_1)

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        headers=_session_headers(client),
        json={"gatewayMode": "model", "prompt": "解释市场"},
    )

    assert response.status_code == 422
    assert fake_adapter.requests == []
    assert fake_model_adapter.requests == []


def test_manifest_1_1_requires_a_scoped_session_token(
    client: TestClient,
) -> None:
    _publish(client, MANIFEST_V1_1)

    response = client.post(
        "/api/modules/market-daily/actions/market.summarize",
        json={"prompt": "总结市场"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "valid Mod session token is required"}


def test_manifest_1_1_rejects_a_session_from_another_mod_instance(
    client: TestClient,
) -> None:
    _publish(client, MANIFEST_V1_1)
    headers = _session_headers(client)
    headers["X-Newma-Dock-Instance-Id"] = "instance-2"

    response = client.post(
        "/api/modules/market-daily/actions/market.summarize",
        headers=headers,
        json={"prompt": "总结市场"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Mod session does not grant this instance"
    }


def test_manifest_1_1_validates_inline_action_input_before_dispatch(
    client: TestClient,
    fake_model_adapter: FakeModelAdapter,
) -> None:
    manifest = json.loads(json.dumps(MANIFEST_V1_1))
    manifest["actions"]["market.summarize"]["inputSchema"] = {
        "type": "object",
        "required": ["prompt"],
        "properties": {"prompt": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }
    _publish(client, manifest)

    response = client.post(
        "/api/modules/market-daily/actions/market.summarize",
        headers=_session_headers(client),
        json={"date": "2026-07-23"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "schema_input_invalid"
    assert fake_model_adapter.requests == []


def test_manifest_1_1_validates_inline_action_output(
    client: TestClient,
    fake_model_adapter: FakeModelAdapter,
) -> None:
    manifest = json.loads(json.dumps(MANIFEST_V1_1))
    manifest["actions"]["market.summarize"]["outputSchema"] = {
        "type": "object",
        "required": ["notReturnedByModel"],
    }
    _publish(client, manifest)

    response = client.post(
        "/api/modules/market-daily/actions/market.summarize",
        headers=_session_headers(client),
        json={"prompt": "总结市场"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "schema_output_invalid"
    assert len(fake_model_adapter.requests) == 1


def test_manifest_1_1_routes_agent_action_with_declared_memory_scope(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
) -> None:
    _publish(client, MANIFEST_V1_1)
    SnapshotStore(tmp_path, tmp_path / "actions.db").write_success(
        "market-daily",
        {
            "asOf": "2026-07-23T09:30:00+08:00",
            "breadth": {"up": 2600, "down": 2200, "flat": 100},
            "indices": [],
            "globalIndices": [],
            "leaders": [],
        },
    )

    headers = _session_headers(client, user_id="alice", workspace_id="desk-1")
    saved = client.put(
        "/api/modules/market-daily/context",
        headers=headers,
        json={
            "context": {
                "view": {"id": "market-daily", "title": "市场行情"},
                "visibleBlocks": [{"id": "leaders", "type": "table"}],
                "selection": {"symbol": "600519", "market": "CN"},
                "filters": {"industry": "半导体"},
                "data": {
                    "asOf": "2026-07-23T09:30:00+08:00",
                    "source": "vibe-research",
                    "freshness": "fresh",
                },
                "actions": [{"id": "market.explain", "available": True}],
                "tasks": [],
            }
        },
    )
    assert saved.status_code == 200

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        headers=headers,
        json={"prompt": "解释市场"},
    )

    assert response.status_code == 202
    deadline = time.monotonic() + 1
    while not fake_adapter.requests and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fake_adapter.requests[0].memory_scope == "user-agent-mod"
    structured = fake_adapter.requests[0].context["vibedesk"]
    assert structured["mod"] == {"id": "market-daily", "revision": 1}
    assert structured["workspace"] == {"id": "desk-1"}
    assert structured["page"]["selection"] == {
        "symbol": "600519",
        "market": "CN",
    }
    assert "breadth" in fake_adapter.requests[0].prompt


def test_manifest_1_1_routes_model_action_without_creating_agent_task(
    client: TestClient,
    fake_adapter: FakeAgentAdapter,
    fake_model_adapter: FakeModelAdapter,
) -> None:
    _publish(client, MANIFEST_V1_1)

    response = client.post(
        "/api/modules/market-daily/actions/market.summarize",
        headers=_session_headers(client),
        json={"prompt": "总结市场", "date": "2026-07-23"},
    )

    assert response.status_code == 200
    assert fake_adapter.requests == []
    assert len(fake_model_adapter.requests) == 1
    request = fake_model_adapter.requests[0]
    assert request.capability == "market.summarize"
    assert request.input == {"date": "2026-07-23"}


def test_manifest_1_1_routes_declared_data_action(
    client: TestClient,
    fake_data_client: FakeDataClient,
) -> None:
    _publish(client, MANIFEST_V1_1)

    response = client.post(
        "/api/modules/market-daily/actions/market.overview",
        headers=_session_headers(client),
        json={"date": "2026-07-23"},
    )

    assert response.status_code == 200
    assert response.json() == {"breadth": 0.63}
    assert fake_data_client.calls == [
        ("market-data", "market.overview", {"date": "2026-07-23"})
    ]


def test_manifest_1_1_unified_data_action_selects_highest_priority_provider(
    client: TestClient,
    tmp_path: Path,
    fake_data_client: FakeDataClient,
) -> None:
    _publish(client, MANIFEST_V1_1_UNIFIED)

    response = client.post(
        "/api/modules/market-daily/actions/market.overview",
        headers=_session_headers(
            client,
            user_id="alice",
            workspace_id="desk-1",
        ),
        json={"date": "2026-07-23"},
    )

    assert response.status_code == 200
    assert fake_data_client.calls == [
        ("market-data", "market.overview", {"date": "2026-07-23"})
    ]
    audit = _audit_details(tmp_path / "actions.db")[-1]
    assert audit["routing"] == "unified"
    assert audit["service_id"] == "market-data"


def test_manifest_1_1_unified_data_action_honors_suite_provider_preference(
    client: TestClient,
    fake_data_client: FakeDataClient,
) -> None:
    _publish(client, MANIFEST_V1_1_UNIFIED)
    saved = client.put(
        "/api/data-services/preferences/market-suite",
        headers={"X-User-Id": "alice", "X-Workspace-Id": "desk-1"},
        json={
            "capabilityServices": {
                "market.overview": "alternate-market-data",
            }
        },
    )
    assert saved.status_code == 200

    response = client.post(
        "/api/modules/market-daily/actions/market.overview",
        headers=_session_headers(
            client,
            user_id="alice",
            workspace_id="desk-1",
        ),
        json={"date": "2026-07-23"},
    )

    assert response.status_code == 200
    assert fake_data_client.calls == [
        ("alternate-market-data", "market.overview", {"date": "2026-07-23"})
    ]


def test_mod_session_persists_structured_context_for_agent_reading(
    client: TestClient,
) -> None:
    _publish(client, MANIFEST_V1_1)
    headers = _session_headers(client, user_id="alice", workspace_id="desk-1")
    context = {
        "view": {"id": "market-daily", "title": "市场行情"},
        "visibleBlocks": [{"id": "breadth", "type": "metrics"}],
        "selection": {"symbol": "600519"},
        "filters": {},
        "data": {
            "asOf": "2026-07-23T09:30:00+08:00",
            "source": "vibe-research",
            "freshness": "fresh",
        },
        "actions": [{"id": "market.explain", "available": True}],
        "tasks": [],
    }

    saved = client.put(
        "/api/modules/market-daily/context",
        headers=headers,
        json={"context": context},
    )
    loaded = client.get(
        "/api/modules/market-daily/context",
        headers={"X-User-Id": "alice", "X-Workspace-Id": "desk-1"},
    )

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["context"] == context
    assert loaded.json()["revision"] == 1


def test_published_module_can_call_declared_data_capability(
    client: TestClient,
    fake_data_client: FakeDataClient,
) -> None:
    _publish(client)

    response = client.post(
        "/api/modules/market-daily/actions/market.overview",
        json={"date": "2026-07-20"},
    )

    assert response.status_code == 200
    assert response.json() == {"breadth": 0.63}
    assert fake_data_client.calls == [
        ("market-data", "market.overview", {"date": "2026-07-20"})
    ]


def test_market_refresh_runs_locally_instead_of_creating_an_agent_task(
    client: TestClient,
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
    fake_refresh_service: FakeRefreshService,
) -> None:
    _publish(
        client,
        {
            **MANIFEST,
            "agentCapabilities": ["market.explain", "market.refresh"],
        },
    )

    response = client.post(
        "/api/modules/market-daily/actions/market.refresh",
        headers={"X-User-Id": "alice"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["data"]["asOf"] == "2026-07-20T15:00:00+08:00"
    assert fake_refresh_service.calls == ["market-daily"]
    assert fake_adapter.requests == []
    audit = _audit_details(tmp_path / "actions.db")[-1]
    assert audit["decision"] == "allowed"
    assert audit["snapshot_id"] == "snapshot-1"


def test_undeclared_capability_returns_forbidden_and_is_audited(
    client: TestClient,
    tmp_path: Path,
) -> None:
    _publish(client)

    response = client.post(
        "/api/modules/market-daily/actions/market.delete",
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "module action is not declared"}
    assert _audit_details(tmp_path / "actions.db")[-1]["decision"] == "denied"


def test_disabled_module_returns_conflict(client: TestClient) -> None:
    _publish(client)
    client.post("/api/modules/market-daily/disable")

    response = client.post(
        "/api/modules/market-daily/actions/market.explain",
        json={},
    )

    assert response.status_code == 409


def test_trade_execute_requires_matching_confirmation_and_remains_disabled(
    client: TestClient,
) -> None:
    trade_manifest = {
        **MANIFEST,
        "permissions": ["market.read", "trade.execute"],
    }
    _publish(client, trade_manifest)
    action_url = "/api/modules/market-daily/actions/trade.execute"
    trade_input = {"symbol": "600519", "quantity": 100}

    missing = client.post(action_url, headers={"X-User-Id": "alice"}, json=trade_input)
    confirmation = TradeConfirmationService("test-confirmation-secret")
    wrong_payload_token = confirmation.issue(
        user_id="alice",
        module_id="market-daily",
        action_id="trade.execute",
        payload_hash=payload_hash({"symbol": "600519", "quantity": 200}),
    )
    wrong = client.post(
        action_url,
        headers={
            "X-User-Id": "alice",
            "X-Confirmation-Token": wrong_payload_token,
        },
        json=trade_input,
    )
    valid_token = confirmation.issue(
        user_id="alice",
        module_id="market-daily",
        action_id="trade.execute",
        payload_hash=payload_hash(trade_input),
    )
    valid = client.post(
        action_url,
        headers={
            "X-User-Id": "alice",
            "X-Confirmation-Token": valid_token,
        },
        json=trade_input,
    )

    assert missing.status_code == 428
    assert wrong.status_code == 428
    assert valid.status_code == 501
    assert valid.json() == {"detail": "real trading is disabled in the MVP"}
