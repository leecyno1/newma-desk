"""从公开披露页面摘取并持久化基金持有人结构。"""

import os
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen


class _HolderTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_cell = False
        self.current_cell: List[str] = []
        self.current_row: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if tag == "table" and "cyrjg" in str(attributes.get("class") or "").split():
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


class FundHolderStructureService:
    SOURCE = "eastmoney.fundf10.holder_structure"
    PAGE_URL_TEMPLATE = "https://fundf10.eastmoney.com/cyrjg_{code}.html"
    FETCH_URL_TEMPLATE = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=cyrjg&code={code}&rt=0.123"
    SCOPE = "半年报、年报披露口径，不代表当前实时持有人情况。"
    INTERNAL_RATIO_NOTE = "“内部持有比例”为数据源披露口径，不等于员工自购；ETF 等产品可能包含联接基金持有份额。"

    def __init__(self, repo: Optional[Any] = None, opener=urlopen):
        if repo is None:
            from repositories import get_fund_holder_structure_repo

            repo = get_fund_holder_structure_repo()
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
                "previous": None,
                "comparison": None,
                "history": [],
                "source": self.SOURCE,
                "source_url": self._page_url(wind_code),
                "scope": self.SCOPE,
                "internal_ratio_note": self.INTERNAL_RATIO_NOTE,
                "missing_items": (sync_result or {}).get("missing_items") or ["公开披露暂未返回持有人结构"],
            }

        latest = history[0]
        previous = history[1] if len(history) > 1 else None
        return {
            "wind_code": wind_code,
            "status": "available",
            "latest": latest,
            "previous": previous,
            "comparison": self._comparison(latest, previous),
            "history": history,
            "source": latest.get("source") or self.SOURCE,
            "source_url": latest.get("source_url") or self._page_url(wind_code),
            "scope": self.SCOPE,
            "internal_ratio_note": self.INTERNAL_RATIO_NOTE,
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
                "source_url": self._page_url(wind_code),
                "missing_items": [],
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "wind_code": wind_code,
                "records": 0,
                "source": self.SOURCE,
                "source_url": self._page_url(wind_code),
                "missing_items": [str(exc) or "持有人结构同步失败"],
            }

    def fetch(self, wind_code: str) -> List[Dict[str, Any]]:
        page_url = self._page_url(wind_code)
        request = Request(
            self._fetch_url(wind_code),
            headers={"User-Agent": "Mozilla/5.0 FundResearch/1.0", "Referer": page_url},
        )
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        with self.opener(request, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="replace")
        rows = self.parse_html(content, source_url=page_url)
        if not rows:
            raise ValueError("公开披露中未找到持有人结构明细")
        return rows

    @classmethod
    def parse_html(cls, content: str, source_url: str = "") -> List[Dict[str, Any]]:
        parser = _HolderTableParser()
        parser.feed(content)
        parsed = []
        for cells in parser.rows:
            if len(cells) < 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
                continue
            parsed.append({
                "report_date": cells[0],
                "institution_ratio": cls._ratio(cells[1]),
                "individual_ratio": cls._ratio(cells[2]),
                "internal_ratio": cls._ratio(cells[3]),
                "total_shares_yi": cls._number(cells[4]),
                "source": cls.SOURCE,
                "source_url": source_url,
            })
        parsed.sort(key=lambda item: item["report_date"], reverse=True)
        return parsed

    @staticmethod
    def _comparison(latest: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not previous:
            return None

        def difference(key: str) -> Optional[float]:
            left = latest.get(key)
            right = previous.get(key)
            return round(float(left) - float(right), 8) if left is not None and right is not None else None

        return {
            "previous_report_date": previous.get("report_date"),
            "institution_ratio_change": difference("institution_ratio"),
            "individual_ratio_change": difference("individual_ratio"),
            "internal_ratio_change": difference("internal_ratio"),
            "total_shares_yi_change": difference("total_shares_yi"),
        }

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
    def _fund_code(cls, wind_code: str) -> str:
        match = re.match(r"^(\d{6})", str(wind_code or "").strip())
        if not match:
            raise ValueError("基金代码格式不支持持有人结构查询")
        return match.group(1)

    @classmethod
    def _page_url(cls, wind_code: str) -> str:
        return cls.PAGE_URL_TEMPLATE.format(code=cls._fund_code(wind_code))

    @classmethod
    def _fetch_url(cls, wind_code: str) -> str:
        return cls.FETCH_URL_TEMPLATE.format(code=cls._fund_code(wind_code))
