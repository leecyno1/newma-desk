import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from vibe_visualization_api.agent_gateway.models import (
    AdapterEvent,
    AgentTaskCreate,
)
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "external", "url": "https://example.com/market"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": ["market.explain", "market.refresh"],
    "events": {"emits": [], "accepts": []},
}


class SlowAgentAdapter(FakeAgentAdapter):
    async def run(
        self,
        task_id: str,
        request: AgentTaskCreate,
    ) -> AsyncIterator[AdapterEvent]:
        self.requests.append(request)
        yield AdapterEvent(type="progress", data={"message": "working"})
        await asyncio.sleep(0.05)
        yield AdapterEvent(type="completed", data={"answer": "slow: done"})


class BlockingAgentAdapter(FakeAgentAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()

    async def run(
        self,
        task_id: str,
        request: AgentTaskCreate,
    ) -> AsyncIterator[AdapterEvent]:
        self.requests.append(request)
        yield AdapterEvent(type="progress", data={"message": "waiting"})
        self.started.set()
        await asyncio.Event().wait()


class FailingAgentAdapter(FakeAgentAdapter):
    async def run(
        self,
        task_id: str,
        request: AgentTaskCreate,
    ) -> AsyncIterator[AdapterEvent]:
        self.requests.append(request)
        raise RuntimeError("internal server-secret-key")
        yield


@contextmanager
def _client(
    tmp_path: Path,
    adapter: FakeAgentAdapter,
) -> Iterator[TestClient]:
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "gateway.db",
        agent_default_adapter=adapter.id,
    )
    application = create_app(settings, agent_adapters=[adapter])
    with TestClient(application) as client:
        yield client


@pytest.fixture
def fake_adapter() -> FakeAgentAdapter:
    return FakeAgentAdapter()


@pytest.fixture
def client(
    tmp_path: Path,
    fake_adapter: FakeAgentAdapter,
) -> Iterator[TestClient]:
    with _client(tmp_path, fake_adapter) as test_client:
        yield test_client


def _wait_for_status(
    client: TestClient,
    task_id: str,
    expected: str,
) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(f"/api/agent/tasks/{task_id}")
        assert response.status_code == 200
        if response.json()["status"] == expected:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"task {task_id} did not become {expected}")


def _sse_records(body: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for block in body.strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, value = line.split(":", 1)
            fields[key] = value.strip()
        records.append(
            {
                "id": int(fields["id"]),
                "event": fields["event"],
                "data": json.loads(fields["data"]),
            }
        )
    return records


@pytest.mark.parametrize(
    ("module_id", "capability", "requested_scope", "effective_scope"),
    [
        ("earnings-workbench", "module.explain", None, "task"),
        ("earnings-workbench", "module.analyze", "user-agent-mod", "task"),
        ("earnings-workbench", None, "user-agent-mod", "task"),
        ("earnings-workbench", "module.edit", "user-agent-mod", "user-agent-mod"),
        ("industry-map", "module.explain", "user-agent-mod", "user-agent-mod"),
    ],
)
def test_earnings_analysis_uses_task_memory_at_the_gateway(
    client: TestClient,
    fake_adapter: FakeAgentAdapter,
    module_id: str,
    capability: str | None,
    requested_scope: str | None,
    effective_scope: str,
) -> None:
    payload = {"moduleId": module_id, "capability": capability, "prompt": "分析当前底稿"}
    if requested_scope is not None:
        payload["memoryScope"] = requested_scope
    response = client.post("/api/agent/tasks", json=payload)
    assert response.status_code == 202
    task = _wait_for_status(client, response.json()["id"], "completed")
    assert task["request"]["memoryScope"] == effective_scope
    assert fake_adapter.requests[-1].memory_scope == effective_scope


def test_capability_discovery_lists_adapters_and_module_actions(
    client: TestClient,
) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()
    client.post(f"/api/modules/market-daily/revisions/{draft['revision']}/publish")

    response = client.get("/api/capabilities")

    assert response.status_code == 200
    assert response.json()["adapters"] == [
        {
            "id": "fake",
            "capabilities": ["chat", "module.explain"],
            "default": True,
        }
    ]
    assert response.json()["moduleActions"] == [
        {
            "moduleId": "market-daily",
            "capabilities": ["market.explain", "market.refresh"],
        }
    ]


def test_create_task_returns_202_and_persists_completion(
    client: TestClient,
    fake_adapter: FakeAgentAdapter,
) -> None:
    created = client.post("/api/agent/tasks", json={"prompt": "hello"})

    assert created.status_code == 202
    task_id = created.json()["id"]
    completed = _wait_for_status(client, task_id, "completed")
    assert completed["result"] == {"answer": "fake: hello"}
    assert fake_adapter.requests[0].prompt == "hello"


def test_current_request_evidence_wins_over_stored_mod_context(
    client: TestClient,
    fake_adapter: FakeAgentAdapter,
) -> None:
    client.app.state.mod_context_store.put(
        user_id="alice",
        workspace_id="desk-1",
        module_id="market-daily",
        instance_id="old-instance",
        revision=7,
        context={"view": {"id": "old", "title": "旧页面"}},
    )
    created = client.post(
        "/api/agent/tasks",
        headers={"X-User-Id": "alice", "X-Workspace-Id": "desk-1"},
        json={
            "moduleId": "market-daily",
            "prompt": "解释当前页面",
            "context": {
                "vibedesk": {
                    "mod": {
                        "id": "market-daily",
                        "name": "市场行情",
                        "version": "1.2.3",
                    },
                    "page": {"view": {"id": "current", "title": "当前页面"}},
                    "visual": {
                        "image": {
                            "artifactId": "0123456789abcdef0123456789abcdef"
                        }
                    },
                }
            },
        },
    )

    assert created.status_code == 202
    _wait_for_status(client, created.json()["id"], "completed")
    vibedesk = fake_adapter.requests[0].context["vibedesk"]
    assert vibedesk["page"]["view"]["id"] == "current"
    assert vibedesk["mod"] == {
        "id": "market-daily",
        "name": "市场行情",
        "version": "1.2.3",
        "revision": 7,
    }
    assert vibedesk["visual"]["image"]["artifactId"].startswith("012345")
    assert "storedContextUpdatedAt" in vibedesk


def test_agent_preferences_can_select_default_and_module_override(
    client: TestClient,
) -> None:
    initial = client.get("/api/agent/preferences")

    assert initial.status_code == 200
    assert initial.json() == {
        "userId": "local-user",
        "defaultAdapter": "fake",
        "moduleOverrides": {},
        "profileTargets": {},
        "moduleProfileOverrides": {},
        "updatedAt": None,
    }

    updated = client.put(
        "/api/agent/preferences",
        json={
            "defaultAdapter": "fake",
            "moduleOverrides": {"market-daily": "fake"},
            "profileTargets": {
                "deep": "fake",
                "batch": "fake",
                "edit": "fake",
            },
            "moduleProfileOverrides": {
                "market-daily": {"batch": "fake"},
            },
        },
    )

    assert updated.status_code == 200
    assert updated.json()["moduleOverrides"] == {"market-daily": "fake"}
    created = client.post(
        "/api/agent/tasks",
        json={
            "moduleId": "market-daily",
            "profile": "batch",
            "prompt": "hello",
        },
    )
    assert created.status_code == 202
    assert created.json()["request"]["adapter"] == "fake"
    assert created.json()["request"]["profile"] == "batch"


def test_agent_preferences_reject_unknown_adapter(client: TestClient) -> None:
    response = client.put(
        "/api/agent/preferences",
        json={"defaultAdapter": "missing", "moduleOverrides": {}},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unknown agent adapter"}


def test_sse_replays_persisted_events_with_protocol_fields(
    client: TestClient,
) -> None:
    task_id = client.post(
        "/api/agent/tasks",
        json={"prompt": "hello"},
    ).json()["id"]
    _wait_for_status(client, task_id, "completed")

    response = client.get(f"/api/agent/tasks/{task_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    records = _sse_records(response.text)
    assert [(record["id"], record["event"]) for record in records] == [
        (1, "queued"),
        (2, "progress"),
        (3, "completed"),
    ]
    assert records[-1]["data"] == {"answer": "fake: hello"}


def test_sse_switches_from_replay_to_live_events_without_duplicates(
    tmp_path: Path,
) -> None:
    adapter = SlowAgentAdapter()
    with _client(tmp_path, adapter) as client:
        task_id = client.post(
            "/api/agent/tasks",
            json={"prompt": "hello"},
        ).json()["id"]

        response = client.get(f"/api/agent/tasks/{task_id}/events")

    records = _sse_records(response.text)
    assert [record["id"] for record in records] == [1, 2, 3]
    assert records[-1]["data"] == {"answer": "slow: done"}


def test_sse_after_parameter_filters_replayed_events(client: TestClient) -> None:
    task_id = client.post(
        "/api/agent/tasks",
        json={"prompt": "hello"},
    ).json()["id"]
    _wait_for_status(client, task_id, "completed")

    response = client.get(f"/api/agent/tasks/{task_id}/events?after=1")

    assert [record["id"] for record in _sse_records(response.text)] == [2, 3]


def test_sse_closes_when_after_is_beyond_a_terminal_sequence(
    client: TestClient,
) -> None:
    task_id = client.post(
        "/api/agent/tasks",
        json={"prompt": "hello"},
    ).json()["id"]
    _wait_for_status(client, task_id, "completed")

    response = client.get(f"/api/agent/tasks/{task_id}/events?after=999")

    assert response.status_code == 200
    assert response.text == ""


def test_live_sse_closes_when_after_is_ahead_of_future_terminal_event(
    tmp_path: Path,
) -> None:
    adapter = SlowAgentAdapter()
    with _client(tmp_path, adapter) as client:
        task_id = client.post(
            "/api/agent/tasks",
            json={"prompt": "hello"},
        ).json()["id"]

        response = client.get(f"/api/agent/tasks/{task_id}/events?after=999")

    assert response.status_code == 200
    assert response.text == ""


def test_cancel_stops_adapter_and_persists_terminal_event(tmp_path: Path) -> None:
    adapter = BlockingAgentAdapter()
    with _client(tmp_path, adapter) as client:
        task_id = client.post(
            "/api/agent/tasks",
            json={"prompt": "wait"},
        ).json()["id"]
        assert adapter.started.wait(timeout=1)

        response = client.post(f"/api/agent/tasks/{task_id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert adapter.cancelled_task_ids == [task_id]
        events = client.get(f"/api/agent/tasks/{task_id}/events")
        assert _sse_records(events.text)[-1]["event"] == "cancelled"


def test_unknown_adapter_is_rejected_without_creating_a_task(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/agent/tasks",
        json={"prompt": "hello", "adapter": "missing"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unknown agent adapter"}


def test_adapter_exception_becomes_a_safe_failed_task(tmp_path: Path) -> None:
    adapter = FailingAgentAdapter()
    with _client(tmp_path, adapter) as client:
        task_id = client.post(
            "/api/agent/tasks",
            json={"prompt": "hello"},
        ).json()["id"]

        failed = _wait_for_status(client, task_id, "failed")
        events = client.get(f"/api/agent/tasks/{task_id}/events")

    assert failed["error"] == "Agent adapter failed"
    assert "server-secret-key" not in json.dumps(failed)
    assert "server-secret-key" not in events.text


def test_missing_task_routes_return_not_found(client: TestClient) -> None:
    assert client.get("/api/agent/tasks/missing").status_code == 404
    assert client.get("/api/agent/tasks/missing/events").status_code == 404
    assert client.post("/api/agent/tasks/missing/cancel").status_code == 404
