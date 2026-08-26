"""从公开主数据源查询债券发行人、评级和到期信息。"""

import json
import os
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class BondSecurityMetadataService:
    CHINAMONEY_SEARCH_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/BondMarketInfoList2"
    CHINAMONEY_DETAIL_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bond-md/BondDetailInfo"
    CHINAMONEY_PAGE_URL = "https://www.chinamoney.com.cn/chinese/zqjc/?bondDefinedCode={defined_code}"
    EASTMONEY_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    EXCHANGE_BOND_PREFIXES = ("110", "113", "118", "123", "127", "128", "132")

    def __init__(self, opener: Callable[..., Any] = urlopen):
        self.opener = opener
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_chinamoney_request_at = 0.0

    def lookup(self, bond_code: str, bond_name: str = "") -> Dict[str, Any]:
        code = str(bond_code or "").strip().upper().split(".", 1)[0]
        if not code:
            return self.unavailable("")
        if code in self._cache:
            return dict(self._cache[code])

        lookups = (
            (self._lookup_eastmoney, self._lookup_chinamoney)
            if code.startswith(self.EXCHANGE_BOND_PREFIXES)
            else (self._lookup_chinamoney, self._lookup_eastmoney)
        )
        for lookup in lookups:
            try:
                result = lookup(code, bond_name)
            except Exception:
                result = None
            if result:
                self._cache[code] = result
                return dict(result)

        result = self.unavailable(code)
        self._cache[code] = result
        return dict(result)

    def _lookup_chinamoney(self, bond_code: str, bond_name: str) -> Optional[Dict[str, Any]]:
        match = None
        for bond_type in self._chinamoney_type_codes(bond_name):
            search = self._post_chinamoney_json(self.CHINAMONEY_SEARCH_URL, {
                "pageNo": "1",
                "pageSize": "15",
                "bondName": "",
                "bondCode": bond_code,
                "issueEnty": "",
                "bondType": bond_type,
                "bondSpclPrjctVrty": "",
                "couponType": "",
                "issueYear": "",
                "entyDefinedCode": "",
                "rtngShrt": "",
            })
            matches = ((search.get("data") or {}).get("resultList") or [])
            match = next((item for item in matches if str(item.get("bondCode") or "").strip().upper() == bond_code), None)
            if match:
                break
        if not match:
            return None
        defined_code = str(match.get("bondDefinedCode") or "").strip()
        detail_payload = self._post_chinamoney_json(self.CHINAMONEY_DETAIL_URL, {"bondDefinedCode": defined_code}) if defined_code else {}
        detail = ((detail_payload.get("data") or {}).get("bondBaseInfo") or {})
        return self.parse_chinamoney(match, detail)

    @staticmethod
    def _chinamoney_type_codes(bond_name: str) -> tuple[str, ...]:
        name = str(bond_name or "").strip().upper()
        rules = [
            (("二级资本", "银行二级", "二级债"), ("100054", "100005")),
            (("TLAC", "非资本债"), ("100086",)),
            (("永续", "无固定期限资本"), ("100083", "100007")),
            (("农发", "国开", "进出"), ("100003",)),
            (("同业存单", "CD"), ("100041",)),
            (("超短融", "SCP"), ("100029",)),
            (("短融", "CP"), ("100006",)),
            (("中票", "MTN"), ("100010",)),
            (("地方债", "政府债"), ("100011",)),
            (("国债",), ("100001",)),
            (("ABN", "资产支持票据"), ("100072",)),
            (("ABS", "资产支持"), ("999999",)),
            (("保险公司债", "资本补充债"), ("100056",)),
            (("金融债", "银行债"), ("100007", "100054", "100083")),
            (("企业债",), ("100004",)),
            (("公司债",), ("100004",)),
        ]
        for keywords, codes in rules:
            if any(keyword in name for keyword in keywords):
                return codes
        provinces = ("北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆")
        if name.endswith(tuple(f"{province}债" for province in provinces)) or any(f"{province}债" in name for province in provinces):
            return ("100011",)
        return ()

    def _lookup_eastmoney(self, bond_code: str, _bond_name: str) -> Optional[Dict[str, Any]]:
        query = urlencode({
            "reportName": "RPT_BOND_BASICINFO",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{bond_code}")',
        })
        payload = self._get_json(f"{self.EASTMONEY_API_URL}?{query}")
        rows = ((payload.get("result") or {}).get("data") or [])
        match = next((item for item in rows if str(item.get("SECURITY_CODE") or "").strip().upper() == bond_code), None)
        return self.parse_eastmoney(match) if match else None

    @classmethod
    def parse_chinamoney(cls, search: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
        debt_rating = cls._normalize_rating(cls._clean(search.get("debtRtng")))
        subject_ratings = detail.get("creditRateEntyList") or []
        subject_rating = cls._normalize_rating(cls._clean(subject_ratings[0].get("creditSubjectRating"))) if subject_ratings else None
        defined_code = cls._clean(search.get("bondDefinedCode")) or ""
        coupon_percent = cls._number(detail.get("parCouponRate"))
        return {
            "bond_code": cls._clean(search.get("bondCode")) or "",
            "issuer": cls._clean(detail.get("entyFullName")) or cls._clean(search.get("entyFullName")),
            "security_bond_type": cls._clean(detail.get("bondType")) or cls._clean(search.get("bondType")),
            "credit_rating": debt_rating or subject_rating,
            "rating_type": "bond" if debt_rating else ("issuer_subject" if subject_rating else None),
            "maturity_date": cls._clean(detail.get("mrtyDate")),
            "coupon_rate": round(coupon_percent / 100, 8) if coupon_percent is not None else None,
            "metadata_source": "chinamoney.bond_base_info",
            "metadata_url": cls.CHINAMONEY_PAGE_URL.format(defined_code=defined_code) if defined_code else cls.CHINAMONEY_SEARCH_URL,
            "metadata_status": "available",
        }

    @classmethod
    def parse_eastmoney(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        bond_code = cls._clean(row.get("SECURITY_CODE")) or ""
        security_type = "可交换公司债券" if bond_code.startswith("132") else "可转换公司债券"
        query = urlencode({
            "reportName": "RPT_BOND_BASICINFO",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{bond_code}")',
        })
        return {
            "bond_code": bond_code,
            "issuer": cls._clean(row.get("CORRE_SECURITY_NAME")),
            "security_bond_type": security_type,
            "credit_rating": cls._normalize_rating(cls._clean(row.get("RATING"))),
            "rating_type": "bond" if cls._clean(row.get("RATING")) else None,
            "maturity_date": cls._date(cls._clean(row.get("RESIDUAL_YEAR"))),
            "coupon_rate": None,
            "metadata_source": "eastmoney.bond_basicinfo",
            "metadata_url": f"{cls.EASTMONEY_API_URL}?{query}",
            "metadata_status": "available",
        }

    @staticmethod
    def unavailable(bond_code: str) -> Dict[str, Any]:
        return {
            "bond_code": bond_code,
            "issuer": None,
            "security_bond_type": None,
            "credit_rating": None,
            "rating_type": None,
            "maturity_date": None,
            "coupon_rate": None,
            "metadata_source": None,
            "metadata_url": None,
            "metadata_status": "unavailable",
        }

    def _post_json(self, url: str, payload: Dict[str, str]) -> Dict[str, Any]:
        request = Request(
            url,
            data=urlencode(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        return self._open_json(request)

    def _post_chinamoney_json(self, url: str, payload: Dict[str, str]) -> Dict[str, Any]:
        interval = max(0.0, float(os.environ.get("CHINAMONEY_REQUEST_INTERVAL_SECONDS", "0.12")))
        remaining = interval - (time.monotonic() - self._last_chinamoney_request_at)
        if remaining > 0:
            time.sleep(remaining)
        result = self._post_json(url, payload)
        self._last_chinamoney_request_at = time.monotonic()
        return result

    def _get_json(self, url: str) -> Dict[str, Any]:
        return self._open_json(Request(url, headers=self._headers()))

    def _open_json(self, request: Request) -> Dict[str, Any]:
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        with self.opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    @staticmethod
    def _headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 FundResearch/1.0",
            "Referer": "https://www.chinamoney.com.cn/chinese/scsjzqxx/",
        }

    @staticmethod
    def _clean(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return None if text in {"", "-", "--", "---", "None", "null"} else text

    @classmethod
    def _date(cls, value: Optional[str]) -> Optional[str]:
        return value[:10] if value and len(value) >= 10 else value

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _normalize_rating(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        parts = list(dict.fromkeys(
            part.strip()
            for part in value.split("/")
            if part.strip() not in {"", "-", "--", "---"}
        ))
        return "/".join(parts) or None
