from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.registry.models import (
    IndicatorSpec,
    RegistryBundle,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


REGISTRY_DIR = Path(__file__).resolve().parents[3] / "config" / "seven_cycle"

CHANNEL_STATE_FIELDS = [
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
]

PROVENANCE_FIELDS = [
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
]


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2024, 6, 30),
        data_vintage=date(2024, 6, 30),
        model_version="channel-state-v1",
        config={"channels": ["inflation_prices"], "strict_vintage": True},
        input_checksums={"observations.parquet": _checksum(b"observations")},
        quality_summary={"failed": 0, "passed": 1},
        created_at=datetime(2026, 7, 13, 3, 30, tzinfo=timezone.utc),
    )


def _registry() -> RegistryBundle:
    return load_registry_bundle(REGISTRY_DIR)


def _indicator(indicator_id: str) -> IndicatorSpec:
    return next(
        indicator
        for indicator in _registry().indicators
        if indicator.indicator_id == indicator_id
    ).model_copy(deep=True)


def _clone_indicator(
    indicator: IndicatorSpec,
    *,
    indicator_id: str,
    concept: str | None = None,
    quality_tier: str | None = None,
    direction_prior: float | None = 1.0,
) -> IndicatorSpec:
    updates: dict[str, object] = {
        "indicator_id": indicator_id,
        "name_zh": indicator_id,
        "name_en": indicator_id,
        "direction_prior": direction_prior,
        "active": True,
    }
    if concept is not None:
        updates["concept"] = concept
    if quality_tier is not None:
        updates["quality_tier"] = quality_tier
    return indicator.model_copy(deep=True, update=updates)


def _channel_bundle(
    indicators: list[IndicatorSpec],
    *,
    concepts: tuple[str, ...],
    minimum_breadth: int,
) -> RegistryBundle:
    base = _registry()
    template = next(
        channel
        for channel in base.channels
        if channel.channel_id == "inflation_prices"
    )
    channel = template.model_copy(
        deep=True,
        update={
            "eligible_indicator_concepts": list(concepts),
            "minimum_breadth": minimum_breadth,
        },
    )
    return RegistryBundle(
        cycles=[cycle.model_copy(deep=True) for cycle in base.cycles],
        indicators=[indicator.model_copy(deep=True) for indicator in indicators],
        channels=[channel],
        assets=[asset.model_copy(deep=True) for asset in base.assets],
    )


def _observation(
    indicator: IndicatorSpec,
    *,
    observation_date: date,
    visible_date: date,
    value: float,
    revision_number: int = 0,
    vintage_kind: VintageKind = VintageKind.REALTIME,
    release_date: date | None = None,
) -> Observation:
    release = release_date or visible_date
    return Observation(
        entity_id=indicator.indicator_id,
        observation_date=observation_date,
        release_date=release,
        vintage_date=visible_date,
        value=value,
        unit=indicator.unit,
        source=indicator.source,
        retrieval_time=datetime.combine(
            visible_date,
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=revision_number,
        quality_status="accepted",
        vintage_kind=vintage_kind,
    )


def _monthly_archive(
    indicators: list[IndicatorSpec],
    values: dict[str, list[float]],
    *,
    start: str = "2022-01-31",
    vintage_kind: VintageKind = VintageKind.REALTIME,
) -> list[Observation]:
    lengths = {len(series) for series in values.values()}
    assert len(lengths) == 1
    periods = lengths.pop()
    dates = pd.date_range(start, periods=periods, freq="ME")
    by_id = {indicator.indicator_id: indicator for indicator in indicators}
    records: list[Observation] = []
    for entity_id, series in values.items():
        indicator = by_id[entity_id]
        for observation_date, value in zip(dates, series, strict=True):
            visible_date = (observation_date + pd.Timedelta(days=5)).date()
            records.append(
                _observation(
                    indicator,
                    observation_date=observation_date.date(),
                    visible_date=visible_date,
                    value=value,
                    vintage_kind=vintage_kind,
                )
            )
    return records


def _member_payload(row: pd.Series) -> dict[str, dict[str, object]]:
    payload = json.loads(row["member_weights_json"])
    return {
        member["entity_id"]: member
        for member in payload["members"]
    }


def _last_observed_diagnostic(result: object) -> pd.Series:
    diagnostics = result.diagnostics
    observed = diagnostics.loc[diagnostics["raw_value"].notna()]
    return observed.sort_values("date", kind="stable").iloc[-1]


def _eligible_members(
    registry: RegistryBundle,
    channel_id: str,
) -> list[IndicatorSpec]:
    channel = next(
        channel for channel in registry.channels if channel.channel_id == channel_id
    )
    return [
        indicator
        for indicator in registry.indicators
        if indicator.active
        and indicator.concept in channel.eligible_indicator_concepts
    ]


def _weights_payload(
    registry: RegistryBundle,
    *,
    channel_id: str,
    available_ids: set[str],
) -> dict[str, object]:
    quality_scores = {"A": 1.0, "B": 0.75, "C": 0.5}
    channel = next(
        channel for channel in registry.channels if channel.channel_id == channel_id
    )
    members = _eligible_members(registry, channel_id)
    available_concepts = sorted(
        {
            member.concept
            for member in members
            if member.indicator_id in available_ids
        }
    )
    concept_weight = (
        1.0 / len(available_concepts) if available_concepts else 0.0
    )
    concept_weights = {
        concept: concept_weight for concept in available_concepts
    }
    payload_members = []
    for member in members:
        available = member.indicator_id in available_ids
        risk = 0.1 if available else 0.0
        available_in_concept = [
            candidate
            for candidate in members
            if candidate.concept == member.concept
            and candidate.indicator_id in available_ids
        ]
        within = 1.0 / len(available_in_concept) if available else 0.0
        member_concept_weight = concept_weights.get(member.concept, 0.0)
        payload_members.append(
            {
                "available": available,
                "concept": member.concept,
                "concept_breadth": 0.8,
                "concept_weight": member_concept_weight,
                "direction": 1.0 if available else None,
                "effective_weight": within * member_concept_weight,
                "entity_id": member.indicator_id,
                "lagged_revision_risk": risk,
                "member_breadth": 0.8,
                "quality_score": quality_scores[member.quality_tier],
                "quality_tier": member.quality_tier,
                "raw_reliability": 0.8,
                "revision_event_risk": risk,
                "revision_risk": risk,
                "walk_forward_fit": 0.8,
                "within_concept_weight": within,
            }
        )
    return {
        "concept_weights": concept_weights,
        "members": payload_members,
        "minimum_breadth": channel.minimum_breadth,
        "observation_used": len(available_ids) >= channel.minimum_breadth,
    }


def _weights_json(
    registry: RegistryBundle,
    *,
    available_ids: set[str],
) -> str:
    return json.dumps(
        _weights_payload(
            registry,
            channel_id="inflation_prices",
            available_ids=available_ids,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )


def _product_state_frame(registry: RegistryBundle) -> pd.DataFrame:
    members = _eligible_members(registry, "inflation_prices")
    by_concept = {member.concept: member.indicator_id for member in members}
    observed_ids = {by_concept["cpi"], by_concept["ppi"]}
    prediction_ids = {by_concept["cpi"]}
    return pd.DataFrame(
        [
            {
                "date": datetime(2024, 5, 31, 18, 30),
                "channel_id": "inflation_prices",
                "state": 0.5,
                "innovation": 0.2,
                "uncertainty": 0.3,
                "member_count": 2,
                "concept_count": 2,
                "revision_risk": 0.1,
                "vintage_kind": VintageKind.REALTIME,
                "confidence": 0.8,
                "status": "observed",
                "status_reason": "minimum breadth satisfied",
                "member_weights_json": _weights_json(
                    registry,
                    available_ids=observed_ids,
                ),
            },
            {
                "date": datetime(2024, 6, 30, 12, 0),
                "channel_id": "inflation_prices",
                "state": 0.5,
                "innovation": np.nan,
                "uncertainty": 0.4,
                "member_count": 1,
                "concept_count": 1,
                "revision_risk": 0.1,
                "vintage_kind": VintageKind.REALTIME,
                "confidence": 0.25,
                "status": "prediction_only",
                "status_reason": "current member breadth is below minimum",
                "member_weights_json": _weights_json(
                    registry,
                    available_ids=prediction_ids,
                ),
            },
            {
                "date": datetime(2024, 6, 30, 12, 0),
                "channel_id": "inflation_prices",
                "state": np.nan,
                "innovation": np.nan,
                "uncertainty": np.nan,
                "member_count": 0,
                "concept_count": 0,
                "revision_risk": 0.0,
                "vintage_kind": VintageKind.LATEST_HISTORICAL,
                "confidence": 0.0,
                "status": "unavailable",
                "status_reason": "state has not been initialized",
                "member_weights_json": _weights_json(
                    registry,
                    available_ids=set(),
                ),
            },
        ]
    )


def test_engine_loads_real_registry_concepts_and_active_members() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    bundle = _registry()
    engine = ChannelEngine(bundle)

    assert engine.channel_ids == tuple(
        channel.channel_id for channel in bundle.channels
    )
    for channel in bundle.channels:
        expected_members = [
            indicator
            for indicator in bundle.indicators
            if indicator.active
            and indicator.concept in channel.eligible_indicator_concepts
        ]
        actual_members = engine.members_for(channel.channel_id)

        assert engine.eligible_concepts(channel.channel_id) == tuple(
            channel.eligible_indicator_concepts
        )
        assert [member.indicator_id for member in actual_members] == [
            member.indicator_id for member in expected_members
        ]
        assert {member.concept for member in actual_members}.issubset(
            channel.eligible_indicator_concepts
        )


def test_engine_rejects_registry_and_archive_breadth_below_minimum() -> None:
    from seven_cycle_platform.channels.engine import (
        ChannelBreadthError,
        ChannelEngine,
    )

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="cpi_a")
    ppi = _clone_indicator(_indicator("cn_ppi"), indicator_id="ppi_a")
    invalid_registry = _channel_bundle(
        [cpi, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=3,
    )

    with pytest.raises(ChannelBreadthError, match="registry.*breadth"):
        ChannelEngine(invalid_registry)

    valid_registry = _channel_bundle(
        [cpi, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=2,
    )
    engine = ChannelEngine(valid_registry, standardization_min_periods=2)
    archive = _monthly_archive(
        [cpi],
        {cpi.indicator_id: [1.0, 2.0, 3.0, 4.0]},
    )

    with pytest.raises(ChannelBreadthError, match="data.*breadth"):
        engine.estimate(
            archive,
            as_of=date(2022, 5, 31),
            interpretation=VintageKind.REALTIME,
            strict_vintage=True,
        )


def test_visibility_uses_release_and_vintage_month_not_observation_month() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="visible_cpi")
    bundle = _channel_bundle(
        [cpi],
        concepts=("cpi",),
        minimum_breadth=1,
    )
    archive = [
        _observation(
            cpi,
            observation_date=date(2024, 1, 31),
            visible_date=date(2024, 3, 1),
            value=1.0,
        ),
        _observation(
            cpi,
            observation_date=date(2024, 2, 29),
            visible_date=date(2024, 3, 5),
            value=2.0,
        ),
        _observation(
            cpi,
            observation_date=date(2024, 2, 29),
            release_date=date(2024, 3, 5),
            visible_date=date(2024, 3, 20),
            value=3.0,
            revision_number=1,
        ),
        _observation(
            cpi,
            observation_date=date(2024, 3, 31),
            visible_date=date(2024, 4, 5),
            value=99.0,
        ),
    ]

    result = ChannelEngine(
        bundle,
        standardization_min_periods=2,
    ).estimate(
        archive,
        as_of=date(2024, 3, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )

    assert result.states["date"].tolist() == [pd.Timestamp("2024-03-31")]
    diagnostic = _last_observed_diagnostic(result)
    assert diagnostic["raw_value"] == 3.0
    assert diagnostic["observation_date"] == date(2024, 2, 29)
    assert diagnostic["revision_number"] == 1
    assert diagnostic["visible_date"] == date(2024, 3, 20)


def test_future_values_and_revisions_do_not_change_history() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="causal_cpi")
    ppi = _clone_indicator(_indicator("cn_ppi"), indicator_id="causal_ppi")
    bundle = _channel_bundle(
        [cpi, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=2,
    )
    values = {
        cpi.indicator_id: [1.0, 1.4, 1.9, 2.2, 2.8, 3.1, 3.6, 4.0, 4.4, 4.9],
        ppi.indicator_id: [0.5, 0.7, 1.1, 1.0, 1.5, 1.7, 2.0, 2.2, 2.5, 2.7],
    }
    base_archive = _monthly_archive([cpi, ppi], values)
    original = next(
        record
        for record in base_archive
        if record.entity_id == cpi.indicator_id
    )
    base_revision = _observation(
        cpi,
        observation_date=original.observation_date,
        release_date=original.release_date,
        visible_date=date(2022, 10, 15),
        value=1.2,
        revision_number=1,
    )
    perturbed_revision = base_revision.model_copy(update={"value": 200.0})
    perturbed_archive = []
    for record in base_archive:
        visible_month = pd.Timestamp(record.vintage_date) + pd.offsets.MonthEnd(0)
        if visible_month >= pd.Timestamp("2022-10-31"):
            perturbed_archive.append(record.model_copy(update={"value": record.value * 50.0}))
        else:
            perturbed_archive.append(record)

    engine = ChannelEngine(bundle, standardization_min_periods=2)
    base = engine.estimate(
        [*base_archive, base_revision],
        as_of=date(2022, 11, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    perturbed = engine.estimate(
        [*perturbed_archive, perturbed_revision],
        as_of=date(2022, 11, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )

    historical_columns = [
        "date",
        "channel_id",
        "state",
        "innovation",
        "uncertainty",
        "member_count",
        "concept_count",
        "revision_risk",
        "confidence",
        "status",
        "member_weights_json",
    ]
    base_history = base.states.loc[
        base.states["date"] <= pd.Timestamp("2022-09-30"),
        historical_columns,
    ].reset_index(drop=True)
    perturbed_history = perturbed.states.loc[
        perturbed.states["date"] <= pd.Timestamp("2022-09-30"),
        historical_columns,
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_history, perturbed_history, check_exact=True)

    base_diagnostics = base.diagnostics.loc[
        base.diagnostics["date"] <= pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    perturbed_diagnostics = perturbed.diagnostics.loc[
        perturbed.diagnostics["date"] <= pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        base_diagnostics,
        perturbed_diagnostics,
        check_exact=True,
    )
    base_future_states = base.states.loc[
        base.states["date"] > pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    perturbed_future_states = perturbed.states.loc[
        perturbed.states["date"] > pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    base_future_diagnostics = base.diagnostics.loc[
        base.diagnostics["date"] > pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    perturbed_future_diagnostics = perturbed.diagnostics.loc[
        perturbed.diagnostics["date"] > pd.Timestamp("2022-09-30")
    ].reset_index(drop=True)
    assert not base_future_states.equals(perturbed_future_states) or not (
        base_future_diagnostics.equals(perturbed_future_diagnostics)
    )


def test_same_visible_month_keeps_all_updates_and_selects_latest_observation() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="updates_cpi")
    bundle = _channel_bundle(
        [cpi],
        concepts=("cpi",),
        minimum_breadth=1,
    )
    initial = _observation(
        cpi,
        observation_date=date(2024, 1, 31),
        visible_date=date(2024, 2, 5),
        value=10.0,
    )
    new_observation = _observation(
        cpi,
        observation_date=date(2024, 2, 29),
        visible_date=date(2024, 3, 5),
        value=20.0,
    )
    old_revision = _observation(
        cpi,
        observation_date=initial.observation_date,
        release_date=initial.release_date,
        visible_date=date(2024, 3, 20),
        value=15.0,
        revision_number=1,
    )

    result = ChannelEngine(
        bundle,
        standardization_min_periods=2,
    ).estimate(
        [initial, new_observation, old_revision],
        as_of=date(2024, 3, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    diagnostic = result.diagnostics.loc[
        result.diagnostics["date"].eq(pd.Timestamp("2024-03-31"))
    ].iloc[0]
    updates = json.loads(diagnostic["updates_json"])

    assert diagnostic["raw_value"] == 20.0
    assert diagnostic["observation_date"] == date(2024, 2, 29)
    assert diagnostic["update_count"] == 2
    assert diagnostic["revision_event_count"] == 1
    assert len(updates) == 2
    assert sum(update["selected_for_state"] for update in updates) == 1
    selected = next(update for update in updates if update["selected_for_state"])
    revision = next(update for update in updates if update["revision_number"] == 1)
    assert selected["observation_date"] == "2024-02-29"
    assert selected["value"] == 20.0
    assert revision["observation_date"] == "2024-01-31"
    assert revision["revision_event_risk"] > 0.0
    assert revision["selected_for_state"] is False


def test_revision_event_risk_reduces_weight_and_confidence_immediately() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    template = _indicator("cn_cpi")
    stable = _clone_indicator(template, indicator_id="stable_member")
    revised = _clone_indicator(template, indicator_id="revised_member")
    bundle = _channel_bundle(
        [stable, revised],
        concepts=("cpi",),
        minimum_breadth=2,
    )
    values = {
        stable.indicator_id: [1.0, 1.4, 1.8, 2.2, 2.6, 3.0, 3.4, 3.8],
        revised.indicator_id: [1.0, 1.4, 1.8, 2.2, 2.6, 3.0, 3.4, 3.8],
    }
    archive = _monthly_archive([stable, revised], values)
    original = next(
        record
        for record in archive
        if record.entity_id == revised.indicator_id
        and record.observation_date == date(2022, 2, 28)
    )
    revision = _observation(
        revised,
        observation_date=original.observation_date,
        release_date=original.release_date,
        visible_date=date(2022, 9, 15),
        value=20.0,
        revision_number=1,
    )
    engine = ChannelEngine(bundle, standardization_min_periods=2)
    baseline = engine.estimate(
        archive,
        as_of=date(2022, 9, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    with_revision = engine.estimate(
        [*archive, revision],
        as_of=date(2022, 9, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    baseline_row = baseline.states.iloc[-1]
    revised_row = with_revision.states.iloc[-1]
    baseline_member = _member_payload(baseline_row)[revised.indicator_id]
    revised_member = _member_payload(revised_row)[revised.indicator_id]

    assert revised_member["revision_event_risk"] > 0.0
    assert revised_member["lagged_revision_risk"] == pytest.approx(
        baseline_member["lagged_revision_risk"]
    )
    assert revised_member["revision_risk"] > baseline_member["revision_risk"]
    assert revised_member["effective_weight"] < baseline_member["effective_weight"]
    assert revised_row["revision_risk"] > baseline_row["revision_risk"]
    assert revised_row["confidence"] < baseline_row["confidence"]


def test_real_registry_unknown_directions_start_unavailable_then_identify() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    registry = _registry()
    members = _eligible_members(registry, "inflation_prices")
    assert len(members) >= 2
    assert all(member.direction_prior is None for member in members)
    values = {
        member.indicator_id: [
            1.0,
            1.4,
            1.9,
            2.5,
            3.2,
            4.0,
            4.9,
            5.9,
            7.0,
            8.2,
        ]
        for member in members
    }
    archive = _monthly_archive(members, values)
    result = ChannelEngine(
        registry,
        standardization_min_periods=2,
    ).estimate(
        archive,
        as_of=date(2022, 11, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
        channel_ids=("inflation_prices",),
    )
    standardized_dates = result.diagnostics.loc[
        result.diagnostics["standardized_value"].notna(),
        "date",
    ]
    early_date = standardized_dates.min()
    early_diagnostics = result.diagnostics.loc[
        result.diagnostics["date"].eq(early_date)
    ]
    early_state = result.states.loc[result.states["date"].eq(early_date)].iloc[0]
    early_payload = json.loads(early_state["member_weights_json"])

    assert early_diagnostics["direction"].isna().all()
    assert not early_diagnostics["available"].any()
    assert early_diagnostics["effective_weight"].eq(0.0).all()
    assert early_state["status"] == "unavailable"
    assert all(member["direction"] is None for member in early_payload["members"])

    final_diagnostics = result.diagnostics.loc[
        result.diagnostics["date"].eq(result.states.iloc[-1]["date"])
    ]
    assert final_diagnostics["available"].sum() >= 2
    assert final_diagnostics.loc[
        final_diagnostics["available"],
        "direction",
    ].isin([-1.0, 1.0]).all()
    assert result.states.iloc[-1]["status"] == "observed"


def test_reliability_rewards_quality_low_revision_and_walk_forward_fit() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    template = _indicator("cn_cpi")
    good = _clone_indicator(
        template,
        indicator_id="good_member",
        quality_tier="A",
    )
    weak = _clone_indicator(
        template,
        indicator_id="weak_member",
        quality_tier="C",
    )
    bundle = _channel_bundle(
        [good, weak],
        concepts=("cpi",),
        minimum_breadth=2,
    )
    archive = _monthly_archive(
        [good, weak],
        {
            good.indicator_id: [float(value) for value in range(1, 17)],
            weak.indicator_id: [
                0.0,
                10.0,
                -10.0,
                12.0,
                -12.0,
                14.0,
                -14.0,
                16.0,
                -16.0,
                18.0,
                -18.0,
                20.0,
                -20.0,
                22.0,
                -22.0,
                24.0,
            ],
        },
    )
    weak_original = next(
        record
        for record in archive
        if record.entity_id == weak.indicator_id
        and record.observation_date == date(2022, 3, 31)
    )
    archive.append(
        _observation(
            weak,
            observation_date=weak_original.observation_date,
            release_date=weak_original.release_date,
            visible_date=date(2022, 10, 15),
            value=40.0,
            revision_number=1,
        )
    )

    result = ChannelEngine(
        bundle,
        standardization_min_periods=2,
    ).estimate(
        archive,
        as_of=date(2023, 5, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    final_row = result.states.iloc[-1]
    members = _member_payload(final_row)

    assert final_row["status"] == "observed"
    assert members[good.indicator_id]["quality_score"] > members[weak.indicator_id][
        "quality_score"
    ]
    assert members[good.indicator_id]["revision_risk"] < members[weak.indicator_id][
        "revision_risk"
    ]
    assert members[good.indicator_id]["walk_forward_fit"] > members[
        weak.indicator_id
    ]["walk_forward_fit"]
    assert members[good.indicator_id]["effective_weight"] > members[
        weak.indicator_id
    ]["effective_weight"]


def test_duplicate_members_do_not_amplify_concept_weight() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="base_cpi")
    ppi = _clone_indicator(_indicator("cn_ppi"), indicator_id="base_ppi")
    duplicate = _clone_indicator(cpi, indicator_id="duplicate_cpi")
    values = {
        cpi.indicator_id: [1.0, 1.4, 1.2, 1.8, 1.6, 2.2, 2.0, 2.6, 2.4, 3.0],
        ppi.indicator_id: [-1.0, -0.7, -0.4, -0.1, 0.2, 0.5, 0.8, 1.1, 1.4, 1.7],
    }
    base_bundle = _channel_bundle(
        [cpi, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=2,
    )
    duplicate_bundle = _channel_bundle(
        [cpi, duplicate, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=2,
    )
    base_archive = _monthly_archive([cpi, ppi], values)
    duplicate_archive = _monthly_archive(
        [cpi, duplicate, ppi],
        {
            **values,
            duplicate.indicator_id: values[cpi.indicator_id],
        },
    )

    base = ChannelEngine(
        base_bundle,
        standardization_min_periods=2,
    ).estimate(
        base_archive,
        as_of=date(2022, 11, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    duplicated = ChannelEngine(
        duplicate_bundle,
        standardization_min_periods=2,
    ).estimate(
        duplicate_archive,
        as_of=date(2022, 11, 30),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )

    pd.testing.assert_series_equal(
        base.states["state"],
        duplicated.states["state"],
        check_names=False,
        check_exact=True,
    )
    pd.testing.assert_series_equal(
        base.states["innovation"],
        duplicated.states["innovation"],
        check_names=False,
        check_exact=True,
    )
    base_payload = json.loads(base.states.iloc[-1]["member_weights_json"])
    duplicate_payload = json.loads(
        duplicated.states.iloc[-1]["member_weights_json"]
    )
    assert base_payload["concept_weights"] == {"cpi": 0.5, "ppi": 0.5}
    assert duplicate_payload["concept_weights"] == {"cpi": 0.5, "ppi": 0.5}
    effective_by_concept: dict[str, float] = {}
    for member in duplicate_payload["members"]:
        effective_by_concept.setdefault(member["concept"], 0.0)
        effective_by_concept[member["concept"]] += member["effective_weight"]
    assert effective_by_concept == pytest.approx({"cpi": 0.5, "ppi": 0.5})


def test_local_level_innovation_matches_hand_calculation() -> None:
    from seven_cycle_platform.channels.innovations import (
        local_level_innovations,
    )

    values = pd.Series(
        [2.0, 3.0],
        index=pd.date_range("2024-01-31", periods=2, freq="ME"),
        name="channel",
    )

    result = local_level_innovations(
        values,
        process_variance=0.0,
        observation_variance=1.0,
        initial_state=0.0,
        initial_variance=1.0,
    )

    assert result.prediction.tolist() == pytest.approx([0.0, 1.0])
    assert result.innovation.tolist() == pytest.approx([2.0, 2.0])
    assert result.state.tolist() == pytest.approx([1.0, 5.0 / 3.0])
    assert result.prediction_uncertainty.tolist() == pytest.approx(
        [np.sqrt(2.0), np.sqrt(1.5)]
    )
    assert result.uncertainty.tolist() == pytest.approx(
        [np.sqrt(0.5), np.sqrt(1.0 / 3.0)]
    )


def test_current_breadth_shortfall_is_prediction_only_not_an_innovation() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="sparse_cpi")
    ppi = _clone_indicator(_indicator("cn_ppi"), indicator_id="sparse_ppi")
    bundle = _channel_bundle(
        [cpi, ppi],
        concepts=("cpi", "ppi"),
        minimum_breadth=2,
    )
    archive = _monthly_archive(
        [cpi, ppi],
        {
            cpi.indicator_id: [1.0, 1.2, 1.5, 1.7, 2.0, 2.2],
            ppi.indicator_id: [0.5, 0.7, 0.9, 1.0, 1.2, 1.4],
        },
    )
    archive.append(
        _observation(
            cpi,
            observation_date=date(2022, 7, 31),
            visible_date=date(2022, 8, 5),
            value=2.5,
        )
    )

    result = ChannelEngine(
        bundle,
        standardization_min_periods=2,
    ).estimate(
        archive,
        as_of=date(2022, 8, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )

    first = result.states.iloc[0]
    previous = result.states.iloc[-2]
    final = result.states.iloc[-1]
    assert first["status"] == "unavailable"
    assert pd.isna(first["state"])
    assert pd.isna(first["innovation"])
    assert pd.isna(first["uncertainty"])
    assert first["confidence"] == 0.0
    assert previous["status"] == "observed"
    assert final["status"] == "prediction_only"
    assert final["member_count"] == 1
    assert final["concept_count"] == 1
    assert np.isfinite(final["state"])
    assert pd.isna(final["innovation"])
    assert np.isfinite(final["uncertainty"])
    assert final["confidence"] < previous["confidence"]
    assert "minimum_breadth" in final["status_reason"]


def test_vintage_interpretations_and_strict_selection_are_explicit() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="vintage_cpi")
    bundle = _channel_bundle(
        [cpi],
        concepts=("cpi",),
        minimum_breadth=1,
    )
    realtime = _monthly_archive(
        [cpi],
        {cpi.indicator_id: [1.0, 2.0, 3.0, 4.0]},
        vintage_kind=VintageKind.REALTIME,
    )
    latest = _monthly_archive(
        [cpi],
        {cpi.indicator_id: [10.0, 20.0, 30.0, 40.0]},
        vintage_kind=VintageKind.LATEST_HISTORICAL,
    )
    pseudo = _monthly_archive(
        [cpi],
        {cpi.indicator_id: [100.0, 200.0, 300.0, 400.0]},
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
    )
    engine = ChannelEngine(bundle, standardization_min_periods=2)

    realtime_result = engine.estimate(
        [*realtime, *latest, *pseudo],
        as_of=date(2022, 5, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    latest_result = engine.estimate(
        [*realtime, *latest, *pseudo],
        as_of=date(2022, 5, 31),
        interpretation=VintageKind.LATEST_HISTORICAL,
        strict_vintage=True,
    )
    pseudo_result = engine.estimate(
        [*realtime, *latest, *pseudo],
        as_of=date(2022, 5, 31),
        interpretation=VintageKind.PSEUDO_VINTAGE,
        strict_vintage=False,
    )

    assert _last_observed_diagnostic(realtime_result)["raw_value"] == 4.0
    assert _last_observed_diagnostic(latest_result)["raw_value"] == 40.0
    assert _last_observed_diagnostic(pseudo_result)["raw_value"] == 400.0
    assert set(realtime_result.states["vintage_kind"]) == {"realtime"}
    assert set(latest_result.states["vintage_kind"]) == {"latest_historical"}
    assert set(pseudo_result.states["vintage_kind"]) == {"pseudo_vintage"}

    with pytest.raises(ValueError, match="strict vintage.*pseudo_vintage"):
        engine.estimate(
            pseudo,
            as_of=date(2022, 5, 31),
            interpretation=VintageKind.REALTIME,
            strict_vintage=True,
        )

    fallback = engine.estimate(
        pseudo,
        as_of=date(2022, 5, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=False,
    )
    assert set(fallback.states["vintage_kind"]) == {"pseudo_vintage"}


def test_estimate_outputs_and_diagnostics_are_defensive_copies() -> None:
    from seven_cycle_platform.channels.engine import ChannelEngine

    cpi = _clone_indicator(_indicator("cn_cpi"), indicator_id="copy_cpi")
    bundle = _channel_bundle(
        [cpi],
        concepts=("cpi",),
        minimum_breadth=1,
    )
    archive = _monthly_archive(
        [cpi],
        {cpi.indicator_id: [1.0, 2.0, 3.0, 4.0]},
    )
    result = ChannelEngine(
        bundle,
        standardization_min_periods=2,
    ).estimate(
        archive,
        as_of=date(2022, 5, 31),
        interpretation=VintageKind.REALTIME,
        strict_vintage=True,
    )
    states = result.states
    diagnostics = result.diagnostics
    original_state = result.states.iloc[-1]["state"]
    original_raw = result.diagnostics.iloc[-1]["raw_value"]

    states.loc[states.index[-1], "state"] = 999.0
    diagnostics.loc[diagnostics.index[-1], "raw_value"] = 999.0

    assert result.states.iloc[-1]["state"] == original_state
    assert result.diagnostics.iloc[-1]["raw_value"] == original_raw


def test_channel_state_product_schema_provenance_and_validation() -> None:
    from seven_cycle_platform.contracts.arrow import CHANNEL_STATE_SCHEMA
    from seven_cycle_platform.products.channel_state import (
        build_channel_state,
        validate_channel_state,
    )

    expected_types = {
        "date": pa.date32(),
        "channel_id": pa.string(),
        "state": pa.float64(),
        "innovation": pa.float64(),
        "uncertainty": pa.float64(),
        "member_count": pa.int32(),
        "concept_count": pa.int32(),
        "revision_risk": pa.float64(),
        "vintage_kind": pa.string(),
        "confidence": pa.float64(),
        "status": pa.string(),
        "status_reason": pa.string(),
        "member_weights_json": pa.string(),
        "run_id": pa.string(),
        "as_of": pa.date32(),
        "data_vintage": pa.date32(),
        "model_version": pa.string(),
        "config_hash": pa.string(),
        "created_at": pa.timestamp("us", tz="UTC"),
    }
    assert CHANNEL_STATE_SCHEMA.names == [
        *CHANNEL_STATE_FIELDS,
        *PROVENANCE_FIELDS,
    ]
    assert {
        field.name: field.type for field in CHANNEL_STATE_SCHEMA
    } == expected_types

    context = _context()
    registry = _registry()
    states = _product_state_frame(registry).iloc[::-1].reset_index(drop=True)
    states_before = states.copy(deep=True)
    product = build_channel_state(states, context=context, registry=registry)
    repeated = build_channel_state(states, context=context, registry=registry)

    pd.testing.assert_frame_equal(states, states_before, check_exact=True)
    pd.testing.assert_frame_equal(product, repeated, check_exact=True)
    assert list(product.columns) == [*CHANNEL_STATE_FIELDS, *PROVENANCE_FIELDS]
    assert not product.duplicated(
        ["date", "channel_id", "vintage_kind"]
    ).any()
    assert product["run_id"].eq(context.run_id).all()
    assert product["as_of"].eq(context.as_of).all()
    assert product["data_vintage"].eq(context.data_vintage).all()
    assert product["model_version"].eq(context.model_version).all()
    assert product["config_hash"].eq(context.config_hash).all()
    assert product["created_at"].eq(context.created_at).all()
    validate_channel_state(product, context=context, registry=registry)

    duplicated = pd.concat([states, states.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="date.*channel_id.*vintage_kind.*unique"):
        build_channel_state(duplicated, context=context, registry=registry)

    injected = states.assign(run_id="caller-controlled")
    with pytest.raises(ValueError, match="provenance.*RunContext"):
        build_channel_state(injected, context=context, registry=registry)

    malformed = states.copy(deep=True)
    prediction_row = malformed["status"].eq("prediction_only")
    malformed.loc[prediction_row, "innovation"] = 1.0
    with pytest.raises(ValueError, match="prediction_only.*innovation"):
        build_channel_state(malformed, context=context, registry=registry)


@pytest.mark.parametrize(
    "vintage",
    [VintageKind.EXPLICIT_PROXY, VintageKind.UNAVAILABLE],
)
def test_channel_state_product_rejects_data_identity_vintages(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.products.channel_state import build_channel_state

    registry = _registry()
    states = _product_state_frame(registry).assign(vintage_kind=vintage.value)

    with pytest.raises(
        ValueError,
        match=rf"channel_state product.*{vintage.value}",
    ):
        build_channel_state(states, context=_context(), registry=registry)


def test_channel_state_product_rejects_unknown_channel_and_low_observed_breadth() -> None:
    from seven_cycle_platform.products.channel_state import build_channel_state

    registry = _registry()
    context = _context()
    states = _product_state_frame(registry)

    unknown = states.iloc[[0]].assign(channel_id="unknown_channel")
    with pytest.raises(ValueError, match="unknown channel_id"):
        build_channel_state(unknown, context=context, registry=registry)

    low_breadth = states.iloc[[0]].copy(deep=True)
    available_id = next(
        member.indicator_id
        for member in _eligible_members(registry, "inflation_prices")
        if member.concept == "cpi"
    )
    low_breadth["member_count"] = 1
    low_breadth["concept_count"] = 1
    low_breadth["member_weights_json"] = _weights_json(
        registry,
        available_ids={available_id},
    )
    with pytest.raises(ValueError, match="minimum_breadth"):
        build_channel_state(low_breadth, context=context, registry=registry)


def test_channel_state_product_rejects_malformed_or_unconserved_weights() -> None:
    from seven_cycle_platform.products.channel_state import build_channel_state

    registry = _registry()
    context = _context()
    states = _product_state_frame(registry).iloc[[0]].copy(deep=True)

    malformed = states.copy(deep=True)
    malformed["member_weights_json"] = json.dumps({"foo": "bar"})
    with pytest.raises(ValueError, match="member_weights_json.*keys"):
        build_channel_state(malformed, context=context, registry=registry)

    unconserved = states.copy(deep=True)
    payload = json.loads(unconserved.iloc[0]["member_weights_json"])
    available_member = next(
        member for member in payload["members"] if member["available"]
    )
    available_member["effective_weight"] += 0.2
    unconserved["member_weights_json"] = json.dumps(payload)
    with pytest.raises(ValueError, match="effective_weight"):
        build_channel_state(unconserved, context=context, registry=registry)

    unknown_direction = states.copy(deep=True)
    payload = json.loads(unknown_direction.iloc[0]["member_weights_json"])
    available_member = next(
        member for member in payload["members"] if member["available"]
    )
    available_member["direction"] = None
    unknown_direction["member_weights_json"] = json.dumps(payload)
    with pytest.raises(ValueError, match="available.*direction"):
        build_channel_state(
            unknown_direction,
            context=context,
            registry=registry,
        )

    inconsistent_risk = states.copy(deep=True)
    payload = json.loads(inconsistent_risk.iloc[0]["member_weights_json"])
    available_member = next(
        member for member in payload["members"] if member["available"]
    )
    available_member["revision_event_risk"] = 0.9
    available_member["lagged_revision_risk"] = 0.1
    available_member["revision_risk"] = 0.1
    inconsistent_risk["member_weights_json"] = json.dumps(payload)
    with pytest.raises(ValueError, match="revision_risk.*max"):
        build_channel_state(
            inconsistent_risk,
            context=context,
            registry=registry,
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_channel_state_product_rejects_missing_or_duplicate_members(
    mutation: str,
) -> None:
    from seven_cycle_platform.products.channel_state import build_channel_state

    registry = _registry()
    context = _context()
    states = _product_state_frame(registry).iloc[[0]].copy(deep=True)
    payload = json.loads(states.iloc[0]["member_weights_json"])
    if mutation == "missing":
        payload["members"].pop()
    else:
        payload["members"].append(payload["members"][0].copy())
    states["member_weights_json"] = json.dumps(payload)

    with pytest.raises(ValueError, match="members.*eligible|entity_id.*unique"):
        build_channel_state(states, context=context, registry=registry)


def test_channel_state_writer_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.contracts.arrow import CHANNEL_STATE_SCHEMA
    from seven_cycle_platform.products.channel_state import (
        CHANNEL_STATE_FILENAME,
        build_channel_state,
        write_channel_state,
    )

    context = _context()
    registry = _registry()
    product = build_channel_state(
        _product_state_frame(registry),
        context=context,
        registry=registry,
    )
    shuffled = product.sample(frac=1.0, random_state=19).reset_index(drop=True)
    shuffled_before = shuffled.copy(deep=True)
    first_run_dir = tmp_path / "first" / context.run_id
    second_run_dir = tmp_path / "second" / context.run_id
    first_run_dir.mkdir(parents=True)
    second_run_dir.mkdir(parents=True)

    first_path = write_channel_state(
        first_run_dir,
        product,
        context=context,
        registry=registry,
    )
    second_path = write_channel_state(
        second_run_dir,
        shuffled,
        context=context,
        registry=registry,
    )

    pd.testing.assert_frame_equal(shuffled, shuffled_before, check_exact=True)
    assert first_path == first_run_dir / CHANNEL_STATE_FILENAME
    assert first_path.read_bytes() == second_path.read_bytes()
    assert pq.read_schema(first_path) == CHANNEL_STATE_SCHEMA
    persisted = pd.read_parquet(first_path)
    assert list(persisted.columns) == [
        *CHANNEL_STATE_FIELDS,
        *PROVENANCE_FIELDS,
    ]
    with pytest.raises(FileExistsError, match="refuse.*overwrite"):
        write_channel_state(
            first_run_dir,
            product,
            context=context,
            registry=registry,
        )
