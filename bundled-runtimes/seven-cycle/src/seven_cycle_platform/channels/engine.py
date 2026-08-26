"""Registry-bound causal transmission-channel estimation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import json
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.channels.innovations import local_level_innovations
from seven_cycle_platform.cycles.preprocess import expanding_standardize
from seven_cycle_platform.cycles.vintage import read_vintage
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.registry.models import (
    ChannelSpec,
    IndicatorSpec,
    RegistryBundle,
)
from seven_cycle_platform.types import VintageKind


CHANNEL_STATE_COLUMNS = (
    "date",
    "channel_id",
    "state",
    "innovation",
    "uncertainty",
    "member_count",
    "concept_count",
    "revision_risk",
    "vintage_kind",
    "confidence",
    "status",
    "status_reason",
    "member_weights_json",
)

CHANNEL_DIAGNOSTIC_COLUMNS = (
    "date",
    "channel_id",
    "entity_id",
    "concept",
    "raw_value",
    "standardized_value",
    "oriented_value",
    "observation_date",
    "visible_date",
    "revision_number",
    "update_count",
    "revision_event_count",
    "updates_json",
    "quality_tier",
    "quality_score",
    "direction",
    "walk_forward_fit",
    "revision_event_risk",
    "lagged_revision_risk",
    "revision_risk",
    "member_breadth",
    "concept_breadth",
    "raw_reliability",
    "within_concept_weight",
    "concept_weight",
    "effective_weight",
    "available",
    "observation_used",
)

_QUALITY_SCORES = {"A": 1.0, "B": 0.75, "C": 0.5}
_RESULT_FIELDS = ("states", "diagnostics")


class ChannelBreadthError(ValueError):
    """A channel cannot meet its governed member-breadth requirement."""


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


@dataclass(frozen=True)
class ChannelEstimateResult:
    """Detached channel states and member-level reliability diagnostics."""

    states: pd.DataFrame
    diagnostics: pd.DataFrame

    def __post_init__(self) -> None:
        states = object.__getattribute__(self, "states")
        diagnostics = object.__getattribute__(self, "diagnostics")
        if not isinstance(states, pd.DataFrame):
            raise TypeError("states must be a pandas DataFrame")
        if not isinstance(diagnostics, pd.DataFrame):
            raise TypeError("diagnostics must be a pandas DataFrame")
        if tuple(states.columns) != CHANNEL_STATE_COLUMNS:
            raise ValueError("states columns do not match the channel contract")
        if tuple(diagnostics.columns) != CHANNEL_DIAGNOSTIC_COLUMNS:
            raise ValueError(
                "diagnostics columns do not match the channel contract"
            )
        if states.duplicated(
            ["date", "channel_id", "vintage_kind"]
        ).any():
            raise ValueError(
                "date × channel_id × vintage_kind states must be unique"
            )
        if diagnostics.duplicated(
            ["date", "channel_id", "entity_id"]
        ).any():
            raise ValueError(
                "date × channel_id × entity_id diagnostics must be unique"
            )
        object.__setattr__(self, "states", _copy_frame(states))
        object.__setattr__(self, "diagnostics", _copy_frame(diagnostics))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.states

    @property
    def member_diagnostics(self) -> pd.DataFrame:
        return self.diagnostics


@dataclass(frozen=True)
class _VisibilityArchive:
    values: pd.DataFrame
    observation_dates: pd.DataFrame
    visible_dates: pd.DataFrame
    revision_numbers: pd.DataFrame
    revision_events: pd.DataFrame
    update_counts: pd.DataFrame
    revision_event_counts: pd.DataFrame
    updates_json: pd.DataFrame
    vintage_kinds: pd.Series


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _nonnegative_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _positive_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _normalize_as_of(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError("as_of must be a date")
    return value


def _normalize_records(records: object) -> tuple[Observation, ...]:
    if isinstance(records, (str, bytes, bytearray, Mapping)) or isinstance(
        records,
        (bool, np.bool_),
    ):
        raise TypeError("observations must be an iterable of Observation values")
    try:
        normalized = tuple(records)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "observations must be an iterable of Observation values"
        ) from error
    if any(not isinstance(record, Observation) for record in normalized):
        raise TypeError("observations must contain only Observation values")
    for record in normalized:
        if not np.isfinite(record.value):
            raise ValueError("observation values must be finite")
    return normalized


def _candidate_kinds(interpretation: VintageKind) -> frozenset[VintageKind]:
    if interpretation is VintageKind.REALTIME:
        return frozenset(
            {VintageKind.REALTIME, VintageKind.PSEUDO_VINTAGE}
        )
    return frozenset({interpretation})


def _selection_signature(record: Observation) -> tuple[object, ...]:
    return (
        record.entity_id,
        record.observation_date,
        record.release_date,
        record.vintage_date,
        record.value,
        record.unit,
        record.source,
        record.revision_number,
        record.quality_status,
        record.vintage_kind,
    )


def _monthly_choice_key(record: Observation) -> tuple[object, ...]:
    return (
        record.observation_date,
        record.vintage_date,
        record.revision_number,
        record.release_date,
        record.retrieval_time,
        record.value,
    )


def _revision_event_risk(
    previous: Observation | None,
    current: Observation,
) -> float:
    if previous is None:
        return min(1.0, 0.1 * float(current.revision_number))
    denominator = max(abs(previous.value), 1.0)
    relative_size = min(1.0, abs(current.value - previous.value) / denominator)
    revision_step = max(current.revision_number - previous.revision_number, 0)
    revision_signal = min(1.0, 0.1 * float(revision_step))
    return max(relative_size, revision_signal)


def _canonical_updates_json(
    changes: list[tuple[Observation, float]],
    selected: Observation,
) -> str:
    updates = [
        {
            "observation_date": record.observation_date.isoformat(),
            "release_date": record.release_date.isoformat(),
            "revision_event_risk": float(risk),
            "revision_number": record.revision_number,
            "selected_for_state": record is selected,
            "value": float(record.value),
            "visible_date": max(
                record.release_date,
                record.vintage_date,
            ).isoformat(),
        }
        for record, risk in sorted(
            changes,
            key=lambda item: _monthly_choice_key(item[0]),
        )
    ]
    return json.dumps(
        updates,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _stable_signs(correlation: pd.Series, threshold: float = 0.1) -> pd.Series:
    current = np.nan
    signs = np.full(len(correlation), np.nan, dtype="float64")
    for position, value in enumerate(correlation.to_numpy(dtype="float64")):
        if np.isfinite(value):
            if value > threshold:
                current = 1.0
            elif value < -threshold:
                current = -1.0
        signs[position] = current
    return pd.Series(signs, index=correlation.index, dtype="float64")


def _bounded(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _json_number(value: object) -> float:
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError("member weight diagnostics must be finite")
    return numeric


def _json_direction(value: object) -> float | None:
    numeric = float(value)
    if not np.isfinite(numeric):
        return None
    if numeric not in {-1.0, 1.0}:
        raise ValueError("member direction must be -1, 1, or unknown")
    return numeric


class ChannelEngine:
    """Estimate governed channel states using point-in-time observations only."""

    def __init__(
        self,
        registry: RegistryBundle,
        *,
        standardization_min_periods: int = 3,
        process_variance: float = 0.05,
        observation_variance: float = 0.25,
        initial_state: float = 0.0,
        initial_variance: float = 1.0,
    ) -> None:
        if not isinstance(registry, RegistryBundle):
            raise TypeError("registry must be a RegistryBundle")
        validated = RegistryBundle.model_validate(
            registry.model_dump(mode="python")
        )
        self._minimum_periods = _positive_integer(
            standardization_min_periods,
            "standardization_min_periods",
        )
        self._process_variance = _nonnegative_real(
            process_variance,
            "process_variance",
        )
        self._observation_variance = _positive_real(
            observation_variance,
            "observation_variance",
        )
        self._initial_state = _finite_real(initial_state, "initial_state")
        self._initial_variance = _positive_real(
            initial_variance,
            "initial_variance",
        )
        self._channels, self._members = self._validate_registry(validated)
        self._channel_ids = tuple(self._channels)

    @staticmethod
    def _validate_registry(
        registry: RegistryBundle,
    ) -> tuple[
        dict[str, ChannelSpec],
        dict[str, tuple[IndicatorSpec, ...]],
    ]:
        indicator_ids = [indicator.indicator_id for indicator in registry.indicators]
        if len(indicator_ids) != len(set(indicator_ids)):
            raise ValueError("registry indicators must have unique indicator_id values")
        channel_ids = [channel.channel_id for channel in registry.channels]
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError("registry channels must have unique channel_id values")
        concept_scopes: dict[str, set[str]] = {}
        for indicator in registry.indicators:
            concept_scopes.setdefault(indicator.concept, set()).add(
                indicator.concept_scope
            )
        mixed = [
            concept for concept, scopes in concept_scopes.items() if len(scopes) > 1
        ]
        if mixed:
            raise ValueError(
                "registry indicator concepts must have one scope: "
                + ", ".join(sorted(mixed))
            )
        channels: dict[str, ChannelSpec] = {}
        members: dict[str, tuple[IndicatorSpec, ...]] = {}
        for channel in registry.channels:
            unknown = set(channel.eligible_indicator_concepts).difference(
                concept_scopes
            )
            if unknown:
                raise ValueError(
                    f"channel {channel.channel_id} references unknown concepts: "
                    + ", ".join(sorted(unknown))
                )
            nonsystemic = [
                concept
                for concept in channel.eligible_indicator_concepts
                if concept_scopes[concept] != {"systemic"}
            ]
            if nonsystemic:
                raise ValueError(
                    f"channel {channel.channel_id} requires systemic concepts: "
                    + ", ".join(sorted(nonsystemic))
                )
            active_members = tuple(
                indicator.model_copy(deep=True)
                for indicator in registry.indicators
                if indicator.active
                and indicator.concept in channel.eligible_indicator_concepts
            )
            if len(active_members) < channel.minimum_breadth:
                raise ChannelBreadthError(
                    f"registry breadth for {channel.channel_id} is "
                    f"{len(active_members)}, below minimum "
                    f"{channel.minimum_breadth}"
                )
            channels[channel.channel_id] = channel.model_copy(deep=True)
            members[channel.channel_id] = active_members
        if not channels:
            raise ValueError("registry must contain at least one channel")
        return channels, members

    @property
    def channel_ids(self) -> tuple[str, ...]:
        return self._channel_ids

    def _channel(self, channel_id: object) -> ChannelSpec:
        if not isinstance(channel_id, str) or not channel_id:
            raise TypeError("channel_id must be a non-empty string")
        try:
            return self._channels[channel_id]
        except KeyError as error:
            raise ValueError(f"unknown channel_id: {channel_id}") from error

    def eligible_concepts(self, channel_id: str) -> tuple[str, ...]:
        channel = self._channel(channel_id)
        return tuple(channel.eligible_indicator_concepts)

    def members_for(self, channel_id: str) -> tuple[IndicatorSpec, ...]:
        self._channel(channel_id)
        return tuple(
            member.model_copy(deep=True) for member in self._members[channel_id]
        )

    def _requested_channels(
        self,
        channel_ids: object,
    ) -> tuple[str, ...]:
        if channel_ids is None:
            return self._channel_ids
        if isinstance(channel_ids, (str, bytes, bytearray, Mapping)):
            raise TypeError("channel_ids must be an iterable of channel IDs")
        try:
            requested = tuple(channel_ids)  # type: ignore[arg-type]
        except TypeError as error:
            raise TypeError(
                "channel_ids must be an iterable of channel IDs"
            ) from error
        if not requested:
            raise ValueError("channel_ids must contain at least one channel")
        if any(not isinstance(channel_id, str) or not channel_id for channel_id in requested):
            raise TypeError("channel_ids must contain non-empty strings")
        if len(requested) != len(set(requested)):
            raise ValueError("channel_ids must be unique")
        unknown = set(requested).difference(self._channel_ids)
        if unknown:
            raise ValueError(
                "unknown channel_ids: " + ", ".join(sorted(unknown))
            )
        requested_set = set(requested)
        return tuple(
            channel_id
            for channel_id in self._channel_ids
            if channel_id in requested_set
        )

    def _visibility_archive(
        self,
        records: tuple[Observation, ...],
        *,
        as_of: date,
        interpretation: VintageKind,
        strict_vintage: bool,
        channel_ids: tuple[str, ...],
    ) -> _VisibilityArchive:
        member_ids = tuple(
            dict.fromkeys(
                member.indicator_id
                for channel_id in channel_ids
                for member in self._members[channel_id]
            )
        )
        member_id_set = set(member_ids)
        eligible_records = tuple(
            record for record in records if record.entity_id in member_id_set
        )
        final_selection = read_vintage(
            eligible_records,
            as_of=as_of,
            strict=strict_vintage,
            interpretation=interpretation,
        )
        final_entities = {
            observation.entity_id for observation in final_selection.observations
        }
        for channel_id in channel_ids:
            channel = self._channels[channel_id]
            available = sum(
                member.indicator_id in final_entities
                for member in self._members[channel_id]
            )
            if available < channel.minimum_breadth:
                raise ChannelBreadthError(
                    f"data breadth for {channel_id} is {available}, below "
                    f"minimum {channel.minimum_breadth} at {as_of}"
                )
        candidates = [
            record
            for record in eligible_records
            if record.vintage_kind in _candidate_kinds(interpretation)
            and record.release_date <= as_of
            and record.vintage_date <= as_of
        ]
        earliest_visible = min(
            max(record.release_date, record.vintage_date) for record in candidates
        )
        start = pd.Timestamp(earliest_visible) + pd.offsets.MonthEnd(0)
        end = pd.Timestamp(as_of) + pd.offsets.MonthEnd(0)
        index = pd.date_range(start, end, freq="ME", name="date")
        values = pd.DataFrame(
            np.nan,
            index=index,
            columns=member_ids,
            dtype="float64",
        )
        observation_dates = pd.DataFrame(
            None,
            index=index,
            columns=member_ids,
            dtype="object",
        )
        visible_dates = pd.DataFrame(
            None,
            index=index,
            columns=member_ids,
            dtype="object",
        )
        revision_numbers = pd.DataFrame(
            np.nan,
            index=index,
            columns=member_ids,
            dtype="float64",
        )
        revision_events = pd.DataFrame(
            np.nan,
            index=index,
            columns=member_ids,
            dtype="float64",
        )
        update_counts = pd.DataFrame(
            0,
            index=index,
            columns=member_ids,
            dtype="int64",
        )
        revision_event_counts = pd.DataFrame(
            0,
            index=index,
            columns=member_ids,
            dtype="int64",
        )
        updates_json = pd.DataFrame(
            "[]",
            index=index,
            columns=member_ids,
            dtype="object",
        )
        vintage_kinds = pd.Series(
            interpretation.value,
            index=index,
            name="vintage_kind",
            dtype="object",
        )
        previous: dict[tuple[str, date], Observation] = {}
        for month in index:
            cutoff = min(month.date(), as_of)
            event_dates = sorted(
                {
                    max(record.release_date, record.vintage_date)
                    for record in candidates
                    if (
                        pd.Timestamp(
                            max(record.release_date, record.vintage_date)
                        )
                        + pd.offsets.MonthEnd(0)
                    )
                    == month
                    and max(record.release_date, record.vintage_date) <= cutoff
                }
            )
            evaluation_dates = sorted({*event_dates, cutoff})
            monthly_changes: list[
                tuple[Observation, Observation | None, float]
            ] = []
            selection = None
            for evaluation_date in evaluation_dates:
                selection = read_vintage(
                    eligible_records,
                    as_of=evaluation_date,
                    strict=strict_vintage,
                    interpretation=interpretation,
                )
                current = {
                    (record.entity_id, record.observation_date): record
                    for record in selection.observations
                }
                for key, record in current.items():
                    prior = previous.get(key)
                    if prior is None or _selection_signature(
                        prior
                    ) != _selection_signature(record):
                        monthly_changes.append(
                            (
                                record,
                                prior,
                                _revision_event_risk(prior, record),
                            )
                        )
                previous = current
            if selection is None:
                raise RuntimeError("monthly vintage selection was not evaluated")
            by_entity: dict[
                str,
                list[tuple[Observation, float]],
            ] = {}
            for record, _, risk in monthly_changes:
                by_entity.setdefault(record.entity_id, []).append((record, risk))
            for entity_id, entity_changes in by_entity.items():
                chosen = max(
                    (record for record, _ in entity_changes),
                    key=_monthly_choice_key,
                )
                values.at[month, entity_id] = float(chosen.value)
                observation_dates.at[month, entity_id] = chosen.observation_date
                visible_dates.at[month, entity_id] = max(
                    chosen.release_date,
                    chosen.vintage_date,
                )
                revision_numbers.at[month, entity_id] = float(
                    chosen.revision_number
                )
                revision_events.at[month, entity_id] = max(
                    risk for _, risk in entity_changes
                )
                update_counts.at[month, entity_id] = len(entity_changes)
                revision_event_counts.at[month, entity_id] = sum(
                    risk > 0.0 for _, risk in entity_changes
                )
                updates_json.at[month, entity_id] = _canonical_updates_json(
                    entity_changes,
                    chosen,
                )
            vintage_kinds.at[month] = selection.vintage.value
        return _VisibilityArchive(
            values=values,
            observation_dates=observation_dates,
            visible_dates=visible_dates,
            revision_numbers=revision_numbers,
            revision_events=revision_events,
            update_counts=update_counts,
            revision_event_counts=revision_event_counts,
            updates_json=updates_json,
            vintage_kinds=vintage_kinds,
        )

    def _directions(
        self,
        standardized: pd.DataFrame,
        members: tuple[IndicatorSpec, ...],
    ) -> pd.DataFrame:
        member_by_id = {member.indicator_id: member for member in members}
        directions: dict[str, pd.Series] = {}
        minimum = max(2, self._minimum_periods)
        for entity_id in standardized.columns:
            member = member_by_id[entity_id]
            prior = member.direction_prior
            if prior is not None and prior != 0.0:
                directions[entity_id] = pd.Series(
                    float(np.sign(prior)),
                    index=standardized.index,
                    dtype="float64",
                )
                continue
            peers = [
                peer.indicator_id
                for peer in members
                if peer.indicator_id != entity_id
                and peer.concept == member.concept
            ]
            if not peers:
                peers = [
                    peer.indicator_id
                    for peer in members
                    if peer.indicator_id != entity_id
                ]
            if not peers:
                correlation = pd.Series(
                    np.nan,
                    index=standardized.index,
                    dtype="float64",
                )
            else:
                reference = standardized.loc[:, peers].mean(axis=1, skipna=True)
                correlation = (
                    standardized[entity_id]
                    .expanding(min_periods=minimum)
                    .corr(reference)
                    .shift(1)
                )
            directions[entity_id] = _stable_signs(correlation)
        return pd.DataFrame(directions, index=standardized.index).astype("float64")

    def _estimate_channel(
        self,
        channel_id: str,
        visibility: _VisibilityArchive,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        channel = self._channels[channel_id]
        members = self._members[channel_id]
        member_ids = [member.indicator_id for member in members]
        raw_values = visibility.values.loc[:, member_ids].copy(deep=True)
        standardized = pd.DataFrame(
            {
                entity_id: expanding_standardize(
                    raw_values[entity_id],
                    self._minimum_periods,
                )
                for entity_id in member_ids
            },
            index=raw_values.index,
            dtype="float64",
        )
        directions = self._directions(standardized, members)
        oriented = standardized * directions
        availability = raw_values.notna().astype("float64")
        member_breadth = pd.DataFrame(
            {
                entity_id: availability[entity_id]
                .expanding(min_periods=1)
                .mean()
                .shift(1)
                .fillna(0.5)
                for entity_id in member_ids
            },
            index=raw_values.index,
            dtype="float64",
        )
        concept_members = {
            concept: [
                member.indicator_id
                for member in members
                if member.concept == concept
            ]
            for concept in channel.eligible_indicator_concepts
            if any(member.concept == concept for member in members)
        }
        concept_breadth_by_concept: dict[str, pd.Series] = {}
        for concept, concept_member_ids in concept_members.items():
            current_breadth = availability.loc[:, concept_member_ids].mean(axis=1)
            concept_breadth_by_concept[concept] = (
                current_breadth
                .expanding(min_periods=1)
                .mean()
                .shift(1)
                .fillna(0.5)
                .astype("float64")
            )
        revision_event_risk = (
            visibility.revision_events.loc[:, member_ids]
            .fillna(0.0)
            .clip(0.0, 1.0)
            .astype("float64")
        )
        lagged_revision_risk = pd.DataFrame(
            {
                entity_id: visibility.revision_events[entity_id]
                .expanding(min_periods=1)
                .mean()
                .shift(1)
                .fillna(0.0)
                .clip(0.0, 1.0)
                for entity_id in member_ids
            },
            index=raw_values.index,
            dtype="float64",
        )
        revision_risk = pd.DataFrame(
            np.maximum(
                revision_event_risk.to_numpy(dtype="float64"),
                lagged_revision_risk.to_numpy(dtype="float64"),
            ),
            index=raw_values.index,
            columns=member_ids,
            dtype="float64",
        )
        walk_forward_fit: dict[str, pd.Series] = {}
        for entity_id in member_ids:
            member_filter = local_level_innovations(
                standardized[entity_id],
                process_variance=self._process_variance,
                observation_variance=self._observation_variance,
                initial_state=self._initial_state,
                initial_variance=self._initial_variance,
            )
            lagged_rmse = (
                member_filter.innovation.pow(2)
                .expanding(min_periods=1)
                .mean()
                .shift(1)
                .pow(0.5)
            )
            walk_forward_fit[entity_id] = (
                1.0 / (1.0 + lagged_rmse)
            ).fillna(0.5).clip(0.0, 1.0)
        fit = pd.DataFrame(
            walk_forward_fit,
            index=raw_values.index,
            dtype="float64",
        )
        quality = pd.Series(
            {
                member.indicator_id: _QUALITY_SCORES[member.quality_tier]
                for member in members
            },
            dtype="float64",
        )
        concept_breadth = pd.DataFrame(
            {
                member.indicator_id: concept_breadth_by_concept[member.concept]
                for member in members
            },
            index=raw_values.index,
            dtype="float64",
        )
        breadth_factor = 0.25 + 0.75 * np.sqrt(
            member_breadth * concept_breadth
        )
        fit_factor = 0.25 + 0.75 * fit
        revision_factor = 1.0 - 0.8 * revision_risk
        raw_reliability = (
            fit_factor
            * revision_factor
            * breadth_factor
            * quality.reindex(member_ids)
        ).clip(0.0, 1.0)
        composites: list[float] = []
        member_counts: list[int] = []
        concept_counts: list[int] = []
        channel_revision_risks: list[float] = []
        base_confidences: list[float] = []
        weights_json: list[str] = []
        diagnostic_rows: list[dict[str, object]] = []
        member_by_id = {member.indicator_id: member for member in members}
        active_concept_count = len(concept_members)

        for row_date in raw_values.index:
            valid_ids = [
                entity_id
                for entity_id in member_ids
                if np.isfinite(oriented.at[row_date, entity_id])
                and np.isfinite(raw_reliability.at[row_date, entity_id])
            ]
            available_concepts = [
                concept
                for concept in channel.eligible_indicator_concepts
                if any(
                    member_by_id[entity_id].concept == concept
                    for entity_id in valid_ids
                )
            ]
            concept_weight = (
                1.0 / float(len(available_concepts))
                if available_concepts
                else 0.0
            )
            within_weights = {entity_id: 0.0 for entity_id in member_ids}
            effective_weights = {entity_id: 0.0 for entity_id in member_ids}
            concept_weights = {
                concept: concept_weight for concept in available_concepts
            }
            concept_values: list[float] = []
            for concept in available_concepts:
                concept_ids = [
                    entity_id
                    for entity_id in valid_ids
                    if member_by_id[entity_id].concept == concept
                ]
                reliability_values = raw_reliability.loc[
                    row_date,
                    concept_ids,
                ].astype("float64")
                reliability_sum = float(reliability_values.sum())
                if reliability_sum <= 0.0:
                    normalized = pd.Series(
                        1.0 / float(len(concept_ids)),
                        index=concept_ids,
                        dtype="float64",
                    )
                else:
                    normalized = reliability_values / reliability_sum
                concept_value = 0.0
                for entity_id in concept_ids:
                    within = float(normalized[entity_id])
                    effective = within * concept_weight
                    within_weights[entity_id] = within
                    effective_weights[entity_id] = effective
                    concept_value += (
                        float(oriented.at[row_date, entity_id]) * within
                    )
                concept_values.append(concept_value)
            composite = (
                float(np.mean(concept_values)) if concept_values else np.nan
            )
            member_count = len(valid_ids)
            concept_count = len(available_concepts)
            observation_used = member_count >= channel.minimum_breadth
            composites.append(composite if observation_used else np.nan)
            member_counts.append(member_count)
            concept_counts.append(concept_count)
            if valid_ids:
                current_revision_risk = sum(
                    effective_weights[entity_id]
                    * float(revision_risk.at[row_date, entity_id])
                    for entity_id in valid_ids
                )
                weighted_reliability = sum(
                    effective_weights[entity_id]
                    * float(raw_reliability.at[row_date, entity_id])
                    for entity_id in valid_ids
                )
            else:
                current_revision_risk = float(
                    revision_risk.loc[row_date, member_ids].mean()
                )
                weighted_reliability = 0.0
            current_revision_risk = _bounded(current_revision_risk)
            channel_revision_risks.append(current_revision_risk)
            member_ratio = member_count / float(len(member_ids))
            concept_ratio = concept_count / float(active_concept_count)
            breadth_score = np.sqrt(member_ratio * concept_ratio)
            confidence_base = 0.5 * breadth_score + 0.5 * weighted_reliability
            confidence_base *= 1.0 - 0.5 * current_revision_risk
            base_confidences.append(_bounded(confidence_base))
            payload_members: list[dict[str, object]] = []
            for entity_id in member_ids:
                member = member_by_id[entity_id]
                payload_members.append(
                    {
                        "available": entity_id in valid_ids,
                        "concept": member.concept,
                        "concept_breadth": _json_number(
                            concept_breadth.at[row_date, entity_id]
                        ),
                        "concept_weight": _json_number(
                            concept_weights.get(member.concept, 0.0)
                        ),
                        "direction": _json_direction(
                            directions.at[row_date, entity_id]
                        ),
                        "effective_weight": _json_number(
                            effective_weights[entity_id]
                        ),
                        "entity_id": entity_id,
                        "lagged_revision_risk": _json_number(
                            lagged_revision_risk.at[row_date, entity_id]
                        ),
                        "member_breadth": _json_number(
                            member_breadth.at[row_date, entity_id]
                        ),
                        "quality_score": _json_number(quality[entity_id]),
                        "quality_tier": member.quality_tier,
                        "raw_reliability": _json_number(
                            raw_reliability.at[row_date, entity_id]
                        ),
                        "revision_event_risk": _json_number(
                            revision_event_risk.at[row_date, entity_id]
                        ),
                        "revision_risk": _json_number(
                            revision_risk.at[row_date, entity_id]
                        ),
                        "walk_forward_fit": _json_number(
                            fit.at[row_date, entity_id]
                        ),
                        "within_concept_weight": _json_number(
                            within_weights[entity_id]
                        ),
                    }
                )
                diagnostic_rows.append(
                    {
                        "date": row_date,
                        "channel_id": channel_id,
                        "entity_id": entity_id,
                        "concept": member.concept,
                        "raw_value": raw_values.at[row_date, entity_id],
                        "standardized_value": standardized.at[
                            row_date,
                            entity_id,
                        ],
                        "oriented_value": oriented.at[row_date, entity_id],
                        "observation_date": visibility.observation_dates.at[
                            row_date,
                            entity_id,
                        ],
                        "visible_date": visibility.visible_dates.at[
                            row_date,
                            entity_id,
                        ],
                        "revision_number": visibility.revision_numbers.at[
                            row_date,
                            entity_id,
                        ],
                        "update_count": visibility.update_counts.at[
                            row_date,
                            entity_id,
                        ],
                        "revision_event_count": (
                            visibility.revision_event_counts.at[
                                row_date,
                                entity_id,
                            ]
                        ),
                        "updates_json": visibility.updates_json.at[
                            row_date,
                            entity_id,
                        ],
                        "quality_tier": member.quality_tier,
                        "quality_score": float(quality[entity_id]),
                        "direction": directions.at[row_date, entity_id],
                        "walk_forward_fit": fit.at[row_date, entity_id],
                        "revision_event_risk": revision_event_risk.at[
                            row_date,
                            entity_id,
                        ],
                        "lagged_revision_risk": lagged_revision_risk.at[
                            row_date,
                            entity_id,
                        ],
                        "revision_risk": revision_risk.at[
                            row_date,
                            entity_id,
                        ],
                        "member_breadth": member_breadth.at[
                            row_date,
                            entity_id,
                        ],
                        "concept_breadth": concept_breadth.at[
                            row_date,
                            entity_id,
                        ],
                        "raw_reliability": raw_reliability.at[
                            row_date,
                            entity_id,
                        ],
                        "within_concept_weight": within_weights[entity_id],
                        "concept_weight": concept_weights.get(
                            member.concept,
                            0.0,
                        ),
                        "effective_weight": effective_weights[entity_id],
                        "available": entity_id in valid_ids,
                        "observation_used": observation_used,
                    }
                )
            weights_json.append(
                json.dumps(
                    {
                        "concept_weights": concept_weights,
                        "members": payload_members,
                        "minimum_breadth": channel.minimum_breadth,
                        "observation_used": observation_used,
                    },
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        composite_series = pd.Series(
            composites,
            index=raw_values.index,
            name=channel_id,
            dtype="float64",
        )
        state_filter = local_level_innovations(
            composite_series,
            process_variance=self._process_variance,
            observation_variance=self._observation_variance,
            initial_state=self._initial_state,
            initial_variance=self._initial_variance,
        )
        state_rows: list[dict[str, object]] = []
        prior_confidence = 0.0
        for position, row_date in enumerate(raw_values.index):
            observed = np.isfinite(composite_series.iat[position])
            state = state_filter.state.iat[position]
            uncertainty = state_filter.uncertainty.iat[position]
            if observed:
                status = "observed"
                status_reason = (
                    "minimum_breadth satisfied with "
                    f"{member_counts[position]} members across "
                    f"{concept_counts[position]} concepts"
                )
                confidence = base_confidences[position]
                if np.isfinite(uncertainty):
                    confidence *= 1.0 / (1.0 + float(uncertainty))
                confidence = _bounded(confidence)
            elif np.isfinite(state):
                status = "prediction_only"
                status_reason = (
                    f"current member breadth {member_counts[position]} is below "
                    f"minimum_breadth {channel.minimum_breadth}; causal "
                    "prediction only"
                )
                current_ratio = member_counts[position] / float(len(member_ids))
                confidence = _bounded(
                    prior_confidence
                    * 0.5
                    * max(current_ratio, 0.25)
                    * (1.0 - channel_revision_risks[position])
                )
            else:
                status = "unavailable"
                status_reason = (
                    f"state unavailable because current member breadth "
                    f"{member_counts[position]} is below minimum_breadth "
                    f"{channel.minimum_breadth} and no prior valid update exists"
                )
                confidence = 0.0
            prior_confidence = confidence
            state_rows.append(
                {
                    "date": row_date,
                    "channel_id": channel_id,
                    "state": state,
                    "innovation": state_filter.innovation.iat[position],
                    "uncertainty": uncertainty,
                    "member_count": member_counts[position],
                    "concept_count": concept_counts[position],
                    "revision_risk": channel_revision_risks[position],
                    "vintage_kind": visibility.vintage_kinds.iat[position],
                    "confidence": confidence,
                    "status": status,
                    "status_reason": status_reason,
                    "member_weights_json": weights_json[position],
                }
            )
        states = pd.DataFrame(state_rows, columns=CHANNEL_STATE_COLUMNS)
        diagnostics = pd.DataFrame(
            diagnostic_rows,
            columns=CHANNEL_DIAGNOSTIC_COLUMNS,
        )
        return states, diagnostics

    def estimate(
        self,
        observations: object,
        *,
        as_of: date,
        interpretation: VintageKind = VintageKind.REALTIME,
        strict_vintage: bool = True,
        channel_ids: Iterable[str] | None = None,
    ) -> ChannelEstimateResult:
        """Estimate selected channel histories as known at one archive cutoff."""

        cutoff = _normalize_as_of(as_of)
        if not isinstance(interpretation, VintageKind):
            raise TypeError("interpretation must be a VintageKind")
        if not isinstance(strict_vintage, bool):
            raise TypeError("strict_vintage must be a boolean")
        requested = self._requested_channels(channel_ids)
        records = _normalize_records(observations)
        visibility = self._visibility_archive(
            records,
            as_of=cutoff,
            interpretation=interpretation,
            strict_vintage=strict_vintage,
            channel_ids=requested,
        )
        state_frames: list[pd.DataFrame] = []
        diagnostic_frames: list[pd.DataFrame] = []
        for channel_id in requested:
            states, diagnostics = self._estimate_channel(
                channel_id,
                visibility,
            )
            state_frames.append(states)
            diagnostic_frames.append(diagnostics)
        channel_order = {channel_id: position for position, channel_id in enumerate(requested)}
        states = (
            pd.concat(state_frames, ignore_index=True)
            .assign(
                _channel_order=lambda frame: frame["channel_id"].map(
                    channel_order
                )
            )
            .sort_values(["date", "_channel_order"], kind="stable")
            .drop(columns="_channel_order")
            .reset_index(drop=True)
            .loc[:, CHANNEL_STATE_COLUMNS]
        )
        diagnostics = (
            pd.concat(diagnostic_frames, ignore_index=True)
            .assign(
                _channel_order=lambda frame: frame["channel_id"].map(
                    channel_order
                )
            )
            .sort_values(
                ["date", "_channel_order", "entity_id"],
                kind="stable",
            )
            .drop(columns="_channel_order")
            .reset_index(drop=True)
            .loc[:, CHANNEL_DIAGNOSTIC_COLUMNS]
        )
        return ChannelEstimateResult(states=states, diagnostics=diagnostics)


__all__ = [
    "CHANNEL_DIAGNOSTIC_COLUMNS",
    "CHANNEL_STATE_COLUMNS",
    "ChannelBreadthError",
    "ChannelEngine",
    "ChannelEstimateResult",
]
