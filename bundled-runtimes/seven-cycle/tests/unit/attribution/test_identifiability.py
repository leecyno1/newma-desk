from dataclasses import FrozenInstanceError
from importlib import import_module
from types import ModuleType

import numpy as np
import pandas as pd
import pytest


CYCLE_IDS = tuple(f"C{number}" for number in range(1, 8))
ALL_CYCLES_GROUP = "+".join(CYCLE_IDS)
REQUIRED_API = (
    "IDENTIFIABILITY_COLUMNS",
    "IdentifiabilityConfig",
    "identify_cycle_groups",
)


def _api() -> ModuleType:
    module = import_module("seven_cycle_platform.attribution")
    missing = [name for name in REQUIRED_API if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"Task 16 identifiability API is missing: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _stage1_history(
    *,
    count: int = 24,
    seed: int = 20260713,
    relation: str = "independent",
) -> tuple[pd.DataFrame, pd.Timestamp]:
    generator = np.random.default_rng(seed)
    dates = pd.date_range("2019-01-31", periods=count + 1, freq="ME")
    values = generator.normal(size=(count + 1, len(CYCLE_IDS)))
    if relation == "positive":
        values[:, 1] = values[:, 0]
    elif relation == "negative":
        values[:, 1] = -values[:, 0]
    elif relation == "linear_dependency":
        values[:, 6] = values[:, :6].sum(axis=1)
    rows = [
        {
            "date": date,
            "channel_id": channel_id,
            "cycle_id": cycle_id,
            "cycle_innovation": float(values[date_position, cycle_position]),
            "status": "estimated",
        }
        for date_position, date in enumerate(dates)
        for channel_id in ("growth", "inflation")
        for cycle_position, cycle_id in enumerate(CYCLE_IDS)
    ]
    return pd.DataFrame(rows), dates[-1]


def _index(date: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date, date],
            "asset_id": ["asset_a", "asset_b"],
        }
    )


def test_negative_correlation_merges_cycles_deterministically() -> None:
    api = _api()
    stage1, current_date = _stage1_history(relation="negative")

    result = api.identify_cycle_groups(
        stage1,
        _index(current_date),
        config=api.IdentifiabilityConfig(
            min_history_count=12,
            correlation_threshold=0.95,
            condition_number_threshold=1_000_000.0,
        ),
    )

    assert tuple(result.columns) == api.IDENTIFIABILITY_COLUMNS
    for _, asset_group in result.groupby("asset_id", sort=False):
        merged = asset_group.loc[asset_group["cycle_id"].isin(["C1", "C2"])]
        assert merged["group_id"].eq("C1+C2").all()
        assert merged["group_size"].eq(2).all()
        assert merged["status"].eq("merged_cycles").all()
        assert merged["max_abs_correlation"].eq(1.0).all()
        independent = asset_group.loc[~asset_group["cycle_id"].isin(["C1", "C2"])]
        assert independent["group_id"].eq(independent["cycle_id"]).all()
        assert independent["status"].eq("independent").all()
        assert asset_group["history_count"].eq(24).all()


def test_identifiability_uses_strictly_past_history() -> None:
    api = _api()
    stage1, current_date = _stage1_history(relation="independent")
    config = api.IdentifiabilityConfig(
        min_history_count=12,
        correlation_threshold=0.90,
        condition_number_threshold=1_000_000.0,
    )
    base = api.identify_cycle_groups(stage1, _index(current_date), config=config)

    future_date = current_date + pd.offsets.MonthEnd(1)
    future = stage1.loc[stage1["date"].eq(current_date)].copy(deep=True)
    future["date"] = future_date
    future.loc[future["cycle_id"].eq("C1"), "cycle_innovation"] = 1000.0
    future.loc[future["cycle_id"].eq("C2"), "cycle_innovation"] = -1000.0
    changed = api.identify_cycle_groups(
        pd.concat([stage1, future], ignore_index=True),
        _index(current_date),
        config=config,
    )

    pd.testing.assert_frame_equal(base, changed)


def test_missing_current_stage1_is_explicitly_unavailable() -> None:
    api = _api()
    stage1, current_date = _stage1_history()
    stage1 = stage1.loc[stage1["date"].lt(current_date)]

    result = api.identify_cycle_groups(
        stage1,
        _index(current_date).iloc[[0]],
        config=api.IdentifiabilityConfig(min_history_count=12),
    )

    assert result["group_id"].eq(ALL_CYCLES_GROUP).all()
    assert result["group_size"].eq(7).all()
    assert result["status"].eq("unavailable").all()


def test_insufficient_history_returns_one_unallocated_cycle_group() -> None:
    api = _api()
    stage1, current_date = _stage1_history(count=5)

    result = api.identify_cycle_groups(
        stage1,
        _index(current_date).iloc[[0]],
        config=api.IdentifiabilityConfig(min_history_count=8),
    )

    assert len(result) == 7
    assert result["group_id"].eq(ALL_CYCLES_GROUP).all()
    assert result["group_size"].eq(7).all()
    assert result["history_count"].eq(5).all()
    assert result["status"].eq("insufficient_history").all()


def test_severe_unidentifiability_without_reliable_pair_is_explicit() -> None:
    api = _api()
    stage1, current_date = _stage1_history(
        count=80,
        relation="linear_dependency",
    )

    result = api.identify_cycle_groups(
        stage1,
        _index(current_date).iloc[[0]],
        config=api.IdentifiabilityConfig(
            min_history_count=24,
            correlation_threshold=0.99,
            condition_number_threshold=100_000.0,
        ),
    )

    assert result["group_id"].eq(ALL_CYCLES_GROUP).all()
    assert result["status"].eq("not_identifiable").all()
    assert np.isinf(result["condition_number"]).all()


def test_merge_does_not_hide_remaining_matrix_unidentifiability() -> None:
    api = _api()
    stage1, current_date = _stage1_history(count=80, relation="positive")
    cycle_values = stage1.pivot_table(
        index=["date", "channel_id"],
        columns="cycle_id",
        values="cycle_innovation",
    )
    cycle_values["C7"] = cycle_values[["C3", "C4", "C5", "C6"]].sum(axis=1)
    replacement = (
        cycle_values.stack(future_stack=True).rename("cycle_innovation").reset_index()
    )
    stage1 = stage1.drop(columns="cycle_innovation").merge(
        replacement,
        on=["date", "channel_id", "cycle_id"],
        validate="one_to_one",
    )

    result = api.identify_cycle_groups(
        stage1,
        _index(current_date).iloc[[0]],
        config=api.IdentifiabilityConfig(
            min_history_count=24,
            correlation_threshold=0.99,
            condition_number_threshold=100_000.0,
        ),
    )

    assert result["group_id"].eq(ALL_CYCLES_GROUP).all()
    assert result["status"].eq("not_identifiable").all()


def test_identifiability_rejects_inconsistent_cross_channel_innovations() -> None:
    api = _api()
    stage1, current_date = _stage1_history()
    conflict = (
        stage1["date"].eq(stage1["date"].min())
        & stage1["channel_id"].eq("inflation")
        & stage1["cycle_id"].eq("C1")
    )
    stage1.loc[conflict, "cycle_innovation"] += 0.25

    with pytest.raises(ValueError, match="cycle innovation"):
        api.identify_cycle_groups(stage1, _index(current_date))


def test_identifiability_config_is_frozen_and_validated() -> None:
    api = _api()
    config = api.IdentifiabilityConfig()
    with pytest.raises(FrozenInstanceError):
        config.min_history_count = 1
    with pytest.raises(ValueError, match="correlation_threshold"):
        api.IdentifiabilityConfig(correlation_threshold=1.01)
    with pytest.raises(ValueError, match="min_history_count"):
        api.IdentifiabilityConfig(min_history_count=1)
