from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib

import numpy as np
import pandas as pd

from seven_cycle_platform.legacy.research_current_mapping_release import (
    RETROSPECTIVE_ANALOG_COLUMNS,
    RetrospectiveAnalogConfig,
    build_retrospective_current_distribution,
    select_retrospective_analogs,
)
from seven_cycle_platform.mapping.distribution import CurrentDistributionResult
from seven_cycle_platform.mapping.features import (
    CurrentFeatureSnapshot,
    FeatureInput,
    FeatureKind,
    FeaturePayload,
    FeatureProvenance,
    FreshnessPolicy,
    StructuralDriftFlag,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


AS_OF = date(2025, 12, 31)
ASSETS = ("asset_alpha", "asset_beta")


def _context() -> RunContext:
    return RunContext.create(
        as_of=AS_OF,
        data_vintage=date(2025, 12, 15),
        model_version="m4-retrospective-cycle-analog-v1",
        config={"method": "retrospective_cycle_analog_knn_v1"},
        input_checksums={"fixture": hashlib.sha256(b"fixture").hexdigest()},
        quality_summary={"vintage_status": "retrospective_only"},
        created_at=datetime(2026, 7, 16, 8, 30, tzinfo=timezone.utc),
    )


def _feature(
    kind: FeatureKind,
    feature_id: str,
    *,
    entity_id: str | None = None,
) -> FeatureInput:
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values={"status": "unavailable", "value": 0.5},
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=date(2025, 10, 31),
        release_date=date(2025, 10, 31),
        vintage_date=date(2025, 12, 15),
        source="retrospective-research-fixture",
        unit="score",
        retrieval_time=datetime.combine(
            date(2026, 7, 16), time(8, 0), tzinfo=timezone.utc
        ),
        revision_number=0,
        quality_status="accepted_for_retrospective_research",
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
        methodology="retrospective_cycle_analog_knn_v1",
        vintage_caveat="Pseudo-vintage research evidence; not realtime history.",
    )
    return FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=120,
            max_visible_age_days=30,
        ),
        structural_drift=StructuralDriftFlag(
            detected=False,
            score=0.0,
            threshold=1.0,
            method="retrospective_release_gate",
            baseline_id="retrospective-cycle-analog-v1",
            evaluated_at=date(2025, 12, 15),
            reason="formal structural validation is not published",
        ),
    )


def _snapshot() -> CurrentFeatureSnapshot:
    return CurrentFeatureSnapshot(
        as_of=AS_OF,
        cycle_states=tuple(
            _feature(FeatureKind.CYCLE, f"C{position}") for position in range(1, 8)
        ),
        channel_states=(_feature(FeatureKind.CHANNEL, "growth_demand"),),
        valuation_controls=tuple(
            _feature(
                FeatureKind.VALUATION,
                "valuation_unavailable",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        earnings_controls=tuple(
            _feature(
                FeatureKind.EARNINGS,
                "earnings_unavailable",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        positioning_controls=tuple(
            _feature(
                FeatureKind.POSITIONING,
                "positioning_unavailable",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        liquidity_controls=tuple(
            _feature(
                FeatureKind.LIQUIDITY,
                "liquidity_unavailable",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        event_scenarios=tuple(
            _feature(
                FeatureKind.EVENT,
                "event_unavailable",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        historical_posterior=tuple(
            _feature(
                FeatureKind.HISTORICAL_POSTERIOR,
                "analog_history",
                entity_id=asset_id,
            )
            for asset_id in ASSETS
        ),
        run_context=_context(),
    )


def _cycle_phase() -> pd.DataFrame:
    months = pd.date_range("2020-01-31", periods=60, freq="ME")
    rows: list[dict[str, object]] = []
    for month_index, month in enumerate(months):
        for position in range(1, 8):
            angle = float((month_index * (position + 2) * 9) % 360)
            rows.append(
                {
                    "date": month,
                    "cycle_id": f"C{position}",
                    "angle": angle,
                }
            )
    current = months[-1]
    rows[-7]["angle"] = 359.0
    rows[0]["angle"] = 1.0
    assert rows[-7]["date"] == current
    return pd.DataFrame(rows)


def _asset_returns() -> pd.DataFrame:
    months = pd.date_range("2020-01-31", periods=60, freq="ME")
    rows: list[dict[str, object]] = []
    for month_index, month in enumerate(months):
        alpha = 0.01 + month_index / 100_000
        beta = -0.002 + month_index / 200_000
        for asset_id, value, benchmark in (
            ("asset_alpha", alpha, beta),
            ("asset_beta", beta, alpha),
        ):
            rows.append(
                {
                    "date": month,
                    "asset_id": asset_id,
                    "return": value,
                    "benchmark_return": benchmark,
                }
            )
    return pd.DataFrame(rows)


def test_select_analogs_uses_circular_distance_and_complete_forward_paths() -> None:
    analogs = select_retrospective_analogs(
        _cycle_phase(),
        _asset_returns(),
        RetrospectiveAnalogConfig(draw_count=8, min_effective_samples=8),
    )

    assert tuple(analogs.columns) == RETROSPECTIVE_ANALOG_COLUMNS
    assert analogs["draw_id"].tolist() == list(range(8))
    assert analogs["analog_origin"].max() <= date(2023, 12, 31)
    assert analogs["distance"].is_monotonic_increasing
    assert np.isfinite(analogs["distance"]).all()


def test_build_distribution_reuses_same_analog_draws_for_every_asset() -> None:
    snapshot = _snapshot()
    result = build_retrospective_current_distribution(
        snapshot=snapshot,
        cycle_phase=_cycle_phase(),
        asset_returns=_asset_returns(),
        config=RetrospectiveAnalogConfig(draw_count=8, min_effective_samples=8),
    )

    assert isinstance(result.distribution, CurrentDistributionResult)
    assert result.distribution.config.draw_count == 8
    assert result.distribution.summary["status"].eq("available").all()
    assert (
        result.distribution.summary["calibration_version"]
        .eq("retrospective-cycle-analog-knn-v1")
        .all()
    )
    assert set(result.distribution.summary["asset_id"]) == set(ASSETS)
    assert set(result.distribution.summary["horizon_months"]) == {3, 6, 12}
    assert set(result.distribution.summary["return_basis"]) == {
        "absolute",
        "excess",
    }
    assert len(result.analogs) == 8

    monthly = result.distribution.monthly_draws
    for draw_id in range(8):
        assert set(monthly.loc[monthly["draw_id"].eq(draw_id), "asset_id"]) == set(
            ASSETS
        )
        assert (
            len(
                monthly.loc[
                    monthly["draw_id"].eq(draw_id),
                    ["forecast_origin", "date"],
                ].drop_duplicates()
            )
            == 12
        )
