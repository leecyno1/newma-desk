"""Explicit adapters from legacy pandas panels to vintage observations."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from numbers import Integral

import pandas as pd
from pydantic import BaseModel, ConfigDict

from seven_cycle_platform.data.observations import Observation, ReleaseRule
from seven_cycle_platform.types import VintageKind


class LegacyObservationBatch(BaseModel):
    """Immutable observations and evidence caveats from one conversion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observations: tuple[Observation, ...]
    caveats: tuple[str, ...]


def _normalize_retrieval_time(retrieval_time: datetime) -> datetime:
    if retrieval_time.tzinfo is None or retrieval_time.utcoffset() is None:
        raise ValueError("retrieval_time must be timezone-aware")
    return retrieval_time.astimezone(timezone.utc)


def _validate_release_rules(
    panel: pd.DataFrame,
    release_rules: Mapping[object, ReleaseRule],
    strict_vintage: bool,
) -> None:
    missing_columns = [
        column for column in panel.columns if column not in release_rules
    ]
    if missing_columns:
        missing = ", ".join(str(column) for column in missing_columns)
        raise ValueError(f"Missing release rules for panel columns: {missing}")

    non_pseudo_rules = [
        release_rules[column]
        for column in panel.columns
        if release_rules[column].vintage_kind is not VintageKind.PSEUDO_VINTAGE
    ]
    if non_pseudo_rules:
        details = ", ".join(
            f"{rule.entity_id} uses {rule.vintage_kind.value}"
            for rule in non_pseudo_rules
        )
        raise ValueError(
            "Legacy adapters require pseudo_vintage release rules; "
            f"{details}"
        )

    if strict_vintage:
        entities = ", ".join(
            dict.fromkeys(
                release_rules[column].entity_id for column in panel.columns
            )
        )
        raise ValueError(
            "strict vintage mode rejects "
            f"{entities} because its release rule is pseudo-vintage"
        )


def _adapt_panel(
    panel: pd.DataFrame,
    observation_dates: Sequence[date],
    release_rules: Mapping[object, ReleaseRule],
    retrieval_time: datetime,
    strict_vintage: bool,
) -> LegacyObservationBatch:
    normalized_retrieval_time = _normalize_retrieval_time(retrieval_time)
    _validate_release_rules(panel, release_rules, strict_vintage)
    retrieval_date = normalized_retrieval_time.date()

    observations: list[Observation] = []
    pseudo_entities: dict[str, None] = {}
    for row_number, observation_date in enumerate(observation_dates):
        for column_number, column in enumerate(panel.columns):
            value = panel.iat[row_number, column_number]
            if pd.isna(value):
                continue

            rule = release_rules[column]
            release_date = observation_date + timedelta(
                days=rule.publication_lag_days
            )
            if retrieval_date < release_date:
                raise ValueError(
                    f"{rule.entity_id}: retrieval date {retrieval_date} "
                    f"precedes synthetic release date {release_date}"
                )
            observations.append(
                Observation(
                    entity_id=rule.entity_id,
                    observation_date=observation_date,
                    release_date=release_date,
                    vintage_date=retrieval_date,
                    value=float(value),
                    unit=rule.unit,
                    source=rule.source,
                    retrieval_time=normalized_retrieval_time,
                    revision_number=rule.revision_number,
                    quality_status=rule.quality_status,
                    vintage_kind=rule.vintage_kind,
                )
            )
            if rule.vintage_kind is VintageKind.PSEUDO_VINTAGE:
                pseudo_entities[rule.entity_id] = None

    caveats = tuple(
        f"{entity_id} is pseudo-vintage because the legacy panel has no "
        "true historical release vintage."
        for entity_id in pseudo_entities
    )
    return LegacyObservationBatch(
        observations=tuple(observations),
        caveats=caveats,
    )


def adapt_monthly_panel(
    panel: pd.DataFrame,
    *,
    release_rules: Mapping[object, ReleaseRule],
    retrieval_time: datetime,
    strict_vintage: bool = False,
) -> LegacyObservationBatch:
    """Convert a DatetimeIndex monthly panel using explicit release rules."""

    if not isinstance(panel.index, pd.DatetimeIndex):
        raise TypeError("Monthly panels require a pandas DatetimeIndex")
    if panel.index.hasnans:
        raise ValueError("Monthly panel index cannot contain missing dates")

    observation_dates = [timestamp.date() for timestamp in panel.index]
    return _adapt_panel(
        panel,
        observation_dates,
        release_rules,
        retrieval_time,
        strict_vintage,
    )


def adapt_annual_panel(
    panel: pd.DataFrame,
    *,
    release_rules: Mapping[object, ReleaseRule],
    retrieval_time: datetime,
    strict_vintage: bool = False,
) -> LegacyObservationBatch:
    """Convert an integer-year panel using December 31 observation dates."""

    observation_dates: list[date] = []
    for year in panel.index:
        if isinstance(year, bool) or not isinstance(year, Integral):
            raise TypeError("Annual panel index values must be integer years")
        observation_dates.append(date(int(year), 12, 31))

    return _adapt_panel(
        panel,
        observation_dates,
        release_rules,
        retrieval_time,
        strict_vintage,
    )
