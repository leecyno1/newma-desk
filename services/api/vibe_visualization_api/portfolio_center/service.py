from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from vibe_visualization_api.portfolio_center.asset_allocation import (
    build_strategic_allocation,
    fetch_cycle_views,
)

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
    PortfolioPerformanceMetrics,
    PortfolioPerformancePoint,
    PortfolioPerformanceRequest,
    PortfolioPerformanceResult,
    PortfolioOptimizationAllocation,
    PortfolioOptimizationGap,
    PortfolioOptimizationRequest,
    PortfolioOptimizationResult,
    PortfolioPosition,
    StrategicAllocationRequest,
    StrategicAllocationResult,
)
from vibe_visualization_api.portfolio_center.history import (
    NullPortfolioHistoryProvider,
    PortfolioHistoryProvider,
)
from vibe_visualization_api.portfolio_center.optimization import optimize_weights
from vibe_visualization_api.portfolio_center.performance import analyze_performance
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
        history_provider: PortfolioHistoryProvider | None = None,
        legacy_portfolio_path: Path | None = None,
        cycle_base_url: str = "http://127.0.0.1:4174",
        cycle_client: httpx.AsyncClient | None = None,
    ):
        self._store = store
        self._quote_provider = quote_provider or NullPortfolioQuoteProvider()
        self._history_provider = history_provider or NullPortfolioHistoryProvider()
        self._legacy_portfolio_path = legacy_portfolio_path
        self._cycle_base_url = cycle_base_url
        self._cycle_client = cycle_client

    async def strategic_allocation(
        self,
        request: StrategicAllocationRequest,
    ) -> StrategicAllocationResult:
        try:
            cycle_rows = await fetch_cycle_views(
                self._cycle_base_url,
                request.horizon_months,
                client=self._cycle_client,
            )
        except (httpx.HTTPError, ValueError):
            result = build_strategic_allocation(request, [])
            result.warnings.append("周期模块暂时不可用，当前结果仅使用长期均衡先验。")
            return result
        return build_strategic_allocation(request, cycle_rows)

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

    async def optimize_allocation(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: PortfolioOptimizationRequest,
    ) -> PortfolioOptimizationResult:
        dashboard = await self.dashboard(
            user_id=user_id,
            workspace_id=workspace_id,
            include_quotes=True,
        )
        candidates = self._optimization_candidates(dashboard.positions, request)
        cash_weight = request.cash_weight if request.allow_cash else 0.0
        warnings = [
            "结果基于历史周线估计，仅用于组合研究，不代表未来收益。",
        ]
        if not candidates:
            return PortfolioOptimizationResult(
                status="insufficient-data",
                objective=request.objective,
                method="no-assets",
                currency=request.currency,
                lookbackWeeks=request.lookback_weeks,
                observations=0,
                dataSources=[],
                currentConcentration=0,
                targetConcentration=round(cash_weight * cash_weight, 6),
                allocations=self._cash_allocation(request, cash_weight),
                missingAssets=[],
                warnings=[*warnings, "当前币种没有可优化的持仓或自定义资产。"],
                generatedAt=datetime.now(UTC),
            )

        identities = [candidate["identity"] for candidate in candidates]
        histories = await self._history_provider.get_histories(
            identities,
            limit=request.lookback_weeks + 1,
        )
        valid: list[dict] = []
        missing: list[PortfolioOptimizationGap] = []
        frozen_targets: dict[SecurityIdentity, float] = {}
        risky_target = 1 - cash_weight
        for candidate in candidates:
            identity = candidate["identity"]
            history = histories.get(identity)
            if history is None or len(history.closes) < 9:
                frozen_targets[identity] = candidate["current_weight"] * risky_target
                missing.append(
                    PortfolioOptimizationGap(
                        market=identity.market,
                        symbol=identity.symbol,
                        reason="周线历史不足或统一行情服务暂不可用",
                    )
                )
            else:
                valid.append({**candidate, "history": history})

        frozen_weight = sum(frozen_targets.values())
        available_weight = max(0.0, risky_target - frozen_weight)
        estimate = None
        if valid and available_weight > _EPSILON:
            estimate = optimize_weights(
                [item["history"].closes for item in valid],
                objective=request.objective,
                total_weight=available_weight,
                max_weight=request.max_weight,
                risk_free_rate=request.risk_free_rate_pct / 100,
                cash_weight=cash_weight,
            )
            warnings.extend(estimate.warnings)
        elif missing:
            warnings.append("没有足够历史序列，目标权重暂时保持当前结构。")

        target_weights = dict(frozen_targets)
        expected: dict[SecurityIdentity, float] = {}
        volatility: dict[SecurityIdentity, float] = {}
        risk_contribution: dict[SecurityIdentity, float] = {}
        history_points: dict[SecurityIdentity, int] = {}
        if estimate is not None:
            for index, item in enumerate(valid):
                identity = item["identity"]
                target_weights[identity] = estimate.weights[index]
                expected[identity] = estimate.annual_returns[index]
                volatility[identity] = estimate.annual_volatilities[index]
                risk_contribution[identity] = estimate.risk_contributions[index]
                history_points[identity] = len(item["history"].closes)

        allocations = [
            PortfolioOptimizationAllocation(
                market=candidate["identity"].market,
                symbol=candidate["identity"].symbol,
                name=candidate["name"],
                currency=request.currency,
                currentWeight=round(candidate["current_weight"] * 100, 4),
                targetWeight=round(
                    target_weights.get(candidate["identity"], 0.0) * 100,
                    4,
                ),
                changeWeight=round(
                    (
                        target_weights.get(candidate["identity"], 0.0)
                        - candidate["current_weight"]
                    )
                    * 100,
                    4,
                ),
                expectedReturnPct=(
                    round(expected[candidate["identity"]] * 100, 4)
                    if candidate["identity"] in expected
                    else None
                ),
                volatilityPct=(
                    round(volatility[candidate["identity"]] * 100, 4)
                    if candidate["identity"] in volatility
                    else None
                ),
                riskContributionPct=(
                    round(risk_contribution[candidate["identity"]] * 100, 4)
                    if candidate["identity"] in risk_contribution
                    else None
                ),
                historyPoints=history_points.get(candidate["identity"], 0),
                frozen=candidate["identity"] in frozen_targets,
            )
            for candidate in candidates
        ]
        allocations.extend(self._cash_allocation(request, cash_weight))
        allocations.sort(key=lambda item: item.target_weight, reverse=True)
        current_concentration = sum(
            candidate["current_weight"] ** 2 for candidate in candidates
        )
        target_concentration = sum(
            (allocation.target_weight / 100) ** 2 for allocation in allocations
        )
        data_sources = sorted(
            {
                item["history"].source
                for item in valid
                if item["history"].source
            }
        )
        as_of_values = [
            item["history"].as_of
            for item in valid
            if item["history"].as_of
        ]
        if any(
            target > request.max_weight + _EPSILON
            for target in frozen_targets.values()
        ):
            warnings.append("部分缺失历史的持仓超过权重上限，已冻结其当前风险份额。")
        return PortfolioOptimizationResult(
            status=(
                "insufficient-data"
                if estimate is None
                else "partial"
                if missing
                else "ready"
            ),
            objective=request.objective,
            method=estimate.method if estimate is not None else "preserve-current-weights",
            currency=request.currency,
            lookbackWeeks=request.lookback_weeks,
            observations=estimate.observations if estimate is not None else 0,
            dataSources=data_sources,
            asOf=max(as_of_values) if as_of_values else None,
            annualizedExpectedReturnPct=(
                round(estimate.portfolio_return * 100, 4)
                if estimate is not None
                else None
            ),
            annualizedVolatilityPct=(
                round(estimate.portfolio_volatility * 100, 4)
                if estimate is not None
                else None
            ),
            currentConcentration=round(current_concentration, 6),
            targetConcentration=round(target_concentration, 6),
            allocations=allocations,
            missingAssets=missing,
            warnings=list(dict.fromkeys(warnings)),
            generatedAt=datetime.now(UTC),
        )

    async def analyze_historical_performance(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: PortfolioPerformanceRequest,
    ) -> PortfolioPerformanceResult:
        dashboard = await self.dashboard(
            user_id=user_id,
            workspace_id=workspace_id,
            include_quotes=True,
        )
        candidates = self._currency_candidates(
            dashboard.positions,
            request.currency,
        )
        warnings = [
            "指标采用当前持仓权重进行历史周线模拟，不等同于包含全部现金流的账户 TWR。",
            "历史表现只用于研究，不代表未来收益。",
        ]
        if not candidates:
            return PortfolioPerformanceResult(
                status="insufficient-data",
                method="quantstats-inspired-weekly",
                currency=request.currency,
                lookbackWeeks=request.lookback_weeks,
                observations=0,
                coverageWeightPct=0,
                series=[],
                dataSources=[],
                missingAssets=[],
                warnings=[*warnings, "当前币种没有可分析持仓。"],
                generatedAt=datetime.now(UTC),
            )
        histories = await self._history_provider.get_histories(
            [candidate["identity"] for candidate in candidates],
            limit=request.lookback_weeks + 1,
        )
        valid: list[dict] = []
        missing: list[PortfolioOptimizationGap] = []
        for candidate in candidates:
            identity = candidate["identity"]
            history = histories.get(identity)
            if history is None or len(history.closes) < 9:
                missing.append(
                    PortfolioOptimizationGap(
                        market=identity.market,
                        symbol=identity.symbol,
                        reason="周线历史不足或统一行情服务暂不可用",
                    )
                )
            else:
                valid.append({**candidate, "history": history})
        coverage_weight = sum(item["current_weight"] for item in valid)
        if not valid or coverage_weight <= _EPSILON:
            return PortfolioPerformanceResult(
                status="insufficient-data",
                method="quantstats-inspired-weekly",
                currency=request.currency,
                lookbackWeeks=request.lookback_weeks,
                observations=0,
                coverageWeightPct=0,
                series=[],
                dataSources=[],
                missingAssets=missing,
                warnings=[*warnings, "没有足够历史序列生成绩效指标。"],
                generatedAt=datetime.now(UTC),
            )
        estimate = analyze_performance(
            [item["history"].closes for item in valid],
            [item["current_weight"] / coverage_weight for item in valid],
            risk_free_rate=request.risk_free_rate_pct / 100,
        )
        reference_timestamps = valid[0]["history"].timestamps
        if len(reference_timestamps) >= estimate.observations:
            labels = [
                self._history_label(value)
                for value in reference_timestamps[-estimate.observations :]
            ]
        else:
            labels = [f"W{index + 1}" for index in range(estimate.observations)]
        series = [
            PortfolioPerformancePoint(
                label=label,
                equity=round(equity, 6),
                drawdownPct=round(drawdown * 100, 4),
            )
            for label, equity, drawdown in zip(
                labels,
                estimate.equity_curve,
                estimate.drawdowns,
                strict=True,
            )
        ]
        data_sources = sorted(
            {
                item["history"].source
                for item in valid
                if item["history"].source
            }
        )
        as_of_values = [
            item["history"].as_of
            for item in valid
            if item["history"].as_of
        ]
        if missing:
            warnings.append("缺少历史的持仓未纳入模拟，覆盖率已单独显示。")
        metrics = PortfolioPerformanceMetrics(
            totalReturnPct=round(estimate.total_return * 100, 4),
            annualizedReturnPct=round(estimate.annualized_return * 100, 4),
            annualizedVolatilityPct=round(estimate.annualized_volatility * 100, 4),
            sharpe=round(estimate.sharpe, 4) if estimate.sharpe is not None else None,
            sortino=round(estimate.sortino, 4) if estimate.sortino is not None else None,
            calmar=round(estimate.calmar, 4) if estimate.calmar is not None else None,
            maxDrawdownPct=round(estimate.max_drawdown * 100, 4),
            maxDrawdownDurationWeeks=estimate.max_drawdown_duration,
            winRatePct=round(estimate.win_rate * 100, 4),
            profitFactor=(
                round(estimate.profit_factor, 4)
                if estimate.profit_factor is not None
                else None
            ),
            bestWeekPct=round(estimate.best_period * 100, 4),
            worstWeekPct=round(estimate.worst_period * 100, 4),
            valueAtRisk95Pct=round(estimate.value_at_risk_95 * 100, 4),
            conditionalValueAtRisk95Pct=round(
                estimate.conditional_value_at_risk_95 * 100,
                4,
            ),
        )
        return PortfolioPerformanceResult(
            status="partial" if missing else "ready",
            method="quantstats-inspired-weekly",
            currency=request.currency,
            lookbackWeeks=request.lookback_weeks,
            observations=estimate.observations,
            coverageWeightPct=round(coverage_weight * 100, 4),
            metrics=metrics,
            series=series,
            dataSources=data_sources,
            asOf=max(as_of_values) if as_of_values else None,
            missingAssets=missing,
            warnings=warnings,
            generatedAt=datetime.now(UTC),
        )

    @staticmethod
    def _optimization_candidates(
        positions: list[PortfolioPosition],
        request: PortfolioOptimizationRequest,
    ) -> list[dict]:
        if not request.assets:
            return PortfolioCenterService._currency_candidates(
                positions,
                request.currency,
            )
        values: defaultdict[SecurityIdentity, float] = defaultdict(float)
        names: dict[SecurityIdentity, str] = {}
        for position in positions:
            if position.currency != request.currency:
                continue
            identity = SecurityIdentity(position.market, position.symbol)
            values[identity] += max(
                0.0,
                position.market_value
                if position.market_value is not None
                else position.cost_value,
            )
            names[identity] = position.name
        identities = [
            SecurityIdentity(asset.market, asset.symbol)
            for asset in request.assets
        ]
        for asset, identity in zip(request.assets, identities, strict=True):
            names[identity] = asset.name or names.get(identity, asset.symbol)
        total = sum(values[identity] for identity in identities)
        return [
            {
                "identity": identity,
                "name": names.get(identity, identity.symbol),
                "current_weight": (
                    values[identity] / total if total > _EPSILON else 0.0
                ),
            }
            for identity in identities
        ]

    @staticmethod
    def _currency_candidates(
        positions: list[PortfolioPosition],
        currency: str,
    ) -> list[dict]:
        values: defaultdict[SecurityIdentity, float] = defaultdict(float)
        names: dict[SecurityIdentity, str] = {}
        for position in positions:
            if position.currency != currency:
                continue
            identity = SecurityIdentity(position.market, position.symbol)
            values[identity] += max(
                0.0,
                position.market_value
                if position.market_value is not None
                else position.cost_value,
            )
            names[identity] = position.name
        total = sum(values.values())
        return [
            {
                "identity": identity,
                "name": names.get(identity, identity.symbol),
                "current_weight": values[identity] / total if total > _EPSILON else 0.0,
            }
            for identity in sorted(values, key=lambda item: (item.market, item.symbol))
        ]

    @staticmethod
    def _history_label(value: float) -> str:
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, UTC).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)

    @staticmethod
    def _cash_allocation(
        request: PortfolioOptimizationRequest,
        cash_weight: float,
    ) -> list[PortfolioOptimizationAllocation]:
        if cash_weight <= _EPSILON:
            return []
        return [
            PortfolioOptimizationAllocation(
                market="CASH",
                symbol=request.currency,
                name=f"{request.currency} 现金储备",
                currency=request.currency,
                currentWeight=0,
                targetWeight=round(cash_weight * 100, 4),
                changeWeight=round(cash_weight * 100, 4),
                expectedReturnPct=request.risk_free_rate_pct,
                volatilityPct=0,
                riskContributionPct=0,
                historyPoints=0,
            )
        ]

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
