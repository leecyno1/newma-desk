"""
滚动评价指标服务

面向基金研究场景生成 3M/6M/1Y/3Y 等多窗口指标快照，供评分、筛选和详情页统一读取。
"""
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.metric_factory import MetricFactory


DEFAULT_WINDOWS = {
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "3y": 756,
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
        points = self.metric_factory._normalize_nav_series(nav_series)
        if len(points) < 2:
            return []

        effective_as_of = as_of_date or points[-1][0]
        records: List[Dict[str, Any]] = []
        normalized_series = [{"date": item_date, "nav": nav} for item_date, nav in points]
        benchmark_points = self.metric_factory._normalize_nav_series([
            {
                "date": item.get("date") or item.get("trade_date"),
                "nav": item.get("benchmark_nav"),
            }
            for item in nav_series
            if item.get("benchmark_nav") is not None
        ])
        benchmark_by_date = {item_date: nav for item_date, nav in benchmark_points}

        for window, expected_observations in self.windows.items():
            minimum_observations = max(2, int(expected_observations * self.min_observation_ratio))
            if len(normalized_series) < minimum_observations:
                continue

            window_series = normalized_series[-expected_observations:]
            if len(window_series) < minimum_observations:
                continue
            window_benchmark_series = [
                {"date": item["date"], "nav": benchmark_by_date[item["date"]]}
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
                    "calculation_engine": "RollingMetricService",
                    "evaluation_benchmark_code": benchmark_code,
                    "expected_observations": expected_observations,
                    "actual_observations": len(window_series),
                    "benchmark_observations": len(window_benchmark_series),
                    "window_start_date": window_series[0]["date"],
                    "window_end_date": window_series[-1]["date"],
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
        nav_series = nav_repo.get_nav_series(fund_code)
        records = self.calculate_for_nav_series(
            nav_series,
            target_type="fund",
            target_id=fund_code,
            benchmark_code=effective_benchmark,
            as_of_date=as_of_date,
        )

        saved = []
        for record in records:
            saved.append(metric_repo.upsert_metric(
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

        return {
            "fund_code": fund_code,
            "saved": len(saved),
            "windows": sorted({item.get("metric_window") for item in saved if item.get("metric_window")}),
            "metrics": saved,
        }
