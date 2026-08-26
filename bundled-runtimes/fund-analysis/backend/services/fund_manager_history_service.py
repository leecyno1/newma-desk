"""基金维度的经理任职历史。"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


class FundManagerHistoryService:
    BOUNDARY = "经理变动只作为基金评价的解释证据，不因更换、增聘或共管本身直接加减分。"

    def __init__(
        self,
        manager_repo: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        today: Optional[date] = None,
    ):
        if manager_repo is None or fund_repo is None:
            from repositories import get_fund_repo, get_manager_repo

            manager_repo = manager_repo or get_manager_repo()
            fund_repo = fund_repo or get_fund_repo()
        self.manager_repo = manager_repo
        self.fund_repo = fund_repo
        self.today = today or date.today()

    def get(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            raise ValueError(f"Fund not found: {code}")

        rows = self.manager_repo.list_fund_manager_history(code)
        if not rows:
            return {
                "wind_code": code,
                "status": "unavailable",
                "product": {"canonical_code": code, "canonical_name": fund.get("name") or code},
                "summary": {
                    "manager_count": 0,
                    "current_manager_count": 0,
                    "historical_manager_count": 0,
                    "change_event_count": 0,
                    "team_mode": "unavailable",
                },
                "stability_evidence": {
                    "status": "unavailable",
                    "label": "经理任职历史待补",
                    "included_in_score": False,
                    "note": "本地任职表暂无该基金的可核验经理记录。",
                },
                "tenures": [],
                "sources": [],
                "boundary": self.BOUNDARY,
                "missing_items": ["本地任职表暂无该基金的可核验经理记录"],
            }

        tenures = self._merge_tenures(rows)
        current_manager_ids = {
            item["manager_id"] for item in tenures if item["is_current"]
        }
        manager_ids = {item["manager_id"] for item in tenures}
        start_dates = sorted({item["start_date"] for item in tenures if item["start_date"]})
        share_codes = sorted({str(row.get("fund_code") or "").upper() for row in rows if row.get("fund_code")})
        updated_values = [self._date_text(row.get("record_updated_at")) for row in rows]
        updated_values = [value for value in updated_values if value]
        first = rows[0]

        return {
            "wind_code": code,
            "status": "available",
            "product": {
                "entity_id": str(first.get("entity_id") or ""),
                "canonical_code": first.get("canonical_code") or code,
                "canonical_name": first.get("canonical_name") or fund.get("name") or code,
                "share_codes": share_codes,
            },
            "summary": {
                "manager_count": len(manager_ids),
                "current_manager_count": len(current_manager_ids),
                "historical_manager_count": len(manager_ids - current_manager_ids),
                "change_event_count": max(len(start_dates) - 1, 0),
                "team_mode": "co_managed" if len(current_manager_ids) > 1 else "single_manager",
                "first_tenure_start": min(start_dates) if start_dates else None,
                "record_updated_at": max(updated_values) if updated_values else None,
            },
            "stability_evidence": self._stability_evidence(tenures),
            "tenures": sorted(
                tenures,
                key=lambda item: (item["is_current"], item["start_date"], item["manager_name"]),
                reverse=True,
            ),
            "sources": sorted({str(row.get("source") or "") for row in rows if row.get("source")}),
            "boundary": self.BOUNDARY,
            "missing_items": [],
        }

    def _stability_evidence(self, tenures: List[Dict[str, Any]]) -> Dict[str, Any]:
        current = [item for item in tenures if item.get("is_current")]
        if not current:
            return {
                "status": "unavailable",
                "label": "现任团队待核验",
                "included_in_score": False,
                "note": "已有历史任职记录，但未识别出现任经理。",
            }

        current_starts = [self._parse_date(item.get("start_date")) for item in current]
        current_starts = [value for value in current_starts if value]
        team_start = max(current_starts) if current_starts else None
        all_starts = [self._parse_date(item.get("start_date")) for item in tenures]
        all_starts = [value for value in all_starts if value]
        first_start = min(all_starts) if all_starts else None
        change_dates = {
            value for value in all_starts if first_start is not None and value > first_start
        }
        change_dates.update(
            value
            for value in (self._parse_date(item.get("end_date")) for item in tenures)
            if value is not None
        )
        latest_change = max(change_dates) if change_dates else first_start
        recent_cutoff = self.today - timedelta(days=365)
        three_year_cutoff = self.today - timedelta(days=365 * 3)
        changes_last_year = sum(value >= recent_cutoff for value in change_dates)
        changes_last_three_years = sum(value >= three_year_cutoff for value in change_dates)
        team_days = max((self.today - team_start).days + 1, 0) if team_start else 0

        if latest_change and latest_change >= recent_cutoff:
            status, label = "recent_change", "团队近期有变动"
        elif changes_last_three_years == 0 and team_days >= 365 * 3:
            status, label = "stable_3y", "现任团队已稳定三年以上"
        elif team_days >= 365 * 2:
            status, label = "established_team", "现任团队已运行两年以上"
        else:
            status, label = "observation_period", "现任团队仍在观察期"

        names = [str(item.get("manager_name") or "") for item in current if item.get("manager_name")]
        if changes_last_three_years:
            change_note = f"近三年有 {changes_last_three_years} 个经理加入或离任节点"
        else:
            change_note = "近三年没有经理加入或离任记录"
        note = (
            f"现任 {len(current)} 人（{'、'.join(names)}），"
            f"当前团队共同起点 {team_start.isoformat() if team_start else '待核验'}；{change_note}。"
        )
        return {
            "status": status,
            "label": label,
            "current_manager_count": len(current),
            "current_manager_names": names,
            "team_mode": "co_managed" if len(current) > 1 else "single_manager",
            "current_team_start": team_start.isoformat() if team_start else None,
            "current_team_days": team_days,
            "latest_change_date": latest_change.isoformat() if latest_change else None,
            "changes_last_year": changes_last_year,
            "changes_last_three_years": changes_last_three_years,
            "as_of_date": self.today.isoformat(),
            "included_in_score": False,
            "source": "local.postgres.manager_fund_tenures",
            "note": note,
        }

    def _merge_tenures(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduplicated: Dict[tuple, Dict[str, Any]] = {}
        for row in rows:
            manager_id = str(row.get("manager_id") or "").strip()
            start_date = self._parse_date(row.get("start_date"))
            if not manager_id or start_date is None:
                continue
            end_date = self._parse_date(row.get("end_date"))
            key = (manager_id, start_date, end_date, bool(row.get("is_current")))
            item = deduplicated.setdefault(key, {
                "manager_id": manager_id,
                "manager_name": str(row.get("manager_name") or manager_id),
                "company": str(row.get("company") or ""),
                "start": start_date,
                "end": end_date,
                "is_current": bool(row.get("is_current")),
                "share_codes": set(),
                "sources": set(),
            })
            if row.get("fund_code"):
                item["share_codes"].add(str(row["fund_code"]).upper())
            if row.get("source"):
                item["sources"].add(str(row["source"]))

        by_manager: Dict[str, List[Dict[str, Any]]] = {}
        for item in deduplicated.values():
            by_manager.setdefault(item["manager_id"], []).append(item)

        merged: List[Dict[str, Any]] = []
        for intervals in by_manager.values():
            intervals.sort(key=lambda item: item["start"])
            current = intervals[0]
            for item in intervals[1:]:
                current_end = current["end"] or self.today
                if item["start"] <= current_end + timedelta(days=1):
                    if current["end"] is None or item["end"] is None:
                        current["end"] = None
                    else:
                        current["end"] = max(current["end"], item["end"])
                    current["is_current"] = current["is_current"] or item["is_current"]
                    current["share_codes"].update(item["share_codes"])
                    current["sources"].update(item["sources"])
                else:
                    merged.append(self._payload(current))
                    current = item
            merged.append(self._payload(current))
        return merged

    def _payload(self, item: Dict[str, Any]) -> Dict[str, Any]:
        effective_end = self.today if item["is_current"] or item["end"] is None else item["end"]
        return {
            "manager_id": item["manager_id"],
            "manager_name": item["manager_name"],
            "company": item["company"],
            "start_date": item["start"].isoformat(),
            "end_date": item["end"].isoformat() if item["end"] else None,
            "is_current": bool(item["is_current"]),
            "tenure_days": max((effective_end - item["start"]).days + 1, 0),
            "share_codes": sorted(item["share_codes"]),
            "sources": sorted(item["sources"]),
        }

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()[:10]
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    @classmethod
    def _date_text(cls, value: Any) -> Optional[str]:
        parsed = cls._parse_date(value)
        return parsed.isoformat() if parsed else None
