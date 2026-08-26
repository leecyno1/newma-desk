"""
基金数据质量评估服务

给研究与评分层提供可解释的数据可信度状态，避免在关键字段缺失时输出过度确定的投资结论。
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from services.fund_manager_tenure_context import resolve_manager_tenure_context


class DataQualityService:
    """按基金基础信息、研究画像、净值覆盖和指标快照评估可信度。"""

    MANAGER_TENURE_NOT_APPLICABLE = {
        "index_broad",
        "index_sector",
        "index_fixed_income",
        "qdii_index",
        "cash_management",
    }
    MIN_ONE_YEAR_NAV_OBSERVATIONS = 240

    def __init__(self, classification_adapter: Optional[Any] = None):
        self._classification_adapter = classification_adapter

    def evaluate_fund(self, fund_code: str) -> Dict[str, Any]:
        from repositories import (
            get_fund_repo,
            get_manager_repo,
            get_metric_snapshot_repo,
            get_nav_repo,
            get_research_profile_repo,
        )

        fund_repo = get_fund_repo()
        profile_repo = get_research_profile_repo()
        nav_repo = get_nav_repo()
        metric_repo = get_metric_snapshot_repo()

        fund = fund_repo.get_fund_by_identifier(fund_code) or {}
        wind_code = fund.get("wind_code") or fund_code
        profile = profile_repo.get_profile(wind_code) or {}
        nav_series = nav_repo.get_nav_series(wind_code)
        metric_panel = metric_repo.get_latest_panel("fund", wind_code)
        manager_tenure_context = get_manager_repo().get_current_fund_tenure_context(wind_code)
        try:
            classification_context = self._get_classification_adapter().get_classification_context(wind_code) or {}
        except Exception:
            classification_context = {}
        return self.evaluate_from_inputs(
            fund,
            profile,
            metric_panel,
            classification_context,
            nav_series=nav_series,
            manager_tenure_context=manager_tenure_context,
        )

    def evaluate_from_inputs(
        self,
        fund: Dict[str, Any],
        profile: Dict[str, Any],
        metric_panel: List[Dict[str, Any]],
        classification_context: Dict[str, Any],
        nav_series: Optional[List[Dict[str, Any]]] = None,
        manager_tenure_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """对已批量读取的事实评分，避免基金列表和推荐逐只重复查库。"""
        wind_code = fund.get("wind_code") or fund.get("ts_code") or fund.get("id") or "unknown"
        strategy_family_key = classification_context.get("strategy_family_key")
        tenure_context = resolve_manager_tenure_context(fund, profile, manager_tenure_context)
        checks = {
            "fund_base": self._check_fund_base(fund),
            "research_profile": self._check_research_context(profile, classification_context),
            "manager_tenure_start": self._check_manager_tenure(
                tenure_context.get("start_date"),
                strategy_family_key,
            ),
            "nav_coverage": (
                self._check_nav_coverage(nav_series)
                if nav_series is not None
                else self._check_nav_coverage_from_metrics(metric_panel)
            ),
            "metric_snapshots": self._check_metric_snapshots(metric_panel),
        }
        weights = {
            "fund_base": 25,
            "research_profile": 25,
            "manager_tenure_start": 20,
            "nav_coverage": 20,
            "metric_snapshots": 10,
        }
        score = sum(weights[key] for key, check in checks.items() if check["passed"])
        status = "complete" if score >= 85 else "partial" if score >= 60 else "insufficient"
        issues = [
            check["message"]
            for check in checks.values()
            if not check["passed"]
        ]
        checks["manager_tenure_start"]["source"] = tenure_context.get("source")
        checks["manager_tenure_start"]["manager_ids"] = tenure_context.get("manager_ids") or []

        return {
            "target_type": "fund",
            "target_id": wind_code,
            "score": score,
            "status": status,
            "checks": checks,
            "issues": issues,
            "summary": self._summary(status, score, issues),
            "classification_context_status": classification_context.get("status"),
            "strategy_family_key": strategy_family_key,
            "manager_tenure": tenure_context,
        }

    def _check_fund_base(self, fund: Dict[str, Any]) -> Dict[str, Any]:
        required = ["wind_code", "name", "type", "nav_date", "establishment_date"]
        missing = [field for field in required if not fund.get(field)]
        return {
            "passed": not missing,
            "message": "基金基础字段完整" if not missing else f"基金基础字段缺失：{', '.join(missing)}",
            "missing_fields": missing,
        }

    def _check_research_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        required = ["primary_benchmark", "peer_group", "style_label"]
        missing = [field for field in required if not profile.get(field)]
        return {
            "passed": not missing,
            "message": "研究画像字段完整" if not missing else f"研究画像字段缺失：{', '.join(missing)}",
            "missing_fields": missing,
        }

    def _check_research_context(
        self,
        profile: Dict[str, Any],
        classification_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if classification_context.get("status") == "resolved":
            benchmark_code = (classification_context.get("benchmark_mapping") or {}).get("benchmark_code")
            required = {
                "strategy_family_key": classification_context.get("strategy_family_key"),
                "peer_group_key": classification_context.get("peer_group_key"),
                "benchmark_code": benchmark_code,
            }
            missing = [field for field, value in required.items() if not value]
            return {
                "passed": not missing,
                "message": (
                    "标准化分类、同类组与基准上下文完整"
                    if not missing
                    else f"标准化研究上下文缺失：{', '.join(missing)}"
                ),
                "missing_fields": missing,
                "source": "standardized_classification",
            }
        result = self._check_research_profile(profile)
        result["source"] = "fund_research_profiles"
        return result

    def _check_manager_tenure(
        self,
        manager_tenure_start: Any,
        strategy_family_key: Optional[str],
    ) -> Dict[str, Any]:
        if strategy_family_key in self.MANAGER_TENURE_NOT_APPLICABLE:
            return {
                "passed": True,
                "message": "该类别评价方法不使用基金经理任期指标",
                "value": manager_tenure_start,
                "not_applicable": True,
            }
        return self._check_required(
            manager_tenure_start,
            "已配置现任经理任期起点",
            "缺少现任经理任期起点",
        )

    def _get_classification_adapter(self):
        if self._classification_adapter is None:
            from repositories import get_fund_classification_repo

            self._classification_adapter = get_fund_classification_repo()
        return self._classification_adapter

    def _check_required(self, value: Any, success_message: str, failure_message: str) -> Dict[str, Any]:
        return {
            "passed": bool(value),
            "message": success_message if value else failure_message,
            "value": value,
        }

    def _check_nav_coverage(self, nav_series: List[Dict[str, Any]]) -> Dict[str, Any]:
        points = []
        for item in nav_series:
            item_date = self._parse_date(item.get("date") or item.get("trade_date"))
            if item_date is not None and (item.get("nav") or item.get("unit_nav") or item.get("accum_nav")) is not None:
                points.append(item_date)
        points = sorted(set(points))
        if len(points) < 2:
            return {"passed": False, "message": "净值序列不足", "observations": len(points)}
        coverage_days = (points[-1] - points[0]).days + 1
        passed = len(points) >= self.MIN_ONE_YEAR_NAV_OBSERVATIONS and coverage_days >= 365
        return {
            "passed": passed,
            "message": "净值覆盖满足滚动评价" if passed else "净值覆盖不足一年",
            "observations": len(points),
            "coverage_days": coverage_days,
            "start_date": points[0].isoformat(),
            "end_date": points[-1].isoformat(),
        }

    def _check_metric_snapshots(self, metric_panel: List[Dict[str, Any]]) -> Dict[str, Any]:
        windows = sorted({item.get("metric_window") for item in metric_panel if item.get("metric_window")})
        passed = bool(windows)
        return {
            "passed": passed,
            "message": "指标快照已沉淀" if passed else "缺少指标快照",
            "metric_count": len(metric_panel),
            "windows": windows,
        }

    def _check_nav_coverage_from_metrics(self, metric_panel: List[Dict[str, Any]]) -> Dict[str, Any]:
        observations = 0
        for item in metric_panel:
            if item.get("metric_window") != "1y" or item.get("metric_name") != "observations":
                continue
            try:
                observations = max(observations, int(float(item.get("metric_value") or 0)))
            except (TypeError, ValueError):
                continue
        passed = observations >= self.MIN_ONE_YEAR_NAV_OBSERVATIONS
        return {
            "passed": passed,
            "message": "1 年指标样本证明净值覆盖满足评价" if passed else "缺少足够的 1 年净值观察",
            "observations": observations,
            "source": "metric_snapshots.1y.observations",
        }

    def _summary(self, status: str, score: int, issues: List[str]) -> str:
        if status == "complete":
            return f"数据质量完整，可信度评分 {score}。"
        if status == "partial":
            return f"数据质量部分完整，可信度评分 {score}，需复核：{'；'.join(issues[:2])}。"
        return f"数据质量不足，可信度评分 {score}，不建议直接用于投资结论。"

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except ValueError:
            return None
