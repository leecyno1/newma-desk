"""恒生指数公司官方成分、权重和行业快照。"""

import io
import json
import os
import re
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen


class HangSengIndexService:
    SOURCE = "hang_seng_indexes.official"
    CONSTITUENTS_URL = "https://www.hsi.com.hk/data/eng/rt/index-series/hsi/constituents.do"
    INDUSTRY_URL = "https://www.hsi.com.hk/data/eng/rt/index-series/industry/constituents.do"
    FACTSHEET_URL = "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsie.pdf"

    INDUSTRY_NAMES = (
        "Consumer Discretionary",
        "Consumer Staples",
        "Information Technology",
        "Properties & Construction",
        "Telecommunications",
        "Conglomerates",
        "Financials",
        "Healthcare",
        "Materials",
        "Energy",
        "Utilities",
        "Industrials",
    )
    INDUSTRY_ZH = {
        "Consumer Discretionary": "可选消费",
        "Consumer Staples": "必需消费",
        "Information Technology": "信息技术",
        "Properties & Construction": "地产建筑",
        "Telecommunications": "电讯",
        "Conglomerates": "综合企业",
        "Financials": "金融",
        "Healthcare": "医疗保健",
        "Materials": "原材料",
        "Energy": "能源",
        "Utilities": "公用事业",
        "Industrials": "工业",
    }
    SHARE_TYPES = (
        "Other HK-listed Mainland Co.",
        "Foreign Company",
        "HK Ordinary",
        "H Share",
        "Red Chip",
        "A Share",
        "B Share",
        "P Chip",
    )
    WEIGHT_ROW = re.compile(r"^(\d{4,5})\s+([A-Z0-9]{12})\s+(.*?)\s+([\d.]+)$")

    def __init__(self, opener: Callable[..., Any] = urlopen):
        self.opener = opener
        self._cache: Optional[Dict[str, Any]] = None

    def get_hsi_snapshot(self, refresh: bool = False) -> Dict[str, Any]:
        if self._cache is not None and not refresh:
            return self._cache

        constituents = self.parse_constituents(self._get_json(self.CONSTITUENTS_URL))
        industry_map = self.parse_industry_map(self._get_json(self.INDUSTRY_URL))
        factsheet_text = self._get_pdf_text(self.FACTSHEET_URL)
        weights = self.parse_factsheet_weights(factsheet_text)
        as_of_date = self.parse_factsheet_date(factsheet_text)

        rows = []
        for constituent in constituents:
            code = constituent["constituent_code"]
            weight_evidence = weights.get(code) or {}
            industry = industry_map.get(code) or weight_evidence.get("industry")
            rows.append({
                **constituent,
                "weight": weight_evidence.get("weight"),
                "industry": industry,
                "industry_source": self.SOURCE if industry else None,
                "isin": weight_evidence.get("isin"),
            })

        published_weight = round(sum(float(row.get("weight") or 0) for row in rows), 8)
        self._cache = {
            "status": "available" if rows and as_of_date else "partial_evidence",
            "index_code": "HSI",
            "index_name": "恒生指数",
            "as_of_date": as_of_date,
            "constituents": rows,
            "industry_map": industry_map,
            "industry_constituents": [
                {
                    "constituent_code": code,
                    "constituent_name": next(
                        (
                            item.get("constituent_name")
                            for item in rows
                            if item.get("constituent_code") == code
                        ),
                        None,
                    ),
                    "weight": None,
                    "industry": industry,
                    "industry_source": self.SOURCE,
                }
                for code, industry in sorted(industry_map.items())
            ],
            "constituent_count": len(rows),
            "weighted_constituent_count": sum(1 for row in rows if row.get("weight") is not None),
            "published_weight": published_weight,
            "source": self.SOURCE,
            "source_urls": [self.CONSTITUENTS_URL, self.INDUSTRY_URL, self.FACTSHEET_URL],
            "missing_items": (
                [f"官方事实表只公布前50大成分权重，已公布权重合计 {published_weight:.1%}。"]
                if published_weight < 0.999
                else []
            ),
        }
        return self._cache

    def get_hsi_factsheet_snapshot(
        self,
        factsheet_url: str,
        pdf_content: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """从指定官方事实表生成可用于历史归因的时点快照。"""
        text = (
            self._pdf_text(pdf_content)
            if pdf_content is not None
            else self._get_pdf_text(factsheet_url)
        )
        return self.build_factsheet_snapshot(text, factsheet_url)

    @classmethod
    def build_factsheet_snapshot(cls, text: str, source_url: str) -> Dict[str, Any]:
        weights = cls.parse_factsheet_weights(text)
        as_of_date = cls.parse_factsheet_date(text)
        rows = [
            {
                "constituent_code": code,
                "constituent_name": evidence.get("constituent_name"),
                "weight": evidence.get("weight"),
                "industry": evidence.get("industry"),
                "industry_source": cls.SOURCE if evidence.get("industry") else None,
                "isin": evidence.get("isin"),
                "share_class": evidence.get("share_type"),
            }
            for code, evidence in sorted(
                weights.items(),
                key=lambda item: float(item[1].get("weight") or 0),
                reverse=True,
            )
        ]
        published_weight = round(sum(float(row.get("weight") or 0) for row in rows), 8)
        missing_items = []
        if published_weight < 0.999:
            missing_items.append(
                f"官方事实表只公布前50大成分权重，已公布权重合计 {published_weight:.1%}。"
            )
        if not as_of_date:
            missing_items.append("官方事实表日期解析失败，不能作为历史时点证据。")
        if not rows:
            missing_items.append("官方事实表未解析到成分权重。")
        return {
            "status": "available" if rows and as_of_date else "insufficient_evidence",
            "index_code": "HSI",
            "index_name": "恒生指数",
            "as_of_date": as_of_date,
            "constituents": rows,
            "constituent_count": len(rows),
            "weighted_constituent_count": len(rows),
            "published_weight": published_weight,
            "source": cls.SOURCE,
            "source_urls": [source_url],
            "missing_items": missing_items,
        }

    @classmethod
    def parse_constituents(cls, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = []
        seen = set()
        for series in payload.get("indexSeriesList") or []:
            for index in series.get("indexList") or []:
                for item in index.get("constituentContent") or []:
                    code = cls._code(item.get("code"))
                    if not code or code in seen:
                        continue
                    seen.add(code)
                    rows.append({
                        "constituent_code": code,
                        "constituent_name": item.get("constituentName"),
                        "share_class": item.get("type") or None,
                    })
        return rows

    @classmethod
    def parse_industry_map(cls, payload: Dict[str, Any]) -> Dict[str, str]:
        result = {}
        for series in payload.get("indexSeriesList") or []:
            for index in series.get("indexList") or []:
                index_name = str(index.get("indexName") or "")
                english = next((name for name in cls.INDUSTRY_NAMES if name in index_name), None)
                if not english:
                    continue
                industry = cls.INDUSTRY_ZH[english]
                for item in index.get("constituentContent") or []:
                    code = cls._code(item.get("code"))
                    if code:
                        result[code] = industry
        return result

    @classmethod
    def parse_factsheet_weights(cls, text: str) -> Dict[str, Dict[str, Any]]:
        result = {}
        for line in str(text or "").splitlines():
            match = cls.WEIGHT_ROW.match(line.strip())
            if not match:
                continue
            raw_code, isin, middle, raw_weight = match.groups()
            share_type = next((item for item in cls.SHARE_TYPES if middle.endswith(item)), None)
            without_share_type = middle[: -len(share_type)].strip() if share_type else middle
            english_industry = next(
                (item for item in cls.INDUSTRY_NAMES if without_share_type.endswith(item)),
                None,
            )
            name = without_share_type[: -len(english_industry)].strip() if english_industry else without_share_type
            result[cls._code(raw_code)] = {
                "weight": round(float(raw_weight) / 100.0, 8),
                "isin": isin,
                "constituent_name": name or None,
                "industry": cls.INDUSTRY_ZH.get(english_industry),
                "share_type": share_type,
            }
        return result

    @staticmethod
    def parse_factsheet_date(text: str) -> Optional[str]:
        match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
            str(text or ""),
        )
        if not match:
            return None
        parsed = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%B %Y")
        return date(parsed.year, parsed.month, monthrange(parsed.year, parsed.month)[1]).isoformat()

    def _get_json(self, url: str) -> Dict[str, Any]:
        with self.opener(self._request(url, "application/json"), timeout=self._timeout()) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _get_pdf_text(self, url: str) -> str:
        with self.opener(self._request(url, "application/pdf"), timeout=self._timeout()) as response:
            content = response.read()
        return self._pdf_text(content)

    @staticmethod
    def _pdf_text(content: bytes) -> str:
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(content)).pages)

    @staticmethod
    def _request(url: str, accept: str) -> Request:
        return Request(url, headers={
            "User-Agent": "Mozilla/5.0 FundResearch/1.0",
            "Referer": "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi",
            "Accept": accept,
        })

    @staticmethod
    def _timeout() -> int:
        return max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))

    @staticmethod
    def _code(value: Any) -> str:
        text = str(value or "").strip()
        return f"{text.zfill(5)}.HK" if text.isdigit() else ""
