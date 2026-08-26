from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import warnings

import duckdb
import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.assets import LEGACY_CORE_ASSET_MAP
from seven_cycle_platform.catalog.duckdb import build_catalog
from seven_cycle_platform.cycles.phase import phase_from_level_slope
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.products.asset_attribution import (
    ASSET_ATTRIBUTION_COLUMNS,
    ASSET_ATTRIBUTION_CONSERVATION_COLUMNS,
    validate_asset_attribution,
)
from seven_cycle_platform.legacy.research_current_mapping_release import (
    RETROSPECTIVE_ANALOG_COLUMNS,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_COLUMNS,
    M3_INFLUENCE_COLUMNS,
)
from seven_cycle_platform.products.cycle_asset_surface import (
    build_cycle_asset_surface_product,
    write_cycle_asset_surface_product,
)
from seven_cycle_platform.products.cycle_phase import (
    build_and_write_cycle_phase_vintage,
)
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import verify_manifest
from seven_cycle_platform.types import VintageKind
from seven_cycle_platform.verification.cycles import (
    QualityFinding,
    write_quality_findings,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_DIR = PROJECT_ROOT / "config" / "seven_cycle"
CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))
CATEGORY_CHANNELS = {
    "growth": "growth_demand",
    "prices": "inflation_prices",
    "rates": "real_rate_discount",
    "credit": "liquidity_credit",
    "external": "fx_external_demand",
    "market": "risk_premium_crowding",
}


def _api():
    try:
        return importlib.import_module(
            "seven_cycle_platform.legacy.research_attribution_release"
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"research attribution release module is missing: {error}")


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context(*, as_of: date = date(2025, 10, 31)) -> RunContext:
    return RunContext.create(
        as_of=as_of,
        data_vintage=as_of,
        model_version="m3-retrospective-research-v1",
        config={
            "retrospective_only": True,
            "vintage_kind": "pseudo_vintage",
        },
        input_checksums={"fixture": _checksum(b"research-attribution")},
        quality_summary={
            "vintage_status": "retrospective_only",
            "vintage_kind": "pseudo_vintage",
        },
        created_at=datetime(2026, 7, 16, 3, 0, tzinfo=timezone.utc),
    )


def _cycle_phase(months: pd.DatetimeIndex) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    innovations = rng.normal(0.0, 0.2, size=(len(months), len(CYCLE_IDS)))
    levels = innovations.cumsum(axis=0)
    return pd.DataFrame(
        [
            {
                "date": current_date,
                "cycle_id": cycle_id,
                "level": float(levels[position, cycle_position]),
                "slope": float(innovations[position, cycle_position]),
                "angle": float(
                    np.degrees(
                        np.arctan2(
                            innovations[position, cycle_position],
                            levels[position, cycle_position],
                        )
                    )
                    % 360.0
                ),
                "phase": phase_from_level_slope(
                    float(levels[position, cycle_position]),
                    float(innovations[position, cycle_position]),
                ).value,
                "amplitude": float(
                    np.hypot(
                        levels[position, cycle_position],
                        innovations[position, cycle_position],
                    )
                ),
                "uncertainty": 0.15 + cycle_position / 100.0,
                "center_period": 12.0 + cycle_position,
                "bandwidth": 3.0,
                "confidence": 0.8,
                "vintage": "pseudo_vintage",
                "vintage_caveat": "retrospective pseudo-vintage fixture",
            }
            for position, current_date in enumerate(months)
            for cycle_position, cycle_id in enumerate(CYCLE_IDS)
        ]
    )


def _category_members() -> dict[str, str]:
    counts = {
        "growth": 5,
        "prices": 5,
        "rates": 5,
        "credit": 4,
        "external": 4,
        "market": 4,
    }
    return {
        f"{category}_{position:02d}": category
        for category, count in counts.items()
        for position in range(count)
    }


def _research_bundle(
    months: pd.DatetimeIndex,
    *,
    rates_end: pd.Timestamp | None = None,
) -> SimpleNamespace:
    categories = _category_members()
    category_order = {name: position for position, name in enumerate(CATEGORY_CHANNELS)}
    observations: list[Observation] = []
    for entity_position, (entity_id, category) in enumerate(categories.items()):
        rng = np.random.default_rng(1000 + entity_position)
        latent = rng.normal(0.0, 0.4, size=len(months)).cumsum()
        for month_position, current_date in enumerate(months):
            if (
                category == "rates"
                and rates_end is not None
                and current_date > rates_end
            ):
                continue
            observations.append(
                Observation(
                    entity_id=entity_id,
                    observation_date=current_date.date(),
                    release_date=current_date.date(),
                    vintage_date=current_date.date(),
                    value=float(
                        latent[month_position]
                        + category_order[category]
                        + entity_position / 100.0
                    ),
                    unit="index",
                    source="retrospective_fixture",
                    retrieval_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
                    revision_number=0,
                    quality_status="retrospective_research_input",
                    vintage_kind=VintageKind.PSEUDO_VINTAGE,
                )
            )
    return SimpleNamespace(
        observations=tuple(observations),
        monthly_categories=categories,
    )


def _legacy_returns(path: Path, months: pd.DatetimeIndex) -> None:
    columns = pd.MultiIndex.from_tuples(list(LEGACY_CORE_ASSET_MAP))
    rng = np.random.default_rng(29)
    values = rng.normal(0.005, 0.025, size=(len(months), len(columns)))
    pd.DataFrame(values, index=months, columns=columns).to_parquet(path)


def test_cycle_innovations_are_causal_first_differences_without_lookahead() -> None:
    api = _api()
    months = pd.date_range("2024-01-31", periods=5, freq="ME")
    cycle_phase = _cycle_phase(months)

    full = api.build_cycle_innovations(cycle_phase)
    prefix = api.build_cycle_innovations(
        cycle_phase.loc[cycle_phase["date"].le(months[3])]
    )
    changed_future = cycle_phase.copy(deep=True)
    changed_future.loc[changed_future["date"].eq(months[4]), "level"] += 10_000.0
    changed = api.build_cycle_innovations(changed_future)

    assert tuple(full.columns) == ("date", "cycle_id", "innovation")
    assert set(full["cycle_id"]) == set(CYCLE_IDS)
    assert len(full) == (len(months) - 1) * len(CYCLE_IDS)
    assert full["date"].min() == months[1]
    pd.testing.assert_frame_equal(
        full.loc[full["date"].le(months[3])].reset_index(drop=True),
        prefix,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        full.loc[full["date"].le(months[3])].reset_index(drop=True),
        changed.loc[changed["date"].le(months[3])].reset_index(drop=True),
        check_exact=True,
    )


def test_twenty_seven_indicators_form_only_six_causal_pseudo_vintage_channels() -> None:
    api = _api()
    months = pd.date_range("2021-01-31", periods=42, freq="ME")
    bundle = _research_bundle(months)
    states = api.build_research_channel_states(bundle)

    changed_observations = list(bundle.observations)
    cutoff = months[-4]
    changed_observations = [
        record.model_copy(update={"value": record.value + 5000.0})
        if record.observation_date > cutoff.date()
        else record
        for record in changed_observations
    ]
    changed = api.build_research_channel_states(
        SimpleNamespace(
            observations=tuple(changed_observations),
            monthly_categories=bundle.monthly_categories,
        )
    )

    assert len(bundle.monthly_categories) == 27
    assert set(states["channel_id"]) == set(CATEGORY_CHANNELS.values())
    assert states["vintage_kind"].eq("pseudo_vintage").all()
    assert set(states["status"]).issubset({"available", "unavailable"})
    assert set(states.loc[states["date"].eq(months[-1]), "member_count"]) == {4, 5}
    compare_columns = [
        "date",
        "channel_id",
        "state",
        "innovation",
        "uncertainty",
        "member_count",
        "status",
        "status_reason",
    ]
    pd.testing.assert_frame_equal(
        states.loc[states["date"].le(cutoff), compare_columns].reset_index(drop=True),
        changed.loc[changed["date"].le(cutoff), compare_columns].reset_index(drop=True),
        check_exact=True,
    )


@pytest.mark.parametrize("member_delta", [-1, 1])
def test_research_channels_require_exactly_twenty_seven_monthly_entities(
    member_delta: int,
) -> None:
    api = _api()
    months = pd.date_range("2021-01-31", periods=30, freq="ME")
    bundle = _research_bundle(months)
    categories = dict(bundle.monthly_categories)
    observations = list(bundle.observations)
    if member_delta < 0:
        removed_entity = sorted(categories)[0]
        categories.pop(removed_entity)
        observations = [
            record for record in observations if record.entity_id != removed_entity
        ]
    else:
        extra_entity = "growth_extra_27"
        categories[extra_entity] = "growth"
        observations.extend(
            Observation(
                entity_id=extra_entity,
                observation_date=current_date.date(),
                release_date=current_date.date(),
                vintage_date=current_date.date(),
                value=float(position),
                unit="index",
                source="retrospective_fixture",
                retrieval_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
                revision_number=0,
                quality_status="retrospective_research_input",
                vintage_kind=VintageKind.PSEUDO_VINTAGE,
            )
            for position, current_date in enumerate(months)
        )

    with pytest.raises(ValueError, match="exactly 27"):
        api.build_research_channel_states(
            SimpleNamespace(
                observations=tuple(observations),
                monthly_categories=categories,
            )
        )


def test_research_channels_reject_later_pseudo_vintage_duplicate_history() -> None:
    api = _api()
    months = pd.date_range("2021-01-31", periods=30, freq="ME")
    bundle = _research_bundle(months)
    original = bundle.observations[0]
    duplicate = original.model_copy(
        update={
            "value": original.value + 1.0,
            "vintage_date": date(2026, 1, 1),
            "revision_number": 1,
        }
    )

    with pytest.raises(ValueError, match="duplicate.*entity_id.*date"):
        api.build_research_channel_states(
            SimpleNamespace(
                observations=(*bundle.observations, duplicate),
                monthly_categories=bundle.monthly_categories,
            )
        )


def test_bundle_checksum_is_independent_of_observation_order() -> None:
    api = _api()
    months = pd.date_range("2021-01-31", periods=30, freq="ME")
    bundle = _research_bundle(months)
    reversed_bundle = SimpleNamespace(
        observations=tuple(reversed(bundle.observations)),
        monthly_categories=dict(reversed(tuple(bundle.monthly_categories.items()))),
    )

    assert api._bundle_checksum(bundle) == api._bundle_checksum(reversed_bundle)


def test_memory_bundle_snapshot_is_deeply_detached_and_immutable() -> None:
    api = _api()
    months = pd.date_range("2021-01-31", periods=30, freq="ME")
    source = _research_bundle(months)
    mutable_observations = list(source.observations)
    mutable_categories = dict(source.monthly_categories)
    mutable_bundle = SimpleNamespace(
        observations=mutable_observations,
        monthly_categories=mutable_categories,
    )

    snapshot = api._snapshot_memory_bundle(mutable_bundle)
    checksum_before = api._bundle_checksum(snapshot)
    original_first = mutable_observations[0]
    snapshot_first = next(
        record
        for record in snapshot.observations
        if record.entity_id == original_first.entity_id
        and record.observation_date == original_first.observation_date
    )
    original_value = snapshot_first.value

    mutable_categories.clear()
    mutable_observations.reverse()
    object.__setattr__(original_first, "value", original_first.value + 10_000.0)

    assert len(snapshot.monthly_categories) == 27
    assert len(snapshot.observations) == len(source.observations)
    assert snapshot_first.value == original_value
    assert all(
        snapshot_record is not source_record
        for snapshot_record, source_record in zip(
            snapshot.observations,
            sorted(
                source.observations,
                key=lambda record: (
                    record.entity_id,
                    record.observation_date,
                    record.release_date,
                    record.vintage_date,
                    record.revision_number,
                    record.vintage_kind.value,
                    record.value,
                ),
            ),
            strict=True,
        )
    )
    with pytest.raises(TypeError):
        snapshot.monthly_categories["new_entity"] = "growth"
    assert api._bundle_checksum(snapshot) == checksum_before


def test_hierarchy_is_registry_derived_and_absolute_returns_cover_five_assets(
    tmp_path: Path,
) -> None:
    api = _api()
    registry = load_registry_bundle(REGISTRY_DIR)
    asset_ids = tuple(
        sorted(mapping.asset_id for mapping in LEGACY_CORE_ASSET_MAP.values())
    )
    hierarchy = api.build_research_asset_hierarchy(registry, asset_ids)
    asset_lookup = {asset.asset_id: asset for asset in registry.assets}

    assert set(hierarchy["asset_id"]) == set(asset_ids)
    for row in hierarchy.itertuples(index=False):
        asset = asset_lookup[row.asset_id]
        assert row.asset_class_id == f"asset_class:{asset.asset_class}"
        assert row.industry_id == f"segment:{asset.asset_class}:{asset.region}"
        assert row.is_proxy is False
        assert row.confidence_discount == 0.0

    returns_path = tmp_path / "monthly_returns.parquet"
    months = pd.date_range("2015-01-31", periods=132, freq="ME")
    _legacy_returns(returns_path, months)
    returns = api.build_absolute_asset_returns(returns_path, registry)

    assert tuple(returns.columns) == (
        "date",
        "asset_id",
        "return",
        "benchmark_return",
    )
    assert set(returns["asset_id"]) == set(asset_ids)
    assert not returns.duplicated(["date", "asset_id"]).any()
    for _, group in returns.groupby("date", sort=False):
        for row in group.itertuples(index=False):
            expected_benchmark = group.loc[
                group["asset_id"].ne(row.asset_id), "return"
            ].mean()
            assert np.isclose(row.benchmark_return, expected_benchmark)


def test_m3_influence_has_full_coverage_provenance_and_missing_channel_degradation() -> (
    None
):
    api = _api()
    context = _context()
    asset_ids = tuple(
        sorted(mapping.asset_id for mapping in LEGACY_CORE_ASSET_MAP.values())
    )
    period_end = pd.Timestamp("2025-10-31")
    rows: list[dict[str, object]] = []
    available_channels = tuple(
        channel_id
        for channel_id in CATEGORY_CHANNELS.values()
        if channel_id != "real_rate_discount"
    )
    for asset_position, asset_id in enumerate(asset_ids, start=1):
        for horizon in (3, 6, 12):
            for cycle_position, cycle_id in enumerate(CYCLE_IDS, start=1):
                rows.append(
                    {
                        "asset_id": asset_id,
                        "period_end": period_end,
                        "horizon_months": horizon,
                        "return_basis": "absolute",
                        "component_type": "cycle",
                        "component_id": cycle_id,
                        "point_contribution": (asset_position + cycle_position) / 100.0,
                        "interval_status": "available",
                        "status": "independent",
                        "evidence_level": "medium",
                    }
                )
            for channel_position, channel_id in enumerate(available_channels, start=1):
                rows.append(
                    {
                        "asset_id": asset_id,
                        "period_end": period_end,
                        "horizon_months": horizon,
                        "return_basis": "absolute",
                        "component_type": "channel_residual_path",
                        "component_id": channel_id,
                        "point_contribution": -channel_position / 100.0,
                        "interval_status": "available",
                        "status": "estimated",
                        "evidence_level": "medium",
                    }
                )

    influence = api.build_m3_influence(
        pd.DataFrame(rows),
        context=context,
        unavailable_channel_reasons={
            "real_rate_discount": "channel_missing_in_attribution_window"
        },
    )

    assert tuple(influence.columns) == M3_INFLUENCE_COLUMNS
    assert len(influence) == len(asset_ids) * 3 * (7 + 6)
    assert set(influence["asset_id"]) == set(asset_ids)
    assert set(influence["horizon_months"]) == {3, 6, 12}
    assert influence["source_stage"].eq("m3_asset_attribution").all()
    assert influence["source_run_id"].eq(context.run_id).all()
    assert influence["source_date"].eq(context.as_of).all()
    assert influence["source_model_version"].eq(context.model_version).all()
    assert influence["source_config_hash"].eq(context.config_hash).all()
    available = influence.loc[influence["status"].eq("available")]
    assert available["influence_score"].between(-1.0, 1.0).all()
    missing = influence.loc[influence["component_id"].eq("real_rate_discount")]
    assert missing["status"].eq("unavailable").all()
    assert missing["influence_score"].isna().all()
    assert missing["reason_code"].eq("channel_missing_in_attribution_window").all()


def _source_research_run(
    root: Path,
    cycle_phase: pd.DataFrame,
    *,
    omit: str | None = None,
) -> Path:
    context = RunContext.create(
        as_of=pd.Timestamp(cycle_phase["date"].max()).date(),
        data_vintage=pd.Timestamp(cycle_phase["date"].max()).date(),
        model_version="source-retrospective-research-v1",
        config={"retrospective_only": True, "vintage_kind": "pseudo_vintage"},
        input_checksums={"fixture": _checksum(b"source-research")},
        quality_summary={"vintage_status": "retrospective_only"},
        created_at=datetime(2026, 7, 16, 2, 0, tzinfo=timezone.utc),
    )

    def write_staging(staging_dir: Path) -> None:
        if omit != "cycle_phase_vintage.parquet":
            build_and_write_cycle_phase_vintage(
                staging_dir,
                cycle_phase,
                context=context,
            )
        if omit != "cycle_asset_surface.parquet":
            surface = build_cycle_asset_surface_product(
                [
                    {
                        "asset_id": "cn_equity_hs300",
                        "asset_label": "沪深300",
                        "cycle_x": "C1",
                        "cycle_y": "C2",
                        "metric": "observed_return",
                        "horizon_months": 3,
                        "scenario_id": "baseline",
                        "window_months": 36,
                        "grid_size": 9,
                        "status": "not_identifiable",
                        "estimator_version": "fixture-surface-v1",
                        "observations": [
                            {
                                "date": "2024-01-31",
                                "vintage": "pseudo_vintage",
                                "x": 0.1,
                                "y": -0.2,
                                "z": 0.01,
                            }
                        ],
                        "grid": [],
                        "current_point": {"x": 0.2, "y": 0.1, "z": 0.0},
                        "future_path": [],
                        "evidence": {
                            "sample_count": 1,
                            "bandwidth": None,
                            "oos_score": None,
                            "identifiable": False,
                            "reason": "fixture insufficient evidence",
                        },
                    }
                ],
                context=context,
            )
            write_cycle_asset_surface_product(
                staging_dir,
                surface,
                context=context,
            )
        if omit != "cycle_model_versions.json":
            (staging_dir / "cycle_model_versions.json").write_text("{}\n")
        if omit != "verification_plan.json":
            (staging_dir / "verification_plan.json").write_text("{}\n")
        if omit != "quality_findings.parquet":
            write_quality_findings(
                staging_dir,
                (
                    QualityFinding(
                        entity_id="fixture",
                        check="fixture_source_quality",
                        severity="mandatory",
                        status="PASS",
                        message="fixture accepted",
                        observed_value=1.0,
                        threshold=1.0,
                    ),
                ),
            )
        if omit != "registries":
            registries = staging_dir / "registries"
            registries.mkdir()
            (registries / "assets.json").write_text("{}\n")

    manifest = publish_run(root, context, write_staging=write_staging)
    return root / "runs" / manifest.run_id


def test_release_rejects_missing_required_source_artifact(tmp_path: Path) -> None:
    api = _api()
    registry = load_registry_bundle(REGISTRY_DIR)
    cycle_months = pd.date_range("2020-11-30", periods=60, freq="ME")
    observation_months = pd.date_range("2018-01-31", periods=94, freq="ME")
    source_run = _source_research_run(
        tmp_path / "source-missing",
        _cycle_phase(cycle_months),
        omit="cycle_asset_surface.parquet",
    )
    returns_path = tmp_path / "missing-source-returns.parquet"
    _legacy_returns(returns_path, cycle_months)

    with pytest.raises(FileNotFoundError, match="cycle_asset_surface.parquet"):
        api.publish_research_attribution_release(
            source_research_run=source_run,
            pipeline_input_bundle=_research_bundle(observation_months),
            returns_path=returns_path,
            registry_bundle=registry,
            product_root=tmp_path / "not-published",
            draw_count=8,
        )


def test_release_fails_if_original_returns_change_after_snapshot_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    registry = load_registry_bundle(REGISTRY_DIR)
    cycle_months = pd.date_range("2020-11-30", periods=60, freq="ME")
    observation_months = pd.date_range("2018-01-31", periods=94, freq="ME")
    source_run = _source_research_run(
        tmp_path / "source-race",
        _cycle_phase(cycle_months),
    )
    returns_path = tmp_path / "race-returns.parquet"
    _legacy_returns(returns_path, cycle_months)
    original_copy = api._copy_snapshot_file

    def copy_then_tamper(source: Path, destination: Path) -> None:
        original_copy(source, destination)
        if source == returns_path.resolve():
            source.write_bytes(source.read_bytes() + b"tampered")

    monkeypatch.setattr(api, "_copy_snapshot_file", copy_then_tamper)

    with pytest.raises(ValueError, match="changed during snapshot"):
        api.publish_research_attribution_release(
            source_research_run=source_run,
            pipeline_input_bundle=_research_bundle(observation_months),
            returns_path=returns_path,
            registry_bundle=registry,
            product_root=tmp_path / "race-not-published",
            draw_count=8,
        )


def test_lightweight_release_publishes_partial_attribution_without_backdating(
    tmp_path: Path,
) -> None:
    api = _api()
    registry = load_registry_bundle(REGISTRY_DIR)
    cycle_months = pd.date_range("2020-11-30", periods=60, freq="ME")
    observation_months = pd.date_range("2018-01-31", periods=94, freq="ME")
    cycle_phase = _cycle_phase(cycle_months)
    source_run = _source_research_run(tmp_path / "source", cycle_phase)
    returns_path = tmp_path / "returns.parquet"
    _legacy_returns(returns_path, cycle_months)
    bundle = _research_bundle(
        observation_months,
        rates_end=cycle_months[-13],
    )

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        result = api.publish_research_attribution_release(
            source_research_run=source_run,
            pipeline_input_bundle=bundle,
            returns_path=returns_path,
            registry_bundle=registry,
            product_root=tmp_path / "published",
            draw_count=24,
            created_at=datetime(2026, 7, 16, 4, 0, tzinfo=timezone.utc),
        )
    assert not [
        item for item in caught_warnings if issubclass(item.category, FutureWarning)
    ]

    verify_manifest(result.run_dir, expected=result.manifest)
    assert result.period_end == cycle_months[-1].date()
    assert result.manifest.model_version.endswith(
        "+m3-retrospective-attribution-v3+m4-retrospective-analog-v1"
    )
    assert result.manifest.quality_summary["channel_count"] == 6
    assert result.manifest.quality_summary["asset_count"] == 5
    assert result.manifest.quality_summary["forecast_status"] == "not_published"
    assert result.manifest.quality_summary["current_mapping_status"] == (
        "retrospective_only"
    )
    assert result.manifest.quality_summary["current_mapping_method"] == (
        "retrospective_cycle_analog_knn_v1"
    )
    assert result.manifest.quality_summary["vintage_status"] == "retrospective_only"
    assert result.manifest.quality_summary["governed_channel_state_status"] == (
        "not_published"
    )
    assert result.manifest.quality_summary["research_channel_state_role"] == (
        "audit_sidecar"
    )
    assert result.manifest.quality_summary["cycle_innovation_method"] == (
        "causal_first_difference_of_cycle_level"
    )
    assert result.manifest.quality_summary["benchmark_method"] == (
        "leave_one_out_governed_asset_benchmark"
    )
    assert set(result.manifest.quality_summary["active_channel_ids"]) == (
        set(CATEGORY_CHANNELS.values()) - {"real_rate_discount"}
    )
    assert result.manifest.quality_summary["unavailable_channel_ids"] == (
        "real_rate_discount",
    )
    assert result.manifest.quality_summary["attribution_status"] in {
        "available",
        "partial",
    }

    expected_files = {
        "asset_attribution.parquet",
        "asset_attribution_conservation.parquet",
        "asset_mapping_current.parquet",
        "cycle_asset_surface.parquet",
        "cycle_phase_vintage.parquet",
        "m3_influence.parquet",
        "retrospective_analogs.parquet",
        "research_attribution_config.json",
        "research_channel_state_audit.json",
    }
    assert expected_files.issubset(result.manifest.product_checksums)
    assert "research_channel_state.parquet" not in result.manifest.product_checksums
    release_config = json.loads(
        (result.run_dir / "research_attribution_config.json").read_text()
    )
    assert release_config["governed_channel_state_status"] == "not_published"
    assert release_config["research_channel_state_role"] == "audit_sidecar"
    provenance_columns = [
        "run_id",
        "as_of",
        "data_vintage",
        "model_version",
        "config_hash",
        "created_at",
    ]
    for filename in (
        "cycle_phase_vintage.parquet",
        "cycle_asset_surface.parquet",
    ):
        source_product = pd.read_parquet(source_run / filename)
        published_product = pd.read_parquet(result.run_dir / filename)
        pd.testing.assert_frame_equal(
            source_product.drop(columns=provenance_columns),
            published_product.drop(columns=provenance_columns),
            check_exact=True,
        )
        assert published_product["run_id"].eq(result.manifest.run_id).all()
        assert (
            published_product["model_version"].eq(result.manifest.model_version).all()
        )
        assert published_product["config_hash"].eq(result.manifest.config_hash).all()

    attribution = pd.read_parquet(result.run_dir / "asset_attribution.parquet")
    conservation = pd.read_parquet(
        result.run_dir / "asset_attribution_conservation.parquet"
    )
    assert tuple(attribution.columns) == ASSET_ATTRIBUTION_COLUMNS
    assert tuple(conservation.columns) == ASSET_ATTRIBUTION_CONSERVATION_COLUMNS
    validate_asset_attribution(
        attribution,
        conservation,
        context=result.manifest,
    )
    assert set(attribution["horizon_months"]) == {3, 6, 12}
    assert attribution["return_basis"].eq("absolute").all()
    assert attribution["period_end"].eq(cycle_months[-1].date()).all()
    assert conservation["point_conservation_error"].le(1e-10).all()

    channel_state = json.loads(
        (result.run_dir / "research_channel_state_audit.json").read_text()
    )
    assert {row["channel_id"] for row in channel_state} == set(
        CATEGORY_CHANNELS.values()
    )
    rates_window = [
        row
        for row in channel_state
        if row["channel_id"] == "real_rate_discount"
        and row["date"] >= cycle_months[-12].date().isoformat()
    ]
    assert rates_window
    assert all(row["innovation"] is None for row in rates_window)
    assert all(row["state"] is None for row in rates_window)
    assert all(row["uncertainty"] is None for row in rates_window)

    influence = pd.read_parquet(result.run_dir / "m3_influence.parquet")
    missing = influence.loc[influence["component_id"].eq("real_rate_discount")]
    assert missing["status"].eq("unavailable").all()
    assert missing["influence_score"].isna().all()
    assert missing["reason_code"].eq("channel_missing_in_attribution_window").all()
    assert influence["source_run_id"].eq(result.manifest.run_id).all()
    assert influence["source_model_version"].eq(result.manifest.model_version).all()
    assert influence["source_config_hash"].eq(result.manifest.config_hash).all()
    mapping = pd.read_parquet(result.run_dir / "asset_mapping_current.parquet")
    assert tuple(mapping.columns) == ASSET_MAPPING_CURRENT_COLUMNS
    assert len(mapping) == 15
    assert mapping["mapping_status"].eq("retrospective_only").all()
    assert mapping["absolute_distribution_status"].eq("available").all()
    assert mapping["excess_distribution_status"].eq("available").all()
    assert (
        mapping["absolute_calibration_version"]
        .eq("retrospective-cycle-analog-knn-v1")
        .all()
    )
    assert mapping["range_status"].eq("unavailable").all()
    assert mapping["published_min_weight"].isna().all()
    assert mapping["published_max_weight"].isna().all()
    expected_control_caveats = {
        "earnings_control_unavailable",
        "event_scenario_unavailable",
        "liquidity_control_unavailable",
        "positioning_control_unavailable",
        "valuation_control_unavailable",
    }
    for caveat_json in mapping["caveat_codes"]:
        caveats = set(json.loads(caveat_json))
        assert expected_control_caveats.issubset(caveats)
        assert "pseudo_vintage_evidence" in caveats
    analogs = pd.read_parquet(result.run_dir / "retrospective_analogs.parquet")
    assert tuple(analogs.columns) == RETROSPECTIVE_ANALOG_COLUMNS
    assert len(analogs) == 24
    assert analogs["draw_id"].tolist() == list(range(24))
    catalog = build_catalog(
        result.run_dir,
        tmp_path / "catalog.duckdb",
        expected_manifest=result.manifest,
    )
    with duckdb.connect(str(catalog.path), read_only=True) as connection:
        available = connection.execute(
            "SELECT available FROM _catalog_products "
            "WHERE product_name = 'channel_state'"
        ).fetchone()
        channel_row_count = connection.execute(
            "SELECT COUNT(*) FROM _src_channel_state"
        ).fetchone()
        mapping_available = connection.execute(
            "SELECT available FROM _catalog_products "
            "WHERE product_name = 'asset_mapping_current'"
        ).fetchone()
        mapping_row_count = connection.execute(
            "SELECT COUNT(*) FROM asset_mapping_current"
        ).fetchone()
    assert available == (False,)
    assert channel_row_count == (0,)
    assert mapping_available == (True,)
    assert mapping_row_count == (15,)
