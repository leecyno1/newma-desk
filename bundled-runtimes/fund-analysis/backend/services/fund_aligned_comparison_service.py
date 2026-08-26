"""基金同区间净值比较。

所有基金只使用共同有净值的日期，避免用不同起点的曲线和指标做横向比较。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from services.fund_drawdown_recovery_service import FundDrawdownRecoveryService
from services.metric_factory import MetricFactory


class FundAlignedComparisonService:
    WINDOWS = {
        "6m": 190,
        "1y": 370,
        "3y": 1120,
    }
    MINIMUM_SPAN_DAYS = {
        "6m": 183,
        "1y": 365,
        "3y": 1095,
    }

    def __init__(
        self,
        nav_repo: Optional[Any] = None,
        metric_factory: Optional[MetricFactory] = None,
        today: Optional[date] = None,
    ):
        if nav_repo is None:
            from repositories import get_nav_repo

            nav_repo = get_nav_repo()
        self.nav_repo = nav_repo
        self.metric_factory = metric_factory or MetricFactory()
        self.today = today or date.today()

    def build(self, wind_codes: List[str]) -> Dict[str, Any]:
        codes = []
        for value in wind_codes:
            code = str(value or "").strip().upper()
            if code and code not in codes:
                codes.append(code)
        if len(codes) < 2:
            raise ValueError("至少需要两只基金进行同区间比较")
        if len(codes) > 6:
            raise ValueError("单次最多比较 6 只基金")

        earliest = self.today - timedelta(days=max(self.WINDOWS.values()) + 30)
        series: Dict[str, List[Tuple[date, float]]] = {}
        bases: Dict[str, str] = {}
        for code in codes:
            rows = self.nav_repo.get_nav_series(code, earliest.isoformat(), self.today.isoformat())
            points, basis = self._normalize_series(rows)
            series[code] = points
            bases[code] = basis

        missing_codes = [code for code in codes if len(series[code]) < 2]
        windows = {
            key: self._build_window(codes, series, bases, key, days)
            for key, days in self.WINDOWS.items()
        }
        available_windows = [item for item in windows.values() if item.get("status") in {"available", "partial"}]
        return {
            "status": "available" if available_windows else "insufficient",
            "methodology": "same_period_shared_nav_dates_v1",
            "risk_free_rate": self.metric_factory.risk_free_rate,
            "missing_codes": missing_codes,
            "windows": windows,
            "source": "local.postgres.fund_nav",
            "simulation_used": False,
            "product_scope": {
                "fund_browser": "core",
                "fund_evaluation": "supporting_evidence",
                "investment_decision": "excluded",
            },
        }

    def _build_window(
        self,
        codes: List[str],
        series: Dict[str, List[Tuple[date, float]]],
        bases: Dict[str, str],
        window: str,
        days: int,
    ) -> Dict[str, Any]:
        if any(len(series[code]) < 2 for code in codes):
            return self._empty_window(window, "fund_nav_missing")

        common_end = min(series[code][-1][0] for code in codes)
        requested_start = common_end - timedelta(days=days)
        date_sets = [
            {item_date for item_date, _ in series[code] if requested_start <= item_date <= common_end}
            for code in codes
        ]
        common_dates = sorted(set.intersection(*date_sets)) if date_sets else []
        if len(common_dates) < 2:
            return self._empty_window(window, "shared_nav_dates_insufficient")

        values_by_code = {
            code: {item_date: nav for item_date, nav in series[code]}
            for code in codes
        }
        fund_metrics = []
        for code in codes:
            aligned = [
                {"date": item_date, "nav": values_by_code[code][item_date]}
                for item_date in common_dates
            ]
            metrics: Dict[str, Any] = {}
            metrics.update(self.metric_factory.calculate_return_metrics(aligned))
            metrics.update(self.metric_factory.calculate_risk_metrics(aligned))
            drawdown = FundDrawdownRecoveryService.analyze(aligned)
            fund_metrics.append({
                "wind_code": code,
                "nav_basis": bases[code],
                "observations": len(common_dates),
                "total_return": metrics.get("total_return"),
                "annualized_return": metrics.get("annualized_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "annualized_volatility": metrics.get("annualized_volatility"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "drawdown_status": drawdown.get("status"),
                "drawdown_label": drawdown.get("label"),
                "current_drawdown": drawdown.get("current_drawdown"),
                "current_underwater_days": drawdown.get("current_underwater_days"),
                "worst_decline_days": drawdown.get("worst_decline_days"),
                "worst_recovery_days": drawdown.get("worst_recovery_days"),
                "worst_recovered": bool(drawdown.get("worst_recovery_date")),
                "longest_underwater_days": drawdown.get("longest_underwater_days"),
                "material_episode_count": drawdown.get("material_episode_count"),
                "recovered_material_episode_count": drawdown.get("recovered_material_episode_count"),
            })

        first_date = common_dates[0]
        last_date = common_dates[-1]
        actual_span_days = max((last_date - first_date).days, 0)
        minimum_span_days = self.MINIMUM_SPAN_DAYS[window]
        calendar_coverage_ratio = min(actual_span_days / minimum_span_days, 1.0)
        expected_business_days = max(self._business_days(first_date, last_date), 1)
        observation_coverage_ratio = min(len(common_dates) / expected_business_days, 1.0)
        ranking_eligible = (
            len(common_dates) >= 20
            and actual_span_days >= minimum_span_days
            and observation_coverage_ratio >= 0.8
        )
        chart = []
        base_values = {code: values_by_code[code][first_date] for code in codes}
        for item_date in common_dates:
            chart.append({
                "date": item_date,
                "values": {
                    code: values_by_code[code][item_date] / base_values[code] * 100
                    for code in codes
                },
            })

        return {
            "status": "available" if ranking_eligible else "partial",
            "window": window,
            "requested_start_date": requested_start,
            "actual_start_date": first_date,
            "actual_end_date": last_date,
            "observations": len(common_dates),
            "actual_span_days": actual_span_days,
            "calendar_coverage_ratio": round(calendar_coverage_ratio, 4),
            "observation_coverage_ratio": round(observation_coverage_ratio, 4),
            "ranking_eligible": ranking_eligible,
            "funds": fund_metrics,
            "chart": chart,
            "scope_note": (
                "所有基金只使用共同有净值的日期，累计净值优先；收益、风险、回撤和修复时间均按该共同区间重算。"
                + ("共同区间覆盖所选窗口且净值密度充足，可比较相对位置。" if ranking_eligible
                   else "共同区间未完整覆盖所选窗口或净值较稀疏，只展示实际可见期，不输出领先排名。")
            ),
        }

    @staticmethod
    def _empty_window(window: str, reason: str) -> Dict[str, Any]:
        return {
            "status": "insufficient",
            "window": window,
            "reason": reason,
            "observations": 0,
            "actual_span_days": 0,
            "calendar_coverage_ratio": 0.0,
            "observation_coverage_ratio": 0.0,
            "ranking_eligible": False,
            "funds": [],
            "chart": [],
        }

    @staticmethod
    def _business_days(start: date, end: date) -> int:
        if end < start:
            return 0
        total_days = (end - start).days + 1
        full_weeks, remainder = divmod(total_days, 7)
        count = full_weeks * 5
        for offset in range(remainder):
            if (start.weekday() + offset) % 7 < 5:
                count += 1
        return count

    @classmethod
    def _normalize_series(cls, rows: List[Dict[str, Any]]) -> Tuple[List[Tuple[date, float]], str]:
        parsed = []
        for row in rows:
            item_date = cls._parse_date(row.get("date") or row.get("trade_date"))
            unit_nav = cls._positive_number(row.get("nav") or row.get("unit_nav"))
            accum_nav = cls._positive_number(row.get("accum_nav"))
            if item_date is not None and (unit_nav is not None or accum_nav is not None):
                parsed.append((item_date, unit_nav, accum_nav))
        if not parsed:
            return [], "unavailable"

        use_accum = sum(1 for _, _, value in parsed if value is not None) >= max(2, ceil(len(parsed) * 0.9))
        normalized: Dict[date, float] = {}
        for item_date, unit_nav, accum_nav in parsed:
            value = accum_nav if use_accum else unit_nav
            if value is not None:
                normalized[item_date] = value
        return sorted(normalized.items()), "accum_nav" if use_accum else "unit_nav"

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()[:10]
        try:
            return date.fromisoformat(text) if text else None
        except ValueError:
            return None

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
