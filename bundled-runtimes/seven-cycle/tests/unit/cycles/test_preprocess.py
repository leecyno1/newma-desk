from datetime import date, datetime
from importlib import import_module
import os
from pathlib import Path
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles import (
    causal_transform,
    expanding_standardize,
    regularize_panel,
)


def test_regularize_panel_monthly_uses_last_observation_and_complete_grid() -> None:
    panel = pd.DataFrame(
        {"value": [31.0, 1.0, 2.0, 30.0]},
        index=pd.to_datetime(
            ["2024-03-31", "2024-01-05", "2024-01-31", "2024-03-02"]
        ),
    )
    original = panel.copy(deep=True)

    result = regularize_panel(panel, "M")

    expected = pd.DataFrame(
        {"value": [2.0, np.nan, 31.0]},
        index=pd.date_range("2024-01-31", "2024-03-31", freq="ME"),
    )
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(panel, original)


def test_regularize_panel_monthly_preserves_nulls_from_actual_final_row() -> None:
    panel = pd.DataFrame(
        {
            "left": [np.nan, 1.0, 3.0],
            "right": [2.0, np.nan, 4.0],
        },
        index=pd.to_datetime(["2024-01-31", "2024-01-05", "2024-02-15"]),
    )

    result = regularize_panel(panel, "M")

    expected = pd.DataFrame(
        {
            "left": [np.nan, 3.0],
            "right": [2.0, 4.0],
        },
        index=pd.date_range("2024-01-31", "2024-02-29", freq="ME"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_regularize_panel_monthly_preserves_index_name() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.DatetimeIndex(
            ["2024-01-05", "2024-02-10"],
            name="observation_date",
        ),
    )

    result = regularize_panel(panel, "M")

    assert result.index.name == "observation_date"


def test_regularize_panel_monthly_rejects_timezone_without_warning() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.date_range(
            "2024-01-31",
            periods=2,
            freq="ME",
            tz="Asia/Shanghai",
            name="observation_date",
        ),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(ValueError, match="timezone-aware"):
            regularize_panel(panel, "M")


@pytest.mark.parametrize(
    "raw_index",
    [
        ["2024-01-31T00:00:00Z", "2024-02-29T00:00:00Z"],
        ["2024-01-31T00:00:00+08:00", "2024-02-29T00:00:00+09:00"],
    ],
    ids=["same-offset", "mixed-offset"],
)
def test_regularize_panel_monthly_rejects_timezone_strings_without_warning(
    raw_index: list[str],
) -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.Index(raw_index, name="observation_date"),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(ValueError, match="timezone-aware"):
            regularize_panel(panel, "M")


@pytest.mark.parametrize(
    "panel",
    [
        pd.DataFrame(
            {"value": pd.Series(dtype="float64")},
            index=pd.Index([], name="raw_date"),
        ),
        pd.DataFrame(
            {"value": [1.0, 2.0]},
            index=pd.Index(["not-a-date", "still-not-a-date"]),
        ),
    ],
)
def test_regularize_panel_monthly_handles_empty_or_invalid_indexes(
    panel: pd.DataFrame,
) -> None:
    result = regularize_panel(panel, "M")

    assert result.empty
    assert list(result.columns) == ["value"]
    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.index.dtype == "datetime64[ns]"


@pytest.mark.parametrize("frequency", ["A", "Y", "a", "y"])
def test_regularize_panel_annual_accepts_aliases_and_discards_invalid_years(
    frequency: str,
) -> None:
    panel = pd.DataFrame(
        {"value": [22.0, 1.0, 2.0, 21.5, 99.0, 23.0]},
        index=pd.Index(["2022", 2020, 2020.0, 2021.5, "invalid", 2023]),
    )

    result = regularize_panel(panel, frequency)

    expected = pd.DataFrame(
        {"value": [2.0, np.nan, 22.0, 23.0]},
        index=pd.Index([2020, 2021, 2022, 2023], name="year"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_regularize_panel_annual_preserves_nulls_from_actual_final_row() -> None:
    panel = pd.DataFrame(
        {
            "left": [1.0, 3.0, np.nan],
            "right": [np.nan, 4.0, 2.0],
        },
        index=pd.Index([2020, 2021, 2020]),
    )

    result = regularize_panel(panel, "Y")

    expected = pd.DataFrame(
        {
            "left": [np.nan, 3.0],
            "right": [2.0, 4.0],
        },
        index=pd.Index([2020, 2021], name="year"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_regularize_panel_annual_extracts_years_from_datetime_index() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0, 3.0]},
        index=pd.DatetimeIndex(
            ["2020-01-15", "2020-12-31", "2022-06-30"],
            name="observation_date",
        ),
    )

    result = regularize_panel(panel, "Y")

    expected = pd.DataFrame(
        {"value": [2.0, np.nan, 3.0]},
        index=pd.Index([2020, 2021, 2022], name="year"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_regularize_panel_annual_extracts_years_from_timestamp_objects() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0, 3.0]},
        index=pd.Index(
            [
                datetime(2019, 6, 30),
                date(2020, 12, 31),
                pd.Timestamp("2022-03-31"),
            ],
            dtype="object",
        ),
    )

    result = regularize_panel(panel, "A")

    expected = pd.DataFrame(
        {"value": [1.0, 2.0, np.nan, 3.0]},
        index=pd.Index([2019, 2020, 2021, 2022], name="year"),
    )
    pd.testing.assert_frame_equal(result, expected)


def test_regularize_panel_annual_supports_legitimate_long_history_span() -> None:
    panel = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.Index([1270, 2026]))

    result = regularize_panel(panel, "Y")

    assert result.index[0] == 1270
    assert result.index[-1] == 2026
    assert len(result) == 2026 - 1270 + 1


def test_regularize_panel_annual_rejects_extreme_years_before_allocation() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.Index([2020, 10**12]),
    )

    with pytest.raises(ValueError, match="year"):
        regularize_panel(panel, "Y")


def test_regularize_panel_annual_rejects_all_boolean_years() -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.Index([True, False]),
    )

    with pytest.raises(ValueError, match="boolean year"):
        regularize_panel(panel, "Y")


@pytest.mark.parametrize("raw_index", [[2020, True], [False, 2020]])
def test_regularize_panel_annual_rejects_boolean_years_in_mixed_order(
    raw_index: list[object],
) -> None:
    panel = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.Index(raw_index, dtype="object"),
    )

    with pytest.raises(ValueError, match="boolean year"):
        regularize_panel(panel, "Y")


@pytest.mark.parametrize(
    "panel",
    [
        pd.DataFrame(
            {"value": pd.Series(dtype="float64")},
            index=pd.Index([], name="raw_year"),
        ),
        pd.DataFrame(
            {"value": [1.0, 2.0]},
            index=pd.Index(["invalid", 2020.5]),
        ),
    ],
)
def test_regularize_panel_annual_handles_empty_or_invalid_indexes(
    panel: pd.DataFrame,
) -> None:
    result = regularize_panel(panel, "Y")

    assert result.empty
    assert list(result.columns) == ["value"]
    assert result.index.equals(pd.Index([], dtype="int64", name="year"))


def test_regularize_panel_rejects_unsupported_frequency() -> None:
    panel = pd.DataFrame({"value": [1.0]}, index=[2024])

    with pytest.raises(ValueError, match="frequency"):
        regularize_panel(panel, "Q")


@pytest.mark.parametrize("frequency", ["M", "Y"])
def test_causal_transform_log_differences_positive_levels(frequency: str) -> None:
    values = pd.Series([100.0, "110", 121.0], name="level")

    result = causal_transform(values, "level", frequency)

    expected = pd.Series(
        [np.nan, np.log(1.1), np.log(1.1)],
        name="level",
    )
    pd.testing.assert_series_equal(result, expected)


def test_causal_transform_switches_to_ordinary_difference_causally() -> None:
    values = pd.Series([100.0, 110.0, 0.0, 120.0, 132.0], name="level")

    result = causal_transform(values, "price", "M")

    expected = pd.Series(
        [np.nan, np.log(1.1), -110.0, 120.0, 12.0],
        name="level",
    )
    pd.testing.assert_series_equal(result, expected)


def test_causal_transform_is_invariant_to_appended_future_levels() -> None:
    history = pd.Series(
        [100.0, 105.0, np.inf, 115.0, 120.0],
        index=pd.date_range("2020-01-31", periods=5, freq="ME"),
        name="price",
    )
    future = pd.Series(
        [0.0, -50.0, 1_000_000.0],
        index=pd.date_range("2020-06-30", periods=3, freq="ME"),
        name="price",
    )

    history_result = causal_transform(history, "price_adj", "M")
    full_result = causal_transform(pd.concat([history, future]), "price_adj", "M")

    pd.testing.assert_series_equal(
        history_result,
        full_result.loc[history.index],
        check_exact=True,
    )
    assert history_result.isna().tolist() == [True, False, True, True, False]


def test_causal_transform_handles_rates_levels_and_nonfinite_values() -> None:
    values = pd.Series(["1.0", 2.0, np.inf, 5.0], name="rate")

    monthly_rate = causal_transform(values, "rate_level", "M")
    annual_rate = causal_transform(values, "rate_level", "Y")
    monthly_growth = causal_transform(values, "growth", "M")

    expected_levels = pd.Series([1.0, 2.0, np.nan, 5.0], name="rate")
    pd.testing.assert_series_equal(monthly_rate, expected_levels.diff())
    pd.testing.assert_series_equal(annual_rate, expected_levels)
    pd.testing.assert_series_equal(monthly_growth, expected_levels)


def test_legacy_causal_transform_preserves_full_sample_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(project_root / "scripts"))
    legacy_module = import_module("cycle_realtime_core")
    values = pd.Series([100.0, 110.0, 0.0], name="level")

    result = legacy_module.causal_transform(values, "level", "M")

    expected = pd.Series([np.nan, 10.0, -110.0], name="level")
    pd.testing.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    ("frequency", "panel", "expected"),
    [
        (
            "M",
            pd.DataFrame(
                {
                    "left": [np.nan, 1.0],
                    "right": [2.0, np.nan],
                },
                index=pd.to_datetime(["2024-01-31", "2024-01-05"]),
            ),
            pd.DataFrame(
                {"left": [1.0], "right": [2.0]},
                index=pd.date_range("2024-01-31", periods=1, freq="ME"),
            ),
        ),
        (
            "Y",
            pd.DataFrame(
                {
                    "left": [1.0, np.nan],
                    "right": [np.nan, 2.0],
                },
                index=pd.Index([2020, 2020]),
            ),
            pd.DataFrame(
                {"left": [1.0], "right": [2.0]},
                index=pd.Index([2020], name="year"),
            ),
        ),
    ],
)
def test_legacy_regularize_panel_preserves_columnwise_last_non_null_behavior(
    monkeypatch: pytest.MonkeyPatch,
    frequency: str,
    panel: pd.DataFrame,
    expected: pd.DataFrame,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(project_root / "scripts"))
    legacy_module = import_module("cycle_realtime_core")

    result = legacy_module.regularize_panel(panel, frequency)

    pd.testing.assert_frame_equal(result, expected)


def test_legacy_module_bootstraps_repo_src_without_pythonpath() -> None:
    project_root = Path(__file__).resolve().parents[3]
    scripts_directory = project_root / "scripts"
    source_directory = project_root / "src"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    code = f"""
import importlib.abc
from pathlib import Path
import sys

source_directory = {str(source_directory)!r}
source_path = Path(source_directory).resolve()
sys.path[:] = [
    entry
    for entry in sys.path
    if Path(entry or ".").resolve() != source_path
]

class RequireRepoSource(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "seven_cycle_platform" and source_directory not in sys.path:
            raise ModuleNotFoundError("repo src was not bootstrapped")
        return None

sys.meta_path.insert(0, RequireRepoSource())
sys.path.insert(0, {str(scripts_directory)!r})
import cycle_realtime_core
print(cycle_realtime_core.ROOT)
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(project_root)


def test_expanding_standardize_uses_only_lagged_observations() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0], name="signal")

    result = expanding_standardize(values, min_periods=2)

    expected = pd.Series(
        [
            np.nan,
            np.nan,
            3.0,
            (4.0 - 2.0) / np.sqrt(2.0 / 3.0),
        ],
        name="signal",
    )
    pd.testing.assert_series_equal(result, expected)


def test_expanding_standardize_propagates_missingness_and_future_is_invariant() -> None:
    history = pd.Series(
        [1.0, np.nan, 3.0, 4.0, np.nan, 6.0],
        index=pd.RangeIndex(6, name="sample"),
        name="signal",
    )
    future = pd.Series(
        [1_000_000.0, -1_000_000.0, np.nan],
        index=pd.RangeIndex(6, 9, name="sample"),
        name="signal",
    )

    history_result = expanding_standardize(history, min_periods=2, clip=4.0)
    full_result = expanding_standardize(
        pd.concat([history, future]),
        min_periods=2,
        clip=4.0,
    )

    pd.testing.assert_series_equal(
        history_result,
        full_result.loc[history.index],
        check_exact=True,
    )
    assert history_result.isna().tolist() == [True, True, True, False, True, False]


def test_expanding_standardize_zero_variance_and_symmetric_clipping() -> None:
    zero_variance = expanding_standardize(
        pd.Series([2.0, 2.0, 3.0]),
        min_periods=2,
    )
    clipped = expanding_standardize(
        pd.Series([-1.0, 1.0, 100.0, -1_000.0]),
        min_periods=2,
        clip=1.0,
    )

    assert np.isnan(zero_variance.iloc[2])
    assert clipped.iloc[2] == 1.0
    assert clipped.iloc[3] == -1.0


@pytest.mark.parametrize("min_periods", [0, -1, 1.5, True])
def test_expanding_standardize_validates_min_periods(min_periods: object) -> None:
    with pytest.raises((TypeError, ValueError), match="min_periods"):
        expanding_standardize(pd.Series([1.0, 2.0]), min_periods=min_periods)


@pytest.mark.parametrize("clip", [0.0, -1.0, np.nan, np.inf, "six"])
def test_expanding_standardize_validates_clip(clip: object) -> None:
    with pytest.raises((TypeError, ValueError), match="clip"):
        expanding_standardize(pd.Series([1.0, 2.0]), min_periods=1, clip=clip)
