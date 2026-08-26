"""同步并读取基金产品介绍与完整费率档案。"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup


class FundProductProfileService:
    SOURCE = "eastmoney.fundf10"
    USER_AGENT = "Mozilla/5.0 FundAnalysis/1.0"

    def __init__(self, fund_repo: Optional[Any] = None, http_client: Optional[Any] = None):
        if fund_repo is None:
            from repositories import get_fund_repo

            fund_repo = get_fund_repo()
        self.fund_repo = fund_repo
        self.http_client = http_client

    def get(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            raise ValueError(f"Fund not found: {code}")
        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        profile = raw_data.get("product_profile") if isinstance(raw_data.get("product_profile"), dict) else None
        if profile:
            return profile
        return {
            "status": "unavailable",
            "wind_code": code,
            "source": self.SOURCE,
            "product": {},
            "fees": {},
            "missing_items": ["产品介绍和分档费率尚未同步"],
        }

    def sync(self, wind_code: str) -> Dict[str, Any]:
        code = str(wind_code or "").strip().upper()
        fund = self.fund_repo.get_fund(code)
        if not fund:
            raise ValueError(f"Fund not found: {code}")

        public_code = self._public_code(code)
        basic_url = f"https://fundf10.eastmoney.com/jbgk_{public_code}.html"
        fee_url = f"https://fundf10.eastmoney.com/jjfl_{public_code}.html"
        basic_html = self._fetch(basic_url)
        fee_html = self._fetch(fee_url)
        basic = self.parse_basic_page(basic_html)
        fees = self.parse_fee_page(fee_html)

        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        investment_style = str(info.get("invest_type") or universe.get("invest_type") or "").strip()
        product = basic["product"]
        if investment_style:
            product["investment_style"] = investment_style

        missing_items = [
            label
            for label, value in {
                "投资目标": product.get("investment_objective"),
                "投资范围": product.get("investment_scope"),
                "投资策略": product.get("investment_strategy"),
                "风险收益特征": product.get("risk_return_characteristics"),
                "管理费率": fees.get("management_fee_rate"),
                "托管费率": fees.get("custodian_fee_rate"),
            }.items()
            if not value
        ]
        profile = {
            "status": "available" if len(missing_items) < 6 else "insufficient",
            "wind_code": code,
            "source": self.SOURCE,
            "source_urls": {"basic": basic_url, "fees": fee_url},
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "basic_info": basic["basic_info"],
            "product": product,
            "fees": fees,
            "missing_items": missing_items,
        }
        if not self.fund_repo.update_product_profile(code, profile):
            raise RuntimeError(f"产品档案入库失败: {code}")
        return profile

    def _fetch(self, url: str) -> str:
        if self.http_client is not None:
            response = self.http_client.get(url)
        else:
            response = httpx.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=15,
                follow_redirects=True,
            )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    @classmethod
    def parse_basic_page(cls, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        overview = cls._key_value_table(soup.select_one("table.info"))
        section_map = {
            "投资目标": "investment_objective",
            "投资理念": "investment_philosophy",
            "投资范围": "investment_scope",
            "投资策略": "investment_strategy",
            "风险收益特征": "risk_return_characteristics",
        }
        product: Dict[str, Optional[str]] = {
            "management_company": cls._clean_value(overview.get("基金管理人")),
            "custodian": cls._clean_value(overview.get("基金托管人")),
            "investment_objective": None,
            "investment_style": None,
            "investment_philosophy": None,
            "investment_scope": None,
            "investment_strategy": None,
            "risk_return_characteristics": None,
        }
        for box in soup.select("div.boxitem"):
            heading = box.select_one("h4.t label.left")
            if not heading:
                continue
            field = section_map.get(cls._text(heading))
            paragraph = box.find("p")
            if field and paragraph:
                product[field] = cls._clean_value(cls._text(paragraph))

        return {
            "basic_info": {
                "full_name": cls._clean_value(overview.get("基金全称")),
                "short_name": cls._clean_value(overview.get("基金简称")),
                "fund_type": cls._clean_value(overview.get("基金类型")),
                "benchmark": cls._clean_value(overview.get("业绩比较基准")),
                "tracking_target": cls._clean_value(overview.get("跟踪标的")),
            },
            "product": product,
            "overview_fees": {
                "management_fee_rate": cls._clean_value(overview.get("管理费率")),
                "custodian_fee_rate": cls._clean_value(overview.get("托管费率")),
                "sales_service_fee_rate": cls._clean_value(overview.get("销售服务费率")),
            },
        }

    @classmethod
    def parse_fee_page(cls, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        sections: Dict[str, Any] = {}
        for box in soup.select("div.boxitem"):
            heading = box.select_one("h4.t label.left")
            if heading:
                sections[cls._text(heading).replace("费率计算器", "").strip()] = box

        operation = cls._key_value_table(sections.get("运作费用").find("table") if sections.get("运作费用") else None)
        return {
            "management_fee_rate": cls._clean_value(operation.get("管理费率")),
            "custodian_fee_rate": cls._clean_value(operation.get("托管费率")),
            "sales_service_fee_rate": cls._clean_value(operation.get("销售服务费率")),
            "subscription_fee_rules": cls._fee_rules(sections.get("认购费率")),
            "purchase_fee_rules": cls._fee_rules(sections.get("申购费率")),
            "redemption_fee_rules": cls._fee_rules(sections.get("赎回费率")),
            "note": "运作费用已从每日基金净值中计提；交易费率以基金合同、招募说明书和销售渠道实际规则为准。",
        }

    @classmethod
    def _key_value_table(cls, table: Any) -> Dict[str, str]:
        if table is None:
            return {}
        result: Dict[str, str] = {}
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            index = 0
            while index + 1 < len(cells):
                is_key = cells[index].name == "th" or "th" in (cells[index].get("class") or [])
                if is_key:
                    result[cls._text(cells[index])] = cls._text(cells[index + 1])
                    index += 2
                else:
                    index += 1
        return result

    @classmethod
    def _fee_rules(cls, box: Any) -> List[Dict[str, str]]:
        if box is None:
            return []
        table = box.find("table")
        if table is None:
            return []
        headers = [cls._text(cell) for cell in table.select("thead th")]
        rows = []
        for row in table.select("tbody tr"):
            cells = [cls._text(cell) for cell in row.find_all(["th", "td"], recursive=False)]
            if len(cells) < 2:
                continue
            condition = cls._clean_value(cells[0])
            rate = cls._clean_value(cells[-1])
            if condition or rate:
                rows.append({
                    "condition": condition or "全部",
                    "rate": rate or "待补",
                    "condition_label": headers[0] if headers else "适用条件",
                })
        return rows

    @staticmethod
    def _public_code(wind_code: str) -> str:
        matched = re.match(r"^(\d{6})", wind_code)
        if not matched:
            raise ValueError(f"不支持的基金代码: {wind_code}")
        return matched.group(1)

    @staticmethod
    def _text(node: Any) -> str:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""

    @staticmethod
    def _clean_value(value: Any) -> Optional[str]:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return None if text in {"", "-", "--", "---", "暂无数据"} else text
