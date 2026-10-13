"""供应商净值的自然日窗口；不足完整窗口只输出可见期证据，不冒充年度指标。"""
from datetime import date, timedelta
from typing import Any, Dict, List

from services.metric_factory import MetricFactory
from services.performance_nav_series import select_performance_window, performance_evidence


SOURCE_METHODOLOGY_VERSION = "tushare_adjusted_calendar_windows_v1"


def source_window(rows: List[Dict[str, Any]], days: int, as_of: date) -> Dict[str, Any]:
    start = as_of - timedelta(days=days)
    selected, full = select_performance_window(rows, days, as_of)
    valid = [row for row in selected if row["nav"] is not None]
    evidence = performance_evidence(selected)
    factory = MetricFactory()
    metrics = {**factory.calculate_return_metrics(selected), **factory.calculate_risk_metrics(selected)}
    # 比率的分母为零是未定义，不是风险调整收益为零。
    for ratio, denominator in (("sharpe_ratio", "annualized_volatility"),
                               ("sortino_ratio", "downside_risk"), ("calmar_ratio", "max_drawdown")):
        if metrics.get(denominator) == 0:
            metrics[ratio] = None
    return {
        "requested_start_date": start.isoformat(), "requested_end_date": as_of.isoformat(),
        "actual_start_date": valid[0]["date"].isoformat() if valid else None,
        "actual_end_date": valid[-1]["date"].isoformat() if valid else None,
        "coverage_status": "full" if full else "partial" if len(valid) >= 2 else "unavailable",
        "coverage_policy": "period_endpoints_calendar_or_15_day_tolerance",
        "methodology": evidence, "observed_metrics": metrics,
    }


def published_metric(window: Dict[str, Any], metric: str) -> Any:
    if window["coverage_status"] != "full":
        return None
    if metric not in {"total_return", "annualized_return"} and not window["methodology"]["daily_risk_eligible"]:
        return None
    value = window["observed_metrics"].get(metric)
    return round(value, 8) if value is not None else None
