"""基金真实存续状态的统一口径。"""
from typing import Any, Optional


INACTIVE_FUND_STATUSES = frozenset({"D", "DELIST", "DELISTED", "TERMINATED", "LIQUIDATED"})


def fund_status_from_raw_data(raw_data: Any) -> str:
    """任一来源标记摘牌即返回摘牌状态，否则返回最具体的可用状态。"""
    source = raw_data if isinstance(raw_data, dict) else {}
    statuses = []
    for section_name in ("info", "universe"):
        section = source.get(section_name)
        if isinstance(section, dict):
            status = str(section.get("status") or "").strip().upper()
            if status:
                statuses.append(status)
    root_status = str(source.get("status") or "").strip().upper()
    if root_status:
        statuses.append(root_status)
    return next((status for status in statuses if status in INACTIVE_FUND_STATUSES), statuses[0] if statuses else "")


def is_active_fund(raw_data: Any, name: Any = "") -> bool:
    normalized_name = str(name or "")
    if any(marker in normalized_name for marker in ("清算", "终止", "退市")):
        return False
    return fund_status_from_raw_data(raw_data) not in INACTIVE_FUND_STATUSES


def active_fund_sql(alias: Optional[str] = None) -> str:
    """返回可嵌入 PostgreSQL 查询的存续基金条件。"""
    prefix = f"{alias}." if alias else ""
    return f"""
        NOT (
            {prefix}name ILIKE '%清算%'
            OR {prefix}name ILIKE '%终止%'
            OR {prefix}name ILIKE '%退市%'
            OR UPPER(COALESCE({prefix}raw_data#>>'{{info,status}}', ''))
                IN ('D', 'DELIST', 'DELISTED', 'TERMINATED', 'LIQUIDATED')
            OR UPPER(COALESCE({prefix}raw_data#>>'{{universe,status}}', ''))
                IN ('D', 'DELIST', 'DELISTED', 'TERMINATED', 'LIQUIDATED')
            OR UPPER(COALESCE({prefix}raw_data->>'status', ''))
                IN ('D', 'DELIST', 'DELISTED', 'TERMINATED', 'LIQUIDATED')
        )
    """.strip()
