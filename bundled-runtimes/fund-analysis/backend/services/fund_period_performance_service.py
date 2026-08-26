"""基金自然年度业绩与同类年度排名。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional


class FundPeriodPerformanceService:
    MIN_OBSERVATIONS = 20
    MIN_OBSERVATION_COVERAGE = 0.70
    DATE_TOLERANCE_DAYS = 15
    BOUNDARY = "年度收益基于本地真实净值；同类排名只使用相同标准同类组、同一自然年度且覆盖完整的基金实体，不构成收益承诺。"

    def __init__(
        self,
        nav_repo: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
    ):
        if nav_repo is None or fund_repo is None or classification_repo is None:
            from repositories import get_fund_classification_repo, get_fund_repo, get_nav_repo

            nav_repo = nav_repo or get_nav_repo()
            fund_repo = fund_repo or get_fund_repo()
            classification_repo = classification_repo or get_fund_classification_repo()
        self.nav_repo = nav_repo
        self.fund_repo = fund_repo
        self.classification_repo = classification_repo

    def get(self, wind_code: str, years: int = 5) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            raise ValueError(f"Fund not found: {code}")

        period_count = max(1, min(int(years), 8))
        current_year = date.today().year
        earliest = date(current_year - period_count, 11, 15)
        rows = self.nav_repo.get_nav_series(code, earliest.isoformat(), date.today().isoformat())
        points, nav_basis = self._points(rows)
        if len(points) < 2:
            return self._unavailable(code, nav_basis, len(points), "至少需要两个可用净值日")

        latest_date = points[-1]["date"]
        period_years = range(latest_date.year, latest_date.year - period_count, -1)
        context = self.classification_repo.get_classification_context(code) or {}
        peer_group_id = str(context.get("peer_group_id") or "").strip()
        peer_group_name = str(context.get("peer_group_name") or "").strip()
        target_entity_id = str(context.get("entity_id") or "").strip()
        minimum_peer_count = max(2, int(context.get("minimum_peer_count") or 5))

        periods = []
        for year in period_years:
            start_date = date(year, 1, 1)
            end_date = min(date(year, 12, 31), latest_date)
            target = self._period_result(points, start_date, end_date)
            if target is None:
                continue
            peer_rank = self._peer_rank(
                target,
                peer_group_id=peer_group_id,
                target_entity_id=target_entity_id,
                start_date=start_date,
                end_date=end_date,
                minimum_peer_count=minimum_peer_count,
            )
            periods.append({
                "year": year,
                "label": f"{year} 年以来" if year == latest_date.year else f"{year} 年",
                "is_ytd": year == latest_date.year,
                **target,
                **peer_rank,
            })

        if not periods:
            return self._unavailable(code, nav_basis, len(points), "可见净值不足以计算自然年度收益")

        complete_periods = [item for item in periods if item["coverage_status"] == "complete"]
        ranked_periods = [item for item in periods if item.get("rank") is not None]
        best = max(complete_periods, key=lambda item: item["return"], default=None)
        worst = min(complete_periods, key=lambda item: item["return"], default=None)
        return {
            "wind_code": code,
            "status": "available",
            "nav_basis": nav_basis,
            "latest_nav_date": latest_date.isoformat(),
            "peer_group_id": peer_group_id or None,
            "peer_group_name": peer_group_name or None,
            "minimum_peer_count": minimum_peer_count,
            "periods": periods,
            "summary": {
                "available_period_count": len(periods),
                "complete_period_count": len(complete_periods),
                "positive_period_count": sum(item["return"] > 0 for item in complete_periods),
                "peer_ranked_period_count": len(ranked_periods),
                "above_peer_median_count": sum(item.get("above_peer_median") is True for item in ranked_periods),
                "best_period": self._period_summary(best),
                "worst_period": self._period_summary(worst),
            },
            "source": "local.postgres.fund_nav+standardized_peer_group",
            "methodology_version": "calendar_period_peer_rank_v1",
            "included_in_score": False,
            "boundary": self.BOUNDARY,
            "missing_items": [] if peer_group_id else ["标准同类组待补，暂不显示年度同类排名"],
        }

    def _peer_rank(
        self,
        target: Dict[str, Any],
        peer_group_id: str,
        target_entity_id: str,
        start_date: date,
        end_date: date,
        minimum_peer_count: int,
    ) -> Dict[str, Any]:
        if target.get("coverage_status") != "complete":
            return self._empty_rank("target_period_incomplete")
        if not peer_group_id:
            return self._empty_rank("classification_unavailable")

        summaries = self.classification_repo.list_peer_calendar_period_summaries(
            peer_group_id,
            start_date,
            end_date,
            start_date - timedelta(days=45),
        )
        peer_returns = []
        for summary in summaries:
            if target_entity_id and str(summary.get("entity_id") or "") == target_entity_id:
                continue
            item = self._summary_period_result(summary, start_date, end_date)
            if item and item["coverage_status"] == "complete":
                peer_returns.append(float(item["return"]))

        peer_count = len(peer_returns) + 1
        if peer_count < minimum_peer_count:
            return {
                **self._empty_rank("insufficient_peer_sample"),
                "peer_count": peer_count,
            }
        target_return = float(target["return"])
        rank = 1 + sum(value > target_return for value in peer_returns)
        percentile = 100.0 if peer_count == 1 else (peer_count - rank) / (peer_count - 1) * 100
        peer_median = median(peer_returns) if peer_returns else None
        return {
            "sample_status": "sufficient",
            "rank": rank,
            "peer_count": peer_count,
            "percentile": round(percentile, 2),
            "peer_median_return": peer_median,
            "above_peer_median": target_return > peer_median if peer_median is not None else None,
        }

    @classmethod
    def _period_result(
        cls,
        points: List[Dict[str, Any]],
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]:
        baseline = next((item for item in reversed(points) if item["date"] < start_date), None)
        in_period = [item for item in points if start_date <= item["date"] <= end_date]
        if not in_period:
            return None
        first = in_period[0]
        last = in_period[-1]
        base = baseline or first
        if base["nav"] <= 0 or last["nav"] <= 0 or base["date"] >= last["date"]:
            return None
        expected = cls._expected_observations(start_date, end_date)
        observation_coverage = min(1.0, len(in_period) / expected) if expected else 0.0
        complete = bool(
            baseline
            and (start_date - baseline["date"]).days <= cls.DATE_TOLERANCE_DAYS
            and (end_date - last["date"]).days <= cls.DATE_TOLERANCE_DAYS
            and len(in_period) >= cls.MIN_OBSERVATIONS
            and observation_coverage >= cls.MIN_OBSERVATION_COVERAGE
        )
        return {
            "return": last["nav"] / base["nav"] - 1,
            "requested_start_date": start_date.isoformat(),
            "requested_end_date": end_date.isoformat(),
            "actual_start_date": base["date"].isoformat(),
            "actual_end_date": last["date"].isoformat(),
            "observations": len(in_period),
            "expected_observations": expected,
            "observation_coverage": round(observation_coverage, 6),
            "coverage_status": "complete" if complete else "partial",
            "return_basis": "full_period" if complete else "since_inception_or_data_start",
        }

    @classmethod
    def _summary_period_result(
        cls,
        summary: Dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]:
        baseline_date = cls._date(summary.get("baseline_date"))
        first_date = cls._date(summary.get("first_date"))
        last_date = cls._date(summary.get("last_date"))
        baseline_nav = cls._positive(summary.get("baseline_nav"))
        first_nav = cls._positive(summary.get("first_nav"))
        last_nav = cls._positive(summary.get("last_nav"))
        observations = int(summary.get("observations") or 0)
        if not first_date or not last_date or last_nav is None:
            return None
        base_date = baseline_date or first_date
        base_nav = baseline_nav or first_nav
        if base_nav is None or base_nav <= 0 or base_date >= last_date:
            return None
        expected = cls._expected_observations(start_date, end_date)
        observation_coverage = min(1.0, observations / expected) if expected else 0.0
        complete = bool(
            baseline_date
            and (start_date - baseline_date).days <= cls.DATE_TOLERANCE_DAYS
            and (end_date - last_date).days <= cls.DATE_TOLERANCE_DAYS
            and observations >= cls.MIN_OBSERVATIONS
            and observation_coverage >= cls.MIN_OBSERVATION_COVERAGE
        )
        return {
            "return": last_nav / base_nav - 1,
            "coverage_status": "complete" if complete else "partial",
        }

    @staticmethod
    def _empty_rank(status: str) -> Dict[str, Any]:
        return {
            "sample_status": status,
            "rank": None,
            "peer_count": 0,
            "percentile": None,
            "peer_median_return": None,
            "above_peer_median": None,
        }

    @staticmethod
    def _expected_observations(start_date: date, end_date: date) -> int:
        days = max(1, (end_date - start_date).days + 1)
        return max(2, round(days / 365.25 * 252))

    @staticmethod
    def _period_summary(period: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not period:
            return None
        return {"year": period["year"], "label": period["label"], "return": period["return"]}

    @staticmethod
    def _points(rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], str]:
        accum_count = sum(FundPeriodPerformanceService._positive(row.get("accum_nav")) is not None for row in rows)
        unit_count = sum(FundPeriodPerformanceService._positive(row.get("nav") or row.get("unit_nav")) is not None for row in rows)
        use_accum = accum_count >= max(2, round(max(accum_count, unit_count) * 0.9))
        points = {}
        for row in rows:
            day = FundPeriodPerformanceService._date(row.get("date") or row.get("trade_date"))
            value = FundPeriodPerformanceService._positive(
                row.get("accum_nav") if use_accum else row.get("nav") or row.get("unit_nav")
            )
            if day and value is not None:
                points[day] = {"date": day, "nav": value}
        return sorted(points.values(), key=lambda item: item["date"]), "accum_nav" if use_accum else "unit_nav"

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value or "")[:10])
        except ValueError:
            return None

    @staticmethod
    def _positive(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if number > 0 and number == number else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _unavailable(cls, code: str, nav_basis: str, observations: int, reason: str) -> Dict[str, Any]:
        return {
            "wind_code": code,
            "status": "insufficient_evidence",
            "nav_basis": nav_basis,
            "periods": [],
            "summary": {},
            "source": "local.postgres.fund_nav",
            "methodology_version": "calendar_period_peer_rank_v1",
            "included_in_score": False,
            "boundary": cls.BOUNDARY,
            "missing_items": [reason],
            "observations": observations,
        }
