"""基金现任经理任期事实解析。"""

from datetime import datetime
from typing import Any, Dict, Optional


def _date_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return None


def _manager_ids(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def resolve_manager_tenure_context(
    fund: Dict[str, Any],
    profile: Dict[str, Any],
    authoritative: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按权威任期表、同步原始字段、人工画像的顺序解析现任团队起点。"""
    authoritative = authoritative or {}
    authoritative_start = _date_text(
        authoritative.get("start_date") or authoritative.get("manager_tenure_start")
    )
    if authoritative_start:
        return {
            "start_date": authoritative_start,
            "source": authoritative.get("source") or "manager_fund_tenures",
            "manager_ids": _manager_ids(authoritative.get("manager_ids")),
            "resolution": "current_team_latest_start",
        }

    raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
    manager_sync = raw_data.get("manager_sync") if isinstance(raw_data.get("manager_sync"), dict) else {}
    synced_start = _date_text(manager_sync.get("manager_tenure_start"))
    if synced_start:
        return {
            "start_date": synced_start,
            "source": manager_sync.get("source") or "funds.raw_data.manager_sync",
            "manager_ids": _manager_ids(manager_sync.get("manager_ids") or fund.get("manager_ids")),
            "resolution": "synced_current_team_latest_start",
        }

    profile_start = _date_text(profile.get("manager_tenure_start"))
    if profile_start:
        return {
            "start_date": profile_start,
            "source": profile.get("manager_tenure_source") or "fund_research_profiles",
            "manager_ids": _manager_ids(fund.get("manager_ids")),
            "resolution": "research_profile_fallback",
        }

    return {
        "start_date": None,
        "source": None,
        "manager_ids": _manager_ids(fund.get("manager_ids")),
        "resolution": "unavailable",
    }


def enrich_profile_with_manager_tenure(
    profile: Dict[str, Any],
    tenure_context: Dict[str, Any],
) -> Dict[str, Any]:
    effective_profile = dict(profile or {})
    if tenure_context.get("start_date"):
        effective_profile["manager_tenure_start"] = tenure_context["start_date"]
        effective_profile["manager_tenure_source"] = tenure_context.get("source")
        effective_profile["manager_tenure_manager_ids"] = tenure_context.get("manager_ids") or []
    return effective_profile
