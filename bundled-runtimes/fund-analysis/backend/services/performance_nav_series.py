"""业绩序列的统一口径；基金原始行仅用复权净值，缺口保留。"""
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from services.fund_trading_calendar import get_trading_calendar


METHODOLOGY_VERSION = "adjusted_nav_trading_calendar_v3"


def positive_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def normalize_performance_rows(
    rows: Iterable[Dict[str, Any]], as_of_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    dated = {}
    for row in rows:
        raw_date = row.get("date") or row.get("trade_date")
        try:
            day = raw_date.date() if isinstance(raw_date, datetime) else (
                raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
            )
        except ValueError:
            continue
        if as_of_date is None or day <= as_of_date:
            dated[day] = row  # 同日最后一条，包括明确缺值的修订，不复活旧值。

    # 整个序列选一次字段，不能逐行借用另一种量纲。
    fund_rows = any(any(key in row for key in ("adj_nav", "accum_nav", "unit_nav")) for row in dated.values())
    normalized = []
    for day, row in sorted(dated.items()):
        normalized.append({
            "date": day,
            "nav": positive_number(row.get("adj_nav" if fund_rows else "nav")),
            "nav_basis": "adj_nav" if fund_rows else row.get("nav_basis", "provided_nav"),
            "benchmark_nav": positive_number(row.get("benchmark_nav")),
            "risk_calendar": row.get("risk_calendar"),
        })
    return normalized


def select_performance_window(rows: Iterable[Dict[str, Any]], days: int, as_of: date) -> tuple[List[Dict[str, Any]], bool]:
    """选真实自然日窗口及期初基点；端点缺值不回退，完整性与源入口一致。"""
    normalized = normalize_performance_rows(rows, as_of_date=as_of)
    start = as_of - timedelta(days=days)
    baseline = next((row for row in reversed(normalized) if row['date'] <= start), None)
    selected = [row for row in normalized if start < row['date'] <= as_of]
    if baseline and (start - baseline['date']).days <= 15:
        selected.insert(0, baseline)
    valid = [row for row in selected if row['nav'] is not None]
    full = len(valid) >= 2 and (valid[0]['date'] - start).days <= 15 and (as_of - valid[-1]['date']).days <= 15
    if selected and (selected[0]['nav'] is None or selected[-1]['nav'] is None):
        full = False
    if {row.get('risk_calendar') for row in selected} == {'SSE'}:
        calendar = get_trading_calendar()
        expected = calendar.open_days(start - timedelta(days=15), as_of) if calendar else None
        if not expected:
            full = False
        else:
            prior = [day for day in expected if day <= start]
            full = bool(full and prior and valid[0]['date'] <= start
                        and valid[0]['date'] >= max(prior) and valid[-1]['date'] >= max(expected))
    return selected, full


def performance_evidence(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [row for row in rows if row["nav"] is not None]
    bounded = [row for row in rows if valid and valid[0]["date"] <= row["date"] <= valid[-1]["date"]]
    span = (valid[-1]["date"] - valid[0]["date"]).days if len(valid) >= 2 else 0
    longest_gap = max(((b["date"] - a["date"]).days for a, b in zip(valid, valid[1:])), default=0)
    missing = sum(row["nav"] is None for row in bounded)
    # 日频风险的保守检查，不冒充交易所日历；长假也可能需要补充核验。
    daily_eligible = len(valid) >= 2 and missing == 0 and longest_gap <= 7 and (len(valid) - 1) / max(span, 1) >= 0.5
    calendar_evidence = {"calendar_status": "not_configured", "calendar_exchange": None,
                         "calendar_source": None, "expected_open_days": None,
                         "missing_open_days": None}
    calendars = {row.get("risk_calendar") for row in rows}
    if calendars == {"SSE"}:
        calendar = get_trading_calendar()
        calendar_evidence.update({"calendar_exchange": "SSE", "calendar_status": "unavailable"})
        expected = calendar.open_days(valid[0]["date"], valid[-1]["date"]) if calendar and len(valid) >= 2 else None
        daily_eligible = False
        if expected is not None:
            observed = {row["date"] for row in valid}
            absent = sorted(expected - observed)
            unexpected = sorted(observed - expected)
            daily_eligible = len(expected) >= 2 and missing == 0 and not absent
            calendar_evidence.update({
                "calendar_status": "verified" if daily_eligible else "incomplete_nav",
                "calendar_source": "tushare.trade_cal", "calendar_fetched_at": calendar.fetched_at,
                "calendar_start_date": calendar.start.isoformat(), "calendar_end_date": calendar.end.isoformat(),
                "expected_open_days": len(expected), "missing_open_days": len(absent),
                "missing_open_dates": [day.isoformat() for day in absent[:12]],
                "off_calendar_observations": len(unexpected),
                "risk_sampling": "exchange_open_days",
                "risk_observations": len(expected & observed),
                "risk_start_date": min(expected).isoformat() if expected else None,
                "risk_end_date": max(expected).isoformat() if expected else None,
            })
        elif calendar and len(valid) >= 2:
            calendar_evidence["calendar_status"] = "out_of_range"
    elif any(calendars):
        # 不混用两个市场或用部分行的市场覆盖其余未知行。
        daily_eligible = False
        calendar_evidence["calendar_status"] = "mixed_or_unsupported"
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "nav_basis": rows[0]["nav_basis"] if rows else "unavailable",
        "return_annualization": "actual_days_365.25",
        "risk_annualization": "daily_252" if daily_eligible else "unavailable",
        "valid_observations": len(valid),
        "missing_observations": sum(row["nav"] is None for row in rows),
        "longest_gap_days": longest_gap,
        "daily_risk_eligible": daily_eligible,
        **calendar_evidence,
    }


def daily_risk_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """仅返回合格的日频样本；休市日披露仍保留在原收益/回撤序列中。"""
    evidence = performance_evidence(rows)
    if not evidence["daily_risk_eligible"]:
        return []
    valid = [row for row in rows if row["nav"] is not None]
    if evidence["calendar_status"] == "verified":
        opened = get_trading_calendar().open_days(valid[0]["date"], valid[-1]["date"])
        return [row for row in valid if row["date"] in opened]
    return valid
