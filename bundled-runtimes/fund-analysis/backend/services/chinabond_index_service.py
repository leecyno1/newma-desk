"""同步中债分期限财富指数及指数久期。"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


class ChinaBondIndexService:
    SOURCE = "chinabond.index"
    API_URL = "https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQueryResult"
    PAGE_URL = "https://yield.chinabond.com.cn/cbweb-mn/indices/single_index_query?locale=zh_CN"
    INDICATORS = {"wealth": "CFZS", "duration": "PJSZFJQ"}
    GROUP_LABELS = {
        "policy_bank": "国开行债券",
        "credit": "信用债",
        "short_financing": "短融",
        "interbank_cd": "同业存单",
    }
    GROUPS = {
        "policy_bank": {
            "index_id": "2c908188111fac07011125068f91044d",
            "index_name": "中债-国开行债券总指数",
            "periods": [("01", "1年以下"), ("02", "1-3年"), ("03", "3-5年"), ("04", "5-7年"), ("05", "7-10年")],
        },
        "credit": {
            "index_id": "8a8b2ca038d716f10138dadde8416adc",
            "index_name": "中债-信用债总指数",
            "periods": [("01", "1年以下"), ("02", "1-3年"), ("03", "3-5年"), ("04", "5-7年"), ("05", "7-10年")],
        },
        "short_financing": {
            "index_id": "2c90818811d3f4fa0111d5ed286b7367",
            "index_name": "中债-短融总指数",
            "periods": [("07", "0-3个月"), ("08", "3-6个月"), ("09", "6-9个月"), ("10", "9-12个月"), ("00", "总值")],
        },
        "interbank_cd": {
            "index_id": "8a8b2c8f611af5db01611cb3586c00f0",
            "index_name": "中债-同业存单总指数",
            "periods": [("07", "0-3个月"), ("08", "3-6个月"), ("09", "6-9个月"), ("10", "9-12个月"), ("00", "总值")],
        },
    }

    def __init__(self, repo: Optional[Any] = None, opener=urlopen):
        if repo is None:
            from repositories import get_bond_duration_repo

            repo = get_bond_duration_repo()
        self.repo = repo
        self.opener = opener
        self._last_request_at = 0.0

    @classmethod
    def definitions(cls) -> List[Dict[str, Any]]:
        result = []
        for group, config in cls.GROUPS.items():
            for period_code, period_label in config["periods"]:
                result.append({
                    "series_key": f"{group}:{period_code}",
                    "index_group": group,
                    "group_label": cls.GROUP_LABELS[group],
                    "index_name": config["index_name"],
                    "index_id": config["index_id"],
                    "period_code": period_code,
                    "period_label": period_label,
                    "source": cls.SOURCE,
                    "source_url": cls.PAGE_URL,
                })
        return result

    def fetch(self, definition: Dict[str, Any], indicator: str) -> List[Dict[str, Any]]:
        indicator_code = self.INDICATORS[indicator]
        params = {
            "indexid": definition["index_id"],
            "qxlxt": definition["period_code"],
            "ltcslx": "",
            "zslxt": indicator_code,
            "zslxt1": indicator_code,
            "lx": "1",
            "locale": "zh_CN",
        }
        self._throttle()
        request = Request(
            f"{self.API_URL}?{urlencode(params)}",
            method="POST",
            headers={"User-Agent": "Mozilla/5.0 FundResearch/1.0", "Referer": self.PAGE_URL},
        )
        timeout = max(5, min(int(os.environ.get("CHINABOND_TIMEOUT_SECONDS", "20")), 60))
        with self.opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get(f"{indicator_code}_{definition['period_code']}") or {}
        if not raw:
            raise ValueError(payload.get("emsg") or f"中债指数无数据：{definition['series_key']} {indicator}")
        points = []
        shanghai = ZoneInfo("Asia/Shanghai")
        for timestamp_ms, value in raw.items():
            try:
                trade_date = datetime.fromtimestamp(int(timestamp_ms) / 1000, timezone.utc).astimezone(shanghai).date().isoformat()
                parsed_value = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if parsed_value > 0:
                points.append({"trade_date": trade_date, "value": parsed_value})
        return sorted(points, key=lambda item: item["trade_date"])

    def sync(self, lookback_years: int = 4) -> Dict[str, Any]:
        start_date = date.today() - timedelta(days=max(2, min(lookback_years, 15)) * 366)
        results = []
        for definition in self.definitions():
            for indicator in self.INDICATORS:
                rows = [row for row in self.fetch(definition, indicator) if row["trade_date"] >= start_date.isoformat()]
                written = self.repo.upsert_index_points(definition, indicator, rows)
                results.append({
                    "series_key": definition["series_key"],
                    "indicator": indicator,
                    "records": written,
                    "start_date": rows[0]["trade_date"] if rows else None,
                    "end_date": rows[-1]["trade_date"] if rows else None,
                })
        return {
            "status": "synced",
            "series": len(self.definitions()),
            "requests": len(results),
            "records": sum(item["records"] for item in results),
            "source": self.SOURCE,
            "source_url": self.PAGE_URL,
            "results": results,
        }

    def ensure_local_data(self) -> Dict[str, Any]:
        inventory = self.repo.index_inventory()
        end_dates = [
            str(item.get("end_date") or "")[:10]
            for item in (inventory.get("indicators") or {}).values()
            if item.get("end_date")
        ]
        stale_before = date.today() - timedelta(days=7)
        if inventory.get("status") != "ready" or not end_dates or min(date.fromisoformat(value) for value in end_dates) < stale_before:
            self.sync()
            inventory = self.repo.index_inventory()
        return inventory

    def _throttle(self) -> None:
        interval = max(0.0, min(float(os.environ.get("CHINABOND_REQUEST_INTERVAL_SECONDS", "0.08")), 2.0))
        wait = interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()
