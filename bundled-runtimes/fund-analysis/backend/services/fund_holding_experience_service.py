"""用本地真实净值回放不同持有期限的历史体验。"""
from bisect import bisect_left
from calendar import monthrange
from datetime import date, datetime
from statistics import mean, median
from typing import Any, Dict, List, Optional


class FundHoldingExperienceService:
    PERIODS = (1, 3, 6, 12)
    RETURN_THRESHOLDS = (0, 0.01, 0.02, 0.03, 0.04, 0.05)
    MIN_SAMPLE_COUNT = 20
    MAX_TARGET_SLIPPAGE_DAYS = 14

    def __init__(self, nav_repo: Optional[Any] = None):
        self._nav_repo = nav_repo

    def analyze(self, wind_code: str) -> Dict[str, Any]:
        series = self._series(self._repo().get_nav_series(wind_code))
        if len(series) < 2:
            return self._unavailable(wind_code, "本地真实净值样本不足。")

        dates = [item[0] for item in series]
        values = [item[1] for item in series]
        periods = [self._period_result(months, dates, values) for months in self.PERIODS]
        usable = [item for item in periods if item["sample_count"] >= self.MIN_SAMPLE_COUNT]
        return {
            "wind_code": wind_code,
            "status": "available" if usable else "insufficient_evidence",
            "source": "local.postgres.fund_nav",
            "nav_basis": "accum_nav_preferred",
            "sample_start": dates[0].isoformat(),
            "sample_end": dates[-1].isoformat(),
            "nav_observations": len(series),
            "periods": periods,
            "methodology": {
                "rule": "每个历史净值日作为买入日，在目标月数后的首个净值日卖出。",
                "dividend_rule": "优先使用累计净值，避免现金分红扭曲持有回报。",
                "maximum_target_slippage_days": self.MAX_TARGET_SLIPPAGE_DAYS,
                "minimum_sample_count": self.MIN_SAMPLE_COUNT,
                "boundary": "历史持有体验用于基金评价，不代表未来收益或投资建议。",
            },
            "missing_items": [] if usable else [f"各持有期限均未达到 {self.MIN_SAMPLE_COUNT} 个历史样本。"],
        }

    def _repo(self):
        if self._nav_repo is None:
            from repositories import get_nav_repo

            self._nav_repo = get_nav_repo()
        return self._nav_repo

    def _period_result(self, months: int, dates: List[date], values: List[float]) -> Dict[str, Any]:
        returns = []
        actual_days = []
        buy_dates = []
        for index, buy_date in enumerate(dates):
            target_date = self._add_months(buy_date, months)
            sell_index = bisect_left(dates, target_date, lo=index + 1)
            if sell_index >= len(dates):
                break
            sell_date = dates[sell_index]
            if (sell_date - target_date).days > self.MAX_TARGET_SLIPPAGE_DAYS:
                continue
            buy_value = values[index]
            sell_value = values[sell_index]
            if buy_value <= 0 or sell_value <= 0:
                continue
            returns.append(sell_value / buy_value - 1)
            actual_days.append((sell_date - buy_date).days)
            buy_dates.append(buy_date)

        sample_count = len(returns)
        return_threshold_probabilities = [
            {
                "threshold": threshold,
                "probability": self._round(sum(value > threshold for value in returns) / sample_count) if returns else None,
            }
            for threshold in self.RETURN_THRESHOLDS
        ]
        return {
            "months": months,
            "label": f"持有 {months} 个月",
            "status": "sufficient" if sample_count >= self.MIN_SAMPLE_COUNT else "insufficient_evidence",
            "sample_count": sample_count,
            "positive_probability": self._round(sum(value > 0 for value in returns) / sample_count) if returns else None,
            "non_loss_probability": self._round(sum(value >= 0 for value in returns) / sample_count) if returns else None,
            "return_threshold_probabilities": return_threshold_probabilities,
            "median_return": self._round(median(returns)) if returns else None,
            "average_return": self._round(mean(returns)) if returns else None,
            "best_return": self._round(max(returns)) if returns else None,
            "worst_return": self._round(min(returns)) if returns else None,
            "average_actual_days": round(mean(actual_days), 1) if actual_days else None,
            "first_buy_date": buy_dates[0].isoformat() if buy_dates else None,
            "last_buy_date": buy_dates[-1].isoformat() if buy_dates else None,
        }

    @staticmethod
    def _series(rows: List[Dict[str, Any]]) -> List[tuple[date, float]]:
        values: Dict[date, float] = {}
        for row in rows:
            nav_date = FundHoldingExperienceService._date(row.get("date"))
            nav_value = FundHoldingExperienceService._number(row.get("accum_nav"))
            if nav_value is None or nav_value <= 0:
                nav_value = FundHoldingExperienceService._number(row.get("nav"))
            if nav_date and nav_value is not None and nav_value > 0:
                values[nav_date] = nav_value
        return sorted(values.items())

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, min(value.day, monthrange(year, month)[1]))

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _round(value: float) -> float:
        return round(float(value), 6)

    @staticmethod
    def _unavailable(wind_code: str, reason: str) -> Dict[str, Any]:
        return {
            "wind_code": wind_code,
            "status": "insufficient_evidence",
            "source": "local.postgres.fund_nav",
            "nav_basis": "accum_nav_preferred",
            "nav_observations": 0,
            "periods": [],
            "missing_items": [reason],
        }
