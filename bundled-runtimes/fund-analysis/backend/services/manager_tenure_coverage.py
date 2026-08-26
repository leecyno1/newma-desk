"""基金经理任期净值覆盖口径。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional


FULL_START_TOLERANCE_DAYS = 7


def build_manager_tenure_coverage(
    requested_start: Any,
    actual_start: Any,
    actual_end: Any,
    observations: int,
) -> Dict[str, Any]:
    requested = _date(requested_start)
    actual = _date(actual_start)
    end = _date(actual_end)
    if not requested or not actual or not end or end < actual:
        return {
            "tenure_coverage_status": "unavailable",
            "peer_ranking_eligible": False,
        }

    requested_days = max(1, (end - requested).days + 1)
    covered_days = max(1, (end - actual).days + 1)
    start_lag_days = max(0, (actual - requested).days)
    coverage_ratio = min(1.0, covered_days / requested_days)
    status = (
        "full_tenure"
        if start_lag_days <= FULL_START_TOLERANCE_DAYS
        else "partial_since_data_start"
    )
    return {
        "requested_start_date": requested.isoformat(),
        "actual_start_date": actual.isoformat(),
        "actual_end_date": end.isoformat(),
        "requested_tenure_days": requested_days,
        "metric_coverage_days": covered_days,
        "start_lag_days": start_lag_days,
        "tenure_coverage_ratio": round(coverage_ratio, 8),
        "tenure_coverage_status": status,
        "actual_observations": max(0, int(observations or 0)),
        "peer_ranking_eligible": status == "full_tenure",
    }


def metric_details_coverage_status(details: Any) -> Optional[str]:
    if not isinstance(details, dict):
        return None
    explicit = str(details.get("tenure_coverage_status") or "").strip()
    if explicit:
        return explicit
    requested = _date(
        details.get("requested_start_date")
        or details.get("manager_tenure_start")
    )
    actual = _date(
        details.get("actual_start_date")
        or details.get("window_start_date")
    )
    if requested and actual:
        return (
            "full_tenure"
            if (actual - requested).days <= FULL_START_TOLERANCE_DAYS
            else "partial_since_data_start"
        )
    return None


def _date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
