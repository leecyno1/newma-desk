"""
基金经理任期切片指标服务

将现任经理任期起点之后的净值表现单独沉淀为 MetricSnapshot，避免用前任经理历史业绩误导研究结论。
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.fund_manager_tenure_context import resolve_manager_tenure_context
from services.manager_tenure_coverage import build_manager_tenure_coverage
from services.metric_factory import MetricFactory


class ManagerTenureMetricService:
    """计算并保存现任基金经理任期内指标。"""

    WINDOW = "manager_tenure"

    def __init__(
        self,
        metric_factory: Optional[MetricFactory] = None,
        manager_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
    ):
        self.metric_factory = metric_factory or MetricFactory()
        self._manager_repo = manager_repo
        self._classification_repo = classification_repo

    def calculate_and_save_for_fund(self, fund_code: str, source_snapshot_id: Optional[str] = None) -> Dict[str, Any]:
        from repositories import get_fund_repo, get_metric_snapshot_repo, get_nav_repo, get_research_profile_repo

        profile_repo = get_research_profile_repo()
        nav_repo = get_nav_repo()
        metric_repo = get_metric_snapshot_repo()

        fund = get_fund_repo().get_fund_by_identifier(fund_code) or {"wind_code": fund_code}
        profile = profile_repo.get_profile(fund_code) or {}
        tenure_context = resolve_manager_tenure_context(
            fund,
            profile,
            self.manager_repo.get_current_fund_tenure_context(fund_code),
        )
        tenure_start = self._parse_date(tenure_context.get("start_date"))
        if tenure_start is None:
            return {"fund_code": fund_code, "saved": 0, "reason": "missing_manager_tenure_start", "metrics": []}

        nav_series = nav_repo.get_nav_series(fund_code, start_date=tenure_start.isoformat())
        points = self.metric_factory._normalize_nav_series(nav_series)
        if len(points) < 2:
            return {"fund_code": fund_code, "saved": 0, "reason": "insufficient_nav_after_tenure_start", "metrics": []}

        effective_as_of = points[-1][0]
        normalized_series = [{"date": item_date, "nav": nav} for item_date, nav in points]
        coverage = build_manager_tenure_coverage(
            tenure_start,
            normalized_series[0]["date"],
            normalized_series[-1]["date"],
            len(normalized_series),
        )
        classification = self.classification_repo.get_classification_context(fund_code) or {}
        benchmark_mapping = classification.get("benchmark_mapping") or {}
        benchmark_code = profile.get("primary_benchmark") or benchmark_mapping.get("benchmark_code")
        peer_group_key = profile.get("peer_group") or classification.get("peer_group_key")
        records = self.metric_factory.build_metric_records(
            target_type="fund",
            target_id=fund_code,
            as_of_date=effective_as_of,
            nav_series=normalized_series,
            benchmark_code=benchmark_code,
            window=self.WINDOW,
        )
        records.append({
            "target_type": "fund",
            "target_id": fund_code,
            "as_of_date": effective_as_of,
            "metric_name": "tenure_days",
            "metric_value": Decimal(str((effective_as_of - tenure_start).days + 1)),
            "metric_unit": "days",
            "window": self.WINDOW,
            "benchmark_code": benchmark_code,
        })
        records.extend([
            {
                "target_type": "fund",
                "target_id": fund_code,
                "as_of_date": effective_as_of,
                "metric_name": "metric_coverage_days",
                "metric_value": Decimal(str(coverage["metric_coverage_days"])),
                "metric_unit": "days",
                "window": self.WINDOW,
                "benchmark_code": benchmark_code,
            },
            {
                "target_type": "fund",
                "target_id": fund_code,
                "as_of_date": effective_as_of,
                "metric_name": "tenure_coverage_ratio",
                "metric_value": Decimal(str(coverage["tenure_coverage_ratio"])),
                "metric_unit": "ratio",
                "window": self.WINDOW,
                "benchmark_code": benchmark_code,
            },
        ])

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
                benchmark_code=benchmark_code,
                peer_group_key=peer_group_key,
                source_snapshot_id=source_snapshot_id,
                details={
                    "calculation_engine": "ManagerTenureMetricService",
                    "manager_tenure_start": tenure_start.isoformat(),
                    "manager_tenure_source": tenure_context.get("source"),
                    "window_start_date": normalized_series[0]["date"],
                    "window_end_date": normalized_series[-1]["date"],
                    "actual_observations": len(normalized_series),
                    **coverage,
                },
            ))

        return {
            "fund_code": fund_code,
            "saved": len(saved),
            "window": self.WINDOW,
            "manager_tenure_start": tenure_start.isoformat(),
            "manager_tenure_source": tenure_context.get("source"),
            "coverage": coverage,
            "metrics": saved,
        }

    @property
    def manager_repo(self):
        if self._manager_repo is None:
            from repositories import get_manager_repo

            self._manager_repo = get_manager_repo()
        return self._manager_repo

    @property
    def classification_repo(self):
        if self._classification_repo is None:
            from repositories import get_fund_classification_repo

            self._classification_repo = get_fund_classification_repo()
        return self._classification_repo

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.fromisoformat(str(value)[:10]).date()
