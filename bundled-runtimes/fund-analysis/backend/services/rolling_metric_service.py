"""
滚动评价指标服务

面向基金研究场景生成 3M/6M/1Y/3Y 等多窗口指标快照，供评分、筛选和详情页统一读取。
"""
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.metric_factory import MetricFactory
from services.performance_nav_series import normalize_performance_rows, select_performance_window


DEFAULT_WINDOWS = {
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "3y": 756,
    "5y": 1260,
}


class RollingMetricService:
    """计算并持久化基金多窗口滚动指标。"""

    def __init__(
        self,
        windows: Optional[Dict[str, int]] = None,
        min_observation_ratio: float = 0.6,
        metric_factory: Optional[MetricFactory] = None,
    ):
        self.windows = windows or DEFAULT_WINDOWS
        self.min_observation_ratio = min_observation_ratio
        self.metric_factory = metric_factory or MetricFactory()

    def calculate_for_nav_series(
        self,
        nav_series: List[Dict[str, Any]],
        target_type: str,
        target_id: str,
        benchmark_code: Optional[str] = None,
        as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        points = self.metric_factory._normalize_nav_series(nav_series, as_of_date=as_of_date)
        if len(points) < 2:
            return []

        effective_as_of = as_of_date or points[-1][0]
        records: List[Dict[str, Any]] = []
        normalized_series = normalize_performance_rows(nav_series, as_of_date=effective_as_of)
        benchmark_points = self.metric_factory._normalize_nav_series([
            {
                "date": item.get("date") or item.get("trade_date"),
                "nav": item.get("benchmark_nav"),
                "risk_calendar": item.get("risk_calendar"),
            }
            for item in nav_series
            if item.get("benchmark_nav") is not None
        ], as_of_date=effective_as_of)
        benchmark_by_date = {item_date: nav for item_date, nav in benchmark_points}

        for window, expected_observations in self.windows.items():
            minimum_observations = max(2, int(expected_observations * self.min_observation_ratio))
            if len(points) < minimum_observations:
                continue

            calendar_days = {'1y': 365, '3y': 1095, '5y': 1825}.get(window)
            if calendar_days:
                window_series, complete = select_performance_window(normalized_series, calendar_days, effective_as_of)
                if not complete:
                    continue
            else:
                window_series = normalized_series[-expected_observations:]
            if sum(item["nav"] is not None for item in window_series) < minimum_observations:
                continue
            window_benchmark_series = [
                {"date": item["date"], "nav": benchmark_by_date[item["date"]], "risk_calendar": item.get("risk_calendar")}
                for item in window_series
                if item["date"] in benchmark_by_date
            ]
            usable_benchmark_series = (
                window_benchmark_series
                if benchmark_code and len(window_benchmark_series) >= minimum_observations
                else None
            )

            window_records = self.metric_factory.build_metric_records(
                target_type=target_type,
                target_id=target_id,
                as_of_date=effective_as_of,
                nav_series=window_series,
                benchmark_series=usable_benchmark_series,
                benchmark_code=benchmark_code,
                window=window,
            )
            for record in window_records:
                record["details"] = {
                    **record.get("details", {}),
                    "calculation_engine": "RollingMetricService",
                    "evaluation_benchmark_code": benchmark_code,
                    "expected_observations": expected_observations,
                    "actual_observations": len(window_series),
                    "benchmark_observations": len(window_benchmark_series),
                    "window_start_date": record['details']['window_start_date'],
                    "window_end_date": record['details']['window_end_date'],
                }
            records.extend(window_records)

        return records

    def calculate_and_save_for_fund(
        self,
        fund_code: str,
        as_of_date: Optional[date] = None,
        benchmark_code: Optional[str] = None,
        peer_group_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        from repositories import (
            get_fund_classification_repo,
            get_metric_snapshot_repo,
            get_nav_repo,
            get_research_profile_repo,
        )

        nav_repo = get_nav_repo()
        metric_repo = get_metric_snapshot_repo()
        profile_repo = get_research_profile_repo()

        profile = None
        try:
            profile = profile_repo.get_profile(fund_code)
        except Exception:
            profile = None

        classification_context = {}
        try:
            classification_context = get_fund_classification_repo().get_classification_context(fund_code) or {}
        except Exception:
            classification_context = {}
        mapped_benchmark = (classification_context.get("benchmark_mapping") or {}).get("benchmark_code")
        mapped_peer_group = classification_context.get("peer_group_key")

        effective_benchmark = benchmark_code or mapped_benchmark or (profile or {}).get("primary_benchmark")
        effective_peer_group = peer_group_key or mapped_peer_group or (profile or {}).get("peer_group")
        nav_series = nav_repo.get_nav_series(
            fund_code, end_date=as_of_date.isoformat() if as_of_date else None,
        )
        records = self.calculate_for_nav_series(
            nav_series,
            target_type="fund",
            target_id=fund_code,
            benchmark_code=effective_benchmark,
            as_of_date=as_of_date,
        )

        panel = []
        for record in records:
            panel.append(dict(
                target_type=record["target_type"],
                target_id=record["target_id"],
                as_of_date=record["as_of_date"],
                metric_name=record["metric_name"],
                metric_value=Decimal(str(record["metric_value"])),
                metric_unit=record.get("metric_unit"),
                window=record.get("window"),
                benchmark_code=record.get("benchmark_code"),
                peer_group_key=effective_peer_group,
                source_snapshot_id=source_snapshot_id,
                details=record.get("details"),
            ))
        saved = metric_repo.upsert_metrics(panel)

        return {
            "fund_code": fund_code,
            "saved": len(saved),
            "windows": sorted({item.get("metric_window") for item in saved if item.get("metric_window")}),
            "metrics": saved,
        }
