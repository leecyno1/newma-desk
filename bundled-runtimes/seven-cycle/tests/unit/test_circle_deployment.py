from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.contracts.arrow import CYCLE_PHASE_VINTAGE_SCHEMA
from seven_cycle_platform.pipeline.circle_deployment import (
    _asset_attribution_tables,
    _asset_mapping_table,
    _cycle_phase_table,
    _cycle_forecast_table,
)
from seven_cycle_platform.storage import RunContext


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2026, 7, 21),
        data_vintage=date(2026, 6, 30),
        model_version="circle-deployment-v3",
        config={"deployment": "test"},
        input_checksums={"input": hashlib.sha256(b"input").hexdigest()},
        quality_summary={"assets": 1},
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )


def test_asset_mapping_keeps_p20_p80_without_mislabeling_quantiles() -> None:
    context = _context()
    payload = {
        "assets": [
            {
                "assetId": "商品::黄金",
                "dataEnd": "2026-06",
                "horizons": {
                    "3": {
                        "status": "limited",
                        "forecast": {
                            "probabilityUp": 0.6,
                            "medianReturn": 0.04,
                            "low20": -0.03,
                            "high80": 0.12,
                            "conditionalVol": 0.08,
                            "analogs": 24,
                        },
                    }
                },
            }
        ]
    }

    row = _asset_mapping_table(payload, context).to_pylist()[0]

    assert row["absolute_q25"] is None
    assert row["absolute_q50"] == 0.04
    assert row["absolute_q75"] is None
    assert '"p20":-0.03' in row["cycle_influence_json"]
    assert '"p80":0.12' in row["cycle_influence_json"]
    assert row["mapping_status"] == "conditional"
    assert row["run_id"] == context.run_id


def test_asset_attribution_is_conserving_and_explicitly_not_causal() -> None:
    context = _context()
    payload = {
        "assets": [
            {
                "category": "商品",
                "name": "黄金",
                "n_months": 240,
                "actual_2019": 0.18,
                "c4_assoc_contribution_2019": 0.05,
            },
            {
                "category": "商品",
                "name": "新资产",
                "n_months": 24,
                "actual_2019": None,
                "c4_assoc_contribution_2019": None,
            },
        ]
    }

    attribution, conservation = _asset_attribution_tables(payload, context)
    rows = attribution.to_pylist()
    diagnostic = conservation.to_pylist()[0]

    assert len(rows) == 2
    assert sum(row["point_contribution"] for row in rows) == pytest.approx(0.18)
    assert rows[0]["component_id"] == "C4_statistical_association_not_causal"
    assert {row["interval_status"] for row in rows} == {"unavailable"}
    assert {row["evidence_level"] for row in rows} == {"low"}
    assert diagnostic["point_conservation_error"] == 0.0
    assert diagnostic["unavailable_component_count"] == 2


def test_cycle_forecast_publishes_all_phase_probabilities() -> None:
    context = _context()
    payload = {
        "forecast": [
            {
                "date": "2026-07",
                "low": -0.2,
                "high": 0.1,
                "p_recovery": 0.4,
                "p_expansion": 0.2,
                "p_downturn": 0.1,
                "p_contraction": 0.3,
            }
        ]
    }

    row = _cycle_forecast_table(payload, context).to_pylist()[0]

    assert row["cycle_id"] == "C4"
    assert row["horizon_months"] == 1
    assert row["forecast_date"] == date(2026, 7, 31)
    assert row["recovery_probability"] == 0.4
    assert row["contraction_probability"] == 0.3


def test_cycle_phase_appends_limited_realtime_bridge(tmp_path) -> None:
    context = _context()
    row = {name: None for name in CYCLE_PHASE_VINTAGE_SCHEMA.names}
    row.update(
        {
            "date": date(2025, 12, 31),
            "cycle_id": "C4",
            "vintage": "latest_historical",
            "phase": "contraction",
            "run_id": "2025-12-31-0123456789ab-abcdef012345",
            "as_of": date(2025, 12, 31),
            "data_vintage": date(2025, 12, 31),
            "model_version": "foundation",
            "config_hash": "a" * 64,
            "created_at": datetime(2025, 12, 31, tzinfo=timezone.utc),
        }
    )
    source_path = tmp_path / "cycle_phase_vintage.parquet"
    pq.write_table(
        pa.Table.from_pylist([row], schema=CYCLE_PHASE_VINTAGE_SCHEMA),
        source_path,
    )
    research = {
        "C4Realtime": {
            "timeline": [
                {
                    "date": "2025-12",
                    "rt_level": -0.2,
                    "rt_angle": 20.0,
                    "rt_phase": "recovery",
                    "rt_uncertainty": 0.2,
                    "confidence": 0.6,
                },
                {
                    "date": "2026-01",
                    "rt_level": -0.1,
                    "rt_angle": 60.0,
                    "rt_phase": "recovery",
                    "rt_uncertainty": 0.1,
                    "confidence": 0.7,
                },
            ]
        }
    }

    rows = _cycle_phase_table(source_path, research, context).to_pylist()

    assert rows[-1]["date"] == date(2026, 1, 31)
    assert rows[-1]["vintage"] == "pseudo_vintage"
    assert rows[-1]["slope"] == pytest.approx(0.1)
    assert rows[-1]["run_id"] == context.run_id
