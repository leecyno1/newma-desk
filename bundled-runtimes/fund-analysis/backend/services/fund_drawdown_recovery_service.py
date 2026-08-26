"""基金净值回撤事件与修复时间分析。"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional


class FundDrawdownRecoveryService:
    BOUNDARY = "回撤与修复时间基于本地可见净值历史，只描述历史风险，不预测未来表现，也不直接改变基金评分。"

    def __init__(self, nav_repo: Optional[Any] = None, fund_repo: Optional[Any] = None):
        if nav_repo is None or fund_repo is None:
            from repositories import get_fund_repo, get_nav_repo

            nav_repo = nav_repo or get_nav_repo()
            fund_repo = fund_repo or get_fund_repo()
        self.nav_repo = nav_repo
        self.fund_repo = fund_repo

    def get(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        if not self.fund_repo.get_fund(code):
            raise ValueError(f"Fund not found: {code}")
        return {"wind_code": code, **self.analyze(self.nav_repo.get_nav_series(code))}

    @classmethod
    def analyze(cls, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        points, nav_basis = cls._points(rows)
        if len(points) < 2:
            return {
                "status": "insufficient_evidence",
                "nav_basis": nav_basis,
                "observations": len(points),
                "episodes": [],
                "included_in_score": False,
                "boundary": cls.BOUNDARY,
                "missing_items": ["至少需要两个可用净值日"],
            }

        episodes = cls._episodes(points)
        current = episodes[-1] if episodes and episodes[-1]["recovery_date"] is None else None
        worst = min(episodes, key=lambda item: item["depth"], default=None)
        material = [item for item in episodes if item["depth"] <= -0.05]
        recovered_material = [item for item in material if item["recovery_date"]]
        longest = max(episodes, key=lambda item: item["underwater_days"], default=None)
        current_drawdown = current["depth_at_end"] if current else 0.0
        current_days = current["underwater_days"] if current else 0

        if current_drawdown <= -0.10 and current_days >= 180:
            status, label = "deep_unrecovered", "当前处于较深且持续的回撤"
        elif current_drawdown <= -0.05:
            status, label = "current_drawdown", "当前仍在明显回撤中"
        elif current_drawdown < -0.01:
            status, label = "minor_drawdown", "当前处于小幅回撤"
        else:
            status, label = "near_high", "当前净值接近历史高位"

        note_parts = [
            f"当前较最近高点回撤 {abs(current_drawdown) * 100:.1f}%"
            + (f"，已持续 {current_days} 天" if current else "")
            + "。"
        ]
        if worst:
            if worst["recovery_date"]:
                recovery_text = f"谷底后 {worst['recovery_days']} 天修复"
            else:
                recovery_text = f"截至 {points[-1]['date'].isoformat()} 尚未修复"
            note_parts.append(
                f"可见区间最大回撤 {abs(worst['depth']) * 100:.1f}%："
                f"从峰值到谷底 {worst['decline_days']} 天，{recovery_text}。"
            )

        ranked_episodes = sorted(episodes, key=lambda item: (item["depth"], -item["underwater_days"]))[:5]
        return {
            "status": status,
            "label": label,
            "nav_basis": nav_basis,
            "history_start": points[0]["date"].isoformat(),
            "history_end": points[-1]["date"].isoformat(),
            "observations": len(points),
            "current_drawdown": current_drawdown,
            "current_underwater_days": current_days,
            "current_peak_date": current["start_date"] if current else points[-1]["date"].isoformat(),
            "worst_drawdown": worst["depth"] if worst else 0.0,
            "worst_peak_date": worst["start_date"] if worst else None,
            "worst_trough_date": worst["trough_date"] if worst else None,
            "worst_recovery_date": worst["recovery_date"] if worst else None,
            "worst_decline_days": worst["decline_days"] if worst else 0,
            "worst_recovery_days": worst["recovery_days"] if worst else None,
            "worst_underwater_days": worst["underwater_days"] if worst else 0,
            "longest_underwater_days": longest["underwater_days"] if longest else 0,
            "material_episode_count": len(material),
            "recovered_material_episode_count": len(recovered_material),
            "episodes": ranked_episodes,
            "included_in_score": False,
            "source": "local.postgres.fund_nav",
            "boundary": cls.BOUNDARY,
            "note": "".join(note_parts),
            "missing_items": [],
        }

    @staticmethod
    def _episodes(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        peak_date = points[0]["date"]
        peak_nav = points[0]["nav"]
        active = None
        episodes = []

        for point in points[1:]:
            day, nav = point["date"], point["nav"]
            if active is None:
                if nav >= peak_nav:
                    peak_date, peak_nav = day, nav
                    continue
                active = {
                    "start": peak_date,
                    "peak_nav": peak_nav,
                    "trough": day,
                    "trough_nav": nav,
                }
            elif nav < active["trough_nav"]:
                active["trough"], active["trough_nav"] = day, nav

            if active is not None and nav >= active["peak_nav"]:
                episodes.append(FundDrawdownRecoveryService._episode_payload(active, day, nav, day))
                peak_date, peak_nav = day, nav
                active = None

        if active is not None:
            last = points[-1]
            episodes.append(FundDrawdownRecoveryService._episode_payload(active, None, last["nav"], last["date"]))
        return episodes

    @staticmethod
    def _episode_payload(active: Dict[str, Any], recovery_date: Optional[date], end_nav: float, end_date: date) -> Dict[str, Any]:
        decline_days = (active["trough"] - active["start"]).days
        recovery_days = (recovery_date - active["trough"]).days if recovery_date else None
        underwater_days = ((recovery_date or end_date) - active["start"]).days
        return {
            "start_date": active["start"].isoformat(),
            "trough_date": active["trough"].isoformat(),
            "recovery_date": recovery_date.isoformat() if recovery_date else None,
            "depth": active["trough_nav"] / active["peak_nav"] - 1,
            "depth_at_end": end_nav / active["peak_nav"] - 1,
            "decline_days": decline_days,
            "recovery_days": recovery_days,
            "underwater_days": underwater_days,
            "status": "recovered" if recovery_date else "unrecovered",
        }

    @staticmethod
    def _points(rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], str]:
        normalized = []
        accum_count = sum(FundDrawdownRecoveryService._positive(row.get("accum_nav")) is not None for row in rows)
        unit_count = sum(FundDrawdownRecoveryService._positive(row.get("nav") or row.get("unit_nav")) is not None for row in rows)
        use_accum = accum_count >= 2 and accum_count >= unit_count
        for row in rows:
            day = FundDrawdownRecoveryService._date(row.get("date") or row.get("trade_date"))
            nav = FundDrawdownRecoveryService._positive(
                row.get("accum_nav") if use_accum else row.get("nav") or row.get("unit_nav")
            )
            if day and nav is not None:
                normalized.append({"date": day, "nav": nav})
        deduplicated = {item["date"]: item for item in normalized}
        return sorted(deduplicated.values(), key=lambda item: item["date"]), "accum_nav" if use_accum else "unit_nav"

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
