from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


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


class LegacyImportResult(PortfolioModel):
    imported: bool
    activities_created: int
    reason: str
