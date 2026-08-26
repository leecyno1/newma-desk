from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.refresh_research_current_panel import (
    _commodity_price_monthly,
    _fred_monthly_level,
    _linear_proxy_extension,
    _merge_level_variants,
    _normalize_monthly_panel,
    _pmi_history_start,
)


def test_commodity_price_monthly_uses_last_daily_value() -> None:
    frame = pd.DataFrame(
        {
            "日期": ["2026-07-01", "2026-07-31", "2026-08-01"],
            "最新值": [1000, 1020, 1025],
        }
    )

    result = _commodity_price_monthly(frame)

    assert result.loc[pd.Timestamp("2026-07-31")] == 1020
    assert result.loc[pd.Timestamp("2026-08-31")] == 1025


def test_merge_level_variants_updates_only_supplied_months() -> None:
    index = pd.date_range("2024-01-31", "2025-03-31", freq="ME")
    panel = pd.DataFrame(
        {
            "TEST_LEVEL": range(100, 115),
            "TEST_MOM": 0.0,
            "TEST_YOY": 0.0,
        },
        index=index,
    )
    update_index = pd.date_range("2025-01-31", "2025-03-31", freq="ME")
    update = pd.Series([224.0, 336.0, 504.0], index=update_index)

    result = _merge_level_variants(panel.copy(), "TEST", update, change_mode="pct")

    assert result.loc[pd.Timestamp("2024-12-31"), "TEST_LEVEL"] == 111
    assert result.loc[pd.Timestamp("2025-01-31"), "TEST_LEVEL"] == 224
    assert result.loc[pd.Timestamp("2025-02-28"), "TEST_MOM"] == 0.5
    assert result.loc[pd.Timestamp("2025-01-31"), "TEST_YOY"] == pytest.approx(1.24)


def test_merge_level_variants_supports_rate_differences() -> None:
    index = pd.date_range("2025-01-31", "2025-03-31", freq="ME")
    panel = pd.DataFrame(
        {"RATE_LEVEL": [2.0, 2.1, 2.2], "RATE_MOM": 0.0, "RATE_YOY": 0.0},
        index=index,
    )
    update = pd.Series([2.4], index=[pd.Timestamp("2025-04-30")])

    result = _merge_level_variants(panel, "RATE", update, change_mode="diff")

    assert result.loc[pd.Timestamp("2025-04-30"), "RATE_MOM"] == pytest.approx(0.2)


def test_linear_proxy_extension_only_fills_missing_tail() -> None:
    index = pd.date_range("2018-01-31", "2024-12-31", freq="ME")
    parent = pd.Series(range(len(index)), index=index, dtype=float)
    target = 40.0 + 0.5 * parent
    direct_end = pd.Timestamp("2023-12-31")
    target.loc[target.index > direct_end] = float("nan")
    panel = pd.DataFrame(
        {
            "TARGET_LEVEL": target,
            "TARGET_MOM": float("nan"),
            "TARGET_YOY": float("nan"),
            "PARENT_LEVEL": parent,
        },
        index=index,
    )

    result, audit = _linear_proxy_extension(
        panel,
        target_column="TARGET_LEVEL",
        parent_column="PARENT_LEVEL",
        direct_end=direct_end,
        through=pd.Timestamp("2024-12-31"),
    )

    assert result.loc[direct_end, "TARGET_LEVEL"] == 75.5
    assert result.loc[pd.Timestamp("2024-12-31"), "TARGET_LEVEL"] == pytest.approx(81.5)
    assert audit is not None
    assert audit["identity"] == "explicit_statistical_proxy"
    assert audit["proxyObservations"] == 12
    assert audit["r2"] == pytest.approx(1.0)


def test_pmi_history_start_preserves_retired_subindex_identity() -> None:
    result = _pmi_history_start(
        pd.Timestamp("2025-01-31"),
        pd.Timestamp("2026-07-31"),
    )

    assert result == pd.Timestamp("2011-07-31")


def test_normalize_monthly_panel_coalesces_business_and_calendar_month_end() -> None:
    panel = pd.DataFrame(
        {
            "A": [1.0, float("nan")],
            "B": [float("nan"), 2.0],
        },
        index=[pd.Timestamp("2025-05-30"), pd.Timestamp("2025-05-31")],
    )

    result, duplicate_rows = _normalize_monthly_panel(panel)

    assert duplicate_rows == 1
    assert list(result.index) == [pd.Timestamp("2025-05-31")]
    assert result.iloc[0].to_dict() == {"A": 1.0, "B": 2.0}


def test_fred_monthly_level_rejects_unknown_aggregation() -> None:
    with pytest.raises(ValueError, match="Unsupported FRED aggregation"):
        _fred_monthly_level(
            "TEST",
            start=pd.Timestamp("2025-01-01"),
            through=pd.Timestamp("2025-12-31"),
            aggregation="median",
        )
