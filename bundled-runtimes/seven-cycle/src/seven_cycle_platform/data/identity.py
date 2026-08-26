from datetime import date, datetime, timedelta, timezone
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seven_cycle_platform.types import FreshnessStatus, VintageKind


Frequency = Literal["D", "W", "M", "Q", "A"]


def month_distance(start: date, end: date) -> int:
    """Count calendar-month boundaries between two dates, ignoring day values."""
    if end < start:
        raise ValueError("end cannot precede start")
    return (end.year - start.year) * 12 + end.month - start.month


def _freshness_status(
    vintage_kind: VintageKind,
    stale_months: int,
    stale_after_months: int,
) -> FreshnessStatus:
    if vintage_kind is VintageKind.UNAVAILABLE:
        return FreshnessStatus.UNAVAILABLE
    if stale_months > stale_after_months:
        return FreshnessStatus.STALE
    return FreshnessStatus.FRESH


class DataIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entity_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    frequency: Frequency
    unit: str = Field(min_length=1)
    transform: str = Field(min_length=1)
    observation_start: date
    data_as_of: date
    release_date: date
    retrieval_time: datetime
    vintage_kind: VintageKind
    stale_months: int = Field(ge=0)
    stale_after_months: int = Field(ge=0)
    freshness_status: FreshnessStatus
    proxy_for: str | None
    caveat: str = Field(min_length=1)

    @field_validator("proxy_for")
    @classmethod
    def normalize_proxy_for(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("proxy_for must be non-blank")
        return normalized

    @classmethod
    def from_dates(
        cls,
        *,
        entity_id: str,
        source: str,
        frequency: Frequency,
        unit: str,
        transform: str,
        observation_start: date,
        data_as_of: date,
        release_date: date,
        retrieval_time: datetime,
        vintage_kind: VintageKind,
        stale_after_months: int,
        proxy_for: str | None,
        caveat: str,
    ) -> Self:
        if retrieval_time.tzinfo is None or retrieval_time.utcoffset() is None:
            raise ValueError("retrieval_time must be timezone-aware")
        utc_retrieval = retrieval_time.astimezone(timezone.utc)
        stale_months = month_distance(data_as_of, utc_retrieval.date())
        freshness = _freshness_status(
            vintage_kind,
            stale_months,
            stale_after_months,
        )
        return cls(
            entity_id=entity_id,
            source=source,
            frequency=frequency,
            unit=unit,
            transform=transform,
            observation_start=observation_start,
            data_as_of=data_as_of,
            release_date=release_date,
            retrieval_time=utc_retrieval,
            vintage_kind=vintage_kind,
            stale_months=stale_months,
            stale_after_months=stale_after_months,
            freshness_status=freshness,
            proxy_for=proxy_for,
            caveat=caveat,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.observation_start > self.data_as_of:
            raise ValueError("observation_start cannot exceed data_as_of")
        if self.release_date < self.data_as_of:
            raise ValueError("release_date cannot precede data_as_of")
        if (
            self.retrieval_time.tzinfo is None
            or self.retrieval_time.utcoffset() is None
        ):
            raise ValueError("retrieval_time must be timezone-aware")
        if self.retrieval_time.utcoffset() != timedelta(0):
            raise ValueError("retrieval_time must use UTC")
        expected_stale_months = month_distance(
            self.data_as_of,
            self.retrieval_time.date(),
        )
        if self.stale_months != expected_stale_months:
            raise ValueError(
                f"stale_months must equal {expected_stale_months} for data_as_of "
                "and retrieval_time"
            )
        expected_freshness = _freshness_status(
            self.vintage_kind,
            self.stale_months,
            self.stale_after_months,
        )
        if self.freshness_status is not expected_freshness:
            raise ValueError(f"freshness_status must be {expected_freshness.value}")
        if self.vintage_kind is VintageKind.EXPLICIT_PROXY and self.proxy_for is None:
            raise ValueError("explicit proxy identity requires proxy_for")
        if (
            self.vintage_kind is not VintageKind.EXPLICIT_PROXY
            and self.proxy_for is not None
        ):
            raise ValueError("proxy_for is allowed only for explicit proxies")
        return self
