from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ExecutionMode = Literal["demo", "live"]
RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
AgentStatus = Literal["idle", "queued", "working", "completed", "failed"]
AgentConnectionKind = Literal["orchestra", "external_http", "openai_compatible"]
AgentInterventionAction = Literal["follow_up", "supplement", "rereview"]
UserRole = Literal["owner", "manager", "researcher", "viewer"]
TransactionType = Literal["buy", "sell", "cash_in", "cash_out", "dividend", "interest", "fee"]
AssetClass = Literal["equity", "bond", "fund", "commodity", "future", "option", "cash", "other"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceRecord(BaseModel):
    id: str
    source_name: str
    source_url: str | None = None
    observed_at: str | None = None
    retrieved_at: str = Field(default_factory=utc_now)
    tool_name: str
    interface_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    status: str = "success"
    excerpt: str = ""
    content_hash: str


class AgentConnection(BaseModel):
    kind: AgentConnectionKind = "orchestra"
    endpoint: str | None = Field(default=None, max_length=1000)
    model: str | None = Field(default=None, max_length=200)
    secret_id: str | None = Field(default=None, max_length=160)
    timeout_seconds: int = Field(default=180, ge=5, le=600)

    @model_validator(mode="after")
    def validate_connection(self) -> "AgentConnection":
        if self.kind == "external_http" and not self.endpoint:
            raise ValueError("外部 HTTP Agent 必须配置 Endpoint。")
        if self.kind == "openai_compatible" and not self.model:
            raise ValueError("独立大模型必须配置模型名称。")
        if self.endpoint and not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("Endpoint 必须使用 http:// 或 https://。")
        return self


class AgentProfile(BaseModel):
    id: str
    name: str
    title: str
    group: str
    focus: str
    persona: str
    style: str
    role_card: str
    shared_skills: list[str] = Field(default_factory=list)
    specialty_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    default_prompt: str = ""
    research_channels: list[str] = Field(default_factory=list)
    tushare_endpoints: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    risk_controls: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    role_card_content: str = ""
    connection: AgentConnection = Field(default_factory=AgentConnection)
    is_custom: bool = False

    @model_validator(mode="after")
    def validate_skill_count(self) -> "AgentProfile":
        if self.id not in {"ORCHESTRA", "DATA-FOUNDATION"} and not 3 <= len(self.skills) <= 5:
            raise ValueError(f"{self.id} 必须配置 3 至 5 个 Skills。")
        return self


class PublicAgentProfile(BaseModel):
    id: str
    name: str
    title: str
    group: str
    focus: str
    persona: str
    style: str
    default_prompt: str
    shared_skills: list[str]
    specialty_skills: list[str]
    skills: list[str]
    available_skills: list[str]
    missing_skills: list[str]
    research_channels: list[str]
    tushare_endpoints: list[str]
    outputs: list[str]
    connection: AgentConnection = Field(default_factory=AgentConnection)
    is_custom: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    focus: str | None = Field(default=None, min_length=1, max_length=500)
    persona: str | None = Field(default=None, min_length=1, max_length=4000)
    style: str | None = Field(default=None, min_length=1, max_length=4000)
    default_prompt: str | None = Field(default=None, max_length=12000)
    skills: list[str] | None = Field(default=None, min_length=3, max_length=5)
    connection: AgentConnection | None = None


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    group: Literal["宏观组", "配置组", "股票组", "基金经理组"]
    focus: str = Field(min_length=1, max_length=500)
    persona: str = Field(min_length=1, max_length=4000)
    style: str = Field(min_length=1, max_length=4000)
    default_prompt: str = Field(default="", max_length=12000)
    skills: list[str] = Field(min_length=3, max_length=5)
    connection: AgentConnection = Field(default_factory=AgentConnection)


class CreateRunRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=2000)
    mode: ExecutionMode = "demo"
    portfolio_id: str | None = None
    secret_refs: dict[str, str] = Field(default_factory=dict)


class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus
    mode: ExecutionMode


class RunSummary(BaseModel):
    id: str
    topic: str
    mode: ExecutionMode
    status: RunStatus
    phase: str
    created_at: str
    updated_at: str
    completed_agents: int
    total_agents: int
    error: str | None = None
    owner_id: str = "local-user"
    portfolio_id: str | None = None
    parent_run_id: str | None = None
    revision: int = 1
    evidence_count: int = 0


class AgentRuntime(BaseModel):
    id: str
    status: AgentStatus = "idle"
    phase: str | None = None
    output: str = ""
    thinking: str = ""
    thinking_stage: str | None = None
    thoughts: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    registered_skills: list[str] = Field(default_factory=list)
    used_skills: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    intervention_id: str | None = None
    intervention_action: AgentInterventionAction | None = None


class DecisionEvent(BaseModel):
    id: str
    run_id: str
    seq: int
    type: str
    created_at: str = Field(default_factory=utc_now)
    phase: str | None = None
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunSnapshot(BaseModel):
    id: str
    topic: str
    mode: ExecutionMode
    status: RunStatus
    phase: str
    created_at: str
    updated_at: str
    last_event_seq: int = 0
    agents: dict[str, AgentRuntime]
    plan: str = ""
    consensus: str = ""
    decision: str = ""
    orchestra_thinking: str = ""
    orchestra_thinking_stage: str | None = None
    error: str | None = None
    owner_id: str = "local-user"
    portfolio_id: str | None = None
    parent_run_id: str | None = None
    revision: int = 1
    revision_note: str = ""
    secret_refs: dict[str, str] = Field(default_factory=dict)


class ReconsiderRunRequest(BaseModel):
    note: str = Field(min_length=2, max_length=2000)
    mode: ExecutionMode | None = None


class AgentInterventionRequest(BaseModel):
    action: AgentInterventionAction
    instruction: str = Field(min_length=2, max_length=4000)


class AgentInterventionResponse(BaseModel):
    intervention_id: str
    run_id: str
    agent_id: str
    action: AgentInterventionAction
    status: Literal["queued"] = "queued"


class RunComparisonRequest(BaseModel):
    run_ids: list[str] = Field(min_length=2, max_length=5)


class UserProfile(BaseModel):
    id: str
    name: str
    role: UserRole
    created_at: str


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: UserRole = "researcher"


class CreateUserResponse(BaseModel):
    user: UserProfile
    api_token: str


class CreateSessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=160)
    api_token: str = Field(min_length=16, max_length=1000)


class AuthSessionResponse(BaseModel):
    user: UserProfile
    expires_at: str


class Portfolio(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str = ""
    base_currency: str = "CNY"
    created_at: str
    updated_at: str


class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    base_currency: str = Field(default="CNY", min_length=3, max_length=8)


class PortfolioTransaction(BaseModel):
    id: str
    portfolio_id: str
    trade_date: date
    transaction_type: TransactionType
    asset_code: str = ""
    asset_name: str = ""
    asset_class: AssetClass = "other"
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    currency: str = "CNY"
    notes: str = ""
    created_at: str


class CreatePortfolioTransactionRequest(BaseModel):
    trade_date: date = Field(default_factory=date.today)
    transaction_type: TransactionType
    asset_code: str = Field(default="", max_length=64)
    asset_name: str = Field(default="", max_length=160)
    asset_class: AssetClass = "other"
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    fees: Decimal = Field(default=Decimal("0"), ge=0, max_digits=28, decimal_places=8)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_transaction(self) -> "CreatePortfolioTransactionRequest":
        if self.transaction_type in {"buy", "sell"}:
            if not self.asset_code.strip() or not self.asset_name.strip():
                raise ValueError("买卖交易必须填写资产代码和名称。")
            if self.quantity <= 0 or self.price <= 0:
                raise ValueError("买卖交易的数量和价格必须大于0。")
            self.amount = self.quantity * self.price
        elif self.amount <= 0:
            raise ValueError("现金、收益和费用交易的金额必须大于0。")
        return self


class PortfolioPosition(BaseModel):
    asset_code: str
    asset_name: str
    asset_class: AssetClass
    currency: str
    quantity: Decimal
    average_cost: Decimal
    last_price: Decimal
    market_value: Decimal
    cost_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal


class PortfolioSummary(BaseModel):
    as_of: date
    currency: str
    cash_balance: Decimal
    market_value: Decimal
    net_asset_value: Decimal
    total_cost: Decimal
    gross_exposure: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    income: Decimal
    fees: Decimal
    position_count: int


class PortfolioMarkInput(BaseModel):
    asset_code: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    source: str = Field(default="manual", min_length=1, max_length=160)


class CreatePortfolioValuationRequest(BaseModel):
    as_of: date = Field(default_factory=date.today)
    marks: list[PortfolioMarkInput] = Field(default_factory=list, max_length=200)
    unit_count: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=8)
    note: str = Field(default="", max_length=2000)


class PortfolioNavSnapshot(BaseModel):
    id: str
    portfolio_id: str
    as_of: date
    cash_balance: Decimal
    market_value: Decimal
    net_asset_value: Decimal
    unit_count: Decimal | None = None
    unit_nav: Decimal | None = None
    total_cost: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    note: str = ""
    created_at: str


class PortfolioDetail(BaseModel):
    portfolio: Portfolio
    summary: PortfolioSummary
    positions: list[PortfolioPosition]
    transactions: list[PortfolioTransaction]
    nav_history: list[PortfolioNavSnapshot]


class SecretMetadata(BaseModel):
    id: str
    owner_id: str
    provider: Literal["openai", "tushare", "tavily", "ima", "agent"]
    label: str
    created_at: str
    updated_at: str


class CreateSecretRequest(BaseModel):
    provider: Literal["openai", "tushare", "tavily", "ima", "agent"]
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=8, max_length=2000)
