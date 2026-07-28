from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
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
