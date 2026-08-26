from datetime import date, datetime, timedelta, timezone

import pyarrow as pa
from pydantic import ValidationError
import pytest

from seven_cycle_platform.contracts.arrow import (
    QUALITY_FINDING_SCHEMA,
    RAW_OBSERVATION_SCHEMA,
)
from seven_cycle_platform.data.observations import Observation, ReleaseRule
from seven_cycle_platform.types import VintageKind


OBSERVATION_FIELDS = [
    "entity_id",
    "observation_date",
    "release_date",
    "vintage_date",
    "value",
    "unit",
    "source",
    "retrieval_time",
    "revision_number",
    "quality_status",
    "vintage_kind",
]


def _observation_payload() -> dict[str, object]:
    return {
        "entity_id": "cn_cpi",
        "observation_date": date(2024, 1, 31),
        "release_date": date(2024, 2, 9),
        "vintage_date": date(2024, 2, 9),
        "value": 0.7,
        "unit": "percent_yoy",
        "source": "national_bureau_of_statistics",
        "retrieval_time": datetime(2026, 7, 12, 8, tzinfo=timezone.utc),
        "revision_number": 0,
        "quality_status": "accepted",
        "vintage_kind": VintageKind.REALTIME,
    }


def test_observation_exposes_the_raw_vintage_contract() -> None:
    observation = Observation(**_observation_payload())

    assert list(Observation.model_fields) == OBSERVATION_FIELDS
    assert observation.model_dump() == _observation_payload()


def test_observation_is_immutable() -> None:
    observation = Observation(**_observation_payload())

    with pytest.raises(ValidationError, match="frozen_instance"):
        observation.value = 1.2


def test_observation_rejects_extra_fields() -> None:
    payload = _observation_payload()
    payload["availability_inferred"] = True

    with pytest.raises(ValidationError, match="extra_forbidden"):
        Observation(**payload)


@pytest.mark.parametrize(
    ("field_updates", "expected_message"),
    [
        (
            {"release_date": date(2024, 1, 30)},
            "release_date cannot precede observation_date",
        ),
        (
            {"vintage_date": date(2024, 2, 8)},
            "vintage_date cannot precede release_date",
        ),
    ],
)
def test_observation_rejects_invalid_temporal_order(
    field_updates: dict[str, object],
    expected_message: str,
) -> None:
    payload = _observation_payload()
    payload.update(field_updates)

    with pytest.raises(ValidationError, match=expected_message):
        Observation(**payload)


def test_observation_requires_timezone_aware_retrieval_time() -> None:
    payload = _observation_payload()
    payload["retrieval_time"] = datetime(2026, 7, 12, 8)

    with pytest.raises(ValidationError, match="timezone-aware"):
        Observation(**payload)


def test_observation_normalizes_retrieval_time_to_utc() -> None:
    payload = _observation_payload()
    payload["retrieval_time"] = datetime(
        2026,
        7,
        12,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )

    observation = Observation(**payload)

    assert observation.retrieval_time == datetime(
        2026,
        7,
        12,
        tzinfo=timezone.utc,
    )
    assert observation.retrieval_time.tzinfo is timezone.utc


def test_observation_rejects_retrieval_before_vintage_in_utc() -> None:
    payload = _observation_payload()
    payload["vintage_date"] = date(2024, 2, 10)
    payload["retrieval_time"] = datetime(
        2024,
        2,
        10,
        0,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )

    with pytest.raises(
        ValidationError,
        match="retrieval_time UTC date cannot precede vintage_date",
    ):
        Observation(**payload)


def test_release_rule_is_explicit_strict_and_immutable() -> None:
    rule = ReleaseRule(
        entity_id="cn_cpi",
        source="national_bureau_of_statistics",
        unit="percent_yoy",
        publication_lag_days=9,
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
        quality_status="legacy_panel",
        revision_number=0,
    )

    assert list(ReleaseRule.model_fields) == [
        "entity_id",
        "source",
        "unit",
        "publication_lag_days",
        "vintage_kind",
        "quality_status",
        "revision_number",
    ]
    with pytest.raises(ValidationError, match="frozen_instance"):
        rule.publication_lag_days = 10

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ReleaseRule(
            entity_id="cn_cpi",
            source="national_bureau_of_statistics",
            unit="percent_yoy",
            publication_lag_days=9,
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            quality_status="legacy_panel",
            revision_number=0,
            inferred_release_history=True,
        )


@pytest.mark.parametrize(
    ("publication_lag_days", "revision_number"),
    [(-1, 0), (0, -1)],
)
def test_release_rule_rejects_negative_counters(
    publication_lag_days: int,
    revision_number: int,
) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ReleaseRule(
            entity_id="cn_cpi",
            source="national_bureau_of_statistics",
            unit="percent_yoy",
            publication_lag_days=publication_lag_days,
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            quality_status="legacy_panel",
            revision_number=revision_number,
        )


def test_raw_observation_arrow_schema_has_stable_names_and_types() -> None:
    expected_types = {
        "entity_id": pa.string(),
        "observation_date": pa.date32(),
        "release_date": pa.date32(),
        "vintage_date": pa.date32(),
        "value": pa.float64(),
        "unit": pa.string(),
        "source": pa.string(),
        "retrieval_time": pa.timestamp("us", tz="UTC"),
        "revision_number": pa.int32(),
        "quality_status": pa.string(),
        "vintage_kind": pa.string(),
    }

    assert RAW_OBSERVATION_SCHEMA.names == OBSERVATION_FIELDS
    assert {
        field.name: field.type for field in RAW_OBSERVATION_SCHEMA
    } == expected_types


def test_quality_finding_arrow_schema_is_focused_and_stable() -> None:
    expected_types = {
        "entity_id": pa.string(),
        "check": pa.string(),
        "severity": pa.string(),
        "status": pa.string(),
        "message": pa.string(),
        "observed_value": pa.float64(),
        "threshold": pa.float64(),
    }

    assert QUALITY_FINDING_SCHEMA.names == list(expected_types)
    assert {
        field.name: field.type for field in QUALITY_FINDING_SCHEMA
    } == expected_types
