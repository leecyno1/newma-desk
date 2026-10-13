"""基金净值派生序列：水下回撤曲线与滚动收益，供详情页图表直接使用。"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional


WINDOW_OBSERVATIONS = {
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "3y": 756,
}


class FundDerivedSeriesService:
    BOUNDARY = "派生序列基于本地可见净值历史，只描述历史轨迹，不预测未来表现，也不直接改变基金评分。"

    def __init__(self, nav_repo: Optional[Any] = None, fund_repo: Optional[Any] = None):
        if nav_repo is None or fund_repo is None:
            from repositories import get_fund_repo, get_nav_repo

            nav_repo = nav_repo or get_nav_repo()
            fund_repo = fund_repo or get_fund_repo()
        self.nav_repo = nav_repo
        self.fund_repo = fund_repo

    def get(self, wind_code: str, window: str = "1y") -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        if not self.fund_repo.get_fund(code):
            raise ValueError(f"Fund not found: {code}")
        return {"wind_code": code, **self.build(self.nav_repo.get_nav_series(code), window=window)}

    @classmethod
    def build(cls, rows: List[Dict[str, Any]], window: str = "1y") -> Dict[str, Any]:
        points, basis = cls._points(rows)
        window_key = str(window or "1y").lower()
        observations = WINDOW_OBSERVATIONS.get(window_key)
        if observations is None:
            return {
                "status": "unsupported_window",
                "observations": len(points),
                "window": window_key,
                "nav_basis": basis,
                "drawdown_series": [],
                "rolling_return_series": [],
                "boundary": cls.BOUNDARY,
                "missing_items": [f"不支持的滚动窗口：{window}"],
            }
        if len(points) < 2:
            return {
                "status": "insufficient_evidence",
                "observations": len(points),
                "window": window_key,
                "nav_basis": basis,
                "drawdown_series": [],
                "rolling_return_series": [],
                "boundary": cls.BOUNDARY,
                "missing_items": ["至少需要两个可用净值日"],
            }

        running_peak = points[0][1]
        drawdown_series = []
        for point_date, nav in points:
            if nav > running_peak:
                running_peak = nav
            drawdown_series.append({
                "date": point_date.isoformat(),
                "drawdown": nav / running_peak - 1,
            })

        rolling_series = []
        if len(points) > observations:
            for index in range(observations, len(points)):
                previous_nav = points[index - observations][1]
                if previous_nav <= 0:
                    continue
                rolling_series.append({
                    "date": points[index][0].isoformat(),
                    "window": window_key,
                    "value": points[index][1] / previous_nav - 1,
                })
        elif len(points) >= 2:
            # 滚动窗口不够，但真实回撤轨迹照常给出，并携带真实历史起止日，
            # 让前端只隐藏滚动图而不是整段回撤（UAT：短样本回撤隐藏）。
            return {
                "status": "insufficient_evidence",
                "observations": len(points),
                "window": window_key,
                "nav_basis": basis,
                "history_start": points[0][0].isoformat(),
                "history_end": points[-1][0].isoformat(),
                "drawdown_series": drawdown_series,
                "rolling_return_series": [],
                "boundary": cls.BOUNDARY,
                "missing_items": [f"滚动 {window_key} 窗口需要至少 {observations + 1} 个净值点，当前 {len(points)} 个"],
            }

        return {
            "status": "ok",
            "observations": len(points),
            "window": window_key,
            "nav_basis": basis,
            "history_start": points[0][0].isoformat(),
            "history_end": points[-1][0].isoformat(),
            "drawdown_series": drawdown_series,
            "rolling_return_series": rolling_series,
            "boundary": cls.BOUNDARY,
        }

    @staticmethod
    def _points(rows: List[Dict[str, Any]]) -> tuple:
        def positive(value):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            return number if number > 0 else None

        adj_count = sum(positive(row.get("adj_nav")) is not None for row in rows or [])
        accum_count = sum(positive(row.get("accum_nav")) is not None for row in rows or [])
        unit_count = sum(positive(row.get("nav") or row.get("unit_nav")) is not None for row in rows or [])
        if adj_count >= 2 and adj_count >= max(accum_count, unit_count) * 0.6:
            basis = "adj_nav"
        elif accum_count >= 2 and accum_count >= unit_count:
            basis = "accum_nav"
        else:
            basis = "unit_nav"

        points = []
        for row in rows or []:
            raw_date = row.get("date") or row.get("trade_date")
            if isinstance(raw_date, datetime):
                point_date = raw_date.date()
            elif isinstance(raw_date, date):
                point_date = raw_date
            else:
                try:
                    point_date = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    continue
            if basis == "adj_nav":
                nav_value = positive(row.get("adj_nav"))
            elif basis == "accum_nav":
                nav_value = positive(row.get("accum_nav"))
            else:
                nav_value = positive(row.get("nav") or row.get("unit_nav"))
            if nav_value is not None:
                points.append((point_date, nav_value))
        points.sort(key=lambda item: item[0])
        return points, basis
