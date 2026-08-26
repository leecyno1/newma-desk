"""Stable ``channel_state`` product construction and persistence."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from numbers import Integral, Real
from pathlib import Path
import stat

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.channels.engine import (
    CHANNEL_STATE_COLUMNS as ENGINE_CHANNEL_STATE_COLUMNS,
    ChannelEngine,
)
from seven_cycle_platform.contracts.arrow import CHANNEL_STATE_SCHEMA
from seven_cycle_platform.registry.models import (
    ChannelSpec,
    IndicatorSpec,
    RegistryBundle,
)
from seven_cycle_platform.storage.run_context import RunContext
from seven_cycle_platform.types import VintageKind


CHANNEL_STATE_FILENAME = "channel_state.parquet"
CHANNEL_STATE_COLUMNS = tuple(CHANNEL_STATE_SCHEMA.names)
_DIMENSION_COLUMNS = ("date", "channel_id", "vintage_kind")
_PROVENANCE_COLUMNS = (
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
)
_STATUS_VALUES = {"observed", "prediction_only", "unavailable"}
_QUALITY_SCORES = {"A": 1.0, "B": 0.75, "C": 0.5}
_WEIGHT_PAYLOAD_KEYS = {
    "concept_weights",
    "members",
    "minimum_breadth",
    "observation_used",
}
_MEMBER_WEIGHT_KEYS = {
    "available",
    "concept",
    "concept_breadth",
    "concept_weight",
    "direction",
    "effective_weight",
    "entity_id",
    "lagged_revision_risk",
    "member_breadth",
    "quality_score",
    "quality_tier",
    "raw_reliability",
    "revision_event_risk",
    "revision_risk",
    "walk_forward_fit",
    "within_concept_weight",
}
_UNIT_INTERVAL_MEMBER_FIELDS = {
    "concept_breadth",
    "concept_weight",
    "effective_weight",
    "lagged_revision_risk",
    "member_breadth",
    "quality_score",
    "raw_reliability",
    "revision_event_risk",
    "revision_risk",
    "walk_forward_fit",
    "within_concept_weight",
}
_VINTAGE_ORDER = {
    VintageKind.REALTIME.value: 0,
    VintageKind.LATEST_HISTORICAL.value: 1,
    VintageKind.PSEUDO_VINTAGE.value: 2,
}
_SUPPORTED_PRODUCT_VINTAGES = frozenset(
    {
        VintageKind.REALTIME,
        VintageKind.LATEST_HISTORICAL,
        VintageKind.PSEUDO_VINTAGE,
    }
)


@dataclass(frozen=True)
class _RegistryContract:
    channels: dict[str, ChannelSpec]
    members: dict[str, tuple[IndicatorSpec, ...]]


def _registry_contract(registry: object) -> _RegistryContract:
    if not isinstance(registry, RegistryBundle):
        raise TypeError("registry must be a RegistryBundle")
    validated = RegistryBundle.model_validate(
        registry.model_dump(mode="python")
    )
    engine = ChannelEngine(validated)
    channels = {
        channel.channel_id: channel.model_copy(deep=True)
        for channel in validated.channels
    }
    members = {
        channel_id: engine.members_for(channel_id)
        for channel_id in engine.channel_ids
    }
    return _RegistryContract(channels=channels, members=members)


def _normalize_date(value: object, *, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} cannot be a boolean; a date is required")
    if isinstance(value, pd.Timestamp):
        timestamp = value
    elif isinstance(value, (date, datetime, np.datetime64, str)):
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must contain valid dates") from error
    else:
        raise TypeError(f"{name} must contain date values")
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot contain missing dates")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone.utc).tz_localize(None)
    return timestamp.normalize()


def _normalize_dates(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_date(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _normalize_real(value: object, *, name: str) -> float:
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and missing:
        return np.nan
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must contain real numbers or missing values")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must contain finite values or missing values")
    return numeric


def _normalize_real_column(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_real(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="float64",
    )


def _normalize_count(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must contain nonnegative integers")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must contain nonnegative integers")
    return numeric


def _normalize_counts(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_count(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="int64",
    )


def _normalize_nonempty_strings(values: pd.Series, *, name: str) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{name} must contain non-empty strings")
        normalized.append(value.strip())
    return pd.Series(normalized, index=values.index, dtype="object")


def _normalize_vintages(values: pd.Series) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if isinstance(value, VintageKind):
            vintage = value
        else:
            if not isinstance(value, str):
                raise TypeError("vintage_kind must contain VintageKind strings")
            try:
                vintage = VintageKind(value)
            except ValueError as error:
                raise ValueError(f"unknown vintage_kind: {value}") from error
        if vintage not in _SUPPORTED_PRODUCT_VINTAGES:
            raise ValueError(
                "channel_state product does not support data-identity vintage: "
                f"{vintage.value}"
            )
        normalized.append(vintage.value)
    return pd.Series(normalized, index=values.index, dtype="object")


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"member_weights_json contains invalid constant: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(
                f"member_weights_json contains duplicate key: {key}"
            )
        payload[key] = value
    return payload


def _decode_member_weights(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("member_weights_json must contain JSON strings")
    try:
        payload = json.loads(
            value,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("member_weights_json must contain valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("member_weights_json must encode a JSON object")
    return payload


def _json_number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"member_weights_json {name} must be numeric")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"member_weights_json {name} must be finite")
    return numeric


def _unit_interval_json_number(value: object, *, name: str) -> float:
    numeric = _json_number(value, name=name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(
            f"member_weights_json {name} must be between 0 and 1"
        )
    return numeric


def _weights_close(left: float, right: float) -> bool:
    return bool(np.isclose(left, right, rtol=1e-9, atol=1e-12))


def _normalized_member_payload(
    payload: object,
    *,
    position: int,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("member_weights_json members must contain objects")
    if set(payload) != _MEMBER_WEIGHT_KEYS:
        raise ValueError(
            "member_weights_json member keys must exactly match the audit contract"
        )
    entity_id = payload["entity_id"]
    concept = payload["concept"]
    quality_tier = payload["quality_tier"]
    available = payload["available"]
    if not isinstance(entity_id, str) or not entity_id:
        raise ValueError(
            f"member_weights_json members[{position}].entity_id must be non-empty"
        )
    if not isinstance(concept, str) or not concept:
        raise ValueError(
            f"member_weights_json members[{position}].concept must be non-empty"
        )
    if not isinstance(quality_tier, str) or not quality_tier:
        raise ValueError(
            f"member_weights_json members[{position}].quality_tier must be non-empty"
        )
    if not isinstance(available, bool):
        raise ValueError(
            f"member_weights_json members[{position}].available must be boolean"
        )
    normalized: dict[str, object] = {
        "available": available,
        "concept": concept,
        "entity_id": entity_id,
        "quality_tier": quality_tier,
    }
    for field_name in sorted(_UNIT_INTERVAL_MEMBER_FIELDS):
        normalized[field_name] = _unit_interval_json_number(
            payload[field_name],
            name=f"members[{position}].{field_name}",
        )
    raw_direction = payload["direction"]
    if raw_direction is None:
        direction = None
    else:
        direction = _json_number(
            raw_direction,
            name=f"members[{position}].direction",
        )
        if direction not in {-1.0, 1.0}:
            raise ValueError(
                "member_weights_json direction must be -1, 1, or null"
            )
    normalized["direction"] = direction
    return normalized


def _canonical_member_weights(
    value: object,
    *,
    row: pd.Series,
    channel: ChannelSpec,
    expected_members: tuple[IndicatorSpec, ...],
) -> str:
    payload = _decode_member_weights(value)
    if set(payload) != _WEIGHT_PAYLOAD_KEYS:
        raise ValueError(
            "member_weights_json top-level keys must exactly match the audit contract"
        )
    minimum_breadth = payload["minimum_breadth"]
    if isinstance(minimum_breadth, bool) or not isinstance(minimum_breadth, int):
        raise ValueError(
            "member_weights_json minimum_breadth must be an integer"
        )
    if minimum_breadth != channel.minimum_breadth:
        raise ValueError(
            "member_weights_json minimum_breadth must match the registry"
        )
    observation_used = payload["observation_used"]
    if not isinstance(observation_used, bool):
        raise ValueError(
            "member_weights_json observation_used must be boolean"
        )
    raw_concept_weights = payload["concept_weights"]
    if not isinstance(raw_concept_weights, dict):
        raise ValueError(
            "member_weights_json concept_weights must be an object"
        )
    concept_weights: dict[str, float] = {}
    for concept, weight in raw_concept_weights.items():
        if not isinstance(concept, str) or not concept:
            raise ValueError(
                "member_weights_json concept_weights keys must be non-empty"
            )
        concept_weights[concept] = _unit_interval_json_number(
            weight,
            name=f"concept_weights.{concept}",
        )
    raw_members = payload["members"]
    if not isinstance(raw_members, list):
        raise ValueError("member_weights_json members must be an array")
    normalized_members = [
        _normalized_member_payload(member, position=position)
        for position, member in enumerate(raw_members)
    ]
    entity_ids = [str(member["entity_id"]) for member in normalized_members]
    if len(entity_ids) != len(set(entity_ids)):
        raise ValueError(
            "member_weights_json member entity_id values must be unique"
        )
    expected_by_id = {
        member.indicator_id: member for member in expected_members
    }
    if set(entity_ids) != set(expected_by_id):
        raise ValueError(
            "member_weights_json members must cover all active eligible indicators"
        )
    normalized_by_id = {
        str(member["entity_id"]): member for member in normalized_members
    }
    ordered_members = [
        normalized_by_id[member.indicator_id] for member in expected_members
    ]
    for member in ordered_members:
        registry_member = expected_by_id[str(member["entity_id"])]
        if member["concept"] != registry_member.concept:
            raise ValueError(
                "member_weights_json member concept must match the registry"
            )
        if member["quality_tier"] != registry_member.quality_tier:
            raise ValueError(
                "member_weights_json member quality_tier must match the registry"
            )
        expected_quality = _QUALITY_SCORES[registry_member.quality_tier]
        if not _weights_close(float(member["quality_score"]), expected_quality):
            raise ValueError(
                "member_weights_json member quality_score must match the registry"
            )
        expected_revision_risk = max(
            float(member["revision_event_risk"]),
            float(member["lagged_revision_risk"]),
        )
        if not _weights_close(
            float(member["revision_risk"]),
            expected_revision_risk,
        ):
            raise ValueError(
                "member_weights_json revision_risk must equal max current and lagged risk"
            )
    available_members = [
        member for member in ordered_members if member["available"] is True
    ]
    for member in ordered_members:
        if member["available"] is True and member["direction"] is None:
            raise ValueError(
                "member_weights_json available member direction must be -1 or 1"
            )
    available_concepts = {
        str(member["concept"]) for member in available_members
    }
    if int(row["member_count"]) != len(available_members):
        raise ValueError(
            "member_count must equal available members in member_weights_json"
        )
    if int(row["concept_count"]) != len(available_concepts):
        raise ValueError(
            "concept_count must equal available concepts in member_weights_json"
        )
    if set(concept_weights) != available_concepts:
        raise ValueError(
            "member_weights_json concept_weights keys must equal available concepts"
        )
    expected_concept_sum = 1.0 if available_concepts else 0.0
    if not _weights_close(sum(concept_weights.values()), expected_concept_sum):
        raise ValueError(
            "member_weights_json concept_weights must conserve to one or zero"
        )
    for concept in {member.concept for member in expected_members}:
        concept_members = [
            member for member in ordered_members if member["concept"] == concept
        ]
        available_in_concept = [
            member for member in concept_members if member["available"] is True
        ]
        expected_within_sum = 1.0 if available_in_concept else 0.0
        actual_within_sum = sum(
            float(member["within_concept_weight"])
            for member in available_in_concept
        )
        if not _weights_close(actual_within_sum, expected_within_sum):
            raise ValueError(
                "member_weights_json within_concept_weight must conserve within concept"
            )
        for member in concept_members:
            top_level_weight = concept_weights.get(concept, 0.0)
            if not _weights_close(
                float(member["concept_weight"]),
                top_level_weight,
            ):
                raise ValueError(
                    "member_weights_json member concept_weight must match top-level"
                )
            if member["available"] is False and not _weights_close(
                float(member["within_concept_weight"]),
                0.0,
            ):
                raise ValueError(
                    "member_weights_json unavailable member within_concept_weight "
                    "must be zero"
                )
            expected_effective = (
                float(member["within_concept_weight"])
                * float(member["concept_weight"])
            )
            if not _weights_close(
                float(member["effective_weight"]),
                expected_effective,
            ):
                raise ValueError(
                    "member_weights_json effective_weight must equal within_concept_weight "
                    "times concept_weight"
                )
            if member["available"] is False and not _weights_close(
                float(member["effective_weight"]),
                0.0,
            ):
                raise ValueError(
                    "member_weights_json unavailable member effective_weight must be zero"
                )
    expected_effective_sum = 1.0 if available_members else 0.0
    actual_effective_sum = sum(
        float(member["effective_weight"]) for member in ordered_members
    )
    if not _weights_close(actual_effective_sum, expected_effective_sum):
        raise ValueError(
            "member_weights_json effective_weight values must conserve to one or zero"
        )
    if available_members:
        expected_revision_risk = sum(
            float(member["effective_weight"])
            * float(member["revision_risk"])
            for member in ordered_members
        )
    else:
        expected_revision_risk = (
            sum(float(member["revision_risk"]) for member in ordered_members)
            / float(len(ordered_members))
        )
    if not _weights_close(float(row["revision_risk"]), expected_revision_risk):
        raise ValueError(
            "revision_risk must equal combined member revision risk"
        )
    expected_observation_used = (
        int(row["member_count"]) >= channel.minimum_breadth
    )
    status_observed = row["status"] == "observed"
    if status_observed and not expected_observation_used:
        raise ValueError(
            "observed member_count must meet registry minimum_breadth"
        )
    if observation_used != expected_observation_used:
        raise ValueError(
            "member_weights_json observation_used must match minimum_breadth"
        )
    if status_observed != expected_observation_used:
        raise ValueError(
            "status observed must match member_weights_json observation_used"
        )
    canonical_payload = {
        "concept_weights": concept_weights,
        "members": ordered_members,
        "minimum_breadth": minimum_breadth,
        "observation_used": observation_used,
    }
    return json.dumps(
        canonical_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _state_frames(states: object) -> tuple[pd.DataFrame, ...]:
    if isinstance(states, pd.DataFrame):
        frames = (states,)
    elif isinstance(states, Mapping):
        normalized: list[pd.DataFrame] = []
        for vintage, frame in sorted(states.items(), key=lambda item: str(item[0])):
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("state mappings must contain pandas DataFrames")
            copied = frame.copy(deep=True)
            normalized_vintage = (
                vintage.value if isinstance(vintage, VintageKind) else str(vintage)
            )
            if "vintage_kind" in copied:
                actual = copied["vintage_kind"].map(
                    lambda value: value.value
                    if isinstance(value, VintageKind)
                    else str(value)
                )
                if not actual.eq(normalized_vintage).all():
                    raise ValueError(
                        "state mapping key must match the vintage_kind column"
                    )
            else:
                copied["vintage_kind"] = normalized_vintage
            normalized.append(copied)
        frames = tuple(normalized)
    elif isinstance(states, Iterable) and not isinstance(
        states,
        (str, bytes, bytearray),
    ):
        frames = tuple(states)
    else:
        raise TypeError("states must be a DataFrame or iterable of DataFrames")
    if not frames:
        raise ValueError("states must contain at least one DataFrame")
    if any(not isinstance(frame, pd.DataFrame) for frame in frames):
        raise TypeError("states must contain only pandas DataFrames")
    return tuple(frame.copy(deep=True) for frame in frames)


def _validate_status_semantics(values: pd.DataFrame) -> None:
    for row in values.itertuples(index=False):
        state_present = pd.notna(row.state)
        innovation_present = pd.notna(row.innovation)
        uncertainty_present = pd.notna(row.uncertainty)
        if row.status == "observed":
            if not (state_present and innovation_present and uncertainty_present):
                raise ValueError(
                    "observed rows require state, innovation, and uncertainty"
                )
            if row.member_count < 1 or row.concept_count < 1:
                raise ValueError("observed rows require positive breadth")
        elif row.status == "prediction_only":
            if not (state_present and uncertainty_present) or innovation_present:
                raise ValueError(
                    "prediction_only rows require state and uncertainty with "
                    "missing innovation"
                )
        elif state_present or innovation_present or uncertainty_present:
            raise ValueError(
                "unavailable rows require missing state, innovation, and uncertainty"
            )
        if row.status == "unavailable" and row.confidence != 0.0:
            raise ValueError("unavailable rows require zero confidence")


def _normalize_state_frame(
    frame: pd.DataFrame,
    registry: _RegistryContract,
) -> pd.DataFrame:
    if frame.columns.has_duplicates:
        raise ValueError("state frame columns must be unique")
    values = frame.copy(deep=True)
    prohibited = set(_PROVENANCE_COLUMNS).intersection(values.columns)
    if prohibited:
        names = ", ".join(sorted(prohibited))
        raise ValueError(
            "product provenance must come only from RunContext; "
            f"remove {names}"
        )
    unexpected = sorted(set(values.columns).difference(ENGINE_CHANNEL_STATE_COLUMNS))
    if unexpected:
        raise ValueError(
            "unexpected state columns: " + ", ".join(map(str, unexpected))
        )
    missing = sorted(set(ENGINE_CHANNEL_STATE_COLUMNS).difference(values.columns))
    if missing:
        raise ValueError("missing required state columns: " + ", ".join(missing))
    values = values.loc[:, ENGINE_CHANNEL_STATE_COLUMNS]
    values["date"] = _normalize_dates(values["date"], name="date")
    values["channel_id"] = _normalize_nonempty_strings(
        values["channel_id"],
        name="channel_id",
    )
    for field_name in ("state", "innovation", "uncertainty"):
        values[field_name] = _normalize_real_column(
            values[field_name],
            name=field_name,
        )
    values["member_count"] = _normalize_counts(
        values["member_count"],
        name="member_count",
    )
    values["concept_count"] = _normalize_counts(
        values["concept_count"],
        name="concept_count",
    )
    values["revision_risk"] = _normalize_real_column(
        values["revision_risk"],
        name="revision_risk",
    )
    values["vintage_kind"] = _normalize_vintages(values["vintage_kind"])
    values["confidence"] = _normalize_real_column(
        values["confidence"],
        name="confidence",
    )
    values["status"] = _normalize_nonempty_strings(
        values["status"],
        name="status",
    )
    values["status_reason"] = _normalize_nonempty_strings(
        values["status_reason"],
        name="status_reason",
    )
    values["member_weights_json"] = _normalize_nonempty_strings(
        values["member_weights_json"],
        name="member_weights_json",
    )
    unknown_channels = set(values["channel_id"]).difference(registry.channels)
    if unknown_channels:
        raise ValueError(
            "unknown channel_id: " + ", ".join(sorted(unknown_channels))
        )
    unknown_statuses = set(values["status"]).difference(_STATUS_VALUES)
    if unknown_statuses:
        raise ValueError(
            "unknown channel status: " + ", ".join(sorted(unknown_statuses))
        )
    if values["revision_risk"].isna().any() or not values[
        "revision_risk"
    ].between(0.0, 1.0).all():
        raise ValueError("revision_risk must be present and between 0 and 1")
    if values["confidence"].isna().any() or not values["confidence"].between(
        0.0,
        1.0,
    ).all():
        raise ValueError("confidence must be present and between 0 and 1")
    finite_uncertainty = values.loc[values["uncertainty"].notna(), "uncertainty"]
    if not finite_uncertainty.ge(0.0).all():
        raise ValueError("uncertainty must be nonnegative")
    if not values["concept_count"].le(values["member_count"]).all():
        raise ValueError("concept_count cannot exceed member_count")
    _validate_status_semantics(values)
    canonical_weights: list[str] = []
    for _, row in values.iterrows():
        channel_id = str(row["channel_id"])
        canonical_weights.append(
            _canonical_member_weights(
                row["member_weights_json"],
                row=row,
                channel=registry.channels[channel_id],
                expected_members=registry.members[channel_id],
            )
        )
    values["member_weights_json"] = pd.Series(
        canonical_weights,
        index=values.index,
        dtype="object",
    )
    return values


def _validate_dimensions(values: pd.DataFrame) -> None:
    if values.duplicated(list(_DIMENSION_COLUMNS)).any():
        raise ValueError(
            "date × channel_id × vintage_kind dimensions must be unique"
        )


def _sort_product(values: pd.DataFrame) -> pd.DataFrame:
    vintage_order = values["vintage_kind"].map(_VINTAGE_ORDER).astype("int64")
    return (
        values.assign(_vintage_order=vintage_order)
        .sort_values(
            ["date", "_vintage_order", "channel_id"],
            kind="stable",
        )
        .drop(columns="_vintage_order")
        .reset_index(drop=True)
    )


def _validate_context(context: object) -> RunContext:
    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    return context


def _add_provenance(values: pd.DataFrame, context: RunContext) -> pd.DataFrame:
    product = values.copy(deep=True)
    product["run_id"] = context.run_id
    product["as_of"] = context.as_of
    product["data_vintage"] = context.data_vintage
    product["model_version"] = context.model_version
    product["config_hash"] = context.config_hash
    product["created_at"] = context.created_at
    return product.loc[:, CHANNEL_STATE_COLUMNS]


def _build_channel_state(
    states: object,
    *,
    context: RunContext,
    registry: _RegistryContract,
) -> pd.DataFrame:
    normalized = pd.concat(
        [
            _normalize_state_frame(frame, registry)
            for frame in _state_frames(states)
        ],
        ignore_index=True,
    )
    _validate_dimensions(normalized)
    product = _add_provenance(_sort_product(normalized), context)
    _validate_channel_state_product(
        product,
        context=context,
        registry=registry,
    )
    return product


def build_channel_state(
    states: object,
    *,
    context: RunContext,
    registry: RegistryBundle,
) -> pd.DataFrame:
    """Build the stable date × channel × vintage product."""

    return _build_channel_state(
        states,
        context=_validate_context(context),
        registry=_registry_contract(registry),
    )


def _validate_common_provenance(
    values: pd.DataFrame,
    context: RunContext,
) -> None:
    expected = {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }
    for field_name, expected_value in expected.items():
        if field_name in {"as_of", "data_vintage"}:
            actual = _normalize_dates(values[field_name], name=field_name)
            if not actual.eq(pd.Timestamp(expected_value)).all():
                raise ValueError(f"{field_name} does not match RunContext")
        elif field_name == "created_at":
            actual = pd.to_datetime(values[field_name], utc=True)
            if not actual.eq(pd.Timestamp(expected_value)).all():
                raise ValueError("created_at does not match RunContext")
        elif not values[field_name].eq(expected_value).all():
            raise ValueError(f"{field_name} does not match RunContext")


def _validate_channel_state_product(
    product: pd.DataFrame,
    *,
    context: RunContext,
    registry: _RegistryContract,
) -> None:
    if not isinstance(product, pd.DataFrame):
        raise TypeError("product must be a pandas DataFrame")
    if product.columns.has_duplicates:
        raise ValueError("product columns must be unique")
    if tuple(product.columns) != CHANNEL_STATE_COLUMNS:
        raise ValueError("product columns do not match the stable schema")
    normalized = _normalize_state_frame(
        product.loc[:, ENGINE_CHANNEL_STATE_COLUMNS],
        registry,
    )
    _validate_dimensions(normalized)
    _validate_common_provenance(product, context)


def validate_channel_state(
    product: pd.DataFrame,
    *,
    context: RunContext,
    registry: RegistryBundle,
) -> None:
    """Validate schema columns, values, dimensions, registry, and provenance."""

    _validate_channel_state_product(
        product,
        context=_validate_context(context),
        registry=_registry_contract(registry),
    )


def _arrow_table(product: pd.DataFrame) -> pa.Table:
    arrays = [
        pa.array(
            product[field.name].tolist(),
            type=field.type,
            from_pandas=True,
        )
        for field in CHANNEL_STATE_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=CHANNEL_STATE_SCHEMA)


def _require_run_directory(run_dir: Path, context: RunContext) -> None:
    try:
        run_stat = run_dir.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(run_stat.st_mode):
        raise ValueError("run_dir must be an existing real directory")
    if run_dir.name != context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")


def _write_channel_state(
    run_dir: Path,
    product: pd.DataFrame,
    *,
    context: RunContext,
    registry: _RegistryContract,
) -> Path:
    directory = Path(run_dir)
    _require_run_directory(directory, context)
    _validate_channel_state_product(
        product,
        context=context,
        registry=registry,
    )
    canonical_states = _normalize_state_frame(
        product.loc[:, ENGINE_CHANNEL_STATE_COLUMNS],
        registry,
    )
    canonical = _add_provenance(_sort_product(canonical_states), context)
    product_path = directory / CHANNEL_STATE_FILENAME
    try:
        product_file = product_path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite of {product_path}"
        ) from error
    try:
        with product_file:
            pq.write_table(
                _arrow_table(canonical),
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
        if pq.read_schema(product_path) != CHANNEL_STATE_SCHEMA:
            raise ValueError("persisted channel state schema mismatch")
    except BaseException:
        product_path.unlink(missing_ok=True)
        raise
    return product_path


def write_channel_state(
    run_dir: Path,
    product: pd.DataFrame,
    *,
    context: RunContext,
    registry: RegistryBundle,
) -> Path:
    """Write ``channel_state.parquet`` without replacing an existing file."""

    return _write_channel_state(
        run_dir,
        product,
        context=_validate_context(context),
        registry=_registry_contract(registry),
    )


def build_and_write_channel_state(
    run_dir: Path,
    states: object,
    *,
    context: RunContext,
    registry: RegistryBundle,
) -> Path:
    """Build, validate, and exclusively persist ``channel_state``."""

    run_context = _validate_context(context)
    registry_contract = _registry_contract(registry)
    product = _build_channel_state(
        states,
        context=run_context,
        registry=registry_contract,
    )
    return _write_channel_state(
        run_dir,
        product,
        context=run_context,
        registry=registry_contract,
    )


__all__ = [
    "CHANNEL_STATE_COLUMNS",
    "CHANNEL_STATE_FILENAME",
    "build_and_write_channel_state",
    "build_channel_state",
    "validate_channel_state",
    "write_channel_state",
]
