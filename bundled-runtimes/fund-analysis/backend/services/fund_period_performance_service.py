"""基金自然年度业绩与同类年度排名。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional
from services.performance_nav_series import normalize_performance_rows, positive_number
from services.fund_trading_calendar import get_trading_calendar, fund_risk_calendar

METHODOLOGY_VERSION = "calendar_period_adjusted_aligned_v2"


class FundPeriodPerformanceService:
    DATE_TOLERANCE_DAYS = 15
    BOUNDARY = "年度收益仅用本地复权净值；同类排名要求日历覆盖完整、实际起止日一致，每个基金实体只计一个份额。使用当前同类成员，不是历史时点成员回测；不纳入评分或构成收益承诺。"

    def __init__(
        self,
        nav_repo: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
        today: Optional[date] = None,
    ):
        if nav_repo is None or fund_repo is None or classification_repo is None:
            from repositories import get_fund_classification_repo, get_fund_repo, get_nav_repo

            nav_repo = nav_repo or get_nav_repo()
            fund_repo = fund_repo or get_fund_repo()
            classification_repo = classification_repo or get_fund_classification_repo()
        self.nav_repo = nav_repo
        self.fund_repo = fund_repo
        self.classification_repo = classification_repo
        self.today = today or date.today()

    def get(self, wind_code: str, years: int = 5) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            raise ValueError(f"Fund not found: {code}")

        period_count = max(1, min(int(years), 8))
        current_year = self.today.year
        earliest = date(current_year - period_count, 11, 15)
        rows = self.nav_repo.get_nav_series(code, earliest.isoformat(), self.today.isoformat())
        points, nav_basis = self._points([{**row, 'risk_calendar': row.get('risk_calendar') or fund_risk_calendar(fund)} for row in rows])
        points = [row for row in points if row['date'] <= self.today]
        valid = [row for row in points if row['nav'] is not None]
        if len(valid) < 2:
            return self._unavailable(code, nav_basis, len(valid), "至少需要两个有效复权净值日，不能用累计或单位净值补造")

        latest_date = valid[-1]["date"]
        period_years = range(current_year, current_year - period_count, -1)
        context = self.classification_repo.get_classification_context(code) or {}
        peer_group_id = str(context.get("peer_group_id") or "").strip()
        peer_group_name = str(context.get("peer_group_name") or "").strip()
        target_entity_id = str(context.get("entity_id") or "").strip()
        minimum_peer_count = max(2, int(context.get("minimum_peer_count") or 5))

        periods = []
        for year in period_years:
            start_date = date(year, 1, 1)
            end_date = min(date(year, 12, 31), self.today)
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
                "label": f"{year} 年以来" if year == current_year else f"{year} 年",
                "is_ytd": year == current_year,
                **target,
                **peer_rank,
            })

        if not periods:
            return self._unavailable(code, nav_basis, len(points), "可见净值不足以计算自然年度收益")

        complete_periods = [item for item in periods if item["coverage_status"] == "complete" and not item['is_ytd']]
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
            "methodology_version": METHODOLOGY_VERSION,
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
        if not peer_group_id or not target_entity_id:
            return self._empty_rank("classification_unavailable")

        summaries = self.classification_repo.list_peer_calendar_period_summaries(
            peer_group_id,
            start_date,
            end_date,
            start_date - timedelta(days=45),
        )
        peer_returns = []
        seen_entities = set()
        for summary in summaries:
            if target_entity_id and str(summary.get("entity_id") or "") == target_entity_id:
                continue
            item = self._summary_period_result(summary, start_date, end_date)
            entity = str(summary.get('entity_id') or '')
            if (item and entity and entity not in seen_entities and item["coverage_status"] == "complete"
                    and item['actual_start_date'] == target['actual_start_date']
                    and item['actual_end_date'] == target['actual_end_date']):
                peer_returns.append(float(item["return"]))
                seen_entities.add(entity)

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
        valid = [item for item in in_period if item['nav'] is not None]
        if not valid:
            return None
        calendars = {row.get('risk_calendar') for row in in_period + ([baseline] if baseline else [])}
        return cls._summary_period_result({
            'nav_basis': 'adj_nav', 'risk_calendar': 'SSE' if calendars == {'SSE'} else None,
            'baseline_date': baseline['date'] if baseline else None, 'baseline_nav': baseline['nav'] if baseline else None,
            'first_date': valid[0]['date'], 'first_nav': valid[0]['nav'],
            'last_date': valid[-1]['date'], 'last_nav': valid[-1]['nav'],
            'last_record_date': in_period[-1]['date'], 'last_record_nav': in_period[-1]['nav'],
            'observations': len(valid), 'valid_dates': [row['date'] for row in valid],
            'missing_observations': len(in_period) - len(valid),
        }, start_date, end_date)

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
        if summary.get('nav_basis') != 'adj_nav' or not first_date or not last_date or last_nav is None:
            return None
        base_date = baseline_date if baseline_nav is not None else first_date
        base_nav = baseline_nav if baseline_nav is not None else first_nav
        if base_nav is None or base_nav <= 0 or base_date >= last_date:
            return None
        dates = {day for value in summary.get('valid_dates', []) if (day := cls._date(value)) is not None}
        calendar = get_trading_calendar() if summary.get('risk_calendar') == 'SSE' else None
        opened = calendar.open_days(start_date, end_date) if calendar else None
        prior = calendar.open_days(start_date - timedelta(days=cls.DATE_TOLERANCE_DAYS), start_date - timedelta(days=1)) if calendar else None
        expected = len(opened) if opened is not None else cls._expected_observations(start_date, end_date)
        covered = len(dates & opened) if opened is not None else observations
        observation_coverage = min(1.0, covered / expected) if expected else 0.0
        complete = bool(opened and prior and baseline_nav is not None and baseline_date is not None
                        and max(prior) <= baseline_date < start_date and last_date >= max(opened)
                        and not (opened - dates) and not summary.get('missing_observations')
                        and cls._positive(summary.get('last_record_nav')) is not None)
        return {
            "return": last_nav / base_nav - 1,
            "requested_start_date": start_date.isoformat(), "requested_end_date": end_date.isoformat(),
            "actual_start_date": base_date.isoformat(), "actual_end_date": last_date.isoformat(),
            "observations": observations, "expected_observations": expected,
            "observation_coverage": round(observation_coverage, 6),
            "coverage_status": "complete" if complete else "partial",
            "return_basis": "full_period" if complete else "visible_period_only",
            "methodology": {'methodology_version': METHODOLOGY_VERSION, 'nav_basis': 'adj_nav',
                            'calendar_status': 'verified' if complete else 'incomplete_nav' if opened is not None else 'unavailable',
                            'calendar_source': 'tushare.trade_cal' if opened is not None else None,
                            'missing_open_days': len(opened - dates) if opened is not None else None,
                            'missing_observations': int(summary.get('missing_observations') or 0)},
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
        return normalize_performance_rows([{**row, 'adj_nav': row.get('adj_nav')} for row in rows]), 'adj_nav'

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
        return positive_number(value)

    @classmethod
    def _unavailable(cls, code: str, nav_basis: str, observations: int, reason: str) -> Dict[str, Any]:
        return {
            "wind_code": code,
            "status": "insufficient_evidence",
            "nav_basis": nav_basis,
            "periods": [],
            "summary": {},
            "source": "local.postgres.fund_nav",
            "methodology_version": METHODOLOGY_VERSION,
            "included_in_score": False,
            "boundary": cls.BOUNDARY,
            "missing_items": [reason],
            "observations": observations,
        }
