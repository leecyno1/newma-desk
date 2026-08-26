"""Shared domain types."""

from enum import StrEnum


class ReleaseStatus(StrEnum):
    LIVE = "live"
    STALE = "stale"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class MappingStatus(StrEnum):
    FORMAL = "formal"
    CONDITIONAL = "conditional"
    RETROSPECTIVE_ONLY = "retrospective_only"
    UNAVAILABLE = "unavailable"


class PublicationGateStatus(StrEnum):
    FORMAL = "formal"
    LIMITED = "limited"
    BLOCKED = "blocked"
    SCENARIO_ONLY = "scenario_only"
    CALENDAR_ONLY = "calendar_only"


class EvidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class VintageKind(StrEnum):
    REALTIME = "realtime"
    LATEST_HISTORICAL = "latest_historical"
    PSEUDO_VINTAGE = "pseudo_vintage"
    EXPLICIT_PROXY = "explicit_proxy"
    UNAVAILABLE = "unavailable"
