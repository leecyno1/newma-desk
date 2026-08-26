from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from seven_cycle_platform.cycles import SevenCycleEngine
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.types import VintageKind


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = PROJECT_ROOT / "config" / "seven_cycle"
RETRIEVAL_TIME = datetime(2026, 7, 12, 8, tzinfo=timezone.utc)
ANNUAL_CATEGORIES = {
    "annual_alpha": "growth",
    "annual_beta": "inflation",
    "annual_gamma": "credit",
}
MONTHLY_CATEGORIES = {
    "monthly_alpha": "growth",
    "monthly_beta": "inflation",
    "monthly_gamma": "credit",
}
RECONSTRUCTION_COLUMNS = [
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    "frequency",
    "angle",
    "phase",
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "innovation",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
    "evidence_level",
    "usage_status",
    "effective_cycles",
    "observed_observations",
    "member_breadth",
    "category_breadth",
    "total_members",
    "total_categories",
]
NUMERIC_RECONSTRUCTION_COLUMNS = [
    "angle",
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "innovation",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
    "effective_cycles",
    "observed_observations",
    "member_breadth",
    "category_breadth",
    "total_members",
    "total_categories",
]
EXACT_RECONSTRUCTION_COLUMNS = [
    column
    for column in RECONSTRUCTION_COLUMNS
    if column not in NUMERIC_RECONSTRUCTION_COLUMNS
]


def _observation(
    *,
    entity_id: str,
    observation_date: date,
    release_date: date,
    value: float,
    revision_number: int = 0,
    vintage_date: date | None = None,
    retrieval_time: datetime = RETRIEVAL_TIME,
    vintage_kind: VintageKind = VintageKind.REALTIME,
) -> Observation:
    return Observation(
        entity_id=entity_id,
        observation_date=observation_date,
        release_date=release_date,
        vintage_date=vintage_date or release_date,
        value=value,
        unit="index_points",
        source="synthetic_archive",
        retrieval_time=retrieval_time,
        revision_number=revision_number,
        quality_status="accepted",
        vintage_kind=vintage_kind,
    )


def _synthetic_archive() -> tuple[Observation, ...]:
    records: list[Observation] = []
    annual_entities = tuple(ANNUAL_CATEGORIES)
    for year in range(1870, 2023):
        observation_date = date(year, 12, 31)
        release_date = observation_date + timedelta(days=90)
        time = float(year - 1870)
        values = (
            np.sin(2.0 * np.pi * time / 9.0)
            + 0.35 * np.sin(2.0 * np.pi * time / 14.0),
            np.cos(2.0 * np.pi * time / 16.0)
            + 0.20 * np.sin(2.0 * np.pi * time / 45.0),
            np.sin(2.0 * np.pi * time / 11.0 + 0.4),
        )
        records.extend(
            _observation(
                entity_id=entity_id,
                observation_date=observation_date,
                release_date=release_date,
                value=float(value),
            )
            for entity_id, value in zip(annual_entities, values, strict=True)
        )

    monthly_entities = tuple(MONTHLY_CATEGORIES)
    monthly_dates = pd.date_range("1990-01-31", "2022-12-31", freq="ME")
    for position, timestamp in enumerate(monthly_dates):
        observation_date = timestamp.date()
        release_date = observation_date + timedelta(days=10)
        time = float(position)
        values = (
            np.sin(2.0 * np.pi * time / 42.0)
            + 0.45 * np.sin(2.0 * np.pi * time / 21.0),
            np.cos(2.0 * np.pi * time / 30.0)
            + 0.15 * np.sin(2.0 * np.pi * time / 6.0),
            np.sin(2.0 * np.pi * time / 15.0 + 0.6),
        )
        records.extend(
            _observation(
                entity_id=entity_id,
                observation_date=observation_date,
                release_date=release_date,
                value=float(value),
            )
            for entity_id, value in zip(monthly_entities, values, strict=True)
        )

    records.extend(
        [
            _observation(
                entity_id="annual_alpha",
                observation_date=date(2010, 12, 31),
                release_date=date(2011, 3, 31),
                vintage_date=date(2016, 1, 15),
                revision_number=1,
                value=1.2345,
            ),
            _observation(
                entity_id="annual_alpha",
                observation_date=date(2010, 12, 31),
                release_date=date(2011, 3, 31),
                vintage_date=date(2020, 1, 15),
                revision_number=2,
                value=-9.0,
            ),
            _observation(
                entity_id="monthly_alpha",
                observation_date=date(2017, 1, 31),
                release_date=date(2017, 2, 10),
                vintage_date=date(2018, 3, 15),
                revision_number=1,
                value=0.8765,
            ),
            _observation(
                entity_id="monthly_alpha",
                observation_date=date(2017, 1, 31),
                release_date=date(2017, 2, 10),
                vintage_date=date(2019, 3, 15),
                revision_number=2,
                value=-8.0,
            ),
        ]
    )
    return tuple(records)


@pytest.fixture(scope="module")
def archive() -> tuple[Observation, ...]:
    return _synthetic_archive()


@pytest.fixture(scope="module")
def engine() -> SevenCycleEngine:
    return SevenCycleEngine(load_registry_bundle(REGISTRY_DIR).cycles)


def test_reader_uses_release_and_vintage_timing_not_retrieval_time(
    archive: tuple[Observation, ...],
) -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    cutoff = date(2018, 6, 30)
    selection = read_vintage(archive, as_of=cutoff, strict=True)
    selected = {
        (record.entity_id, record.observation_date): record
        for record in selection.observations
    }

    annual_revision = selected[("annual_alpha", date(2010, 12, 31))]
    monthly_revision = selected[("monthly_alpha", date(2017, 1, 31))]
    assert annual_revision.revision_number == 1
    assert monthly_revision.revision_number == 1
    assert annual_revision.retrieval_time.date() > cutoff
    assert monthly_revision.retrieval_time.date() > cutoff
    assert selection.vintage is VintageKind.REALTIME
    assert selection.caveats == ()


def test_reader_uses_retrieval_only_for_equivalent_reingestion_ties() -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    first = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.5,
        retrieval_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    later_reingestion = first.model_copy(
        update={
            "retrieval_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
    )

    selection = read_vintage(
        [later_reingestion, first],
        as_of=date(2024, 12, 31),
        strict=True,
    )

    assert selection.observations == (later_reingestion,)


def test_reader_rejects_conflicting_duplicate_revisions() -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    first = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.5,
    )
    conflict = first.model_copy(
        update={
            "value": 1.6,
            "retrieval_time": datetime(2026, 7, 12, 9, tzinfo=timezone.utc),
        }
    )

    with pytest.raises(ValueError, match="ambiguous duplicate revision"):
        read_vintage(
            [first, conflict],
            as_of=date(2024, 12, 31),
            strict=True,
        )


def test_pseudo_vintage_is_rejected_in_strict_mode_and_caveated_otherwise() -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    pseudo = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        vintage_date=date(2024, 2, 10),
        value=1.5,
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
    )

    with pytest.raises(ValueError, match="strict vintage.*pseudo_vintage"):
        read_vintage([pseudo], as_of=date(2024, 12, 31), strict=True)

    selection = read_vintage(
        [pseudo],
        as_of=date(2024, 12, 31),
        strict=False,
    )

    assert selection.vintage is VintageKind.PSEUDO_VINTAGE
    assert selection.observations == (pseudo,)
    assert selection.caveats
    assert "pseudo-vintage" in selection.caveats[0].lower()
    assert "monthly_alpha" in selection.caveats[0]


def test_latest_historical_and_realtime_are_selected_as_separate_views() -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    realtime = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.5,
    )
    latest = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        vintage_date=date(2024, 6, 30),
        revision_number=1,
        value=2.5,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
    )

    realtime_view = read_vintage(
        [latest, realtime],
        as_of=date(2024, 12, 31),
        strict=True,
    )
    latest_view = read_vintage(
        [latest, realtime],
        as_of=date(2024, 12, 31),
        strict=True,
        interpretation=VintageKind.LATEST_HISTORICAL,
    )

    assert realtime_view.vintage is VintageKind.REALTIME
    assert latest_view.vintage is VintageKind.LATEST_HISTORICAL
    assert realtime_view.observations[0].value == 1.5
    assert latest_view.observations[0].value == 2.5


@pytest.mark.parametrize(
    ("field_updates", "expected_message"),
    [
        ({"release_date": date(2024, 7, 1)}, "visible.*release_date"),
        ({"vintage_date": date(2024, 7, 1)}, "visible.*vintage_date"),
    ],
)
def test_vintage_selection_constructor_rejects_future_visible_rows(
    field_updates: dict[str, object],
    expected_message: str,
) -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    observation = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
    ).model_copy(update=field_updates)

    with pytest.raises(ValueError, match=expected_message):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.REALTIME,
            observations=[observation],
            caveats=[],
        )


def test_vintage_selection_constructor_rejects_pseudo_labeled_realtime() -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    pseudo = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
    )

    with pytest.raises(ValueError, match="REALTIME.*only REALTIME"):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.REALTIME,
            observations=[pseudo],
            caveats=["pseudo-vintage evidence"],
        )


@pytest.mark.parametrize(
    ("selection_vintage", "row_vintage", "expected_message"),
    [
        (
            VintageKind.LATEST_HISTORICAL,
            VintageKind.REALTIME,
            "LATEST_HISTORICAL.*only LATEST_HISTORICAL",
        ),
        (
            VintageKind.REALTIME,
            VintageKind.LATEST_HISTORICAL,
            "REALTIME.*only REALTIME",
        ),
    ],
)
def test_vintage_selection_constructor_rejects_latest_realtime_mismatches(
    selection_vintage: VintageKind,
    row_vintage: VintageKind,
    expected_message: str,
) -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    observation = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
        vintage_kind=row_vintage,
    )

    with pytest.raises(ValueError, match=expected_message):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=selection_vintage,
            observations=[observation],
            caveats=[],
        )


def test_vintage_selection_constructor_rejects_latest_historical_caveats() -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    latest = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
    )

    with pytest.raises(ValueError, match="LATEST_HISTORICAL.*caveats"):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.LATEST_HISTORICAL,
            observations=[latest],
            caveats=["pseudo-vintage evidence"],
        )


def test_vintage_selection_constructor_accepts_canonical_mixed_pseudo_view() -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    realtime = _observation(
        entity_id="z_realtime",
        observation_date=date(2024, 2, 29),
        release_date=date(2024, 3, 10),
        value=2.0,
    )
    pseudo = _observation(
        entity_id="a_pseudo",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
    )
    source_observations = [realtime, pseudo]
    source_caveats = [" z caveat ", "a caveat"]

    selection = VintageSelection(
        as_of=date(2024, 6, 30),
        vintage=VintageKind.PSEUDO_VINTAGE,
        observations=source_observations,
        caveats=source_caveats,
    )
    source_observations.clear()
    source_caveats.clear()

    assert isinstance(selection.observations, tuple)
    assert isinstance(selection.caveats, tuple)
    assert [record.entity_id for record in selection.observations] == [
        "a_pseudo",
        "z_realtime",
    ]
    assert selection.caveats == ("a caveat", "z caveat")


def test_vintage_selection_constructor_rejects_duplicate_entity_dates() -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    initial = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
    )
    revision = initial.model_copy(
        update={
            "vintage_date": date(2024, 3, 15),
            "revision_number": 1,
            "value": 1.1,
        }
    )

    with pytest.raises(ValueError, match="one observation.*entity_id.*date"):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.REALTIME,
            observations=[revision, initial],
            caveats=[],
        )


def test_vintage_selection_constructor_rejects_invalid_pseudo_semantics() -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    realtime = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
    )
    latest = realtime.model_copy(
        update={"vintage_kind": VintageKind.LATEST_HISTORICAL}
    )

    with pytest.raises(ValueError, match="PSEUDO_VINTAGE.*at least one PSEUDO"):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.PSEUDO_VINTAGE,
            observations=[realtime],
            caveats=["pseudo-vintage evidence"],
        )
    with pytest.raises(ValueError, match="PSEUDO_VINTAGE.*LATEST_HISTORICAL"):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=VintageKind.PSEUDO_VINTAGE,
            observations=[latest],
            caveats=["pseudo-vintage evidence"],
        )


@pytest.mark.parametrize(
    "vintage",
    [
        VintageKind.REALTIME,
        VintageKind.LATEST_HISTORICAL,
        VintageKind.PSEUDO_VINTAGE,
    ],
)
def test_vintage_selection_empty_views_preserve_requested_vintage(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    selection = VintageSelection(
        as_of=date(2024, 6, 30),
        vintage=vintage,
        observations=[],
        caveats=[],
    )

    assert selection.vintage is vintage
    assert selection.observations == ()
    assert selection.caveats == ()


@pytest.mark.parametrize(
    "vintage",
    [VintageKind.EXPLICIT_PROXY, VintageKind.UNAVAILABLE],
)
def test_vintage_selection_rejects_data_identity_kinds_even_when_empty(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.cycles.vintage import VintageSelection

    with pytest.raises(
        ValueError,
        match=rf"cycle vintage selection.*{vintage.value}",
    ):
        VintageSelection(
            as_of=date(2024, 6, 30),
            vintage=vintage,
            observations=[],
            caveats=[],
        )


@pytest.mark.parametrize(
    "vintage",
    [VintageKind.EXPLICIT_PROXY, VintageKind.UNAVAILABLE],
)
def test_reader_rejects_data_identity_interpretations_with_empty_records(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    with pytest.raises(
        ValueError,
        match=rf"cycle vintage interpretation.*{vintage.value}",
    ):
        read_vintage(
            [],
            as_of=date(2024, 6, 30),
            interpretation=vintage,
        )


@pytest.mark.parametrize(
    "vintage",
    [VintageKind.EXPLICIT_PROXY, VintageKind.UNAVAILABLE],
)
def test_reader_rejects_data_identity_observation_kinds(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    observation = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2024, 1, 31),
        release_date=date(2024, 2, 10),
        value=1.0,
    ).model_copy(update={"vintage_kind": vintage})

    with pytest.raises(
        ValueError,
        match=rf"cycle vintage records.*{vintage.value}",
    ):
        read_vintage(
            [observation],
            as_of=date(2024, 6, 30),
            interpretation=VintageKind.REALTIME,
        )


@pytest.mark.parametrize(
    ("cutoff", "dates"),
    [
        (
            date(2018, 12, 31),
            [date(year, 12, 31) for year in range(2014, 2019)],
        ),
        (
            date(2018, 6, 30),
            [timestamp.date() for timestamp in pd.date_range(
                "2018-01-31",
                "2018-06-30",
                freq="ME",
            )],
        ),
    ],
)
def test_full_archive_and_truncated_archive_reconstruct_exact_realtime_states(
    archive: tuple[Observation, ...],
    engine: SevenCycleEngine,
    cutoff: date,
    dates: list[date],
) -> None:
    from seven_cycle_platform.cycles.vintage import reconstruct_cycle_vintage

    truncated_archive = tuple(
        record
        for record in archive
        if record.release_date <= cutoff and record.vintage_date <= cutoff
    )
    annual_categories_before = dict(ANNUAL_CATEGORIES)
    monthly_categories_before = dict(MONTHLY_CATEGORIES)
    arguments = {
        "engine": engine,
        "annual_categories": ANNUAL_CATEGORIES,
        "monthly_categories": MONTHLY_CATEGORIES,
        "as_of": dates,
        "strict": True,
    }

    full = reconstruct_cycle_vintage(archive, **arguments)
    truncated = reconstruct_cycle_vintage(truncated_archive, **arguments)
    repeat = reconstruct_cycle_vintage(archive, **arguments)

    assert ANNUAL_CATEGORIES == annual_categories_before
    assert MONTHLY_CATEGORIES == monthly_categories_before
    pd.testing.assert_frame_equal(full, repeat, check_exact=True)
    assert list(full.columns) == RECONSTRUCTION_COLUMNS
    assert list(truncated.columns) == RECONSTRUCTION_COLUMNS
    assert full.columns.equals(truncated.columns)
    assert set(full["vintage"]) == {VintageKind.REALTIME.value}
    assert full["vintage_caveat"].isna().all()
    assert len(full) == 7 * len(dates)
    assert len(truncated) == 7 * len(dates)
    expected_cycle_ids = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    for states in (full, truncated):
        assert states.groupby("date", sort=False).size().eq(7).all()
        assert states.groupby("date", sort=False)["cycle_id"].agg(list).eq(
            [expected_cycle_ids] * len(dates)
        ).all()

    key_columns = ["date", "cycle_id", "vintage"]
    full = full.sort_values(key_columns).reset_index(drop=True)
    truncated = truncated.sort_values(key_columns).reset_index(drop=True)

    pd.testing.assert_frame_equal(
        full[key_columns],
        truncated[key_columns],
        check_exact=True,
    )
    assert full[["level", "slope", "angle"]].notna().any().all()
    pd.testing.assert_frame_equal(
        full[EXACT_RECONSTRUCTION_COLUMNS],
        truncated[EXACT_RECONSTRUCTION_COLUMNS],
        check_exact=True,
    )
    for field in NUMERIC_RECONSTRUCTION_COLUMNS:
        actual = full[field].to_numpy(dtype="float64")
        expected = truncated[field].to_numpy(dtype="float64")
        assert np.isnan(actual).tolist() == np.isnan(expected).tolist()
        np.testing.assert_allclose(
            actual,
            expected,
            rtol=0.0,
            atol=1e-10,
            equal_nan=True,
        )


def test_latest_historical_and_realtime_publish_as_distinct_vintage_views(
    archive: tuple[Observation, ...],
    engine: SevenCycleEngine,
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.cycles.vintage import reconstruct_cycle_vintage
    from seven_cycle_platform.products.cycle_phase import (
        CYCLE_PHASE_VINTAGE_FILENAME,
        build_cycle_phase_vintage,
        write_cycle_phase_vintage,
    )
    from seven_cycle_platform.storage import RunContext, publish_run
    from seven_cycle_platform.storage.manifest import sha256_file

    cutoff = date(2018, 6, 30)
    latest_historical = tuple(
        record.model_copy(
            update={"vintage_kind": VintageKind.LATEST_HISTORICAL}
        )
        for record in archive
    )
    revised_latest = _observation(
        entity_id="monthly_alpha",
        observation_date=date(2012, 5, 31),
        release_date=date(2012, 6, 10),
        vintage_date=date(2018, 1, 15),
        revision_number=1,
        value=25.0,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
    )
    combined_archive = (*archive, *latest_historical, revised_latest)
    arguments = {
        "engine": engine,
        "annual_categories": ANNUAL_CATEGORIES,
        "monthly_categories": MONTHLY_CATEGORIES,
        "as_of": cutoff,
        "strict": True,
    }

    realtime = reconstruct_cycle_vintage(combined_archive, **arguments)
    latest = reconstruct_cycle_vintage(
        combined_archive,
        interpretation=VintageKind.LATEST_HISTORICAL,
        **arguments,
    )

    assert set(realtime["vintage"]) == {VintageKind.REALTIME.value}
    assert set(latest["vintage"]) == {VintageKind.LATEST_HISTORICAL.value}
    paired_states = realtime.merge(
        latest,
        on=["date", "cycle_id"],
        suffixes=("_realtime", "_latest"),
        validate="one_to_one",
    )
    differing_fields = []
    for field in [
        "angle",
        "level",
        "slope",
        "amplitude",
        "uncertainty",
        "confidence",
    ]:
        realtime_values = paired_states[f"{field}_realtime"].to_numpy(
            dtype="float64"
        )
        latest_values = paired_states[f"{field}_latest"].to_numpy(
            dtype="float64"
        )
        differing_fields.append(
            bool(
                (~np.isclose(
                    realtime_values,
                    latest_values,
                    rtol=0.0,
                    atol=1e-10,
                    equal_nan=True,
                )).any()
            )
        )
    assert any(differing_fields)

    context = RunContext.create(
        as_of=cutoff,
        data_vintage=cutoff,
        model_version="seven-cycle-v1",
        config={"cycles": "C1-C7", "views": ["realtime", "latest_historical"]},
        input_checksums={
            "observations.parquet": hashlib.sha256(
                b"dual-vintage-observations"
            ).hexdigest()
        },
        quality_summary={"failed": 0, "passed": 2},
        created_at=datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    )
    product = build_cycle_phase_vintage([realtime, latest], context=context)
    assert len(product) == 14
    assert product.groupby(["date", "cycle_id"]).size().eq(2).all()
    assert product.groupby(["date", "cycle_id"])["vintage"].agg(set).apply(
        lambda labels: labels
        == {
            VintageKind.REALTIME.value,
            VintageKind.LATEST_HISTORICAL.value,
        }
    ).all()

    product_root = tmp_path / "products" / "seven_cycle"

    def write_staging(staging_dir: Path) -> None:
        write_cycle_phase_vintage(staging_dir, product, context=context)

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )

    published_path = (
        product_root
        / "runs"
        / context.run_id
        / CYCLE_PHASE_VINTAGE_FILENAME
    )
    published = pd.read_parquet(published_path)
    assert published.groupby(["date", "cycle_id"]).size().eq(2).all()
    assert manifest.product_checksums[CYCLE_PHASE_VINTAGE_FILENAME] == (
        sha256_file(published_path)
    )


@pytest.mark.parametrize(
    ("archive_view", "cutoff", "unavailable_cycle_ids"),
    [
        (
            "annual_only",
            date(2018, 6, 30),
            {"C4", "C5", "C6", "C7"},
        ),
        (
            "monthly_only",
            date(2018, 6, 30),
            {"C1", "C2", "C3"},
        ),
        (
            "no_visible",
            date(1800, 1, 1),
            {"C1", "C2", "C3", "C4", "C5", "C6", "C7"},
        ),
    ],
)
def test_degenerate_cutoffs_emit_governed_unavailable_rows_without_leakage(
    archive: tuple[Observation, ...],
    engine: SevenCycleEngine,
    archive_view: str,
    cutoff: date,
    unavailable_cycle_ids: set[str],
) -> None:
    from seven_cycle_platform.cycles.vintage import reconstruct_cycle_vintage

    if archive_view == "annual_only":
        records = tuple(
            record for record in archive if record.entity_id in ANNUAL_CATEGORIES
        )
    elif archive_view == "monthly_only":
        records = tuple(
            record for record in archive if record.entity_id in MONTHLY_CATEGORIES
        )
    else:
        records = archive

    states = reconstruct_cycle_vintage(
        records,
        engine=engine,
        annual_categories=ANNUAL_CATEGORIES,
        monthly_categories=MONTHLY_CATEGORIES,
        as_of=cutoff,
        strict=True,
    )

    assert list(states.columns) == RECONSTRUCTION_COLUMNS
    assert len(states) == 7
    assert states["cycle_id"].tolist() == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]
    assert set(states["vintage"]) == {VintageKind.REALTIME.value}
    assert states["vintage_caveat"].isna().all()

    unavailable = states.loc[states["cycle_id"].isin(unavailable_cycle_ids)]
    unavailable_state_fields = [
        "angle",
        "phase",
        "level",
        "slope",
        "acceleration",
        "amplitude",
        "innovation",
        "uncertainty",
    ]
    assert unavailable[unavailable_state_fields].isna().all().all()
    assert unavailable["confidence"].eq(0.0).all()
    assert unavailable["effective_cycles"].eq(0.0).all()
    assert unavailable["observed_observations"].eq(0).all()
    assert unavailable["member_breadth"].eq(0.0).all()
    assert unavailable["category_breadth"].eq(0.0).all()
    assert unavailable["evidence_level"].eq("low").all()
    assert unavailable["usage_status"].eq("unavailable").all()
    assert unavailable["total_members"].eq(3).all()
    assert unavailable["total_categories"].eq(3).all()


def test_panel_builder_rejects_unaligned_and_overlapping_entities() -> None:
    from seven_cycle_platform.cycles.vintage import (
        build_vintage_panels,
        read_vintage,
    )

    unaligned_annual = _observation(
        entity_id="annual_alpha",
        observation_date=date(2024, 6, 30),
        release_date=date(2024, 7, 15),
        value=1.0,
    )
    selection = read_vintage(
        [unaligned_annual],
        as_of=date(2024, 12, 31),
        strict=True,
    )

    with pytest.raises(ValueError, match="annual.*December 31"):
        build_vintage_panels(
            selection,
            annual_categories={"annual_alpha": "growth"},
            monthly_categories={},
        )
    with pytest.raises(ValueError, match="both annual and monthly"):
        build_vintage_panels(
            selection,
            annual_categories={"annual_alpha": "growth"},
            monthly_categories={"annual_alpha": "growth"},
        )


@pytest.mark.parametrize("invalid_as_of", [True, np.bool_(False)])
def test_reader_rejects_boolean_cutoffs(invalid_as_of: object) -> None:
    from seven_cycle_platform.cycles.vintage import read_vintage

    with pytest.raises(TypeError, match="as_of.*date"):
        read_vintage([], as_of=invalid_as_of, strict=True)
