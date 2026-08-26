"""从腾讯证券公开日 K 线读取港股区间收益。"""

import json
import os
from typing import Any, Callable, Dict, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HongKongMarketDataService:
    SOURCE = "tencent.hk.fqkline"
    API_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self, opener: Callable[..., Any] = urlopen):
        self.opener = opener
        self._cache: Dict[tuple[str, str, str], float] = {}

    def get_period_returns(
        self,
        stock_codes: Iterable[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        returns: Dict[str, float] = {}
        for stock_code in sorted(set(stock_codes)):
            code = str(stock_code or "").strip().upper()
            if not code.endswith(".HK"):
                continue
            cache_key = (code, start_date, end_date)
            if cache_key in self._cache:
                returns[code] = self._cache[cache_key]
                continue
            try:
                value = self._fetch_period_return(code, start_date, end_date)
            except Exception:
                continue
            if value is not None:
                value = round(value, 8)
                self._cache[cache_key] = value
                returns[code] = value
        return {
            "returns": returns,
            "source": self.SOURCE if returns else None,
            "adjustment": "unadjusted_close",
        }

    def _fetch_period_return(self, stock_code: str, start_date: str, end_date: str):
        symbol = f"hk{stock_code.split('.', 1)[0]}"
        start = self._date_text(start_date)
        end = self._date_text(end_date)
        query = urlencode({"param": f"{symbol},day,{start},{end},320,qfq"})
        request = Request(
            f"{self.API_URL}?{query}",
            headers={
                "User-Agent": "Mozilla/5.0 FundResearch/1.0",
                "Referer": "https://gu.qq.com/",
            },
        )
        timeout = max(3, min(int(os.environ.get("FUND_PUBLIC_DATA_TIMEOUT_SECONDS", "12")), 30))
        with self.opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        data = ((payload.get("data") or {}).get(symbol) or {})
        rows = data.get("qfqday") or data.get("day") or []
        closes = [self._number(row[2]) for row in rows if isinstance(row, list) and len(row) >= 3]
        closes = [value for value in closes if value is not None and value > 0]
        if len(closes) < 2:
            return None
        return closes[-1] / closes[0] - 1

    @staticmethod
    def _date_text(value: str) -> str:
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text[:10]

    @staticmethod
    def _number(value: Any):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed == parsed else None
