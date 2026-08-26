from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import ValidationError
import pytest

from seven_cycle_platform.data.legacy_adapters import (
    LegacyObservationBatch,
    adapt_annual_panel,
    adapt_monthly_panel,
)
from seven_cycle_platform.data.observations import ReleaseRule
from seven_cycle_platform.types import VintageKind


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REAL_MONTHLY_PANEL = PROJECT_ROOT / "data" / "research_input_monthly_macro.parquet"
RETRIEVAL_TIME = datetime(2026, 7, 12, 9, tzinfo=timezone.utc)


def _rule(
    entity_id: str,
    *,
    lag_days: int = 10,
    vintage_kind: VintageKind = VintageKind.PSEUDO_VINTAGE,
) -> ReleaseRule:
    return ReleaseRule(
        entity_id=entity_id,
        source="legacy_research_panel",
        unit="percent",
        publication_lag_days=lag_days,
        vintage_kind=vintage_kind,
        quality_status="legacy_panel",
        revision_number=0,
    )


def test_monthly_panel_emits_one_observation_per_non_null_cell() -> None:
    index = pd.DatetimeIndex(["2024-01-31", "2024-02-29"])
    panel = pd.DataFrame(
        {
            "cpi": [0.7, np.nan],
            "industrial_output": [pd.NA, 6.8],
        },
        index=index,
    )

    batch = adapt_monthly_panel(
        panel,
        release_rules={
            "cpi": _rule("cn_cpi", lag_days=9),
            "industrial_output": _rule("cn_industrial_output", lag_days=12),
        },
        retrieval_time=RETRIEVAL_TIME,
    )

    assert isinstance(batch, LegacyObservationBatch)
    assert len(batch.observations) == 2
    cpi, industrial_output = batch.observations
    assert cpi.entity_id == "cn_cpi"
    assert cpi.observation_date == date(2024, 1, 31)
    assert cpi.release_date == date(2024, 2, 9)
    assert cpi.vintage_date == RETRIEVAL_TIME.date()
    assert cpi.value == pytest.approx(0.7)
    assert cpi.retrieval_time == RETRIEVAL_TIME
    assert industrial_output.entity_id == "cn_industrial_output"
    assert industrial_output.observation_date == date(2024, 2, 29)
    assert industrial_output.release_date == date(2024, 3, 12)
    assert industrial_output.value == pytest.approx(6.8)


def test_annual_panel_maps_integer_years_to_year_end_dates() -> None:
    panel = pd.DataFrame(
        {"gdp": [5.2, np.nan, 5.0]},
        index=pd.Index([2022, 2023, 2024]),
    )

    batch = adapt_annual_panel(
        panel,
        release_rules={"gdp": _rule("cn_gdp", lag_days=90)},
        retrieval_time=RETRIEVAL_TIME,
    )

    assert [item.observation_date for item in batch.observations] == [
        date(2022, 12, 31),
        date(2024, 12, 31),
    ]
    assert [item.release_date for item in batch.observations] == [
        date(2022, 12, 31) + timedelta(days=90),
        date(2024, 12, 31) + timedelta(days=90),
    ]


def test_adapter_requires_a_release_rule_for_every_panel_column() -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7], "gdp": [5.2]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )

    with pytest.raises(ValueError, match="Missing release rules.*gdp"):
        adapt_monthly_panel(
            panel,
            release_rules={"cpi": _rule("cn_cpi")},
            retrieval_time=RETRIEVAL_TIME,
        )


@pytest.mark.parametrize(
    "vintage_kind",
    [VintageKind.REALTIME, VintageKind.LATEST_HISTORICAL],
)
@pytest.mark.parametrize("strict_vintage", [False, True])
def test_legacy_adapter_rejects_non_pseudo_release_rules_in_all_modes(
    vintage_kind: VintageKind,
    strict_vintage: bool,
) -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )

    with pytest.raises(
        ValueError,
        match=(
            "Legacy adapters require pseudo_vintage.*"
            f"cn_cpi.*{vintage_kind.value}"
        ),
    ):
        adapt_monthly_panel(
            panel,
            release_rules={
                "cpi": _rule("cn_cpi", vintage_kind=vintage_kind)
            },
            retrieval_time=RETRIEVAL_TIME,
            strict_vintage=strict_vintage,
        )


def test_pseudo_vintage_conversion_emits_a_human_readable_caveat() -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )

    batch = adapt_monthly_panel(
        panel,
        release_rules={"cpi": _rule("cn_cpi")},
        retrieval_time=RETRIEVAL_TIME,
    )

    assert batch.observations[0].vintage_kind == "pseudo_vintage"
    assert batch.caveats
    assert "pseudo-vintage" in batch.caveats[0].lower()
    assert "cn_cpi" in batch.caveats[0]


def test_adapter_uses_the_utc_retrieval_date_as_vintage_date() -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )
    retrieval_time = datetime(
        2024,
        2,
        11,
        1,
        tzinfo=timezone(timedelta(hours=8)),
    )

    batch = adapt_monthly_panel(
        panel,
        release_rules={"cpi": _rule("cn_cpi", lag_days=9)},
        retrieval_time=retrieval_time,
    )

    observation = batch.observations[0]
    assert observation.release_date == date(2024, 2, 9)
    assert observation.vintage_date == date(2024, 2, 10)
    assert observation.retrieval_time == datetime(
        2024,
        2,
        10,
        17,
        tzinfo=timezone.utc,
    )


def test_adapter_rejects_retrieval_before_synthetic_release_date() -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )
    retrieval_time = datetime(2024, 2, 9, 23, 59, tzinfo=timezone.utc)

    with pytest.raises(
        ValueError,
        match=(
            "cn_cpi.*retrieval date 2024-02-09 precedes "
            "synthetic release date 2024-02-10"
        ),
    ):
        adapt_monthly_panel(
            panel,
            release_rules={"cpi": _rule("cn_cpi", lag_days=10)},
            retrieval_time=retrieval_time,
        )


def test_strict_vintage_mode_rejects_pseudo_vintage_rules() -> None:
    panel = pd.DataFrame(
        {"cpi": [0.7]},
        index=pd.DatetimeIndex(["2024-01-31"]),
    )

    with pytest.raises(ValueError, match="strict vintage.*cn_cpi.*pseudo-vintage"):
        adapt_monthly_panel(
            panel,
            release_rules={"cpi": _rule("cn_cpi")},
            retrieval_time=RETRIEVAL_TIME,
            strict_vintage=True,
        )


def test_legacy_observation_batch_is_immutable() -> None:
    batch = LegacyObservationBatch(observations=(), caveats=())

    with pytest.raises(ValidationError, match="frozen_instance"):
        batch.caveats = ("changed",)


def test_real_monthly_panel_slice_is_explicitly_pseudo_vintage() -> None:
    column = "CN_CPI_CNT_YOY"
    panel = pd.read_parquet(REAL_MONTHLY_PANEL, columns=[column]).iloc[:3]

    batch = adapt_monthly_panel(
        panel,
        release_rules={column: _rule("cn_cpi_county_yoy", lag_days=10)},
        retrieval_time=RETRIEVAL_TIME,
    )

    assert len(batch.observations) == int(panel[column].notna().sum())
    assert batch.observations
    assert all(
        observation.vintage_kind == "pseudo_vintage"
        for observation in batch.observations
    )
    assert all(
        observation.observation_date == timestamp.date()
        for observation, timestamp in zip(
            batch.observations,
            panel.index[panel[column].notna()],
            strict=True,
        )
    )
    assert any("pseudo-vintage" in caveat.lower() for caveat in batch.caveats)
