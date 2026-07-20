import time
from pathlib import Path

from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from vibe_visualization_api.agent_gateway.prompts.market_explain import (
    build_market_explain_prompt,
)
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.snapshots.store import SnapshotStore


STABLE_SNAPSHOT = {
    "asOf": "2026-07-18T15:00:00+08:00",
    "breadth": {"up": 3120, "down": 1800, "flat": 120},
    "indices": [
        {
            "symbol": "000001",
            "name": "上证指数",
            "price": 3520.1,
            "changePct": 0.8,
            "rawResponse": "must-not-leak",
        }
    ],
    "globalIndices": [],
    "leaders": [
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "price": 1488.0,
            "changePct": 3.2,
            "amount": 120_000_000,
            "market": "CN",
            "industry": {"rawResponse": "nested-must-not-leak"},
            "privateNote": "must-not-leak",
        }
    ],
    "charts": {"indexTrend": {"series": []}},
    "rawResponse": {"secret": True},
}

MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/modules/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": ["market.explain"],
    "events": {"emits": [], "accepts": []},
}


def test_market_explain_uses_snapshot_not_raw_upstream_data() -> None:
    prompt = build_market_explain_prompt(
        snapshot=STABLE_SNAPSHOT,
        user_prompt="解释上涨原因",
    )

    assert "breadth" in prompt
    assert "2026-07-18T15:00:00+08:00" in prompt
    assert "rawResponse" not in prompt
    assert "privateNote" not in prompt
    assert "观察" in prompt
    assert "可能驱动" in prompt
    assert "风险" in prompt
    assert len(prompt) < 20_000


def test_market_explain_caps_serialized_context() -> None:
    large_snapshot = {
        **STABLE_SNAPSHOT,
        "leaders": [
            {
                "symbol": f"{index:06d}",
                "name": "超长名称" * 100,
                "price": index,
                "changePct": index / 10,
                "amount": index * 1000,
                "market": "CN",
                "industry": "行业" * 100,
            }
            for index in range(500)
        ],
    }

    prompt = build_market_explain_prompt(
        snapshot=large_snapshot,
        user_prompt="解释行情" * 1000,
    )

    assert len(prompt) < 20_000
    assert "上下文已截断" in prompt


def test_market_explain_action_loads_latest_snapshot_server_side(
    tmp_path: Path,
) -> None:
    adapter = FakeAgentAdapter()
    database_path = tmp_path / "gateway.db"
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=database_path,
        agent_default_adapter=adapter.id,
    )
    application = create_app(settings, agent_adapters=[adapter])

    with TestClient(application) as client:
        draft = client.post("/api/modules/drafts", json=MANIFEST).json()
        client.post(
            f"/api/modules/market-daily/revisions/{draft['revision']}/publish"
        )
        missing = client.post(
            "/api/modules/market-daily/actions/market.explain",
            json={"prompt": "解释上涨原因"},
        )
        assert missing.status_code == 404

        SnapshotStore(tmp_path, database_path).write_success(
            "market-daily", STABLE_SNAPSHOT
        )
        response = client.post(
            "/api/modules/market-daily/actions/market.explain",
            json={"prompt": "解释上涨原因"},
        )
        assert response.status_code == 202
        deadline = time.monotonic() + 1
        while not adapter.requests and time.monotonic() < deadline:
            time.sleep(0.01)

    request = adapter.requests[0]
    assert request.capability == "market.explain"
    assert "解释上涨原因" in request.prompt
    assert "breadth" in request.prompt
    assert "rawResponse" not in request.prompt
    assert request.context == {}
    assert request.input == {}
