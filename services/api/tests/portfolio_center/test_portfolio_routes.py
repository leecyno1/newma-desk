from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.main import create_app
from vibe_visualization_api.portfolio_center.quotes import (
    PortfolioQuote,
    SecurityIdentity,
)


class FakeQuoteProvider:
    def __init__(self):
        self.calls = 0

    async def get_quotes(self, securities):
        self.calls += 1
        quotes = {
            SecurityIdentity("US", "AAPL"): PortfolioQuote(
                price=220,
                name="Apple",
                currency="USD",
                source="test",
            )
        }
        return {security: quotes[security] for security in securities if security in quotes}


class FakeHistoryClient:
    def __init__(self):
        self.calls = []

    async def invoke(self, service, capability_id, input_data):
        self.calls.append((capability_id, input_data))
        base = 100 if input_data["symbol"] == "AAPL" else 200
        return {
            "data": {
                "source": "route-test",
                "asOf": "2026-08-01",
                "items": [
                    {
                        "timestamp": 1_700_000_000_000 + index * 604_800_000,
                        "close": base * (1 + index * 0.002),
                    }
                    for index in range(60)
                ],
            }
        }


def history_service():
    return DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:8911/api/research",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.ohlcv": ServiceCapability(
                method="GET",
                path="/api/market-terminal/ohlcv",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                permission="market.read",
            )
        },
    )


def test_portfolio_center_routes_are_workspace_isolated(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    quote_provider = FakeQuoteProvider()
    app = create_app(settings, portfolio_quote_provider=quote_provider)
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "desk-a"}
    with TestClient(app) as client:
        account = client.post(
            "/api/portfolio-center/accounts",
            headers=headers,
            json={"id": "broker", "name": "海外账户", "currency": "USD"},
        )
        assert account.status_code == 201
        activity = client.post(
            "/api/portfolio-center/activities",
            headers=headers,
            json={
                "accountId": "broker",
                "type": "buy",
                "market": "US",
                "symbol": "AAPL",
                "name": "Apple",
                "currency": "USD",
                "quantity": 10,
                "unitPrice": 200,
                "occurredAt": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
            },
        )
        assert activity.status_code == 201

        dashboard = client.get("/api/portfolio-center", headers=headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["positions"][0]["marketValue"] == 2200
        assert quote_provider.calls == 1

        cost_dashboard = client.get(
            "/api/portfolio-center?includeQuotes=false",
            headers=headers,
        )
        assert cost_dashboard.status_code == 200
        assert cost_dashboard.json()["valuationStatus"] == "cost-based"
        assert cost_dashboard.json()["positions"][0]["marketValue"] is None
        assert quote_provider.calls == 1

        other = client.get(
            "/api/portfolio-center",
            headers={"X-User-Id": "alice", "X-Workspace-Id": "desk-b"},
        )
        assert other.status_code == 200
        assert other.json()["positions"] == []


def test_portfolio_center_rejects_oversell(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/portfolio-center/activities",
            json={
                "accountId": "main",
                "type": "sell",
                "market": "CN",
                "symbol": "600519",
                "currency": "CNY",
                "quantity": 1,
                "unitPrice": 1000,
                "occurredAt": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
            },
        )
        assert response.status_code == 409


def test_portfolio_research_coverage_uses_workspace_archive_references(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    app = create_app(settings)
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "desk-a"}
    with TestClient(app) as client:
        assert client.get(
            "/api/portfolio-center?includeQuotes=false",
            headers=headers,
        ).status_code == 200
        activity = client.post(
            "/api/portfolio-center/activities",
            headers=headers,
            json={
                "accountId": "main",
                "type": "buy",
                "market": "US",
                "symbol": "AAPL",
                "name": "Apple",
                "currency": "USD",
                "quantity": 10,
                "unitPrice": 200,
                "occurredAt": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
            },
        )
        assert activity.status_code == 201
        app.state.mod_storage_store.put(
            user_id="alice",
            workspace_id="desk-a",
            module_id="thesis-tracker",
            namespace="thesis-tracker",
            key="portfolio",
            schema_version=1,
            expected_revision=0,
            value={
                "schemaVersion": "newma-desk.investment-thesis.v1",
                "updatedAt": "2026-08-05T07:00:00Z",
                "theses": [{
                    "id": "thesis-aapl",
                    "title": "Apple 服务业务逻辑",
                    "status": "active",
                    "security": {"market": "US", "symbol": "AAPL", "name": "Apple"},
                    "nextReviewAt": "2026-09-01",
                    "updatedAt": "2026-08-05T07:00:00Z",
                }],
            },
            quota_bytes=1_000_000,
            max_item_bytes=500_000,
        )

        response = client.get("/api/portfolio-center/research-coverage", headers=headers)
        isolated = client.get(
            "/api/portfolio-center/research-coverage",
            headers={"X-User-Id": "alice", "X-Workspace-Id": "desk-b"},
        )

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == "newma-desk.portfolio-research-coverage.v1"
    assert response.json()["positions"][0]["references"][0]["artifactId"] == "thesis-aapl"
    assert response.json()["positions"][0]["missingGroups"] == ["supporting-analysis"]
    assert isolated.status_code == 200
    assert isolated.json()["positions"] == []


def test_portfolio_allocation_route_uses_registered_market_history(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    history_client = FakeHistoryClient()
    app = create_app(
        settings,
        data_services=[history_service()],
        data_service_client=history_client,
    )
    with TestClient(app) as client:
        assert client.get("/api/portfolio-center?includeQuotes=false").status_code == 200
        for symbol, price in (("AAPL", 200), ("MSFT", 400)):
            response = client.post(
                "/api/portfolio-center/activities",
                json={
                    "accountId": "main",
                    "type": "buy",
                    "market": "US",
                    "symbol": symbol,
                    "currency": "USD",
                    "quantity": 10,
                    "unitPrice": price,
                    "occurredAt": datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
                },
            )
            assert response.status_code == 201

        response = client.post(
            "/api/portfolio-center/allocations/optimize",
            json={
                "objective": "risk-balanced",
                "currency": "USD",
                "lookbackWeeks": 52,
                "maxWeight": 0.75,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["dataSources"] == ["route-test"]
    assert len(history_client.calls) == 2
    assert {call[1]["symbol"] for call in history_client.calls} == {"AAPL", "MSFT"}

    with TestClient(app) as client:
        performance = client.post(
            "/api/portfolio-center/performance/analyze",
            json={
                "currency": "USD",
                "lookbackWeeks": 52,
                "riskFreeRatePct": 2,
            },
        )

    assert performance.status_code == 200
    assert performance.json()["status"] == "ready"
    assert performance.json()["metrics"]["maxDrawdownPct"] <= 0


def test_order_lifecycle_is_linked_to_execution_ledger(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/portfolio-center?includeQuotes=false").status_code == 200
        order = client.post(
            "/api/portfolio-center/orders",
            json={
                "accountId": "main",
                "side": "buy",
                "market": "CN",
                "symbol": "600519",
                "name": "贵州茅台",
                "currency": "CNY",
                "orderType": "limit",
                "quantity": 10,
                "limitPrice": 1000,
                "timeInForce": "day",
                "status": "submitted",
            },
        )
        assert order.status_code == 201
        order_id = order.json()["id"]

        first = client.post(
            "/api/portfolio-center/activities",
            json={
                "accountId": "main",
                "type": "buy",
                "market": "CN",
                "symbol": "600519",
                "name": "贵州茅台",
                "currency": "CNY",
                "quantity": 4,
                "unitPrice": 998,
                "orderId": order_id,
                "executionId": "fill-1",
                "decisionPrice": 1002,
                "occurredAt": datetime(2026, 8, 24, tzinfo=UTC).isoformat(),
            },
        )
        assert first.status_code == 201
        partial = client.get("/api/portfolio-center?includeQuotes=false").json()["orders"][0]
        assert partial["status"] == "partial"
        assert partial["filledQuantity"] == 4

        second = client.post(
            "/api/portfolio-center/activities",
            json={
                "accountId": "main",
                "type": "buy",
                "market": "CN",
                "symbol": "600519",
                "currency": "CNY",
                "quantity": 6,
                "unitPrice": 1001,
                "orderId": order_id,
                "executionId": "fill-2",
                "occurredAt": datetime(2026, 8, 24, 1, tzinfo=UTC).isoformat(),
            },
        )
        assert second.status_code == 201
        filled = client.get("/api/portfolio-center?includeQuotes=false").json()["orders"][0]
        assert filled["status"] == "filled"
        assert filled["filledQuantity"] == 10
        assert filled["averageFillPrice"] == 999.8


def test_risk_policy_and_action_log_are_workspace_state(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "newma-desk.db",
        legacy_portfolio_path=tmp_path / "missing.json",
    )
    with TestClient(create_app(settings)) as client:
        policy = client.put(
            "/api/portfolio-center/risk-policy",
            json={
                "singlePositionLimitPct": 25,
                "topThreeLimitPct": 60,
                "minEffectivePositions": 6,
                "maxDrawdownLimitPct": 12,
                "var95LimitPct": 4,
                "maxUnpricedPositions": 1,
                "allowNegativeCash": False,
            },
        )
        assert policy.status_code == 200
        assert policy.json()["singlePositionLimitPct"] == 25

        action = client.post(
            "/api/portfolio-center/risk-actions",
            json={
                "ruleId": "single",
                "severity": "high",
                "title": "单一持仓限额",
                "detail": "当前 42%，上限 25%",
            },
        )
        assert action.status_code == 201
        action_id = action.json()["id"]
        acknowledged = client.patch(
            f"/api/portfolio-center/risk-actions/{action_id}",
            json={"status": "acknowledged", "owner": "组合经理"},
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["owner"] == "组合经理"

        dashboard = client.get("/api/portfolio-center?includeQuotes=false").json()
        assert dashboard["riskPolicy"]["maxDrawdownLimitPct"] == 12
        assert dashboard["riskActions"][0]["status"] == "acknowledged"
