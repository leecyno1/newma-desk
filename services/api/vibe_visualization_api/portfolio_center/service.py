from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from vibe_visualization_api.portfolio_center.models import (
    AllocationSlice,
    ConcentrationSummary,
    CurrencySummary,
    LegacyImportResult,
    PortfolioAccount,
    PortfolioAccountCreate,
    PortfolioActivity,
    PortfolioActivityCreate,
    PortfolioAnalytics,
    PortfolioDashboard,
    PortfolioPosition,
)
from vibe_visualization_api.portfolio_center.quotes import (
    NullPortfolioQuoteProvider,
    PortfolioQuoteProvider,
    SecurityIdentity,
)
from vibe_visualization_api.portfolio_center.store import (
    PortfolioConflictError,
    PortfolioStore,
)


_EPSILON = 1e-9


class PortfolioCenterService:
    def __init__(
        self,
        store: PortfolioStore,
        *,
        quote_provider: PortfolioQuoteProvider | None = None,
        legacy_portfolio_path: Path | None = None,
    ):
        self._store = store
        self._quote_provider = quote_provider or NullPortfolioQuoteProvider()
        self._legacy_portfolio_path = legacy_portfolio_path

    def create_account(
        self,
        *,
        user_id: str,
        workspace_id: str,
        account: PortfolioAccountCreate,
    ) -> PortfolioAccount:
        return self._store.create_account(
            user_id=user_id,
            workspace_id=workspace_id,
            account=account,
        )

    def add_activity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        activity: PortfolioActivityCreate,
    ) -> PortfolioActivity:
        current = self._store.list_activities(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        candidate = PortfolioActivity.model_validate(
            {
                **activity.model_dump(mode="json", by_alias=True),
                "id": "validation",
                "createdAt": datetime.now(UTC),
            }
        )
        self._derive_positions([*current, candidate], quotes={})
        return self._store.add_activity(
            user_id=user_id,
            workspace_id=workspace_id,
            activity=activity,
        )

    def delete_activity(
        self,
        *,
        user_id: str,
        workspace_id: str,
        activity_id: str,
    ) -> None:
        self._store.delete_activity(
            user_id=user_id,
            workspace_id=workspace_id,
            activity_id=activity_id,
        )

    def import_legacy(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> LegacyImportResult:
        if self._legacy_portfolio_path is None:
            return LegacyImportResult(
                imported=False,
                activities_created=0,
                reason="legacy-path-disabled",
            )
        return self._store.import_legacy_file(
            user_id=user_id,
            workspace_id=workspace_id,
            path=self._legacy_portfolio_path,
        )

    async def dashboard(
        self,
        *,
        user_id: str,
        workspace_id: str,
        include_quotes: bool = True,
    ) -> PortfolioDashboard:
        self.import_legacy(user_id=user_id, workspace_id=workspace_id)
        self._store.ensure_default_account(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        accounts = self._store.list_accounts(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        activities = self._store.list_activities(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        identities = sorted(
            {
                SecurityIdentity(activity.market, activity.symbol)
                for activity in activities
                if activity.market and activity.symbol
            },
            key=lambda item: (item.market, item.symbol),
        )
        quotes = (
            await self._quote_provider.get_quotes(identities)
            if include_quotes
            else {}
        )
        positions, currencies = self._derive_positions(activities, quotes=quotes)
        quoted_positions = sum(1 for position in positions if position.price is not None)
        if not positions or quoted_positions == 0:
            valuation_status = "cost-based"
        elif quoted_positions == len(positions):
            valuation_status = "live"
        else:
            valuation_status = "partial"
        analytics = self._analytics(positions, accounts)
        return PortfolioDashboard(
            userId=user_id,
            workspaceId=workspace_id,
            accounts=accounts,
            activities=list(reversed(activities)),
            positions=positions,
            currencies=currencies,
            analytics=analytics,
            valuationStatus=valuation_status,
            updatedAt=datetime.now(UTC),
        )

    @staticmethod
    def _derive_positions(
        activities: list[PortfolioActivity],
        *,
        quotes: dict,
    ) -> tuple[list[PortfolioPosition], list[CurrencySummary]]:
        states: dict[tuple[str, str, str], dict[str, float | str]] = {}
        cash: defaultdict[str, float] = defaultdict(float)
        realized: defaultdict[str, float] = defaultdict(float)
        income: defaultdict[str, float] = defaultdict(float)
        fees: defaultdict[str, float] = defaultdict(float)

        for activity in sorted(
            activities,
            key=lambda item: (item.occurred_at, item.created_at, item.id),
        ):
            currency = activity.currency
            fee = float(activity.fee or 0)
            fees[currency] += fee
            if activity.type == "deposit":
                cash[currency] += float(activity.amount or 0)
                continue
            if activity.type == "withdrawal":
                cash[currency] -= float(activity.amount or 0)
                continue
            if activity.type in {"dividend", "interest"}:
                value = float(activity.amount or 0)
                cash[currency] += value
                income[currency] += value
                continue
            if activity.type == "fee":
                cash[currency] -= abs(float(activity.amount or 0))
                continue
            assert activity.market is not None and activity.symbol is not None
            key = (activity.account_id, activity.market, activity.symbol)
            state = states.setdefault(
                key,
                {
                    "name": activity.name or activity.symbol,
                    "currency": currency,
                    "quantity": 0.0,
                    "average_cost": 0.0,
                    "realized_pnl": 0.0,
                },
            )
            if activity.name:
                state["name"] = activity.name
            quantity = float(state["quantity"])
            average_cost = float(state["average_cost"])
            trade_quantity = float(activity.quantity or 0)
            if activity.type == "buy":
                trade_value = trade_quantity * float(activity.unit_price or 0)
                next_quantity = quantity + trade_quantity
                state["average_cost"] = (
                    (quantity * average_cost + trade_value + fee) / next_quantity
                )
                state["quantity"] = next_quantity
                cash[currency] -= trade_value + fee
            elif activity.type == "sell":
                if trade_quantity > quantity + _EPSILON:
                    raise PortfolioConflictError(
                        f"sell quantity exceeds position for {activity.market}:{activity.symbol}"
                    )
                proceeds = trade_quantity * float(activity.unit_price or 0)
                pnl = proceeds - trade_quantity * average_cost - fee
                state["realized_pnl"] = float(state["realized_pnl"]) + pnl
                realized[currency] += pnl
                state["quantity"] = max(0.0, quantity - trade_quantity)
                cash[currency] += proceeds - fee
                if float(state["quantity"]) <= _EPSILON:
                    state["quantity"] = 0.0
                    state["average_cost"] = 0.0
            elif activity.type == "split":
                ratio = trade_quantity
                if quantity > _EPSILON:
                    state["quantity"] = quantity * ratio
                    state["average_cost"] = average_cost / ratio

        positions: list[PortfolioPosition] = []
        cost_by_currency: defaultdict[str, float] = defaultdict(float)
        market_by_currency: defaultdict[str, float] = defaultdict(float)
        quoted_by_currency: set[str] = set()
        for (account_id, market, symbol), state in sorted(states.items()):
            quantity = float(state["quantity"])
            if quantity <= _EPSILON:
                continue
            average_cost = float(state["average_cost"])
            cost_value = quantity * average_cost
            identity = SecurityIdentity(market=market, symbol=symbol)
            quote = quotes.get(identity)
            price = float(quote.price) if quote is not None else None
            market_value = quantity * price if price is not None else None
            unrealized_pnl = market_value - cost_value if market_value is not None else None
            unrealized_pct = (
                unrealized_pnl / cost_value * 100
                if unrealized_pnl is not None and abs(cost_value) > _EPSILON
                else None
            )
            currency = str(quote.currency or state["currency"]) if quote else str(state["currency"])
            cost_by_currency[currency] += cost_value
            if market_value is not None:
                market_by_currency[currency] += market_value
                quoted_by_currency.add(currency)
            positions.append(
                PortfolioPosition(
                    accountId=account_id,
                    market=market,
                    symbol=symbol,
                    name=(quote.name if quote and quote.name else str(state["name"])),
                    currency=currency,
                    quantity=round(quantity, 8),
                    averageCost=round(average_cost, 8),
                    costValue=round(cost_value, 2),
                    price=round(price, 8) if price is not None else None,
                    marketValue=round(market_value, 2) if market_value is not None else None,
                    unrealizedPnl=round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                    unrealizedPnlPct=round(unrealized_pct, 2) if unrealized_pct is not None else None,
                    realizedPnl=round(float(state["realized_pnl"]), 2),
                    quoteSource=quote.source if quote else None,
                    quoteAsOf=quote.as_of if quote else None,
                )
            )

        currencies = sorted(
            set(cash) | set(cost_by_currency) | set(realized) | set(income) | set(fees)
        )
        summaries = [
            CurrencySummary(
                currency=currency,
                cash=round(cash[currency], 2),
                costValue=round(cost_by_currency[currency], 2),
                marketValue=(
                    round(market_by_currency[currency], 2)
                    if currency in quoted_by_currency
                    else None
                ),
                unrealizedPnl=(
                    round(market_by_currency[currency] - cost_by_currency[currency], 2)
                    if currency in quoted_by_currency
                    else None
                ),
                realizedPnl=round(realized[currency], 2),
                income=round(income[currency], 2),
                fees=round(fees[currency], 2),
            )
            for currency in currencies
        ]
        return positions, summaries

    @staticmethod
    def _analytics(
        positions: list[PortfolioPosition],
        accounts: list[PortfolioAccount],
    ) -> PortfolioAnalytics:
        basis = (
            "market-value"
            if positions and all(position.market_value is not None for position in positions)
            else "cost-value"
        )
        account_names = {account.id: account.name for account in accounts}

        def value(position: PortfolioPosition) -> float:
            if basis == "market-value" and position.market_value is not None:
                return position.market_value
            return position.cost_value

        def grouped(key_fn, label_fn) -> list[AllocationSlice]:
            groups: defaultdict[tuple[str, str], float] = defaultdict(float)
            for position in positions:
                groups[(position.currency, key_fn(position))] += value(position)
            totals: defaultdict[str, float] = defaultdict(float)
            for (currency, _), amount in groups.items():
                totals[currency] += amount
            return [
                AllocationSlice(
                    key=key,
                    label=label_fn(key),
                    currency=currency,
                    value=round(amount, 2),
                    weight=(
                        round(amount / totals[currency] * 100, 2)
                        if abs(totals[currency]) > _EPSILON
                        else 0
                    ),
                )
                for (currency, key), amount in sorted(groups.items())
            ]

        values = [max(0.0, value(position)) for position in positions]
        total = sum(values)
        weights = sorted(
            (amount / total for amount in values if total > _EPSILON),
            reverse=True,
        )
        hhi = sum(weight * weight for weight in weights)
        concentration = ConcentrationSummary(
            positionCount=len(positions),
            topPositionWeight=round((weights[0] if weights else 0) * 100, 2),
            topThreeWeight=round(sum(weights[:3]) * 100, 2),
            herfindahlIndex=round(hhi, 6),
            effectivePositionCount=round(1 / hhi, 2) if hhi > _EPSILON else 0,
        )
        currency_groups: defaultdict[str, float] = defaultdict(float)
        for position in positions:
            currency_groups[position.currency] += value(position)
        nominal_total = sum(currency_groups.values())
        return PortfolioAnalytics(
            basis=basis,
            byMarket=grouped(lambda position: position.market, lambda key: key),
            byCurrency=[
                AllocationSlice(
                    key=currency,
                    label=currency,
                    currency=currency,
                    value=round(amount, 2),
                    weight=(
                        round(amount / nominal_total * 100, 2)
                        if abs(nominal_total) > _EPSILON
                        else 0
                    ),
                )
                for currency, amount in sorted(currency_groups.items())
            ],
            byAccount=grouped(
                lambda position: position.account_id,
                lambda key: account_names.get(key, key),
            ),
            concentration=concentration,
        )
