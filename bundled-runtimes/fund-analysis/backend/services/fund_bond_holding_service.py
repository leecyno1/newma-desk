"""同步并汇总公开披露的基金重仓债券。"""

import json
import os
import re
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen


BOND_TYPE_LABELS = {
    "convertible_exchangeable": "可转债/可交换债",
    "policy_bank": "政策性金融债",
    "financial": "金融债/资本债",
    "government": "国债",
    "local_government": "地方政府债",
    "government_local": "国债/地方政府债（旧口径）",
    "credit": "企业信用债",
    "interbank_cd": "同业存单",
    "asset_backed": "资产支持证券",
    "other": "其他/待核验",
}


class _BondHoldingTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.report_date = ""
        self.table_report_date = ""
        self.in_date = False
        self.in_table = False
        self.in_cell = False
        self.current_cell: List[str] = []
        self.current_row: List[str] = []
        self.rows: List[Tuple[str, List[str]]] = []

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        classes = str(attributes.get("class") or "").split()
        if tag == "font" and "px12" in classes:
            self.in_date = True
        elif tag == "table" and "tzxq" in classes:
            self.in_table = True
            self.table_report_date = self.report_date
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str):
        if self.in_date:
            value = data.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                self.report_date = value
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str):
        if tag == "font" and self.in_date:
            self.in_date = False
        elif self.in_table and tag in {"td", "th"} and self.in_cell:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_cell = False
        elif self.in_table and tag == "tr" and self.current_row:
            self.rows.append((self.table_report_date, self.current_row))
            self.current_row = []
        elif self.in_table and tag == "table":
            self.in_table = False


class FundBondHoldingService:
    SOURCE = "eastmoney.fundf10.bond_holdings"
    PAGE_URL_TEMPLATE = "https://fundf10.eastmoney.com/ccmx1_{code}.html"
    FETCH_URL_TEMPLATE = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=zqcc&code={code}&year={year}&rt=0.123"
    SCOPE = "仅统计定期报告公开展示的重仓债券，不代表基金全部债券组合。"
    CLASSIFICATION_METHOD = "依据公开债券名称中的明确关键词归类；无法确认的债券保留为“其他/待核验”。"
    PROFILE_STYLE_LABELS = {
        "可转债显著暴露": "可转债",
        "利率债型公开证据": "利率债",
        "金融债型公开证据": "金融债",
        "信用债主导，等级待核验": "信用债",
        "中低等级信用债风险证据": "中低等级信用",
        "中高等级信用债公开证据": "高等级信用",
        "信用利率灵活配置公开证据": "信用利率均衡",
    }
    SECONDARY_STYLE_LABELS = {
        "利率债主导": "利率债",
        "金融债主导": "金融债",
        "信用债主导": "信用债",
        "可转债暴露": "可转债",
        "地方政府债暴露": "地方政府债",
    }

    def __init__(self, repo: Optional[Any] = None, opener=urlopen, metadata_service: Optional[Any] = None):
        if repo is None:
            from repositories import get_fund_bond_holding_repo

            repo = get_fund_bond_holding_repo()
        self.repo = repo
        self.opener = opener
        if metadata_service is None:
            from services.bond_security_metadata_service import BondSecurityMetadataService

            metadata_service = BondSecurityMetadataService()
        self.metadata_service = metadata_service

    def get(self, wind_code: str, limit: int = 8, refresh: bool = False) -> Dict[str, Any]:
        sync_result = self.sync(wind_code) if refresh else None
        rows = self.repo.list_latest_periods(wind_code, limit=limit)
        if not rows:
            return {
                "wind_code": wind_code,
                "status": "unavailable",
                "latest": None,
                "history": [],
                "professional_profile": self._professional_profile([]),
                "source": self.SOURCE,
                "source_url": self._page_url(wind_code),
                "scope": self.SCOPE,
                "classification_method": self.CLASSIFICATION_METHOD,
                "missing_items": (sync_result or {}).get("missing_items") or ["本地尚无公开债券持仓，请先执行同步"],
            }

        history = self._summarize(rows)
        professional_profile = self._professional_profile(history)
        latest = history[0]
        latest["holdings"] = latest["holdings"][:20]
        for period in history[1:]:
            period["holdings"] = []
        return {
            "wind_code": wind_code,
            "status": "available",
            "latest": latest,
            "history": history,
            "professional_profile": professional_profile,
            "source": latest.get("source") or self.SOURCE,
            "source_url": latest.get("source_url") or self._page_url(wind_code),
            "scope": self.SCOPE,
            "classification_method": self.CLASSIFICATION_METHOD,
            "missing_items": [],
        }

    @classmethod
    def professional_profiles_from_rows(cls, rows_by_code: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        return {
            code: cls._professional_profile(cls._summarize(rows))
            for code, rows in rows_by_code.items()
            if rows
        }

    @classmethod
    def style_evidence(cls, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        if str(profile.get("status") or "") != "available":
            return []
        values = [cls.PROFILE_STYLE_LABELS.get(str(profile.get("label") or ""))]
        values.extend(
            cls.SECONDARY_STYLE_LABELS.get(str(label or ""))
            for label in profile.get("secondary_labels") or []
        )
        evidence = []
        seen = set()
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            evidence.append({
                "value": value,
                "status": "quantitative",
                "source": "public_bond_holding_profile",
                "basis": str(profile.get("basis") or ""),
                "caveat": "仅基于近 4 期公开重仓债券，不代表完整债券组合。",
                "period_count": int(profile.get("period_count") or 0),
                "data_source": cls.SOURCE,
            })
        return evidence

    def sync(self, wind_code: str, metadata_periods: int = 1) -> Dict[str, Any]:
        try:
            rows = self.fetch(wind_code)
            rows, metadata_updates = self._enrich_metadata(rows, metadata_periods=metadata_periods)
            written = self.repo.upsert_many(wind_code, rows)
            self.repo.update_metadata_many(metadata_updates)
            report_dates = sorted({row["report_date"] for row in rows}, reverse=True)
            latest_rows = [row for row in rows if report_dates and row["report_date"] == report_dates[0]]
            return {
                "status": "synced",
                "wind_code": wind_code,
                "records": written,
                "periods": len(report_dates),
                "latest_report_date": report_dates[0] if report_dates else None,
                "metadata_available": sum(item.get("metadata_status") == "available" for item in latest_rows),
                "metadata_unavailable": sum(item.get("metadata_status") != "available" for item in latest_rows),
                "metadata_periods": max(0, min(metadata_periods, len(report_dates))),
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
                "missing_items": [str(exc) or "公开债券持仓同步失败"],
            }

    def _enrich_metadata(self, rows: List[Dict[str, Any]], metadata_periods: int = 1) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        first_by_code: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if row.get("bond_code"):
                first_by_code.setdefault(str(row["bond_code"]), row)
        normalized_by_code = {code: code.upper().split(".", 1)[0] for code in first_by_code}
        cached_codes = list(dict.fromkeys([*first_by_code, *normalized_by_code.values()]))
        cached = self.repo.metadata_by_codes(cached_codes)
        target_dates = set(sorted({str(row.get("report_date") or "") for row in rows}, reverse=True)[:max(0, metadata_periods)])
        live_metadata: Dict[str, Dict[str, Any]] = {}
        missing = [
            (bond_code, holding)
            for bond_code, holding in first_by_code.items()
            if bond_code not in cached and normalized_by_code[bond_code] not in cached and str(holding.get("report_date") or "") in target_dates
        ]

        def lookup(item: Tuple[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
            bond_code, holding = item
            return bond_code, self.metadata_service.lookup(normalized_by_code[bond_code], str(holding.get("bond_name") or ""))

        for item in missing:
            bond_code, metadata = lookup(item)
            live_metadata[bond_code] = metadata

        metadata_by_code: Dict[str, Dict[str, Any]] = {}
        for bond_code, holding in first_by_code.items():
            metadata = cached.get(bond_code) or cached.get(normalized_by_code[bond_code]) or live_metadata.get(bond_code)
            metadata = dict(metadata or self.metadata_service.unavailable(bond_code))
            metadata["bond_code"] = bond_code
            metadata["normalized_bond_code"] = normalized_by_code[bond_code]
            master_type, master_basis = self.classify_security_type(str(metadata.get("security_bond_type") or ""))
            metadata["bond_type"] = master_type or holding.get("bond_type") or "other"
            metadata["classification_basis"] = master_basis or holding.get("classification_basis")
            metadata_by_code[bond_code] = metadata

        enriched = []
        for row in rows:
            item = dict(row)
            metadata = metadata_by_code.get(str(row.get("bond_code") or ""), {})
            item.update(metadata)
            enriched.append(item)
        return enriched, list(metadata_by_code.values())

    def fetch(self, wind_code: str) -> List[Dict[str, Any]]:
        page_url = self._page_url(wind_code)
        first_payload = self._fetch_payload(wind_code, "", page_url)
        rows, years, current_year = self.parse_payload(first_payload, source_url=page_url)

        previous_year = next((year for year in years if year < current_year), None) if current_year else None
        if previous_year is not None:
            previous_payload = self._fetch_payload(wind_code, str(previous_year), page_url)
            previous_rows, _, _ = self.parse_payload(previous_payload, source_url=page_url)
            rows.extend(previous_rows)

        unique = {
            (row["report_date"], row["bond_code"]): row
            for row in rows
        }
        parsed = sorted(unique.values(), key=lambda item: (item["report_date"], -item["sequence"]), reverse=True)
        if not parsed:
            raise ValueError("公开披露中未找到债券持仓明细")
        return parsed

    def _fetch_payload(self, wind_code: str, year: str, page_url: str) -> str:
        request = Request(
            self._fetch_url(wind_code, year),
            headers={"User-Agent": "Mozilla/5.0 FundResearch/1.0", "Referer": page_url},
        )
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        with self.opener(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    @classmethod
    def parse_payload(cls, payload: str, source_url: str = "") -> Tuple[List[Dict[str, Any]], List[int], Optional[int]]:
        content_match = re.search(r'content\s*:\s*("(?:\\.|[^"\\])*")\s*,\s*arryear', payload, re.S)
        if not content_match:
            return [], [], None
        html = json.loads(content_match.group(1))
        years_match = re.search(r"arryear\s*:\s*\[([^\]]*)\]", payload)
        years = [int(value) for value in re.findall(r"\d{4}", years_match.group(1) if years_match else "")]
        current_match = re.search(r"curyear\s*:\s*(\d{4})", payload)
        current_year = int(current_match.group(1)) if current_match else None
        return cls.parse_html(html, source_url=source_url), years, current_year

    @classmethod
    def parse_html(cls, content: str, source_url: str = "") -> List[Dict[str, Any]]:
        parser = _BondHoldingTableParser()
        parser.feed(content)
        parsed = []
        for report_date, cells in parser.rows:
            if not report_date or len(cells) < 5 or not cells[0].isdigit():
                continue
            bond_name = cells[2].strip()
            bond_type, basis = cls.classify_bond(bond_name)
            parsed.append({
                "report_date": report_date,
                "sequence": int(cells[0]),
                "bond_code": cells[1].strip(),
                "bond_name": bond_name,
                "bond_type": bond_type,
                "nav_ratio": cls._ratio(cells[3]),
                "market_value_wan": cls._number(cells[4]),
                "classification_basis": basis,
                "source": cls.SOURCE,
                "source_url": source_url,
            })
        return parsed

    @staticmethod
    def classify_bond(name: str) -> Tuple[str, str]:
        value = str(name or "").strip().upper()
        if re.search(r"转\d*$", value):
            return "convertible_exchangeable", "名称形态：转债简称"
        if re.search(r"CD\d+", value):
            return "interbank_cd", "名称形态：同业存单代码"
        if "TLAC" in value or "非资本债" in value:
            return "financial", "名称关键词：TLAC非资本债"
        provinces = ("北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆")
        if any(f"{province}债" in value for province in provinces):
            return "local_government", "名称形态：地方政府债简称"
        rules = [
            ("convertible_exchangeable", ("转债", "可转", "可交换债", "EB")),
            ("interbank_cd", ("同业存单",)),
            ("policy_bank", ("国开", "农发", "进出")),
            ("local_government", ("地方政府债", "地方债")),
            ("government", ("国债",)),
            ("asset_backed", ("资产支持", "ABS", "ABN")),
            ("financial", ("二级资本债", "银行二级", "银行永续", "永续债", "金融债", "银行债", "证券公司债", "保险公司债")),
            ("credit", ("中票", "MTN", "SCP", "CP", "短融", "超短融", "企业债", "公司债", "产业债", "PPN")),
        ]
        for bond_type, keywords in rules:
            matched = next((keyword for keyword in keywords if keyword.upper() in value), None)
            if matched:
                return bond_type, f"名称关键词：{matched}"
        return "other", "债券名称未包含可确认券种的关键词"

    @staticmethod
    def classify_security_type(security_type: str) -> Tuple[Optional[str], Optional[str]]:
        value = str(security_type or "").strip().upper()
        rules = [
            ("convertible_exchangeable", ("可转换", "可交换")),
            ("interbank_cd", ("同业存单",)),
            ("policy_bank", ("政策性金融债",)),
            ("local_government", ("地方政府债",)),
            ("government", ("国债",)),
            ("asset_backed", ("资产支持", "资产支持票据")),
            ("financial", ("二级资本", "资本补充", "无固定期限资本", "普通金融债", "金融债", "TLAC", "非资本债")),
            ("credit", ("企业债", "公司债", "中期票据", "短期融资券", "超短期融资券", "定向工具")),
        ]
        for bond_type, keywords in rules:
            matched = next((keyword for keyword in keywords if keyword.upper() in value), None)
            if matched:
                return bond_type, f"公开主数据券种：{security_type}"
        return None, None

    @classmethod
    def _summarize(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("report_date") or "")].append(row)

        history = []
        for report_date in sorted(grouped, reverse=True):
            holdings = []
            for raw_holding in grouped[report_date]:
                holding = dict(raw_holding)
                if holding.get("bond_type") == "government_local":
                    master_type, master_basis = cls.classify_security_type(str(holding.get("security_bond_type") or ""))
                    name_type, name_basis = cls.classify_bond(str(holding.get("bond_name") or ""))
                    normalized_type = master_type or (name_type if name_type != "other" else None)
                    if normalized_type:
                        holding["bond_type"] = normalized_type
                        holding["classification_basis"] = master_basis or name_basis
                holding["remaining_years"] = cls._remaining_years(report_date, holding.get("maturity_date"))
                holdings.append(holding)
            disclosed_nav_ratio = sum(float(row.get("nav_ratio") or 0) for row in holdings)
            bucket_values: Dict[str, Dict[str, Any]] = {}
            for row in holdings:
                bond_type = str(row.get("bond_type") or "other")
                bucket = bucket_values.setdefault(bond_type, {
                    "key": bond_type,
                    "label": BOND_TYPE_LABELS.get(bond_type, bond_type),
                    "nav_ratio": 0.0,
                    "holding_count": 0,
                })
                bucket["nav_ratio"] += float(row.get("nav_ratio") or 0)
                bucket["holding_count"] += 1

            buckets = []
            for bucket in bucket_values.values():
                bucket["nav_ratio"] = round(bucket["nav_ratio"], 8)
                bucket["share_of_disclosed"] = round(bucket["nav_ratio"] / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None
                buckets.append(bucket)
            buckets.sort(key=lambda item: item["nav_ratio"], reverse=True)
            classified_nav_ratio = sum(bucket["nav_ratio"] for bucket in buckets if bucket["key"] != "other")
            metadata_summary = cls._metadata_summary(holdings, disclosed_nav_ratio)
            history.append({
                "report_date": report_date,
                "disclosed_count": len(holdings),
                "disclosed_nav_ratio": round(disclosed_nav_ratio, 8),
                "classified_nav_ratio": round(classified_nav_ratio, 8),
                "classification_coverage": round(classified_nav_ratio / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
                "dominant_type": buckets[0]["label"] if buckets else "",
                "buckets": buckets,
                "holdings": holdings,
                **metadata_summary,
                "source": holdings[0].get("source") or cls.SOURCE,
                "source_url": holdings[0].get("source_url") or "",
            })
        return history

    @classmethod
    def _professional_profile(cls, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        required_periods = 4
        periods = history[:required_periods]
        methodology = "参考基构云公开方法：至少使用近 4 期季报，比较利率债、金融债、信用债和可转债的持仓结构。"
        limitations = [
            "当前只使用公开重仓债券，不是完整持仓穿透。",
            "主体评级只单独展示，不进入信用等级标签判定。",
            "尚未接入隐含评级和 3 年 AA+ 中票收益率，因此不能形成正式信用等级分类。",
        ]
        if len(periods) < required_periods:
            return {
                "status": "insufficient_periods",
                "label": "四期证据不足",
                "period_count": len(periods),
                "required_periods": required_periods,
                "averages": {},
                "periods": [],
                "secondary_labels": [],
                "basis": f"当前只有 {len(periods)} 期公开债券持仓，至少需要 {required_periods} 期。",
                "methodology": methodology,
                "limitations": limitations,
                "formal_classification_ready": False,
            }

        period_profiles = []
        low_rating_holdings = []
        for period in periods:
            disclosed = float(period.get("disclosed_nav_ratio") or 0)
            shares = {str(item.get("key")): float(item.get("share_of_disclosed") or 0) for item in period.get("buckets") or []}
            high_rating_nav = 0.0
            bond_rated_nav = 0.0
            issuer_rated_nav = 0.0
            for holding in period.get("holdings") or []:
                rating = str(holding.get("credit_rating") or "").upper().replace("STI", "")
                rating_type = str(holding.get("rating_type") or "")
                nav_ratio = float(holding.get("nav_ratio") or 0)
                if rating and rating_type == "bond":
                    bond_rated_nav += nav_ratio
                elif rating and rating_type == "issuer_subject":
                    issuer_rated_nav += nav_ratio
                if rating_type == "bond" and (rating.startswith("AAA") or rating.startswith("AA+")):
                    high_rating_nav += nav_ratio
                elif rating_type == "bond" and rating and nav_ratio > 0.01:
                    low_rating_holdings.append({
                        "report_date": period.get("report_date"),
                        "bond_code": holding.get("bond_code"),
                        "bond_name": holding.get("bond_name"),
                        "rating": holding.get("credit_rating"),
                        "nav_ratio": round(nav_ratio, 8),
                    })
            period_profiles.append({
                "report_date": period.get("report_date"),
                "rate_share": round(shares.get("government", 0) + shares.get("policy_bank", 0), 8),
                "local_government_share": round(shares.get("local_government", 0), 8),
                "financial_share": round(shares.get("financial", 0) + shares.get("interbank_cd", 0), 8),
                "credit_share": round(shares.get("credit", 0) + shares.get("asset_backed", 0), 8),
                "convertible_share": round(shares.get("convertible_exchangeable", 0), 8),
                "other_share": round(shares.get("other", 0), 8),
                "high_rating_share": round(high_rating_nav / disclosed, 8) if disclosed else None,
                "bond_rating_coverage": round(bond_rated_nav / disclosed, 8) if disclosed else None,
                "issuer_rating_coverage": round(issuer_rated_nav / disclosed, 8) if disclosed else None,
                "metadata_coverage": period.get("metadata_coverage"),
                "classification_coverage": period.get("classification_coverage"),
            })

        average = lambda key: round(sum(float(item.get(key) or 0) for item in period_profiles) / len(period_profiles), 8)
        averages = {
            "rate_share": average("rate_share"),
            "local_government_share": average("local_government_share"),
            "financial_share": average("financial_share"),
            "credit_share": average("credit_share"),
            "convertible_share": average("convertible_share"),
            "other_share": average("other_share"),
            "high_rating_share": average("high_rating_share"),
            "bond_rating_coverage": average("bond_rating_coverage"),
            "issuer_rating_coverage": average("issuer_rating_coverage"),
            "metadata_coverage": average("metadata_coverage"),
            "classification_coverage": average("classification_coverage"),
        }
        type_sets = [
            {str(item.get("key")) for item in period.get("buckets") or [] if float(item.get("nav_ratio") or 0) > 0}
            for period in periods
        ]
        rate_types = {"government", "policy_bank"}
        financial_types = rate_types | {"financial", "interbank_cd"}
        secondary_labels = []
        if averages["rate_share"] >= 0.6:
            secondary_labels.append("利率债主导")
        if averages["financial_share"] >= 0.6:
            secondary_labels.append("金融债主导")
        if averages["credit_share"] >= 0.6:
            secondary_labels.append("信用债主导")
        if averages["convertible_share"] >= 0.05:
            secondary_labels.append("可转债暴露")
        if averages["local_government_share"] > 0:
            secondary_labels.append("地方政府债暴露")

        if averages["classification_coverage"] < 0.8:
            label = "券种证据不足"
            basis = f"近 4 期公开重仓债券的可归类覆盖仅 {averages['classification_coverage']:.0%}，暂不生成细分标签。"
        elif averages["convertible_share"] >= 0.2:
            label = "可转债显著暴露"
            basis = f"近 4 期公开重仓债券中，可转债平均占比 {averages['convertible_share']:.0%}。"
        elif all(types and types <= rate_types for types in type_sets):
            label = "利率债型公开证据"
            basis = "近 4 期公开重仓债券仅出现国债和政策性金融债。"
        elif all(types and types <= financial_types for types in type_sets):
            label = "金融债型公开证据"
            basis = "近 4 期公开重仓债券仅出现利率债、金融债和同业存单。"
        elif averages["credit_share"] > 0.6 and averages["bond_rating_coverage"] < 0.8:
            label = "信用债主导，等级待核验"
            basis = f"信用债公开占比超过 60%，但债项评级平均覆盖只有 {averages['bond_rating_coverage']:.0%}，暂不判断信用等级。"
        elif averages["credit_share"] > 0.6:
            rating_gap = max(0.0, 1 - averages["high_rating_share"])
            if low_rating_holdings or rating_gap > 0.1:
                label = "中低等级信用债风险证据"
                basis = "信用债公开占比超过 60%，且存在低评级大额持仓或高等级评级覆盖缺口。"
            else:
                label = "中高等级信用债公开证据"
                basis = "信用债公开占比超过 60%，高等级评级覆盖缺口不超过 10%。"
        else:
            label = "信用利率灵活配置公开证据"
            basis = f"近 4 期公开重仓债券中，信用债平均占比 {averages['credit_share']:.0%}，未超过 60%。"

        return {
            "status": "available",
            "label": label,
            "period_count": len(periods),
            "required_periods": required_periods,
            "averages": averages,
            "periods": period_profiles,
            "secondary_labels": secondary_labels,
            "low_rating_holdings": low_rating_holdings[:10],
            "basis": basis,
            "methodology": methodology,
            "limitations": limitations,
            "formal_classification_ready": False,
        }

    @classmethod
    def _metadata_summary(cls, holdings: List[Dict[str, Any]], disclosed_nav_ratio: float) -> Dict[str, Any]:
        available = [row for row in holdings if row.get("metadata_status") == "available"]
        metadata_nav = sum(float(row.get("nav_ratio") or 0) for row in available)

        issuer_values: Dict[str, Dict[str, Any]] = {}
        for row in holdings:
            issuer = str(row.get("issuer") or "").strip()
            if not issuer:
                continue
            item = issuer_values.setdefault(issuer, {"issuer": issuer, "nav_ratio": 0.0, "holding_count": 0})
            item["nav_ratio"] += float(row.get("nav_ratio") or 0)
            item["holding_count"] += 1
        issuers = sorted(issuer_values.values(), key=lambda item: item["nav_ratio"], reverse=True)
        for item in issuers:
            item["nav_ratio"] = round(item["nav_ratio"], 8)
            item["share_of_disclosed"] = round(item["nav_ratio"] / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None
        issuer_nav = sum(item["nav_ratio"] for item in issuers)
        top_three_nav = sum(item["nav_ratio"] for item in issuers[:3])

        rating_values: Dict[str, Dict[str, Any]] = {}
        for row in holdings:
            rating = str(row.get("credit_rating") or "").strip()
            if not rating:
                continue
            item = rating_values.setdefault(rating, {"rating": rating, "nav_ratio": 0.0, "holding_count": 0, "rating_types": set()})
            item["nav_ratio"] += float(row.get("nav_ratio") or 0)
            item["holding_count"] += 1
            if row.get("rating_type"):
                item["rating_types"].add(str(row["rating_type"]))
        rated_nav = sum(item["nav_ratio"] for item in rating_values.values())
        ratings = []
        for item in rating_values.values():
            ratings.append({
                "rating": item["rating"],
                "nav_ratio": round(item["nav_ratio"], 8),
                "share_of_rated": round(item["nav_ratio"] / rated_nav, 8) if rated_nav else None,
                "holding_count": item["holding_count"],
                "rating_types": sorted(item["rating_types"]),
            })
        ratings.sort(key=lambda item: item["nav_ratio"], reverse=True)

        maturity_buckets = [
            {"key": "le_1y", "label": "≤1 年", "min": None, "max": 1.0},
            {"key": "1_3y", "label": "1–3 年", "min": 1.0, "max": 3.0},
            {"key": "3_5y", "label": "3–5 年", "min": 3.0, "max": 5.0},
            {"key": "5_10y", "label": "5–10 年", "min": 5.0, "max": 10.0},
            {"key": "gt_10y", "label": ">10 年", "min": 10.0, "max": None},
        ]
        maturity_known = [row for row in holdings if row.get("remaining_years") is not None]
        maturity_nav = sum(float(row.get("nav_ratio") or 0) for row in maturity_known)
        for bucket in maturity_buckets:
            matched = [
                row for row in maturity_known
                if (bucket["min"] is None or float(row["remaining_years"]) > bucket["min"])
                and (bucket["max"] is None or float(row["remaining_years"]) <= bucket["max"])
            ]
            nav_ratio = sum(float(row.get("nav_ratio") or 0) for row in matched)
            bucket["nav_ratio"] = round(nav_ratio, 8)
            bucket["share_of_known"] = round(nav_ratio / maturity_nav, 8) if maturity_nav else None
            bucket["holding_count"] = len(matched)
            bucket.pop("min")
            bucket.pop("max")

        return {
            "metadata_available_count": len(available),
            "metadata_coverage": round(metadata_nav / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
            "metadata_count_coverage": round(len(available) / len(holdings), 8) if holdings else None,
            "issuer_concentration": {
                "issuer_count": len(issuers),
                "coverage": round(issuer_nav / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
                "top_issuer": issuers[0] if issuers else None,
                "top_three_nav_ratio": round(top_three_nav, 8),
                "top_three_share_of_disclosed": round(top_three_nav / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
                "issuers": issuers[:10],
            },
            "rating_distribution": ratings,
            "rating_coverage": round(rated_nav / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
            "maturity_buckets": maturity_buckets,
            "maturity_coverage": round(maturity_nav / disclosed_nav_ratio, 8) if disclosed_nav_ratio else None,
        }

    @staticmethod
    def _remaining_years(report_date: Any, maturity_date: Any) -> Optional[float]:
        try:
            start = date.fromisoformat(str(report_date)[:10])
            end = date.fromisoformat(str(maturity_date)[:10])
        except (TypeError, ValueError):
            return None
        return round(max(0, (end - start).days / 365.25), 4)

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
            raise ValueError("基金代码格式不支持债券持仓查询")
        return match.group(1)

    @classmethod
    def _page_url(cls, wind_code: str) -> str:
        return cls.PAGE_URL_TEMPLATE.format(code=cls._fund_code(wind_code))

    @classmethod
    def _fetch_url(cls, wind_code: str, year: str) -> str:
        return cls.FETCH_URL_TEMPLATE.format(code=cls._fund_code(wind_code), year=year)
