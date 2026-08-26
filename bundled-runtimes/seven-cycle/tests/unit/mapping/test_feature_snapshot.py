from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from importlib import import_module
import math
from types import ModuleType

import pytest

from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


AS_OF = date(2024, 6, 30)
OBSERVATION_DATE = date(2024, 6, 1)
RELEASE_DATE = date(2024, 6, 5)
VINTAGE_DATE = date(2024, 6, 6)


def _api() -> ModuleType:
    return import_module("seven_cycle_platform.mapping.features")


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_context(
    *,
    as_of: date = AS_OF,
    data_vintage: date | None = None,
) -> RunContext:
    return RunContext.create(
        as_of=as_of,
        data_vintage=data_vintage or as_of,
        model_version="feature-snapshot-v1",
        config={"mapping": "current", "as_of": as_of.isoformat()},
        input_checksums={"feature-inputs.json": _checksum(b"feature-inputs")},
        quality_summary={"failed": 0, "passed": 1},
        created_at=datetime(2026, 7, 13, 4, 30, tzinfo=timezone.utc),
    )


def _drift(
    api: ModuleType,
    *,
    detected: bool = False,
    evaluated_at: date = VINTAGE_DATE,
    score: float = 0.12,
    threshold: float = 0.50,
) -> object:
    return api.StructuralDriftFlag(
        detected=detected,
        score=score,
        threshold=threshold,
        method="rolling_population_stability_index",
        baseline_id="feature-baseline-v1",
        evaluated_at=evaluated_at,
        reason="threshold exceeded" if detected else "within threshold",
    )


def _feature(
    api: ModuleType,
    *,
    kind: object,
    feature_id: str,
    entity_id: str | None = None,
    values: dict[str, object] | None = None,
    observation_date: date = OBSERVATION_DATE,
    release_date: date = RELEASE_DATE,
    vintage_date: date = VINTAGE_DATE,
    vintage_kind: VintageKind = VintageKind.REALTIME,
    vintage_caveat: str | None = None,
    max_observation_age_days: int = 45,
    max_visible_age_days: int = 45,
    drift: object | None = None,
) -> object:
    payload = api.FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values=values or {"value": 0.25},
    )
    provenance = api.FeatureProvenance.from_payload(
        payload,
        observation_date=observation_date,
        release_date=release_date,
        vintage_date=vintage_date,
        source="unit-test-archive",
        unit="score",
        retrieval_time=datetime.combine(
            max(vintage_date, date(2024, 6, 7)),
            time(12),
            tzinfo=timezone.utc,
        ),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=vintage_kind,
        methodology="point_in_time_fixture",
        vintage_caveat=vintage_caveat,
    )
    return api.FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=api.FreshnessPolicy(
            max_observation_age_days=max_observation_age_days,
            max_visible_age_days=max_visible_age_days,
        ),
        structural_drift=drift or _drift(api),
    )


def _groups(api: ModuleType) -> dict[str, tuple[object, ...]]:
    cycle_states = tuple(
        _feature(
            api,
            kind=api.FeatureKind.CYCLE,
            feature_id=f"C{position}",
            values={
                "level": position / 10.0,
                "phase": "expansion",
                "confidence": 0.80,
            },
        )
        for position in range(1, 8)
    )
    return {
        "cycle_states": cycle_states,
        "channel_states": (
            _feature(
                api,
                kind=api.FeatureKind.CHANNEL,
                feature_id="growth_transmission",
                values={"state": 0.40, "innovation": 0.08},
            ),
        ),
        "valuation_controls": (
            _feature(
                api,
                kind=api.FeatureKind.VALUATION,
                feature_id="forward_pe",
                entity_id="asset_alpha",
                values={"z_score": -0.35},
            ),
        ),
        "earnings_controls": (
            _feature(
                api,
                kind=api.FeatureKind.EARNINGS,
                feature_id="earnings_revision",
                entity_id="asset_alpha",
                values={"revision_breadth": 0.22},
            ),
        ),
        "positioning_controls": (
            _feature(
                api,
                kind=api.FeatureKind.POSITIONING,
                feature_id="fund_positioning",
                entity_id="asset_alpha",
                values={"percentile": 0.61},
            ),
        ),
        "liquidity_controls": (
            _feature(
                api,
                kind=api.FeatureKind.LIQUIDITY,
                feature_id="market_liquidity",
                entity_id="asset_alpha",
                values={"impulse": -0.18},
            ),
        ),
        "event_scenarios": (
            _feature(
                api,
                kind=api.FeatureKind.EVENT,
                feature_id="policy_surprise",
                entity_id="asset_alpha",
                values={"probability": 0.20, "shock": -0.45},
            ),
        ),
        "historical_posterior": (
            _feature(
                api,
                kind=api.FeatureKind.HISTORICAL_POSTERIOR,
                feature_id="asset_alpha_posterior",
                entity_id="asset_alpha",
                values={
                    "coefficients": {"growth_transmission": 0.42},
                    "covariance": [[0.08]],
                },
            ),
        ),
    }


def _snapshot(
    api: ModuleType,
    *,
    as_of: date = AS_OF,
    groups: dict[str, tuple[object, ...]] | None = None,
    run_context: RunContext | None = None,
) -> object:
    return api.CurrentFeatureSnapshot(
        as_of=as_of,
        run_context=run_context or _run_context(as_of=as_of),
        **(groups or _groups(api)),
    )


def _replace_group_feature(
    groups: dict[str, tuple[object, ...]],
    field_name: str,
    replacement: object,
) -> None:
    if field_name == "cycle_states":
        groups[field_name] = tuple(
            replacement if feature.payload.feature_id == "C3" else feature
            for feature in groups[field_name]
        )
    else:
        groups[field_name] = (replacement,)


def test_current_snapshot_contains_every_required_group_and_auditable_flags() -> None:
    api = _api()
    snapshot = _snapshot(api)

    assert [feature.feature_id for feature in snapshot.cycle_states] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert [feature.feature_id for feature in snapshot.channel_states] == [
        "growth_transmission"
    ]
    assert set(snapshot.asset_controls) == {
        api.FeatureKind.VALUATION,
        api.FeatureKind.EARNINGS,
        api.FeatureKind.POSITIONING,
        api.FeatureKind.LIQUIDITY,
    }
    assert len(snapshot.event_scenarios) == 1
    assert len(snapshot.historical_posterior) == 1

    assert set(snapshot.freshness) == {feature.key for feature in snapshot.features}
    assert set(snapshot.structural_drift) == {
        feature.key for feature in snapshot.features
    }
    assert set(snapshot.provenance.features) == {
        feature.key for feature in snapshot.features
    }
    for feature in snapshot.features:
        assert isinstance(feature, api.CurrentFeature)
        assert feature.freshness.as_of == AS_OF
        assert feature.freshness.observation_age_days == 29
        assert feature.freshness.visible_age_days == 24
        assert feature.freshness.status is api.FreshnessStatus.FRESH
        assert feature.freshness.is_fresh is True
        assert feature.structural_drift.method
        assert feature.structural_drift.baseline_id
        assert feature.structural_drift.reason
        assert snapshot.freshness[feature.key] == feature.freshness
        assert snapshot.structural_drift[feature.key] == feature.structural_drift
        assert snapshot.provenance.features[feature.key] == feature.provenance

    assert snapshot.provenance.run_id == snapshot.run_context.run_id
    assert snapshot.provenance.as_of == AS_OF
    assert snapshot.provenance.data_vintage == AS_OF
    assert snapshot.provenance.model_version == "feature-snapshot-v1"
    assert snapshot.provenance.input_checksums


def test_freshness_uses_observation_and_visible_dates_per_feature() -> None:
    api = _api()
    groups = _groups(api)
    old_observation = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="old_observation",
        observation_date=date(2024, 5, 1),
        release_date=date(2024, 6, 29),
        vintage_date=date(2024, 6, 29),
        max_observation_age_days=30,
        max_visible_age_days=3,
    )
    old_visibility = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="old_visibility",
        observation_date=date(2024, 6, 20),
        release_date=date(2024, 6, 25),
        vintage_date=date(2024, 6, 25),
        max_observation_age_days=20,
        max_visible_age_days=2,
    )
    groups["channel_states"] = (old_observation, old_visibility)

    snapshot = _snapshot(api, groups=groups)
    by_id = {feature.feature_id: feature for feature in snapshot.channel_states}

    observation_flag = by_id["old_observation"].freshness
    assert observation_flag.observation_age_days == 60
    assert observation_flag.visible_age_days == 1
    assert observation_flag.status is api.FreshnessStatus.STALE
    assert observation_flag.reasons == ("observation_age_exceeded",)

    visibility_flag = by_id["old_visibility"].freshness
    assert visibility_flag.observation_age_days == 10
    assert visibility_flag.visible_age_days == 5
    assert visibility_flag.status is api.FreshnessStatus.STALE
    assert visibility_flag.reasons == ("visible_age_exceeded",)


@pytest.mark.parametrize(
    ("kind_name", "field_name"),
    [
        ("CYCLE", "cycle_states"),
        ("CHANNEL", "channel_states"),
        ("VALUATION", "valuation_controls"),
        ("EARNINGS", "earnings_controls"),
        ("POSITIONING", "positioning_controls"),
        ("LIQUIDITY", "liquidity_controls"),
        ("EVENT", "event_scenarios"),
        ("HISTORICAL_POSTERIOR", "historical_posterior"),
    ],
)
@pytest.mark.parametrize("future_field", ["release_date", "vintage_date"])
def test_snapshot_rejects_every_future_release_or_vintage_without_filtering(
    kind_name: str,
    field_name: str,
    future_field: str,
) -> None:
    api = _api()
    groups = _groups(api)
    kind = getattr(api.FeatureKind, kind_name)
    feature_id = "C3" if field_name == "cycle_states" else f"future_{kind.value}"
    dates = {
        "observation_date": date(2024, 6, 1),
        "release_date": AS_OF,
        "vintage_date": AS_OF,
    }
    dates[future_field] = AS_OF + timedelta(days=1)
    if future_field == "release_date":
        dates["vintage_date"] = dates["release_date"]
    replacement = _feature(
        api,
        kind=kind,
        feature_id=feature_id,
        entity_id=None
        if kind in {api.FeatureKind.CYCLE, api.FeatureKind.CHANNEL}
        else "asset_beta",
        **dates,
        drift=_drift(api, evaluated_at=AS_OF),
    )
    _replace_group_feature(groups, field_name, replacement)

    with pytest.raises(ValueError, match=rf"{future_field}.*as_of"):
        _snapshot(api, groups=groups)


def test_snapshot_rejects_future_observation_date_too() -> None:
    api = _api()
    groups = _groups(api)
    future = AS_OF + timedelta(days=1)
    replacement = _feature(
        api,
        kind=api.FeatureKind.EVENT,
        feature_id="future_event_observation",
        entity_id="asset_beta",
        observation_date=future,
        release_date=future,
        vintage_date=future,
        drift=_drift(api, evaluated_at=AS_OF),
    )
    groups["event_scenarios"] = (replacement,)

    with pytest.raises(ValueError, match=r"observation_date.*as_of"):
        _snapshot(api, groups=groups)


def test_snapshot_requires_exactly_c1_through_c7() -> None:
    api = _api()
    groups = _groups(api)
    groups["cycle_states"] = groups["cycle_states"][:-1]

    with pytest.raises(ValueError, match=r"exactly C1-C7.*missing C7"):
        _snapshot(api, groups=groups)

    groups = _groups(api)
    groups["cycle_states"] += (
        _feature(
            api,
            kind=api.FeatureKind.CYCLE,
            feature_id="C8",
        ),
    )
    with pytest.raises(ValueError, match=r"exactly C1-C7.*unexpected C8"):
        _snapshot(api, groups=groups)


def test_snapshot_rejects_duplicate_cycle_id_across_entity_scopes() -> None:
    api = _api()
    groups = _groups(api)
    groups["cycle_states"] += (
        _feature(
            api,
            kind=api.FeatureKind.CYCLE,
            feature_id="C1",
            entity_id="alternate_scope",
        ),
    )

    with pytest.raises(ValueError, match=r"exactly C1-C7.*duplicate C1"):
        _snapshot(api, groups=groups)


@pytest.mark.parametrize(
    "field_name",
    [
        "channel_states",
        "valuation_controls",
        "earnings_controls",
        "positioning_controls",
        "liquidity_controls",
        "event_scenarios",
        "historical_posterior",
    ],
)
def test_snapshot_requires_every_non_cycle_feature_group(field_name: str) -> None:
    api = _api()
    groups = _groups(api)
    groups[field_name] = ()

    with pytest.raises(ValueError, match=rf"{field_name}.*at least one"):
        _snapshot(api, groups=groups)


def test_snapshot_rejects_duplicate_features_wrong_categories_and_missing_asset_ids() -> (
    None
):
    api = _api()
    groups = _groups(api)
    channel = groups["channel_states"][0]
    groups["channel_states"] = (channel, channel)

    with pytest.raises(ValueError, match=r"duplicate feature.*growth_transmission"):
        _snapshot(api, groups=groups)

    groups = _groups(api)
    groups["valuation_controls"] = (
        _feature(
            api,
            kind=api.FeatureKind.EARNINGS,
            feature_id="wrong_category",
            entity_id="asset_alpha",
        ),
    )
    with pytest.raises(ValueError, match=r"valuation_controls.*VALUATION"):
        _snapshot(api, groups=groups)

    groups = _groups(api)
    groups["liquidity_controls"] = (
        _feature(
            api,
            kind=api.FeatureKind.LIQUIDITY,
            feature_id="missing_asset_id",
        ),
    )
    with pytest.raises(ValueError, match=r"liquidity_controls.*entity_id"):
        _snapshot(api, groups=groups)


def test_input_types_and_enums_are_strict() -> None:
    api = _api()

    with pytest.raises(TypeError, match=r"as_of must be a date"):
        _snapshot(
            api,
            as_of=datetime(2024, 6, 30),
            run_context=_run_context(),
        )
    with pytest.raises(TypeError, match=r"run_context must be a RunContext"):
        api.CurrentFeatureSnapshot(
            as_of=AS_OF,
            run_context={"as_of": AS_OF},
            **_groups(api),
        )
    with pytest.raises(TypeError, match=r"kind must be a FeatureKind"):
        api.FeaturePayload(
            kind="cycle",
            feature_id="C1",
            values={"level": 0.1},
        )
    valid = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="strict_vintage",
    )
    with pytest.raises(TypeError, match=r"vintage_kind must be a VintageKind"):
        replace(valid.provenance, vintage_kind="realtime")
    with pytest.raises(TypeError, match=r"detected must be a boolean"):
        api.StructuralDriftFlag(
            detected=1,
            score=0.1,
            threshold=0.5,
            method="psi",
            baseline_id="baseline",
            evaluated_at=AS_OF,
            reason="stable",
        )
    with pytest.raises(TypeError, match=r"max_observation_age_days.*integer"):
        api.FreshnessPolicy(
            max_observation_age_days=True,
            max_visible_age_days=5,
        )
    with pytest.raises(TypeError, match=r"channel_states.*iterable"):
        api.CurrentFeatureSnapshot(
            as_of=AS_OF,
            run_context=_run_context(),
            **{**_groups(api), "channel_states": "growth_transmission"},
        )


@pytest.mark.parametrize(
    "values",
    [
        {"value": math.nan},
        {"value": math.inf},
        {"nested": {"value": -math.inf}},
    ],
)
def test_non_finite_payload_values_are_rejected(values: dict[str, object]) -> None:
    api = _api()

    with pytest.raises(ValueError, match=r"payload.*finite"):
        api.FeaturePayload(
            kind=api.FeatureKind.CHANNEL,
            feature_id="non_finite",
            values=values,
        )


def test_payload_digest_distinguishes_date_from_mapping_shape() -> None:
    api = _api()
    date_payload = api.FeaturePayload(
        kind=api.FeatureKind.CHANNEL,
        feature_id="typed_digest",
        values={"v": date(2024, 1, 2)},
    )
    mapping_payload = api.FeaturePayload(
        kind=api.FeatureKind.CHANNEL,
        feature_id="typed_digest",
        values={"v": {"date": "2024-01-02"}},
    )

    assert date_payload.payload_digest != mapping_payload.payload_digest


@pytest.mark.parametrize("field_name", ["score", "threshold"])
def test_non_finite_structural_drift_values_are_rejected(field_name: str) -> None:
    api = _api()
    values = {"score": 0.1, "threshold": 0.5}
    values[field_name] = math.nan

    with pytest.raises(ValueError, match=rf"{field_name}.*finite"):
        api.StructuralDriftFlag(
            detected=False,
            method="psi",
            baseline_id="baseline",
            evaluated_at=AS_OF,
            reason="stable",
            **values,
        )


def test_payload_and_provenance_identity_and_digest_must_match() -> None:
    api = _api()
    payload = api.FeaturePayload(
        kind=api.FeatureKind.CHANNEL,
        feature_id="growth_transmission",
        values={"state": 0.4},
    )
    different_payload = api.FeaturePayload(
        kind=api.FeatureKind.CHANNEL,
        feature_id="growth_transmission",
        values={"state": 0.9},
    )
    provenance = api.FeatureProvenance.from_payload(
        different_payload,
        observation_date=OBSERVATION_DATE,
        release_date=RELEASE_DATE,
        vintage_date=VINTAGE_DATE,
        source="unit-test-archive",
        unit="score",
        retrieval_time=datetime(2024, 6, 7, tzinfo=timezone.utc),
        revision_number=0,
        quality_status="accepted",
        vintage_kind=VintageKind.REALTIME,
        methodology="fixture",
    )

    with pytest.raises(ValueError, match=r"payload digest.*provenance"):
        api.FeatureInput(
            payload=payload,
            provenance=provenance,
            freshness_policy=api.FreshnessPolicy(
                max_observation_age_days=30,
                max_visible_age_days=30,
            ),
            structural_drift=_drift(api),
        )

    valid = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="identity_source",
    )
    mismatched = replace(valid.provenance, feature_id="identity_other")
    with pytest.raises(ValueError, match=r"payload identity.*provenance"):
        api.FeatureInput(
            payload=valid.payload,
            provenance=mismatched,
            freshness_policy=valid.freshness_policy,
            structural_drift=valid.structural_drift,
        )


def test_snapshot_and_run_provenance_must_agree() -> None:
    api = _api()

    with pytest.raises(ValueError, match=r"run_context as_of.*snapshot as_of"):
        _snapshot(
            api,
            run_context=_run_context(as_of=AS_OF - timedelta(days=1)),
        )
    with pytest.raises(ValueError, match=r"data_vintage.*as_of"):
        _snapshot(
            api,
            run_context=_run_context(
                data_vintage=AS_OF + timedelta(days=1),
            ),
        )


def test_snapshot_rejects_feature_vintage_after_run_data_vintage() -> None:
    api = _api()

    with pytest.raises(
        ValueError,
        match=(
            r"cycle:C1.*vintage_date 2024-06-06.*"
            r"data_vintage 2024-06-05"
        ),
    ):
        _snapshot(
            api,
            run_context=_run_context(data_vintage=date(2024, 6, 5)),
        )


def test_structural_drift_evaluation_cannot_come_from_the_future() -> None:
    api = _api()
    groups = _groups(api)
    groups["valuation_controls"] = (
        _feature(
            api,
            kind=api.FeatureKind.VALUATION,
            feature_id="future_drift_evaluation",
            entity_id="asset_alpha",
            drift=_drift(
                api,
                evaluated_at=AS_OF + timedelta(days=1),
            ),
        ),
    )

    with pytest.raises(ValueError, match=r"structural drift evaluated_at.*as_of"):
        _snapshot(api, groups=groups)


def test_realtime_and_pseudo_vintage_remain_distinguishable() -> None:
    api = _api()
    realtime = _snapshot(api)

    assert realtime.contains_pseudo_vintage is False
    assert realtime.provenance.vintage_kinds == (VintageKind.REALTIME,)
    assert realtime.provenance.pseudo_vintage_features == ()
    assert all(not feature.is_pseudo_vintage for feature in realtime.features)

    groups = _groups(api)
    pseudo = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="legacy_credit_channel",
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
        vintage_caveat=(
            "release history reconstructed from a governed publication lag"
        ),
    )
    groups["channel_states"] = (pseudo,)
    pseudo_snapshot = _snapshot(api, groups=groups)
    current = pseudo_snapshot.channel_states[0]

    assert current.provenance.vintage_kind is VintageKind.PSEUDO_VINTAGE
    assert current.provenance.vintage_caveat
    assert current.is_pseudo_vintage is True
    assert current.flags.is_pseudo_vintage is True
    assert pseudo_snapshot.contains_pseudo_vintage is True
    assert VintageKind.PSEUDO_VINTAGE in pseudo_snapshot.provenance.vintage_kinds
    assert pseudo_snapshot.provenance.pseudo_vintage_features == (current.key,)
    assert pseudo_snapshot.provenance.features[current.key].vintage_caveat

    with pytest.raises(ValueError, match=r"pseudo_vintage.*caveat"):
        _feature(
            api,
            kind=api.FeatureKind.CHANNEL,
            feature_id="hidden_pseudo",
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
        )


def test_inputs_are_defensively_copied_and_results_are_immutable() -> None:
    api = _api()
    source_values = {
        "state": 0.4,
        "nested": {"weights": [0.25, 0.75]},
    }
    channel = _feature(
        api,
        kind=api.FeatureKind.CHANNEL,
        feature_id="immutable_channel",
        values=source_values,
    )
    source_values["state"] = 99.0
    source_values["nested"]["weights"][0] = 99.0

    assert channel.payload.values["state"] == 0.4
    assert channel.payload.values["nested"]["weights"] == (0.25, 0.75)
    with pytest.raises(TypeError):
        channel.payload.values["state"] = 1.0

    groups = _groups(api)
    channel_inputs = [channel]
    groups["channel_states"] = channel_inputs
    snapshot = _snapshot(api, groups=groups)
    channel_inputs.append(
        _feature(
            api,
            kind=api.FeatureKind.CHANNEL,
            feature_id="late_append",
        )
    )

    assert [feature.feature_id for feature in snapshot.channel_states] == [
        "immutable_channel"
    ]
    with pytest.raises(FrozenInstanceError):
        snapshot.as_of = date(2024, 7, 1)
    with pytest.raises(TypeError):
        snapshot.provenance.features[snapshot.features[0].key] = snapshot.features[
            0
        ].provenance


def test_provenance_dates_and_retrieval_time_are_strict() -> None:
    api = _api()
    payload = api.FeaturePayload(
        kind=api.FeatureKind.CHANNEL,
        feature_id="temporal_provenance",
        values={"state": 0.4},
    )
    common = {
        "source": "unit-test-archive",
        "unit": "score",
        "revision_number": 0,
        "quality_status": "accepted",
        "vintage_kind": VintageKind.REALTIME,
        "methodology": "fixture",
    }

    with pytest.raises(ValueError, match=r"release_date cannot precede"):
        api.FeatureProvenance.from_payload(
            payload,
            observation_date=RELEASE_DATE,
            release_date=OBSERVATION_DATE,
            vintage_date=VINTAGE_DATE,
            retrieval_time=datetime(2024, 6, 7, tzinfo=timezone.utc),
            **common,
        )
    with pytest.raises(ValueError, match=r"vintage_date cannot precede"):
        api.FeatureProvenance.from_payload(
            payload,
            observation_date=OBSERVATION_DATE,
            release_date=VINTAGE_DATE,
            vintage_date=RELEASE_DATE,
            retrieval_time=datetime(2024, 6, 7, tzinfo=timezone.utc),
            **common,
        )
    with pytest.raises(ValueError, match=r"retrieval_time must be timezone-aware"):
        api.FeatureProvenance.from_payload(
            payload,
            observation_date=OBSERVATION_DATE,
            release_date=RELEASE_DATE,
            vintage_date=VINTAGE_DATE,
            retrieval_time=datetime(2024, 6, 7),
            **common,
        )
