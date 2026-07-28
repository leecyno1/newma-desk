from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


PilotMode = Literal["analysis-only", "paper-only"]
PilotState = Literal["disabled", "blocked", "eligible"]


class FinancePilotModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class PilotAuditStatus(FinancePilotModel):
    revision: str
    tag: str | None = None
    reviewed_at: str | None = None
    dependency_audit: str


class PilotRuntimeStatus(FinancePilotModel):
    pilot_id: str
    label: str
    mode: PilotMode
    state: PilotState
    requested: bool
    activatable: bool
    reasons: list[str] = Field(default_factory=list)
    audit: PilotAuditStatus
    workspace: str
    workspace_exists: bool
    origin: str
    capabilities: list[str] = Field(default_factory=list)


class PilotStatusDocument(FinancePilotModel):
    schema_version: Literal["newma-desk.finance-pilots.v1"] = (
        "newma-desk.finance-pilots.v1"
    )
    pilots: list[PilotRuntimeStatus]


class PilotAdaptRequest(FinancePilotModel):
    payload: dict[str, Any]


class ResearchSubject(FinancePilotModel):
    symbol: str
    name: str | None = None
    market: str | None = None


class ResearchContextBlock(FinancePilotModel):
    id: str
    title: str
    status: Literal[
        "available",
        "missing",
        "not_supported",
        "fallback",
        "stale",
        "estimated",
        "partial",
        "fetch_failed",
    ]
    source: str | None = None
    as_of: str | None = None
    warnings: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ResearchDataQuality(FinancePilotModel):
    score: int | None = Field(default=None, ge=0, le=100)
    level: Literal["good", "usable", "limited", "poor"] | None = None
    block_scores: dict[str, int] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchHistoryItem(FinancePilotModel):
    id: str
    status: str
    created_at: str | None = None
    title: str | None = None


class ResearchTaskProgress(FinancePilotModel):
    task_id: str | None = None
    status: str
    stage: str | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    updated_at: str | None = None


class DailyStockAnalysisContext(FinancePilotModel):
    schema_version: Literal["newma-desk.daily-stock-analysis-context.v1"] = (
        "newma-desk.daily-stock-analysis-context.v1"
    )
    pilot_id: Literal["daily-stock-analysis"] = "daily-stock-analysis"
    mode: Literal["analysis-only"] = "analysis-only"
    subject: ResearchSubject
    blocks: list[ResearchContextBlock]
    data_quality: ResearchDataQuality
    report_history: list[ResearchHistoryItem] = Field(default_factory=list)
    task_progress: ResearchTaskProgress | None = None
    sources: list[str] = Field(default_factory=list)
    generated_at: str | None = None
    agent_context: dict[str, Any]


class StrategyIdentity(FinancePilotModel):
    id: str
    name: str
    version: str | None = None
    template_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestDataset(FinancePilotModel):
    symbols: list[str]
    market: str | None = None
    start_date: str
    end_date: str
    timeframe: str | None = None
    source: Literal["newma-desk"] = "newma-desk"


class BacktestMetrics(FinancePilotModel):
    total_return: float | None = None
    annualized_return: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    win_rate: float | None = None
    turnover: float | None = None
    fees: float | None = None
    trade_count: int | None = Field(default=None, ge=0)


class EquityPoint(FinancePilotModel):
    timestamp: str
    equity: float


class AttributionItem(FinancePilotModel):
    factor: str
    contribution: float
    unit: str = "%"
    note: str | None = None


class StrategyLedgerRecord(FinancePilotModel):
    schema_version: Literal["newma-desk.strategy-ledger.v1"] = (
        "newma-desk.strategy-ledger.v1"
    )
    ledger_id: str
    pilot_id: Literal["quantdinger"] = "quantdinger"
    mode: Literal["paper-only"] = "paper-only"
    execution_mode: Literal["paper"] = "paper"
    status: Literal["completed", "failed", "partial"]
    strategy: StrategyIdentity
    dataset: BacktestDataset
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint] = Field(default_factory=list, max_length=5000)
    attribution: list[AttributionItem] = Field(default_factory=list, max_length=100)
    generated_at: str | None = None
    provenance: dict[str, str]
    agent_context: dict[str, Any]
