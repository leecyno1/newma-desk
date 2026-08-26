from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from seven_cycle_platform.data.identity import DataIdentity, month_distance
from seven_cycle_platform.types import FreshnessStatus, VintageKind


def identity_kwargs() -> dict[str, object]:
    return {
        "entity_id": "c4_macro_panel",
        "source": "approved_prototype",
        "frequency": "M",
        "unit": "mixed_standardized",
        "transform": "family_balanced_composite",
        "observation_start": date(2005, 1, 31),
        "data_as_of": date(2025, 12, 31),
        "release_date": date(2026, 1, 15),
        "retrieval_time": datetime(2026, 7, 19, tzinfo=timezone.utc),
        "vintage_kind": VintageKind.LATEST_HISTORICAL,
        "stale_after_months": 2,
        "proxy_for": None,
        "caveat": "Latest-restated observations; original release vintages unavailable.",
    }


def identity_payload() -> dict[str, object]:
    return {
        **identity_kwargs(),
        "stale_months": 7,
        "freshness_status": FreshnessStatus.STALE,
    }


def test_month_distance_counts_calendar_month_boundaries() -> None:
    assert month_distance(date(2025, 12, 31), date(2026, 7, 19)) == 7
    assert month_distance(date(2026, 1, 31), date(2026, 2, 1)) == 1


def test_month_distance_rejects_reverse_order() -> None:
    with pytest.raises(ValueError, match="end cannot precede start"):
        month_distance(date(2026, 7, 19), date(2025, 12, 31))


def test_data_identity_marks_stale_source() -> None:
    identity = DataIdentity.from_dates(**identity_kwargs())

    assert identity.stale_months == 7
    assert identity.freshness_status is FreshnessStatus.STALE


def test_data_identity_is_fresh_at_staleness_threshold() -> None:
    kwargs = identity_kwargs()
    kwargs["stale_after_months"] = 7

    identity = DataIdentity.from_dates(**kwargs)

    assert identity.freshness_status is FreshnessStatus.FRESH


def test_unavailable_vintage_has_unavailable_freshness() -> None:
    kwargs = identity_kwargs()
    kwargs["vintage_kind"] = VintageKind.UNAVAILABLE

    identity = DataIdentity.from_dates(**kwargs)

    assert identity.freshness_status is FreshnessStatus.UNAVAILABLE


def test_retrieval_time_is_normalized_to_utc() -> None:
    kwargs = identity_kwargs()
    kwargs["retrieval_time"] = datetime(
        2026,
        7,
        19,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )

    identity = DataIdentity.from_dates(**kwargs)

    assert identity.retrieval_time == datetime(2026, 7, 19, tzinfo=timezone.utc)
    assert identity.retrieval_time.tzinfo is timezone.utc


def test_retrieval_time_must_be_timezone_aware() -> None:
    kwargs = identity_kwargs()
    kwargs["retrieval_time"] = datetime(2026, 7, 19)

    with pytest.raises(ValueError, match="retrieval_time must be timezone-aware"):
        DataIdentity.from_dates(**kwargs)


def test_direct_instantiation_requires_canonical_utc_retrieval_time() -> None:
    payload = identity_payload()
    payload["retrieval_time"] = datetime(
        2026,
        7,
        19,
        8,
        tzinfo=timezone(timedelta(hours=8)),
    )

    with pytest.raises(ValidationError, match="retrieval_time must use UTC"):
        DataIdentity(**payload)


def test_model_validate_accepts_canonical_derived_values() -> None:
    identity = DataIdentity.model_validate(identity_payload())

    assert identity.retrieval_time.tzinfo is timezone.utc
    assert identity.stale_months == 7
    assert identity.freshness_status is FreshnessStatus.STALE


def test_model_validate_rejects_incorrect_stale_months() -> None:
    payload = identity_payload()
    payload["stale_months"] = 6

    with pytest.raises(ValidationError, match="stale_months must equal 7"):
        DataIdentity.model_validate(payload)


def test_direct_instantiation_rejects_unavailable_marked_fresh() -> None:
    payload = identity_payload()
    payload["vintage_kind"] = VintageKind.UNAVAILABLE
    payload["freshness_status"] = FreshnessStatus.FRESH

    with pytest.raises(
        ValidationError,
        match="freshness_status must be unavailable",
    ):
        DataIdentity(**payload)


def test_data_identity_is_immutable() -> None:
    identity = DataIdentity.from_dates(**identity_kwargs())

    with pytest.raises(ValidationError, match="frozen"):
        identity.source = "replacement"


def test_data_identity_uses_strict_validation() -> None:
    payload = identity_payload()
    payload["stale_after_months"] = "2"

    with pytest.raises(ValidationError):
        DataIdentity.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("observation_start", date(2026, 1, 1), "observation_start"),
        ("release_date", date(2025, 12, 30), "release_date"),
    ],
)
def test_data_identity_validates_date_ordering(
    field: str,
    value: date,
    message: str,
) -> None:
    kwargs = identity_kwargs()
    kwargs[field] = value

    with pytest.raises(ValidationError, match=message):
        DataIdentity.from_dates(**kwargs)


def test_proxy_identity_requires_target_and_caveat() -> None:
    kwargs = identity_kwargs()
    kwargs.update(
        vintage_kind=VintageKind.EXPLICIT_PROXY,
        proxy_for=None,
        caveat="Historical proxy.",
    )

    with pytest.raises(ValueError, match="proxy_for"):
        DataIdentity.from_dates(**kwargs)

    kwargs.update(proxy_for="target_series", caveat="")

    with pytest.raises(ValidationError, match="caveat"):
        DataIdentity.from_dates(**kwargs)


def test_proxy_identity_rejects_whitespace_target_from_factory() -> None:
    kwargs = identity_kwargs()
    kwargs.update(
        vintage_kind=VintageKind.EXPLICIT_PROXY,
        proxy_for="   \t",
    )

    with pytest.raises(ValidationError, match="proxy_for must be non-blank"):
        DataIdentity.from_dates(**kwargs)


def test_proxy_identity_rejects_whitespace_target_during_model_validation() -> None:
    payload = identity_payload()
    payload.update(
        vintage_kind=VintageKind.EXPLICIT_PROXY,
        proxy_for="  \n ",
    )

    with pytest.raises(ValidationError, match="proxy_for must be non-blank"):
        DataIdentity.model_validate(payload)


def test_proxy_identity_stores_stripped_target() -> None:
    kwargs = identity_kwargs()
    kwargs.update(
        vintage_kind=VintageKind.EXPLICIT_PROXY,
        proxy_for="  target_series  ",
    )

    identity = DataIdentity.from_dates(**kwargs)

    assert identity.proxy_for == "target_series"


def test_non_proxy_identity_rejects_proxy_target() -> None:
    kwargs = identity_kwargs()
    kwargs["proxy_for"] = "target_series"

    with pytest.raises(ValueError, match="only for explicit proxies"):
        DataIdentity.from_dates(**kwargs)


def test_data_identity_rejects_extra_fields() -> None:
    payload = identity_payload()
    payload["undocumented"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DataIdentity.model_validate(payload)
