"""Immutable contracts for vintage-aware raw observations."""

from datetime import date, datetime, timezone
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seven_cycle_platform.types import VintageKind


class Observation(BaseModel):
    """One source observation with explicit release and vintage metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    observation_date: date
    release_date: date
    vintage_date: date
    value: float
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    retrieval_time: datetime
    revision_number: int = Field(ge=0)
    quality_status: str = Field(min_length=1)
    vintage_kind: VintageKind

    @field_validator("retrieval_time")
    @classmethod
    def validate_retrieval_time(cls, retrieval_time: datetime) -> datetime:
        if retrieval_time.tzinfo is None or retrieval_time.utcoffset() is None:
            raise ValueError("retrieval_time must be timezone-aware")
        return retrieval_time.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> Self:
        if self.release_date < self.observation_date:
            raise ValueError("release_date cannot precede observation_date")
        if self.vintage_date < self.release_date:
            raise ValueError("vintage_date cannot precede release_date")
        if self.retrieval_time.date() < self.vintage_date:
            raise ValueError(
                "retrieval_time UTC date cannot precede vintage_date"
            )
        return self


class ReleaseRule(BaseModel):
    """Explicit legacy-panel availability rule for one panel column."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    publication_lag_days: int = Field(ge=0)
    vintage_kind: VintageKind
    quality_status: str = Field(min_length=1)
    revision_number: int = Field(ge=0)
