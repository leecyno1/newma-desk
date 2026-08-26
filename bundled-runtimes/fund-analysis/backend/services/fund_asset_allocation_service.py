"""从公开定期报告页面摘取并持久化基金资产配置。"""

import os
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen


class _AllocationTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_cell = False
        self.current_cell: List[str] = []
        self.current_row: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag == "table" and "tzxq" in str(attributes.get("class") or "").split():
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str):
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str):
        if self.in_table and tag in {"td", "th"} and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif self.in_table and tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = []
        elif self.in_table and tag == "table":
            self.in_table = False


class FundAssetAllocationService:
    SOURCE = "eastmoney.fundf10.asset_allocation"
    URL_TEMPLATE = "https://fundf10.eastmoney.com/zcpz_{code}.html"

    def __init__(self, repo: Optional[Any] = None, opener=urlopen):
        if repo is None:
            from repositories import get_fund_asset_allocation_repo

            repo = get_fund_asset_allocation_repo()
        self.repo = repo
        self.opener = opener

    def get(self, wind_code: str, limit: int = 20, refresh: bool = False) -> Dict[str, Any]:
        history = self.repo.list_history(wind_code, limit=limit)
        sync_result = None
        if refresh or not history:
            sync_result = self.sync(wind_code)
            history = self.repo.list_history(wind_code, limit=limit)
        if not history:
            return {
                "wind_code": wind_code,
                "status": "unavailable",
                "latest": None,
                "history": [],
                "scale_trend": {
                    "status": "insufficient_evidence",
                    "label": "规模趋势待补",
                    "included_in_score": False,
                    "note": "至少需要两个报告期的净资产数据。",
                },
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "missing_items": (sync_result or {}).get("missing_items") or ["公开定期报告暂未返回资产配置"],
            }
        from services.fund_scale_trend_service import FundScaleTrendService

        return {
            "wind_code": wind_code,
            "status": "available",
            "latest": history[0],
            "history": history,
            "scale_trend": FundScaleTrendService.analyze(history),
            "source": history[0].get("source") or self.SOURCE,
            "source_url": history[0].get("source_url") or self._source_url(wind_code),
            "missing_items": [],
        }

    def sync(self, wind_code: str) -> Dict[str, Any]:
        try:
            rows = self.fetch(wind_code)
            written = self.repo.upsert_many(wind_code, rows)
            return {
                "status": "synced",
                "wind_code": wind_code,
                "records": written,
                "latest_report_date": rows[0]["report_date"] if rows else None,
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "missing_items": [],
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "wind_code": wind_code,
                "records": 0,
                "source": self.SOURCE,
                "source_url": self._source_url(wind_code),
                "missing_items": [str(exc) or "资产配置同步失败"],
            }

    def fetch(self, wind_code: str) -> List[Dict[str, Any]]:
        url = self._source_url(wind_code)
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 FundResearch/1.0"})
        with self.opener(request, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="replace")
        rows = self.parse_html(content, source_url=url)
        if not rows:
            raise ValueError("公开定期报告中未找到资产配置明细")
        return rows

    @classmethod
    def parse_html(cls, content: str, source_url: str = "") -> List[Dict[str, Any]]:
        parser = _AllocationTableParser()
        parser.feed(content)
        parsed = []
        for cells in parser.rows:
            if len(cells) < 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
                continue
            parsed.append({
                "report_date": cells[0],
                "stock_ratio": cls._ratio(cells[1]),
                "bond_ratio": cls._ratio(cells[2]),
                "cash_ratio": cls._ratio(cells[3]),
                "net_asset_yi": cls._number(cells[4]),
                "source": cls.SOURCE,
                "source_url": source_url,
            })
        parsed.sort(key=lambda item: item["report_date"], reverse=True)
        return parsed

    @staticmethod
    def _ratio(value: str) -> Optional[float]:
        text = str(value or "").strip().replace(",", "")
        if text in {"", "-", "--", "---"}:
            return None
        try:
            return round(float(text.rstrip("%")) / 100.0, 8)
        except ValueError:
            return None

    @staticmethod
    def _number(value: str) -> Optional[float]:
        text = str(value or "").strip().replace(",", "")
        if text in {"", "-", "--", "---"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @classmethod
    def _source_url(cls, wind_code: str) -> str:
        match = re.match(r"^(\d{6})", str(wind_code or "").strip())
        if not match:
            raise ValueError("基金代码格式不支持资产配置查询")
        return cls.URL_TEMPLATE.format(code=match.group(1))
