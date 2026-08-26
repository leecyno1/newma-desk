"""根据基金定期报告净资产形成规模趋势事实。"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional


class FundScaleTrendService:
    BOUNDARY = "规模趋势来自定期报告净资产，只用于解释容量、流动性和持续性，不直接改变基金评分。"

    def __init__(self, repo: Optional[Any] = None):
        if repo is None:
            from repositories import get_fund_asset_allocation_repo

            repo = get_fund_asset_allocation_repo()
        self.repo = repo

    def get(self, wind_code: str, limit: int = 24) -> Dict[str, Any]:
        return self.analyze(self.repo.list_history(wind_code, limit=limit))

    @classmethod
    def analyze(cls, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        points = []
        for row in history:
            report_date = cls._date(row.get("report_date"))
            asset = cls._number(row.get("net_asset_yi"))
            if report_date and asset is not None and asset > 0:
                points.append({"date": report_date, "asset": asset})
        points.sort(key=lambda item: item["date"], reverse=True)

        if len(points) < 2:
            return {
                "status": "insufficient_evidence",
                "label": "规模趋势待补",
                "observations": len(points),
                "included_in_score": False,
                "boundary": cls.BOUNDARY,
                "note": "至少需要两个报告期的净资产数据。",
            }

        latest = points[0]
        previous = points[1]
        one_year = cls._reference(points, latest["date"], 365, 150)
        three_year = cls._reference(points, latest["date"], 365 * 3, 210)
        peak = max(points, key=lambda item: item["asset"])
        trough = min(points, key=lambda item: item["asset"])
        previous_change = cls._change(latest["asset"], previous["asset"])
        one_year_change = cls._change(latest["asset"], one_year["asset"]) if one_year else None
        three_year_change = cls._change(latest["asset"], three_year["asset"]) if three_year else None
        from_peak = cls._change(latest["asset"], peak["asset"])

        status, label = cls._classify(latest["asset"], one_year_change, from_peak)
        comparison = (
            f"较一年前 {one_year_change * 100:+.1f}%"
            if one_year_change is not None
            else f"较上一报告期 {previous_change * 100:+.1f}%"
        )
        peak_note = f"，较可见历史峰值 {from_peak * 100:+.1f}%" if from_peak < -0.05 else ""
        notes = [f"最新报告期净资产 {latest['asset']:.2f} 亿元，{comparison}{peak_note}。"]
        if status == "small_scale":
            notes.append("当前规模低于 2 亿元，需结合持有人结构关注运营持续性。")
        elif status == "shrinking":
            notes.append("规模下降较明显，需结合业绩、申赎和经理变化解释原因。")
        elif status == "rapid_growth":
            notes.append("规模增长较快，主动管理基金需继续观察策略容量和超额收益延续性。")
        elif status == "recovering":
            notes.append("规模正在回升，但仍明显低于可见历史峰值。")

        return {
            "status": status,
            "label": label,
            "latest_report_date": latest["date"].isoformat(),
            "latest_asset_yi": latest["asset"],
            "previous_report_date": previous["date"].isoformat(),
            "previous_asset_yi": previous["asset"],
            "previous_change": previous_change,
            "one_year_reference_date": one_year["date"].isoformat() if one_year else None,
            "one_year_change": one_year_change,
            "three_year_reference_date": three_year["date"].isoformat() if three_year else None,
            "three_year_change": three_year_change,
            "peak_asset_yi": peak["asset"],
            "peak_date": peak["date"].isoformat(),
            "latest_from_peak": from_peak,
            "trough_asset_yi": trough["asset"],
            "trough_date": trough["date"].isoformat(),
            "observations": len(points),
            "history_start": points[-1]["date"].isoformat(),
            "history_end": latest["date"].isoformat(),
            "included_in_score": False,
            "source": "local.postgres.fund_asset_allocations",
            "boundary": cls.BOUNDARY,
            "note": "".join(notes),
        }

    @staticmethod
    def _classify(latest_asset: float, one_year_change: Optional[float], from_peak: float) -> tuple[str, str]:
        if latest_asset < 2:
            return "small_scale", "规模偏小"
        if one_year_change is not None:
            if one_year_change <= -0.30:
                return "shrinking", "规模明显缩水"
            if one_year_change >= 0.50 and from_peak <= -0.50:
                return "recovering", "规模快速回升"
            if one_year_change >= 0.50:
                return "rapid_growth", "规模快速增长"
            if abs(one_year_change) <= 0.15:
                return "stable", "近一年规模基本稳定"
            if one_year_change > 0:
                return "growing", "规模温和增长"
            return "declining", "规模温和下降"
        if from_peak <= -0.50:
            return "shrinking", "规模明显缩水"
        return "available", "规模趋势已有记录"

    @staticmethod
    def _reference(points: List[Dict[str, Any]], latest_date: date, days: int, tolerance: int) -> Optional[Dict[str, Any]]:
        target = (latest_date.toordinal() - days)
        candidates = [
            point for point in points[1:]
            if abs(point["date"].toordinal() - target) <= tolerance
        ]
        return min(candidates, key=lambda item: abs(item["date"].toordinal() - target)) if candidates else None

    @staticmethod
    def _change(latest: float, reference: float) -> float:
        return latest / reference - 1 if reference > 0 else 0.0

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
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if number == number else None
        except (TypeError, ValueError):
            return None
