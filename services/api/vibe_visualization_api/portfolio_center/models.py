from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from vibe_visualization_api.research_archive.models import ResearchArchiveEntry


ACCOUNT_ID_PATTERN = r"^[a-z][a-z0-9-]{0,63}$"
SYMBOL_PATTERN = r"^[A-Z0-9][A-Z0-9.\-]{0,23}$"
CURRENCY_PATTERN = r"^[A-Z]{3,12}$"


class PortfolioModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class PortfolioAccountCreate(PortfolioModel):
    id: str = Field(pattern=ACCOUNT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(default="CNY", pattern=CURRENCY_PATTERN)
    platform: str | None = Field(default=None, max_length=80)
    account_type: Literal["securities", "cash", "paper"] = "securities"

    @field_validator("name", "platform")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioAccount(PortfolioAccountCreate):
    archived: bool = False
    created_at: datetime
    updated_at: datetime


class PortfolioActivityCreate(PortfolioModel):
    account_id: str = Field(pattern=ACCOUNT_ID_PATTERN)
    type: Literal[
        "buy",
        "sell",
        "dividend",
        "interest",
        "fee",
        "deposit",
        "withdrawal",
        "split",
    ]
    market: Literal["CN", "HK", "US"] | None = None
    symbol: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    name: str | None = Field(default=None, max_length=160)
    currency: str = Field(default="CNY", pattern=CURRENCY_PATTERN)
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    fee: float = Field(default=0, ge=0)
    occurred_at: datetime
    note: str | None = Field(default=None, max_length=500)
    source: Literal["manual", "import", "broker"] = "manual"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("name", "note")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_activity_shape(self) -> Self:
        security_types = {"buy", "sell", "dividend", "split"}
        if self.type in security_types and (not self.market or not self.symbol):
            raise ValueError("security activity requires market and symbol")
        if self.type in {"buy", "sell"}:
            if self.quantity is None or self.quantity <= 0:
                raise ValueError("buy and sell require positive quantity")
            if self.unit_price is None or self.unit_price < 0:
                raise ValueError("buy and sell require non-negative unit price")
        elif self.type == "split":
            if self.quantity is None or self.quantity <= 0:
                raise ValueError("split requires a positive ratio")
        elif self.amount is None:
            raise ValueError(f"{self.type} requires amount")
        return self


class PortfolioActivity(PortfolioActivityCreate):
    id: str
    created_at: datetime


class PortfolioPosition(PortfolioModel):
    account_id: str
    market: Literal["CN", "HK", "US"]
    symbol: str
    name: str
    currency: str
    quantity: float
    average_cost: float
    cost_value: float
    price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    realized_pnl: float = 0
    quote_source: str | None = None
    quote_as_of: str | None = None


class CurrencySummary(PortfolioModel):
    currency: str
    cash: float
    cost_value: float
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float
    income: float
    fees: float


class AllocationSlice(PortfolioModel):
    key: str
    label: str
    currency: str
    value: float
    weight: float


class ConcentrationSummary(PortfolioModel):
    position_count: int
    top_position_weight: float
    top_three_weight: float
    herfindahl_index: float
    effective_position_count: float


class PortfolioAnalytics(PortfolioModel):
    basis: Literal["market-value", "cost-value"]
    by_market: list[AllocationSlice]
    by_currency: list[AllocationSlice]
    by_account: list[AllocationSlice]
    concentration: ConcentrationSummary


class PortfolioDashboard(PortfolioModel):
    user_id: str
    workspace_id: str
    accounts: list[PortfolioAccount]
    activities: list[PortfolioActivity]
    positions: list[PortfolioPosition]
    currencies: list[CurrencySummary]
    analytics: PortfolioAnalytics
    valuation_status: Literal["live", "partial", "cost-based"]
    updated_at: datetime


class PortfolioResearchPosition(PortfolioModel):
    market: Literal["CN", "HK", "US"]
    symbol: str
    name: str
    account_ids: list[str]
    status: Literal["complete", "partial", "missing"]
    reference_count: int = Field(ge=0)
    active_reference_count: int = Field(ge=0)
    core_kinds: list[Literal["thesis", "research-memo"]]
    supporting_kinds: list[
        Literal["earnings", "peer-comparison", "valuation"]
    ]
    missing_groups: list[
        Literal["core-thesis-or-memo", "supporting-analysis"]
    ]
    attention_reasons: list[
        Literal["review-overdue", "stale-core-research", "invalidated-thesis"]
    ]
    latest_updated_at: datetime | None = None
    references: list[ResearchArchiveEntry]


class PortfolioResearchSummary(PortfolioModel):
    position_count: int = Field(ge=0)
    complete_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    attention_count: int = Field(ge=0)
    active_reference_count: int = Field(ge=0)


class PortfolioResearchCoverage(PortfolioModel):
    schema_version: Literal["newma-desk.portfolio-research-coverage.v1"] = (
        "newma-desk.portfolio-research-coverage.v1"
    )
    user_id: str
    workspace_id: str
    generated_at: datetime
    summary: PortfolioResearchSummary
    positions: list[PortfolioResearchPosition]


class LegacyImportResult(PortfolioModel):
    imported: bool
    activities_created: int
    reason: str


class PortfolioOptimizationAsset(PortfolioModel):
    market: Literal["CN", "HK", "US"]
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    name: str | None = Field(default=None, max_length=160)
    currency: str = Field(pattern=CURRENCY_PATTERN)

    @field_validator("symbol", "currency")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class PortfolioOptimizationRequest(PortfolioModel):
    objective: Literal[
        "minimum-volatility",
        "risk-balanced",
        "return-seeking",
    ] = "risk-balanced"
    currency: str = Field(default="CNY", pattern=CURRENCY_PATTERN)
    lookback_weeks: int = Field(default=104, ge=40, le=260)
    max_weight: float = Field(default=0.35, ge=0.05, le=1)
    allow_cash: bool = False
    cash_weight: float = Field(default=0, ge=0, le=0.5)
    risk_free_rate_pct: float = Field(default=2, ge=-10, le=30)
    assets: list[PortfolioOptimizationAsset] = Field(
        default_factory=list,
        max_length=30,
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_constraints(self) -> Self:
        if not self.allow_cash and self.cash_weight > 0:
            raise ValueError("cashWeight requires allowCash")
        identities = [(asset.market, asset.symbol) for asset in self.assets]
        if len(identities) != len(set(identities)):
            raise ValueError("optimization assets must be unique")
        if any(asset.currency != self.currency for asset in self.assets):
            raise ValueError("optimization assets must use the selected currency")
        return self


class PortfolioOptimizationAllocation(PortfolioModel):
    market: Literal["CN", "HK", "US", "CASH"]
    symbol: str
    name: str
    currency: str
    current_weight: float
    target_weight: float
    change_weight: float
    expected_return_pct: float | None = None
    volatility_pct: float | None = None
    risk_contribution_pct: float | None = None
    history_points: int = 0
    frozen: bool = False


class PortfolioOptimizationGap(PortfolioModel):
    market: Literal["CN", "HK", "US"]
    symbol: str
    reason: str


class PortfolioOptimizationResult(PortfolioModel):
    status: Literal["ready", "partial", "insufficient-data"]
    objective: Literal[
        "minimum-volatility",
        "risk-balanced",
        "return-seeking",
    ]
    method: str
    currency: str
    timeframe: Literal["1w"] = "1w"
    lookback_weeks: int
    observations: int
    data_sources: list[str]
    as_of: str | None = None
    annualized_expected_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    current_concentration: float
    target_concentration: float
    allocations: list[PortfolioOptimizationAllocation]
    missing_assets: list[PortfolioOptimizationGap]
    warnings: list[str]
    generated_at: datetime


class PortfolioPerformanceRequest(PortfolioModel):
    currency: str = Field(default="CNY", pattern=CURRENCY_PATTERN)
    lookback_weeks: int = Field(default=156, ge=40, le=260)
    risk_free_rate_pct: float = Field(default=2, ge=-10, le=30)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioPerformanceMetrics(PortfolioModel):
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None
    max_drawdown_pct: float
    max_drawdown_duration_weeks: int
    win_rate_pct: float
    profit_factor: float | None = None
    best_week_pct: float
    worst_week_pct: float
    value_at_risk_95_pct: float
    conditional_value_at_risk_95_pct: float


class PortfolioPerformancePoint(PortfolioModel):
    label: str
    equity: float
    drawdown_pct: float


class PortfolioPerformanceResult(PortfolioModel):
    status: Literal["ready", "partial", "insufficient-data"]
    method: str
    currency: str
    timeframe: Literal["1w"] = "1w"
    lookback_weeks: int
    observations: int
    coverage_weight_pct: float
    metrics: PortfolioPerformanceMetrics | None = None
    series: list[PortfolioPerformancePoint]
    data_sources: list[str]
    as_of: str | None = None
    missing_assets: list[PortfolioOptimizationGap]
    warnings: list[str]
    generated_at: datetime


class StrategicAllocationRequest(PortfolioModel):
    model: Literal["black-litterman", "risk-parity", "minimum-volatility"] = (
        "black-litterman"
    )
    target_volatility_pct: float = Field(default=10, ge=3, le=30)
    horizon_months: Literal[1, 3, 6] = 6
    max_weight: float = Field(default=0.35, ge=0.15, le=0.6)
    risk_free_rate_pct: float = Field(default=1.5, ge=-2, le=15)


class StrategicAllocationAsset(PortfolioModel):
    id: str
    name: str
    category: str
    cycle_asset_id: str | None = None
    benchmark_weight_pct: float
    target_weight_pct: float
    expected_return_pct: float
    volatility_pct: float
    risk_contribution_pct: float
    equilibrium_return_pct: float
    cycle_view_return_pct: float | None = None
    up_probability_pct: float | None = None
    confidence_pct: float
    publication_status: str
    evidence_level: str
    source_as_of: str | None = None
    forecast_origin: str | None = None


class StrategicAllocationScenario(PortfolioModel):
    id: str
    name: str
    description: str
    portfolio_impact_pct: float
    asset_impacts_pct: dict[str, float]


class StrategicAllocationResult(PortfolioModel):
    status: Literal["ready", "partial", "prior-only"]
    model: Literal["black-litterman", "risk-parity", "minimum-volatility"]
    method: str
    horizon_months: Literal[1, 3, 6]
    target_volatility_pct: float
    achieved_volatility_pct: float
    expected_return_pct: float
    sharpe: float | None = None
    cash_weight_pct: float
    assets: list[StrategicAllocationAsset]
    scenarios: list[StrategicAllocationScenario]
    insights: list[str]
    warnings: list[str]
    data_sources: list[str]
    cycle_as_of: str | None = None
    generated_at: datetime
