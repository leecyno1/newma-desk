from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backtest.loaders._fundamental_schema import (
    DERIVED_FIELDS,
    RAW_FIELDS,
    SEC_CONCEPT_MAP,
    list_supported_fields,
    resolve_field,
)


EXPECTED_RAW_FIELDS = {
    "revenue",
    "cogs",
    "gross_profit",
    "operating_income",
    "net_income",
    "total_assets",
    "total_equity",
    "total_debt",
    "cash",
    "shares_diluted",
    "cfo",
    "capex",
}


def test_raw_field_schema_and_sec_map_cover_all_raw_fields() -> None:
    assert set(RAW_FIELDS) == EXPECTED_RAW_FIELDS
    assert set(SEC_CONCEPT_MAP) == EXPECTED_RAW_FIELDS

    for field, spec in RAW_FIELDS.items():
        assert spec["statement"]
        assert spec["description"]
        assert SEC_CONCEPT_MAP[field], field


def test_revenue_concept_priority_keeps_new_standard_first() -> None:
    assert SEC_CONCEPT_MAP["revenue"][:4] == [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ]


def test_sec_revenue_fixture_shapes_cover_new_and_old_standard() -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "sec"
    aapl_like = json.loads((fixture_dir / "aapl_like_companyfacts.json").read_text())
    old_standard = json.loads((fixture_dir / "old_standard_companyfacts.json").read_text())

    aapl_concepts = aapl_like["facts"]["us-gaap"]
    old_concepts = old_standard["facts"]["us-gaap"]

    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in aapl_concepts
    assert "Revenues" not in aapl_concepts
    assert "Revenues" in old_concepts
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" not in old_concepts


def test_derived_formulas_are_numerically_correct() -> None:
    idx = pd.to_datetime(["2022-12-31", "2023-12-31"])
    data = {
        "gross_profit": pd.Series([40.0, 60.0], index=idx),
        "net_income": pd.Series([10.0, 15.0], index=idx),
        "total_assets": pd.Series([200.0, 250.0], index=idx),
        "total_equity": pd.Series([50.0, 75.0], index=idx),
        "total_debt": pd.Series([100.0, 125.0], index=idx),
        "cfo": pd.Series([7.0, 12.0], index=idx),
    }

    expected = {
        "roe": pd.Series([0.2, 0.2], index=idx),
        "roa": pd.Series([0.05, 0.06], index=idx),
        "gross_profitability": pd.Series([0.2, 0.24], index=idx),
        "accruals": pd.Series([0.015, 0.012], index=idx),
        "leverage": pd.Series([2.0, 125.0 / 75.0], index=idx),
    }

    for field, expected_series in expected.items():
        result = DERIVED_FIELDS[field]["compute"](data)
        pd.testing.assert_series_equal(result, expected_series, check_names=False)


def test_asset_growth_uses_annual_period_over_period_semantics() -> None:
    idx = pd.to_datetime(["2021-12-31", "2022-12-31", "2023-12-31"])
    data = {"total_assets": pd.Series([100.0, 120.0, 90.0], index=idx)}

    result = DERIVED_FIELDS["asset_growth"]["compute"](data)
    expected = pd.Series([float("nan"), 0.2, -0.25], index=idx)

    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_resolve_field_and_list_supported_fields() -> None:
    kind, raw_spec = resolve_field("revenue")
    assert kind == "raw"
    assert raw_spec is RAW_FIELDS["revenue"]

    kind, derived_spec = resolve_field("roe")
    assert kind == "derived"
    assert derived_spec is DERIVED_FIELDS["roe"]

    supported = list_supported_fields()
    assert supported == sorted(set(RAW_FIELDS) | set(DERIVED_FIELDS))

    with pytest.raises(ValueError, match="unknown fundamental field"):
        resolve_field("earnings_yield")
