from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from vibe_visualization_api.portfolio_center.models import (
    PortfolioAccountCreate,
    PortfolioActivityCreate,
    PortfolioOptimizationRequest,
    PortfolioPerformanceRequest,
)
from vibe_visualization_api.portfolio_center.history import PortfolioPriceHistory
from vibe_visualization_api.portfolio_center.quotes import (
    PortfolioQuote,
    ResearchPortfolioQuoteProvider,
    SecurityIdentity,
)
from vibe_visualization_api.portfolio_center.service import PortfolioCenterService
from vibe_visualization_api.portfolio_center.store import (
    PortfolioConflictError,
    PortfolioStore,
)


class FakeQuoteProvider:
    def __init__(self, quotes):
        self.quotes = quotes

    async def get_quotes(self, securities):
        return {
            security: self.quotes[security]
            for security in securities
            if security in self.quotes
        }


class UnexpectedQuoteProvider:
    async def get_quotes(self, securities):
        raise AssertionError("quote provider must not be called for a cost-only dashboard")


class FakeHistoryProvider:
    def __init__(self, histories):
        self.histories = histories
        self.calls = []

    async def get_histories(self, securities, *, limit):
        self.calls.append((securities, limit))
        return {
            security: self.histories[security]
            for security in securities
            if security in self.histories
        }


def activity(**overrides):
    payload = {
        "accountId": "main",
        "type": "buy",
        "market": "CN",
        "symbol": "600519",
        "name": "贵州茅台",
        "currency": "CNY",
        "quantity": 100,
        "unitPrice": 1000,
        "occurredAt": datetime(2026, 7, 1, tzinfo=UTC),
    }
    payload.update(overrides)
    return PortfolioActivityCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_research_quote_provider_uses_market_terminal_api_route() -> None:
    requested_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_url
        requested_url = str(request.url)
        return httpx.Response(
            200,
            request=request,
            json={
                "data": {
                    "items": [
                        {
                            "market": "CN",
                            "symbol": "600519",
                            "name": "贵州茅台",
                            "price": 1296.42,
                            "currency": "CNY",
                        }
                    ]
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ResearchPortfolioQuoteProvider(
        "http://127.0.0.1:8911/api/research",
        client=http_client,
    )
    identity = SecurityIdentity("CN", "600519")
    try:
        quotes = await provider.get_quotes([identity])
    finally:
        await http_client.aclose()

    assert requested_url == (
        "http://127.0.0.1:8911/api/research/api/market-terminal/quotes"
        "?symbols=CN%3A600519"
    )
    assert quotes[identity].price == 1296.42


@pytest.mark.asyncio
async def test_dashboard_derives_cross_market_positions_and_live_values(tmp_path: Path):
    store = PortfolioStore(tmp_path / "portfolio.db")
    provider = FakeQuoteProvider(
        {
            SecurityIdentity("CN", "600519"): PortfolioQuote(
                1100, name="贵州茅台", currency="CNY", source="test"
            ),
            SecurityIdentity("US", "AAPL"): PortfolioQuote(
                220, name="Apple", currency="USD", source="test"
            ),
        }
    )
    service = PortfolioCenterService(store, quote_provider=provider)
    service.create_account(
        user_id="alice",
        workspace_id="desk",
        account=PortfolioAccountCreate(id="main", name="主账户"),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            market="US",
            symbol="AAPL",
            name="Apple",
            currency="USD",
            quantity=10,
            unitPrice=200,
        ),
    )

    dashboard = await service.dashboard(user_id="alice", workspace_id="desk")

    assert dashboard.valuation_status == "live"
    assert [(item.market, item.symbol) for item in dashboard.positions] == [
        ("CN", "600519"),
        ("US", "AAPL"),
    ]
    assert dashboard.positions[0].market_value == 110_000
    assert dashboard.positions[0].unrealized_pnl == 10_000
    assert dashboard.positions[1].currency == "USD"
    assert {item.currency for item in dashboard.currencies} == {"CNY", "USD"}


@pytest.mark.asyncio
async def test_cost_only_dashboard_does_not_wait_for_quote_provider(tmp_path: Path):
    store = PortfolioStore(tmp_path / "portfolio.db")
    service = PortfolioCenterService(store, quote_provider=UnexpectedQuoteProvider())
    store.ensure_default_account(user_id="alice", workspace_id="desk")
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(),
    )

    dashboard = await service.dashboard(
        user_id="alice",
        workspace_id="desk",
        include_quotes=False,
    )

    assert dashboard.valuation_status == "cost-based"
    assert dashboard.positions[0].price is None
    assert dashboard.positions[0].cost_value == 100_000


@pytest.mark.asyncio
async def test_weighted_cost_sell_and_realized_pnl(tmp_path: Path):
    store = PortfolioStore(tmp_path / "portfolio.db")
    service = PortfolioCenterService(store)
    store.ensure_default_account(user_id="alice", workspace_id="desk")
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(quantity=100, unitPrice=10),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            quantity=100,
            unitPrice=20,
            occurredAt=datetime(2026, 7, 2, tzinfo=UTC),
        ),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            type="sell",
            quantity=50,
            unitPrice=25,
            fee=10,
            occurredAt=datetime(2026, 7, 3, tzinfo=UTC),
        ),
    )

    dashboard = await service.dashboard(user_id="alice", workspace_id="desk")

    position = dashboard.positions[0]
    assert position.quantity == 150
    assert position.average_cost == 15
    assert position.realized_pnl == 490
    assert dashboard.currencies[0].realized_pnl == 490


def test_rejects_sell_larger_than_position(tmp_path: Path):
    store = PortfolioStore(tmp_path / "portfolio.db")
    service = PortfolioCenterService(store)
    store.ensure_default_account(user_id="alice", workspace_id="desk")

    with pytest.raises(PortfolioConflictError, match="exceeds position"):
        service.add_activity(
            user_id="alice",
            workspace_id="desk",
            activity=activity(type="sell", quantity=1, unitPrice=1000),
        )


def test_legacy_import_is_idempotent(tmp_path: Path):
    store = PortfolioStore(tmp_path / "portfolio.db")
    document = {
        "holdings": [{"code": "600519", "shares": 100, "cost": 1200}],
        "closed": [
            {
                "code": "510300",
                "name": "沪深300ETF",
                "date": "2026-07-05",
                "shares": 1000,
                "cost": 3.5,
                "price": 4.0,
            }
        ],
    }

    first = store.import_legacy_document(
        user_id="alice",
        workspace_id="desk",
        document=document,
    )
    second = store.import_legacy_document(
        user_id="alice",
        workspace_id="desk",
        document=document,
    )

    assert first.imported is True
    assert first.activities_created == 3
    assert second.reason == "already-imported"
    assert len(store.list_activities(user_id="alice", workspace_id="desk")) == 3


@pytest.mark.asyncio
async def test_dashboard_never_imports_legacy_portfolio_implicitly(tmp_path: Path):
    legacy_path = tmp_path / "portfolio.json"
    legacy_path.write_text(
        '{"holdings":[{"code":"600519","shares":100,"cost":1200}]}',
        encoding="utf-8",
    )
    store = PortfolioStore(tmp_path / "portfolio.db")
    service = PortfolioCenterService(store, legacy_portfolio_path=legacy_path)

    dashboard = await service.dashboard(
        user_id="alice",
        workspace_id="new-workspace",
        include_quotes=False,
    )

    assert dashboard.positions == []
    migrated = service.import_legacy(
        user_id="alice",
        workspace_id="new-workspace",
    )
    assert migrated.imported is True
    imported = await service.dashboard(
        user_id="alice",
        workspace_id="new-workspace",
        include_quotes=False,
    )
    assert [(item.market, item.symbol) for item in imported.positions] == [
        ("CN", "600519")
    ]


@pytest.mark.asyncio
async def test_allocation_optimization_uses_weekly_history_and_currency_scope(
    tmp_path: Path,
):
    store = PortfolioStore(tmp_path / "portfolio.db")
    stable = [100 * (1.002**index) for index in range(90)]
    volatile = [
        100 * (1.003**index) * (1.04 if index % 2 else 0.96)
        for index in range(90)
    ]
    provider = FakeHistoryProvider(
        {
            SecurityIdentity("US", "AAPL"): PortfolioPriceHistory(
                tuple(stable), source="market-data", as_of="2026-08-01"
            ),
            SecurityIdentity("US", "MSFT"): PortfolioPriceHistory(
                tuple(volatile), source="market-data", as_of="2026-08-01"
            ),
        }
    )
    service = PortfolioCenterService(store, history_provider=provider)
    store.ensure_default_account(user_id="alice", workspace_id="desk")
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            market="US",
            symbol="AAPL",
            name="Apple",
            currency="USD",
            quantity=10,
            unitPrice=200,
        ),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            market="US",
            symbol="MSFT",
            name="Microsoft",
            currency="USD",
            quantity=5,
            unitPrice=400,
        ),
    )
    service.add_activity(
        user_id="alice",
        workspace_id="desk",
        activity=activity(
            market="CN",
            symbol="600519",
            currency="CNY",
        ),
    )

    result = await service.optimize_allocation(
        user_id="alice",
        workspace_id="desk",
        request=PortfolioOptimizationRequest(
            objective="minimum-volatility",
            currency="USD",
            lookbackWeeks=52,
            maxWeight=0.8,
        ),
    )

    assert result.status == "ready"
    assert result.currency == "USD"
    assert result.data_sources == ["market-data"]
    assert sum(item.target_weight for item in result.allocations) == pytest.approx(100)
    targets = {item.symbol: item.target_weight for item in result.allocations}
    assert targets["AAPL"] > targets["MSFT"]
    assert provider.calls[0][1] == 53
    assert {item.symbol for item in result.allocations} == {"AAPL", "MSFT"}

    performance = await service.analyze_historical_performance(
        user_id="alice",
        workspace_id="desk",
        request=PortfolioPerformanceRequest(
            currency="USD",
            lookbackWeeks=52,
            riskFreeRatePct=2,
        ),
    )

    assert performance.status == "ready"
    assert performance.coverage_weight_pct == 100
    assert performance.metrics is not None
    assert performance.metrics.annualized_volatility_pct > 0
    assert len(performance.series) == performance.observations
    assert provider.calls[1][1] == 53
