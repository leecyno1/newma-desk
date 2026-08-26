"""Validated registry contracts."""

from datetime import date
from math import isclose
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seven_cycle_platform.types import MappingStatus, PublicationGateStatus


CycleId = Literal["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
ChannelId = Literal[
    "growth_demand",
    "inflation_prices",
    "real_rate_discount",
    "liquidity_credit",
    "earnings_margin",
    "risk_premium_crowding",
    "fx_external_demand",
    "supply_inventory_geopolitics",
]
Frequency = Literal["D", "W", "M", "Q", "A"]
QualityTier = Literal["A", "B", "C"]
Timing = Literal["leading", "coincident", "lagging"]
ConceptScope = Literal["systemic", "asset_specific"]
AssetClass = Literal["equity", "bond", "commodity", "fx", "cash"]
AssetTier = Literal["core", "extended", "watch"]
PeriodMode = Literal["years", "months", "calendar"]


class RegistryModel(BaseModel):
    """Base model for strict governed registry entries."""

    model_config = ConfigDict(extra="forbid")


class CyclePublicationPolicy(RegistryModel):
    """Publication eligibility for each governed cycle output layer."""

    historical: PublicationGateStatus
    realtime: PublicationGateStatus
    forecast: PublicationGateStatus
    asset_statistics: PublicationGateStatus
    reason: str = Field(min_length=1)


class CycleSpec(RegistryModel):
    """Governed definition of one economic cycle."""

    cycle_id: CycleId
    name_zh: str = Field(min_length=1)
    economic_role: str = Field(min_length=1)
    frequency: Literal["A", "M"]
    search_min: float = Field(gt=0)
    search_max: float = Field(gt=0)
    initial_center: float | None
    center_prior_months: float = Field(gt=0)
    period_mode: PeriodMode
    empirical_band_months: tuple[float, float] | None
    publication: CyclePublicationPolicy
    max_quarterly_drift: float = Field(gt=0)
    horizons: list[int] = Field(min_length=1)
    default_usage: MappingStatus

    @field_validator("horizons")
    @classmethod
    def validate_horizons(cls, horizons: list[int]) -> list[int]:
        if any(horizon <= 0 for horizon in horizons):
            raise ValueError("Cycle horizons must be positive")
        if horizons != sorted(set(horizons)):
            raise ValueError("Cycle horizons must be unique and sorted")
        return horizons

    @model_validator(mode="after")
    def validate_search_band(self) -> Self:
        if self.search_min >= self.search_max:
            raise ValueError("Cycle search_min must be less than search_max")
        if self.initial_center is None:
            raise ValueError(
                "Cycle initial_center is required for center prior validation"
            )
        if not self.search_min <= self.initial_center <= self.search_max:
            raise ValueError("Cycle initial_center must fall inside the search band")
        if self.empirical_band_months is not None:
            lower, upper = self.empirical_band_months
            if lower <= 0 or lower > upper:
                raise ValueError(
                    "empirical_band_months must be positive and ordered"
                )
        if self.cycle_id == "C6" and self.frequency != "M":
            raise ValueError("C6 must use monthly frequency")
        if self.period_mode == "calendar" and self.cycle_id != "C6":
            raise ValueError("Only C6 may use calendar period mode")
        if self.cycle_id == "C6" and self.period_mode != "calendar":
            raise ValueError("C6 must use calendar period mode")
        if self.frequency == "A" and self.period_mode != "years":
            raise ValueError("Annual cycles must use years period mode")
        if (
            self.frequency == "M"
            and self.cycle_id != "C6"
            and self.period_mode != "months"
        ):
            raise ValueError("Monthly cycles must use months period mode")
        expected_prior_months = self.initial_center * (
            12.0 if self.frequency == "A" else 1.0
        )
        if not isclose(
            self.center_prior_months,
            expected_prior_months,
            rel_tol=1e-9,
            abs_tol=1e-4,
        ):
            raise ValueError(
                "center_prior_months must equal initial_center converted to months"
            )
        return self

    def with_initial_center(self, initial_center: float) -> Self:
        """Return a fully revalidated spec with a normalized center prior."""

        payload = self.model_dump(mode="python")
        payload["initial_center"] = initial_center
        payload["center_prior_months"] = initial_center * (
            12.0 if self.frequency == "A" else 1.0
        )
        return type(self).model_validate(payload)


class IndicatorProxyMetadata(RegistryModel):
    """Explicit proxy provenance for an indicator series."""

    is_proxy: bool
    proxy_for: str | None
    effective_from: date | None
    effective_to: date | None
    is_current: bool
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_proxy_interval(self) -> Self:
        if not self.is_proxy:
            if any(
                value is not None
                for value in (
                    self.proxy_for,
                    self.effective_from,
                    self.effective_to,
                )
            ) or self.is_current:
                raise ValueError("Non-proxy indicators cannot define a proxy interval")
            return self

        if self.proxy_for is None or self.effective_from is None:
            raise ValueError("Proxy indicators require proxy_for and effective_from")
        if self.effective_to is None and not self.is_current:
            raise ValueError("Open-ended proxy intervals must be current")
        if self.effective_to is not None and self.is_current:
            raise ValueError("Closed proxy intervals cannot be current")
        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("Proxy effective_to cannot precede effective_from")
        return self


class IndicatorSpec(RegistryModel):
    """Governed macro, policy, earnings, or market indicator."""

    indicator_id: str = Field(min_length=1)
    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    concept_scope: ConceptScope
    source: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    frequency: Frequency
    unit: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    transform: str = Field(min_length=1)
    release_rule: str = Field(min_length=1)
    revision_rule: str = Field(min_length=1)
    quality_tier: QualityTier
    timing: Timing
    allowed_cycles: list[CycleId] = Field(min_length=1)
    allowed_lags: list[int] = Field(min_length=1)
    direction_prior: float | None = Field(default=None, ge=-1, le=1)
    proxy: IndicatorProxyMetadata
    active: bool

    @field_validator("allowed_cycles")
    @classmethod
    def validate_allowed_cycles(cls, cycle_ids: list[CycleId]) -> list[CycleId]:
        if len(cycle_ids) != len(set(cycle_ids)):
            raise ValueError("Indicator allowed_cycles must be unique")
        return cycle_ids

    @field_validator("allowed_lags")
    @classmethod
    def validate_allowed_lags(cls, lags: list[int]) -> list[int]:
        if any(lag < 0 for lag in lags):
            raise ValueError("Indicator allowed_lags cannot be negative")
        if lags != sorted(set(lags)):
            raise ValueError("Indicator allowed_lags must be unique and sorted")
        return lags


class ChannelSpec(RegistryModel):
    """Transmission channel defined only by eligible indicator concepts."""

    channel_id: ChannelId
    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    eligible_indicator_concepts: list[str] = Field(min_length=1)
    minimum_breadth: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_indicator_concepts(self) -> Self:
        concepts = self.eligible_indicator_concepts
        if len(concepts) != len(set(concepts)):
            raise ValueError("Channel indicator concepts must be unique")
        return self


class AssetProxySpec(RegistryModel):
    """Explicitly dated source used as a proxy for an asset."""

    proxy_id: str = Field(min_length=1)
    proxy_for: str = Field(min_length=1)
    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    source: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None
    is_current: bool
    overlap_calibration: str = Field(min_length=1)
    confidence_discount: float = Field(ge=0, lt=1)

    @model_validator(mode="after")
    def validate_effective_interval(self) -> Self:
        if self.effective_to is None and not self.is_current:
            raise ValueError("Open-ended asset proxy intervals must be current")
        if self.effective_to is not None and self.is_current:
            raise ValueError("Closed asset proxy intervals cannot be current")
        if (
            self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("Asset proxy effective_to cannot precede effective_from")
        return self


class AssetSpec(RegistryModel):
    """Governed investable asset or benchmark series."""

    asset_id: str = Field(min_length=1)
    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    asset_class: AssetClass
    region: str = Field(min_length=1)
    tier: AssetTier
    currency: str = Field(min_length=1)
    calendar: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    minimum_history_months: int = Field(gt=0)
    minimum_quality_tier: QualityTier
    maximum_missing_ratio: float = Field(ge=0, le=1)
    proxy_chain: list[AssetProxySpec]
    active: bool


class CycleRegistry(RegistryModel):
    """Cycle registry file payload."""

    cycles: list[CycleSpec] = Field(min_length=1)


class IndicatorRegistry(RegistryModel):
    """Indicator registry file payload."""

    indicators: list[IndicatorSpec] = Field(min_length=1)


class ChannelRegistry(RegistryModel):
    """Channel registry file payload."""

    channels: list[ChannelSpec] = Field(min_length=1)


class AssetRegistry(RegistryModel):
    """Asset registry file payload."""

    assets: list[AssetSpec] = Field(min_length=1)


class RegistryBundle(RegistryModel):
    """Fully validated governed registries."""

    cycles: list[CycleSpec]
    indicators: list[IndicatorSpec]
    channels: list[ChannelSpec]
    assets: list[AssetSpec]
