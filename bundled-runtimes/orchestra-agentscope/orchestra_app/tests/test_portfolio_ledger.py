from decimal import Decimal
from pathlib import Path

import pytest

from orchestra_app.models import (
    CreatePortfolioTransactionRequest,
    PortfolioMarkInput,
)
from orchestra_app.service import CommitteeService
from orchestra_app.storage import SQLiteStore


def test_portfolio_ledger_positions_nav_and_recovery(tmp_path: Path) -> None:
    database = tmp_path / "portfolio.db"
    store = SQLiteStore(database)
    service = CommitteeService(store)
    portfolio = service.create_portfolio("local-user", "成长组合", "测试账本", "CNY")

    service.create_portfolio_transaction(
        portfolio.id,
        "local-user",
        CreatePortfolioTransactionRequest(
            transaction_type="cash_in",
            amount=Decimal("1000000"),
        ),
    )
    service.create_portfolio_transaction(
        portfolio.id,
        "local-user",
        CreatePortfolioTransactionRequest(
            transaction_type="buy",
            asset_code="300570.SZ",
            asset_name="太辰光",
            asset_class="equity",
            quantity=Decimal("100"),
            price=Decimal("10"),
            fees=Decimal("5"),
        ),
    )
    snapshot = service.create_portfolio_valuation(
        portfolio.id,
        "local-user",
        service.get_portfolio_detail(portfolio.id, "local-user").summary.as_of,
        [PortfolioMarkInput(asset_code="300570.SZ", price=Decimal("12"), source="manual")],
        Decimal("1000000"),
        "收盘估值",
    )

    detail = service.get_portfolio_detail(portfolio.id, "local-user")
    assert detail.summary.cash_balance == Decimal("998995")
    assert detail.summary.market_value == Decimal("1200")
    assert detail.summary.net_asset_value == Decimal("1000195")
    assert detail.positions[0].average_cost == Decimal("10.05")
    assert detail.positions[0].unrealized_pnl == Decimal("195.00")
    assert snapshot.unit_nav == Decimal("1.000195")

    with pytest.raises(ValueError, match="卖出数量超过可用持仓"):
        service.create_portfolio_transaction(
            portfolio.id,
            "local-user",
            CreatePortfolioTransactionRequest(
                transaction_type="sell",
                asset_code="300570.SZ",
                asset_name="太辰光",
                asset_class="equity",
                quantity=Decimal("101"),
                price=Decimal("12"),
            ),
        )

    store.close()
    recovered_store = SQLiteStore(database)
    recovered_service = CommitteeService(recovered_store)
    recovered = recovered_service.get_portfolio_detail(portfolio.id, "local-user")
    assert len(recovered.transactions) == 2
    assert recovered.positions[0].asset_code == "300570.SZ"
    assert recovered.nav_history[0].note == "收盘估值"
    recovered_store.close()
