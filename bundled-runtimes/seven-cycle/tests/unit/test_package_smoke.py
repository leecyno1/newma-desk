from seven_cycle_platform.types import (
    EvidenceLevel,
    FreshnessStatus,
    MappingStatus,
    PublicationGateStatus,
    ReleaseStatus,
    VintageKind,
)


def test_release_status_contract() -> None:
    assert [status.value for status in ReleaseStatus] == [
        "live",
        "stale",
        "partial",
        "blocked",
    ]


def test_mapping_status_contract() -> None:
    assert [status.value for status in MappingStatus] == [
        "formal",
        "conditional",
        "retrospective_only",
        "unavailable",
    ]


def test_publication_gate_status_contract() -> None:
    assert [status.value for status in PublicationGateStatus] == [
        "formal",
        "limited",
        "blocked",
        "scenario_only",
        "calendar_only",
    ]


def test_evidence_level_contract() -> None:
    assert [level.value for level in EvidenceLevel] == ["high", "medium", "low"]


def test_vintage_kind_contract() -> None:
    assert [kind.value for kind in VintageKind] == [
        "realtime",
        "latest_historical",
        "pseudo_vintage",
        "explicit_proxy",
        "unavailable",
    ]


def test_freshness_status_contract() -> None:
    assert [status.value for status in FreshnessStatus] == [
        "fresh",
        "stale",
        "unavailable",
    ]
