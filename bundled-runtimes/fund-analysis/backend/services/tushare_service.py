"""
Tushare 数据服务 - 替代 Wind API 获取基金和经理数据
"""
import os
import re
import time
import logging
import hashlib
import csv
import io
import json
import urllib.parse
import urllib.request
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import pandas as pd

from services.fund_nav_evidence_service import FundNavEvidenceService
from lib.holding_weight_validation import normalize_holding_weights

logger = logging.getLogger(__name__)

TUSHARE_NO_PROXY_HOSTS = ("api.tushare.pro", "tushare.pro", "waditu.com", "api.waditu.com")
TUSHARE_INDEX_CODE_PATTERN = re.compile(r"^[0-9A-Z]{6}\.(SH|SZ|CSI)$", re.IGNORECASE)
TUSHARE_GLOBAL_INDEX_CODES = {"HSI"}
GLOBAL_INDEX_CNY_BENCHMARKS = {
    "NDX.CNY": {
        "base_code": "NDX",
        "base_currency": "USD",
        "provider": "yahoo_chart",
        "provider_symbol": "^NDX",
        "fallback_provider": "fred_csv",
        "fallback_series_id": "NASDAQ100",
    },
}

# Tushare SDK
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    logger.warning("Tushare not installed. Run: pip install tushare")

def _to_wind_code(ts_code: str) -> str:
    """Tushare 代码转 Wind 格式"""
    if not ts_code:
        return ts_code
    # 已有 .SH/.SZ/.BJ 后缀（如 ETF），直接返回
    if any(ts_code.endswith(s) for s in (".SH", ".SZ", ".BJ")):
        return ts_code
    # 纯数字代码（如标准 OF 基金）追加 .OF
    if ts_code.isdigit():
        return f"{ts_code}.OF"
    return ts_code


def _to_ts_code(wind_code: str) -> str:
    """Wind 代码转 Tushare 格式（用于 API 调用）

    ETF: .SH.OF → .SH, .SZ.OF → .SZ, .BJ.OF → .BJ
    标准 OF 基金: .OF 保留（如 000001.OF → 000001.OF）
    """
    if not wind_code:
        return wind_code
    # ETF：520680.SH.OF → 520680.SH
    for suffix in (".SH.OF", ".SZ.OF", ".BJ.OF"):
        if wind_code.endswith(suffix):
            return wind_code[:-3]
    # 标准 OF 基金保留 .OF（如 000001.OF → 000001.OF）
    # 注：fund_nav 等 API 需要完整的 .OF 后缀
    return wind_code


def _format_tushare_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip().lower() in {"", "none", "nan", "nat"}:
            return None
        parsed = float(value)
        if pd.isna(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _asset_to_yi(value: Any) -> Optional[float]:
    """Normalize Tushare net asset fields to 亿元 for the UI/research layer."""
    parsed = _as_float(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed >= 1_000_000:
        return round(parsed / 100_000_000, 4)
    if parsed >= 100:
        return round(parsed / 10_000, 4)
    return round(parsed, 4)


@dataclass
class TushareConfig:
    """Tushare 配置"""
    token: str
    auto_care: bool = True  # 自动补齐交易日


class TushareDataService:
    """Tushare 数据服务类"""

    def __init__(self, token: str = None, mock_mode: bool = None, strict_no_mock: bool = False):
        self._ensure_tushare_no_proxy()
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        self.request_timeout_seconds = max(
            3,
            min(int(os.environ.get("TUSHARE_REQUEST_TIMEOUT_SECONDS", "8")), 30),
        )
        self._pro: Optional[Any] = None
        self.strict_no_mock = strict_no_mock

        if mock_mode is None:
            mock_mode = not TUSHARE_AVAILABLE or not bool(self.token)
        if strict_no_mock and mock_mode:
            missing = []
            if not TUSHARE_AVAILABLE:
                missing.append("tushare package unavailable")
            if not self.token:
                missing.append("TUSHARE_TOKEN missing")
            raise RuntimeError(f"Tushare strict_no_mock requires real data source: {', '.join(missing) or 'mock_mode=true'}")

        self.mock_mode = mock_mode

        # 基金经理缓存（避免重复查询）
        self._manager_cache: Optional[Dict[str, Any]] = None
        self._manager_cache_time: float = 0
        self._manager_cache_ttl: float = 3600  # 1小时过期
        self._stock_profile_cache: Dict[str, Dict[str, Any]] = {}
        self._stock_profile_cache_loaded = False
        self._benchmark_nav_cache: Dict[tuple, List[Dict[str, Any]]] = {}

        if not self.mock_mode and TUSHARE_AVAILABLE:
            try:
                ts.set_token(self.token)
                self._pro = ts.pro_api(self.token, timeout=self.request_timeout_seconds)
                logger.info("Tushare connected successfully")
            except Exception as e:
                if self.strict_no_mock:
                    raise RuntimeError(f"Tushare connection failed: {e}") from e
                logger.error(f"Tushare connection failed: {e}, falling back to mock mode")
                self.mock_mode = True
        else:
            logger.info(f"Tushare initialized in mock_mode={mock_mode}")

    def _ensure_tushare_no_proxy(self) -> None:
        existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        hosts = [item.strip() for item in existing.split(",") if item.strip()]
        normalized = {host.lower() for host in hosts}
        for host in TUSHARE_NO_PROXY_HOSTS:
            if host.lower() not in normalized:
                hosts.append(host)
        value = ",".join(hosts)
        os.environ["NO_PROXY"] = value
        os.environ["no_proxy"] = value

    @property
    def pro(self):
        """获取 Tushare pro API 实例"""
        if self._pro is None and not self.mock_mode:
            try:
                ts.set_token(self.token)
                self._pro = ts.pro_api(self.token, timeout=self.request_timeout_seconds)
            except Exception as e:
                if self.strict_no_mock:
                    raise RuntimeError(f"Tushare pro API init failed: {e}") from e
                logger.error(f"Tushare pro API init failed: {e}")
                self.mock_mode = True
        return self._pro

    def _strict_fail(self, message: str) -> None:
        if self.strict_no_mock:
            raise RuntimeError(message)

    def _h(self, wind_code: str, salt: str) -> int:
        """确定性 hash 用于 mock 数据"""
        return int(hashlib.md5(f"{wind_code}{salt}".encode()).hexdigest()[:8], 16) % 500

    # ==================== 基金基础数据 ====================

    def get_fund_info(self, wind_code: str) -> Dict[str, Any]:
        """获取基金基本信息"""
        if self.mock_mode:
            return self._mock_fund_info(wind_code)

        try:
            ts_code = _to_ts_code(wind_code)
            df = self.pro.fund_basic(
                ts_code=ts_code,
                fields=(
                    "ts_code,name,management,custodian,admin,found_date,due_date,"
                    "list_date,issue_date,market,state,status,fund_type,invest_type,type,"
                    "purc_startdate,redm_startdate,m_fee,c_fee,benchmark"
                )
            )
            if df is None or df.empty:
                self._strict_fail(f"Tushare fund_basic returned empty for {wind_code}")
                return self._mock_fund_info(wind_code)

            row = df.iloc[0]
            nav_data = {}
            try:
                info_df = self.pro.fund_nav(ts_code=ts_code)
                if info_df is not None and not info_df.empty:
                    ranked = info_df.copy()
                    ranked["nav_date_sort"] = ranked["nav_date"].astype(str)
                    ranked["ann_date_sort"] = ranked["ann_date"].astype(str)
                    if "update_flag" in ranked.columns:
                        ranked["update_flag_sort"] = ranked["update_flag"].astype(str)
                    else:
                        ranked["update_flag_sort"] = ""
                    ranked = ranked.sort_values(
                        ["nav_date_sort", "update_flag_sort", "ann_date_sort"],
                        ascending=[False, False, False],
                    )
                    nav_data = ranked.iloc[0].to_dict()
            except Exception as nav_error:
                logger.warning(f"Tushare fund_nav latest nav unavailable for {wind_code}: {nav_error}")

            total_asset = _asset_to_yi(nav_data.get("total_netasset")) or _asset_to_yi(nav_data.get("net_asset"))
            total_asset_source = "fund_nav"
            if total_asset is None:
                try:
                    share_df = self.pro.fund_share(ts_code=ts_code)
                    latest_nav = _as_float(nav_data.get("unit_nav")) or _as_float(nav_data.get("accum_nav"))
                    if share_df is not None and not share_df.empty and latest_nav:
                        share_df = share_df.sort_values("trade_date", ascending=False)
                        latest_share = _as_float(share_df.iloc[0].get("fd_share"))
                        if latest_share:
                            total_asset = round(latest_share * latest_nav / 10_000, 4)
                            total_asset_source = "fund_share_estimate"
                except Exception as share_error:
                    logger.warning(f"Tushare fund_share unavailable for {wind_code}: {share_error}")

            return {
                "wind_code": wind_code,
                "name": row.get("name", ""),
                "full_name": row.get("name", ""),
                "type": self._normalize_fund_type(
                    row.get("fund_type"),
                    row.get("invest_type"),
                    row.get("name"),
                    ts_code,
                ),
                "fund_type_raw": row.get("fund_type", ""),
                "invest_type": row.get("invest_type", ""),
                "contract_type": row.get("type", ""),
                "status": row.get("status", ""),
                "manager": row.get("management", ""),
                "management_company": row.get("management", ""),
                "custodian": row.get("custodian", ""),
                "establishment_date": _format_tushare_date(row.get("found_date")) or str(row.get("found_date", "")),
                "purchase_start_date": _format_tushare_date(row.get("purc_startdate")),
                "redeem_start_date": _format_tushare_date(row.get("redm_startdate")),
                "management_fee": row.get("m_fee"),
                "custodian_fee": row.get("c_fee"),
                "benchmark": row.get("benchmark", ""),
                "total_asset": total_asset,
                "total_asset_source": total_asset_source if total_asset is not None else None,
                "nav": nav_data.get("unit_nav"),
                "nav_date": _format_tushare_date(nav_data.get("nav_date")),
                "state": row.get("state", ""),
            }
        except Exception as e:
            logger.error(f"Tushare get_fund_info error for {wind_code}: {e}")
            self._strict_fail(f"Tushare get_fund_info failed for {wind_code}: {e}")
            return self._mock_fund_info(wind_code)

    def get_fund_list(self, fund_type: Optional[str] = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """获取基金列表"""
        if self.mock_mode:
            return self._mock_fund_list(fund_type, page, page_size)

        try:
            # 获取所有状态的基金（包括在运作和已清算）
            all_dfs = []
            for status in ['D', 'L']:
                offset = 0
                limit = 1000
                while True:
                    df = self.pro.fund_basic(
                        status=status,
                        fields=(
                            "ts_code,name,management,custodian,found_date,state,status,"
                            "fund_type,invest_type,type,purc_startdate,redm_startdate,m_fee,c_fee,benchmark"
                        ),
                        offset=offset,
                        limit=limit
                    )
                    if df is None or df.empty:
                        break
                    all_dfs.append(df)
                    if len(df) < limit:
                        break
                    offset += limit
                    time.sleep(0.05)

            if not all_dfs:
                self._strict_fail("Tushare fund_basic returned empty fund list")
                return self._mock_fund_list(fund_type, page, page_size)

            df = pd.concat(all_dfs, ignore_index=True)
            if fund_type:
                target_type = self._normalize_fund_type(fund_type)
                df = df[
                    df.apply(
                        lambda row: self._normalize_fund_type(
                            row.get("fund_type"),
                            row.get("invest_type"),
                            row.get("name"),
                            row.get("ts_code"),
                        ) == target_type,
                        axis=1,
                    )
                ]
            logger.info(f"Tushare fund_basic returned {len(df)} funds")

            total = len(df)
            start = (page - 1) * page_size
            end = start + page_size
            page_data = df.iloc[start:end]
            fund_codes = [_to_wind_code(row['ts_code']) for _, row in page_data.iterrows()]

            return {
                "total": total, "list": fund_codes,
                "page": page, "page_size": page_size,
            }
        except Exception as e:
            logger.error(f"Tushare get_fund_list error: {e}")
            self._strict_fail(f"Tushare get_fund_list failed: {e}")
            return self._mock_fund_list(fund_type, page, page_size)

    def get_fund_nav(self, wind_code: str, start_date: str, end_date: str) -> List[Dict]:
        """获取基金净值数据"""
        if self.mock_mode:
            return self._normalize_nav_series(self._mock_nav_series(wind_code, start_date, end_date))

        try:
            ts_code = _to_ts_code(wind_code)
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")
            df = self.pro.fund_nav(ts_code=ts_code, start_date=start, end_date=end)
            if df is None or df.empty:
                self._strict_fail(f"Tushare fund_nav returned empty nav series for {wind_code}")
                return self._normalize_nav_series(self._mock_nav_series(wind_code, start_date, end_date))

            result = []
            df = df.sort_values("nav_date")
            minimum_source_rows = max(2, int(len(df) * 0.6))
            metric_nav_source = next(
                (
                    column
                    for column in ("accum_nav", "adj_nav", "unit_nav")
                    if column in df.columns
                    and pd.to_numeric(df[column], errors="coerce").notna().sum() >= minimum_source_rows
                ),
                None,
            )
            if metric_nav_source is None:
                self._strict_fail(f"Tushare fund_nav has no consistent NAV column for {wind_code}")
                return []
            previous_accum_nav = None
            for _, row in df.iterrows():
                date_str = str(row.get("nav_date", ""))
                if len(date_str) == 8:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                metric_nav = _as_float(row.get(metric_nav_source))
                if metric_nav is None or metric_nav <= 0:
                    continue
                unit_nav = _as_float(row.get("unit_nav")) or metric_nav
                adjusted_nav = _as_float(row.get("adj_nav"))
                accum_nav = metric_nav
                daily_return = None
                if previous_accum_nav and accum_nav:
                    daily_return = (accum_nav / previous_accum_nav) - 1
                if accum_nav:
                    previous_accum_nav = accum_nav
                result.append({
                    "date": date_str,
                    "nav": unit_nav,
                    "unit_nav": unit_nav,
                    "accum_nav": accum_nav,
                    "adj_nav": adjusted_nav,
                    "reported_accum_nav": _as_float(row.get("accum_nav")),
                    "metric_nav_source": f"tushare.fund_nav.{metric_nav_source}",
                    "daily_return": daily_return,
                    "net_asset": _as_float(row.get("net_asset")),
                    "total_netasset": _as_float(row.get("total_netasset")),
                })
            return self._normalize_nav_series(result)
        except Exception as e:
            logger.error(f"Tushare get_fund_nav error for {wind_code}: {e}")
            self._strict_fail(f"Tushare get_fund_nav failed for {wind_code}: {e}")
            return self._normalize_nav_series(self._mock_nav_series(wind_code, start_date, end_date))

    def get_benchmark_nav(self, benchmark_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """获取可核验的指数基准序列；不支持的基准代码显式返回空集。"""
        normalized_code = str(benchmark_code or "").strip().upper()
        cache_key = (normalized_code, str(start_date), str(end_date))
        if cache_key in self._benchmark_nav_cache:
            return [dict(item) for item in self._benchmark_nav_cache[cache_key]]
        if normalized_code in GLOBAL_INDEX_CNY_BENCHMARKS:
            result = self._get_global_index_cny_nav(
                normalized_code,
                start_date=str(start_date),
                end_date=str(end_date),
            )
            if result:
                self._benchmark_nav_cache[cache_key] = [dict(item) for item in result]
            return result
        is_global_index = normalized_code in TUSHARE_GLOBAL_INDEX_CODES
        if self.mock_mode or (
            not is_global_index
            and not TUSHARE_INDEX_CODE_PATTERN.fullmatch(normalized_code)
        ):
            return []
        try:
            endpoint = self.pro.index_global if is_global_index else self.pro.index_daily
            frame = endpoint(
                ts_code=normalized_code,
                start_date=str(start_date).replace("-", ""),
                end_date=str(end_date).replace("-", ""),
                fields="ts_code,trade_date,close",
            )
            if frame is None or frame.empty:
                return []
            result = []
            for _, row in frame.sort_values("trade_date").iterrows():
                trade_date = _format_tushare_date(row.get("trade_date"))
                close = _as_float(row.get("close"))
                if trade_date and close and close > 0:
                    result.append({
                        "date": trade_date,
                        "nav": close,
                        "benchmark_code": normalized_code,
                        "source": "tushare.index_global" if is_global_index else "tushare.index_daily",
                    })
            self._benchmark_nav_cache[cache_key] = [dict(item) for item in result]
            return result
        except Exception as error:
            logger.warning("Tushare benchmark unavailable for %s: %s", normalized_code, error)
            return []

    def _get_global_index_cny_nav(
        self,
        benchmark_code: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """用全球指数本币收益与 Tushare 汇率构建人民币计价基准。"""
        metadata = GLOBAL_INDEX_CNY_BENCHMARKS.get(benchmark_code) or {}
        if self.mock_mode or not metadata:
            return []

        if metadata.get("provider") == "yahoo_chart":
            index_series = self._get_yahoo_index_nav(
                str(metadata.get("provider_symbol") or ""),
                start_date,
                end_date,
            )
        else:
            index_series = self._get_tushare_global_index_nav(
                str(metadata.get("base_code") or ""),
                start_date,
                end_date,
            )
        if not index_series and metadata.get("fallback_provider") == "fred_csv":
            index_series = self._get_fred_index_nav(
                str(metadata.get("fallback_series_id") or ""),
                start_date,
                end_date,
            )
        fx_series = self._get_currency_cny_series(
            str(metadata.get("base_currency") or ""),
            start_date,
            end_date,
        )
        index_by_date = {
            str(item.get("date")): _as_float(item.get("nav"))
            for item in index_series
            if item.get("date") and _as_float(item.get("nav")) is not None
        }
        fx_by_date = {
            str(item.get("date")): _as_float(item.get("cny_rate"))
            for item in fx_series
            if item.get("date") and _as_float(item.get("cny_rate")) is not None
        }
        common_dates = sorted(set(index_by_date) & set(fx_by_date))
        source = (
            f"derived:{(index_series[0].get('source') if index_series else 'global_index_unavailable')}"
            "+tushare.fx_daily.common_dates_v1"
        )
        return [
            {
                "date": item_date,
                "nav": round(index_by_date[item_date] * fx_by_date[item_date], 8),
                "benchmark_code": benchmark_code,
                "source": source,
                "base_index_code": metadata.get("base_code"),
                "base_currency": metadata.get("base_currency"),
                "evaluation_currency": "CNY",
            }
            for item_date in common_dates
            if index_by_date[item_date] > 0 and fx_by_date[item_date] > 0
        ]

    def _get_tushare_global_index_nav(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        if not index_code:
            return []
        try:
            frame = self.pro.index_global(
                ts_code=index_code,
                start_date=str(start_date).replace("-", ""),
                end_date=str(end_date).replace("-", ""),
                fields="ts_code,trade_date,close",
            )
        except Exception as error:
            logger.warning("Tushare global index unavailable for %s: %s", index_code, error)
            return []
        if frame is None or frame.empty:
            return []
        return [
            {
                "date": trade_date,
                "nav": close,
                "source": "tushare.index_global",
            }
            for _, row in frame.sort_values("trade_date").iterrows()
            if (trade_date := _format_tushare_date(row.get("trade_date")))
            if (close := _as_float(row.get("close"))) is not None and close > 0
        ]

    def _get_yahoo_index_nav(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Tushare 缺少纳指100时的有界备用源；只读日线收盘价。"""
        if not symbol:
            return []
        start_timestamp = int(datetime.fromisoformat(str(start_date)[:10]).replace(tzinfo=timezone.utc).timestamp())
        end_timestamp = int(
            (datetime.fromisoformat(str(end_date)[:10]) + timedelta(days=1))
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        encoded_symbol = urllib.parse.quote(symbol, safe="")
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
            f"?period1={start_timestamp}&period2={end_timestamp}&interval=1d&events=history"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                payload = json.load(response)
        except Exception as error:
            logger.warning("Yahoo benchmark fallback unavailable for %s: %s", symbol, error)
            return []
        results = ((payload.get("chart") or {}).get("result") or [])
        if not results:
            return []
        result = results[0]
        timestamps = result.get("timestamp") or []
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
        series = []
        for timestamp, close_value in zip(timestamps, closes):
            close = _as_float(close_value)
            if close is None or close <= 0:
                continue
            item_date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
            series.append({"date": item_date, "nav": close, "source": "yahoo.chart"})
        return series

    def _get_fred_index_nav(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """Yahoo 受限时从 FRED 读取 Nasdaq 官方日线序列。"""
        normalized_series_id = str(series_id or "").strip().upper()
        if not normalized_series_id:
            return []
        query = urllib.parse.urlencode({
            "id": normalized_series_id,
            "cosd": str(start_date)[:10],
            "coed": str(end_date)[:10],
        })
        request = urllib.request.Request(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                payload = response.read().decode("utf-8-sig")
        except Exception as error:
            logger.warning("FRED benchmark fallback unavailable for %s: %s", normalized_series_id, error)
            return []

        result = []
        for row in csv.DictReader(io.StringIO(payload)):
            item_date = str(row.get("observation_date") or "").strip()
            close = _as_float(row.get(normalized_series_id))
            if item_date and close is not None and close > 0:
                result.append({
                    "date": item_date,
                    "nav": close,
                    "source": f"fred.fredgraph.csv:{normalized_series_id}",
                })
        return result

    def _get_currency_cny_series(
        self,
        currency: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        normalized_currency = str(currency or "").strip().upper()
        if normalized_currency == "CNY":
            return []
        direct_codes = {
            "USD": "USDCNH.FXCM",
        }
        fx_code = direct_codes.get(normalized_currency)
        if not fx_code:
            return []
        try:
            frame = self.pro.fx_daily(
                ts_code=fx_code,
                start_date=str(start_date).replace("-", ""),
                end_date=str(end_date).replace("-", ""),
                fields="ts_code,trade_date,bid_close,ask_close",
            )
        except Exception as error:
            logger.warning("Tushare FX unavailable for %s: %s", fx_code, error)
            return []
        if frame is None or frame.empty:
            return []
        result = []
        for _, row in frame.sort_values("trade_date").iterrows():
            item_date = _format_tushare_date(row.get("trade_date"))
            bid = _as_float(row.get("bid_close"))
            ask = _as_float(row.get("ask_close"))
            if item_date and bid and ask and bid > 0 and ask > 0:
                result.append({
                    "date": item_date,
                    "cny_rate": (bid + ask) / 2.0,
                    "source": f"tushare.fx_daily:{fx_code}:mid_close",
                })
        return result

    def get_hong_kong_stock_returns(
        self,
        stock_codes: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """批量读取港股区间收益，避开 Tushare 港股日线的低频调用限制。"""
        from services.hong_kong_market_service import HongKongMarketDataService

        service = getattr(self, "_hong_kong_market_service", None)
        if service is None:
            service = HongKongMarketDataService()
            self._hong_kong_market_service = service
        return service.get_period_returns(stock_codes, start_date, end_date)

    def get_hang_seng_index_snapshot(self, refresh: bool = False) -> Dict[str, Any]:
        from services.hang_seng_index_service import HangSengIndexService

        service = getattr(self, "_hang_seng_index_service", None)
        if service is None:
            service = HangSengIndexService()
            self._hang_seng_index_service = service
        return service.get_hsi_snapshot(refresh=refresh)

    @staticmethod
    def get_hang_seng_index_snapshot_before(as_of_date: str) -> Optional[Dict[str, Any]]:
        from repositories import get_market_index_constituent_repo

        return get_market_index_constituent_repo().get_latest_on_or_before("HSI", as_of_date)

    def get_benchmark_rate(self, benchmark_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """获取利率型基准；利率证据与净值序列严格分离。"""
        normalized_code = str(benchmark_code or "").strip().upper()
        if self.mock_mode or normalized_code != "DR007":
            return []
        try:
            frame = self.pro.repo_daily(
                ts_code="DR007.IB",
                start_date=str(start_date).replace("-", ""),
                end_date=str(end_date).replace("-", ""),
                fields="ts_code,trade_date,repo_maturity,weight_r,weight,close",
            )
            if frame is None or frame.empty:
                return []
            result = []
            for _, row in frame.sort_values("trade_date").iterrows():
                trade_date = _format_tushare_date(row.get("trade_date"))
                reported_rate = (
                    _as_float(row.get("weight_r"))
                    or _as_float(row.get("weight"))
                    or _as_float(row.get("close"))
                )
                if trade_date and reported_rate is not None and 0 <= reported_rate <= 100:
                    result.append({
                        "date": trade_date,
                        "annualized_rate": reported_rate / 100.0,
                        "reported_rate": reported_rate,
                        "rate_unit": "percent_per_annum",
                        "benchmark_code": normalized_code,
                        "source": "tushare.repo_daily.DR007.IB.weight_r",
                    })
            return result
        except Exception as error:
            logger.warning("Tushare repo_daily unavailable for %s: %s", normalized_code, error)
            return []

    def get_fund_performance(self, wind_code: str) -> Dict[str, Any]:
        """获取基金业绩指标"""
        if self.mock_mode:
            return self._mock_performance(wind_code)

        try:
            ts_code = _to_ts_code(wind_code)
            end_date = datetime.now().strftime("%Y%m%d")
            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            start_3y = (datetime.now() - timedelta(days=1095)).strftime("%Y%m%d")

            nav_df = self.pro.fund_nav(ts_code=ts_code, start_date=start_3y, end_date=end_date)
            if nav_df is None or nav_df.empty or len(nav_df) < 10:
                self._strict_fail(f"Tushare fund_nav returned insufficient performance rows for {wind_code}")
                return self._mock_performance(wind_code)

            nav_df = nav_df.sort_values("nav_date").copy()
            metric_nav = pd.Series(index=nav_df.index, dtype="float64")
            for column in ("accum_nav", "adj_nav", "unit_nav"):
                if column in nav_df.columns:
                    metric_nav = metric_nav.combine_first(pd.to_numeric(nav_df[column], errors="coerce"))
            nav_df["metric_nav"] = metric_nav
            nav_df = nav_df[nav_df["metric_nav"].notna() & (nav_df["metric_nav"] > 0)]
            if len(nav_df) < 10:
                self._strict_fail(f"Tushare fund_nav returned insufficient usable performance rows for {wind_code}")
                return self._mock_performance(wind_code)

            nav_1y = nav_df[nav_df["nav_date"] >= start_1y]
            if len(nav_1y) >= 2:
                nav_start = float(nav_1y.iloc[0]["metric_nav"])
                nav_end = float(nav_1y.iloc[-1]["metric_nav"])
                ret_1y = (nav_end / nav_start - 1) if nav_start > 0 else 0
            else:
                ret_1y = 0

            if len(nav_df) >= 2:
                nav_start_3y = float(nav_df.iloc[0]["metric_nav"])
                nav_end_3y = float(nav_df.iloc[-1]["metric_nav"])
                ret_3y = (nav_end_3y / nav_start_3y - 1) if nav_start_3y > 0 else 0
                years = (datetime.strptime(end_date, "%Y%m%d") - datetime.strptime(nav_df.iloc[0]["nav_date"], "%Y%m%d")).days / 365
                ret_3y_annualized = ((1 + ret_3y) ** (1 / max(years, 0.1)) - 1) if years > 0 else 0
            else:
                ret_3y_annualized = 0

            peak = nav_df["metric_nav"].cummax()
            drawdown = (nav_df["metric_nav"] - peak) / peak
            max_dd = drawdown.min()

            daily_returns = nav_df["metric_nav"].pct_change(fill_method=None).dropna()
            if len(daily_returns) > 0:
                annual_return = daily_returns.mean() * 252
                annual_vol = daily_returns.std() * (252 ** 0.5)
                sharpe = (annual_return / annual_vol) if annual_vol > 0 else 0
                volatility = annual_vol
            else:
                sharpe = 0
                volatility = 0

            performance = {
                "annualized_return_1y": round(ret_1y, 4),
                "annualized_return_3y": round(ret_3y_annualized, 4),
                "max_drawdown": round(max_dd, 4),
                "sharpe_ratio": round(sharpe, 4),
                "volatility": round(volatility, 4),
                "sortino": round(sharpe * 1.2, 4),
                "calmar_ratio": round(abs(ret_1y / max_dd), 4) if max_dd != 0 else 0,
                "win_rate_1y": round((daily_returns > 0).sum() / len(daily_returns), 4) if len(daily_returns) > 0 else 0,
            }
            performance.update(FundNavEvidenceService().derive_money_market_facts([
                {
                    "date": row.get("nav_date"),
                    "unit_nav": _as_float(row.get("unit_nav")),
                    "accum_nav": _as_float(row.get("adj_nav")) or _as_float(row.get("accum_nav")),
                    "adj_nav": _as_float(row.get("adj_nav")),
                    "reported_accum_nav": _as_float(row.get("accum_nav")),
                }
                for _, row in nav_df.iterrows()
            ]))
            return performance
        except Exception as e:
            logger.error(f"Tushare get_fund_performance error for {wind_code}: {e}")
            self._strict_fail(f"Tushare get_fund_performance failed for {wind_code}: {e}")
            return self._mock_performance(wind_code)

    def get_fund_risk_metrics(self, wind_code: str) -> Dict[str, Any]:
        """获取基金风险指标"""
        if self.mock_mode:
            return self._mock_risk_metrics(wind_code)

        try:
            ts_code = _to_ts_code(wind_code)
            end_date = datetime.now().strftime("%Y%m%d")
            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            start_2y = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

            nav_df = self.pro.fund_nav(ts_code=ts_code, start_date=start_2y, end_date=end_date)
            if nav_df is None or nav_df.empty:
                self._strict_fail(f"Tushare fund_nav returned empty risk rows for {wind_code}")
                return self._mock_risk_metrics(wind_code)

            nav_df = nav_df.sort_values("nav_date")
            nav_df["accum_nav"] = nav_df["accum_nav"].ffill()

            daily_returns = nav_df["accum_nav"].pct_change(fill_method=None).dropna()
            vol_1y = daily_returns[-252:].std() * (252 ** 0.5) if len(daily_returns) >= 252 else 0
            vol_2y = daily_returns.std() * (252 ** 0.5)

            peak = nav_df["accum_nav"].cummax()
            drawdown = (nav_df["accum_nav"] - peak) / peak
            max_dd_1y = drawdown[-252:].min() if len(drawdown) >= 252 else drawdown.min()
            max_dd_2y = drawdown.min()

            var_95 = daily_returns[-252:].quantile(0.05) if len(daily_returns) >= 252 else 0

            beta = self._calculate_beta(wind_code, start_1y, end_date)
            alpha = self._calculate_alpha(wind_code, start_1y, end_date)

            return {
                "annualized_volatility_1y": round(vol_1y, 4),
                "annualized_volatility_2y": round(vol_2y, 4),
                "max_drawdown_1y": round(max_dd_1y, 4),
                "max_drawdown_2y": round(max_dd_2y, 4),
                "var_95": round(var_95, 4),
                "beta": round(beta, 4),
                "alpha": round(alpha, 4),
                "tracking_error": round(vol_1y * 0.8, 4),
                "information_ratio": round(alpha / (vol_1y * 0.8), 4) if vol_1y > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Tushare get_fund_risk_metrics error for {wind_code}: {e}")
            self._strict_fail(f"Tushare get_fund_risk_metrics failed for {wind_code}: {e}")
            return self._mock_risk_metrics(wind_code)

    def _calculate_beta(self, wind_code: str, start_date: str, end_date: str) -> float:
        try:
            ts_code = _to_ts_code(wind_code)
            fund_nav = self.pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if fund_nav is None or fund_nav.empty:
                return 1.0

            index_nav = self.pro.index_dailybasic(ts_code="000300.SH", start_date=start_date, end_date=end_date)
            if index_nav is None or index_nav.empty:
                return 1.0

            fund_ret = fund_nav["accum_nav"].pct_change(fill_method=None).dropna()
            index_ret = index_nav["pct_change"].dropna()

            if len(fund_ret) > 5 and len(index_ret) > 5:
                cov = fund_ret.cov(index_ret)
                var = index_ret.var()
                return round(cov / var, 4) if var != 0 else 1.0
        except:
            pass
        return 1.0

    def _calculate_alpha(self, wind_code: str, start_date: str, end_date: str) -> float:
        try:
            beta = self._calculate_beta(wind_code, start_date, end_date)
            ts_code = _to_ts_code(wind_code)
            fund_nav = self.pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if fund_nav is None or fund_nav.empty or len(fund_nav) < 2:
                return 0.0

            fund_ret = (float(fund_nav.iloc[-1]["accum_nav"]) / float(fund_nav.iloc[0]["accum_nav"]) - 1)
            rf = 0.02
            market_ret = 0.05
            alpha = fund_ret - (rf + beta * (market_ret - rf))
            return round(alpha, 4)
        except:
            return 0.0

    # ==================== 持仓数据 ====================

    def get_fund_holdings(self, wind_code: str, quarter: str) -> List[Dict]:
        """获取基金持仓（按季度）"""
        if self.mock_mode:
            return self._mock_holdings(wind_code, quarter)

        try:
            ts_code = _to_ts_code(wind_code)
            year = quarter[:4]
            q = quarter[4:]
            month_map = {"Q1": "0331", "Q2": "0630", "Q3": "0930", "Q4": "1231"}
            date_str = f"{year}{month_map.get(q, '1231')}"

            df = self.pro.fund_portfolio(ts_code=ts_code, period=date_str)
            if df is None or df.empty:
                for offset in [1, 2, 3]:
                    test_date = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=offset * 7)
                    df = self.pro.fund_portfolio(ts_code=ts_code, ann_date=test_date.strftime("%Y%m%d"))
                    if df is not None and not df.empty:
                        break

            if df is not None and not df.empty and "end_date" in df.columns:
                df = df[df["end_date"].astype(str) == date_str]

            if df is None or df.empty:
                logger.warning(
                    "Tushare fund_portfolio unavailable for %s %s; returning empty holdings instead of mock data",
                    wind_code,
                    quarter,
                )
                return []

            stock_codes = [
                self._normalize_stock_code(row.get("symbol") or row.get("stock_code"))
                for _, row in df.iterrows()
            ]
            stock_profiles = self._get_stock_profiles(stock_codes)
            holdings_by_code: Dict[str, Dict[str, Any]] = {}
            for _, row in df.iterrows():
                stock_code = self._normalize_stock_code(row.get("symbol") or row.get("stock_code"))
                stock_profile = stock_profiles.get(stock_code, {})
                ratio = _as_float(row.get("stk_mkv_ratio"))
                market_value = _as_float(row.get("mkv"))

                item = {
                    "stock_code": stock_code,
                    "stock_name": row.get("name") or stock_profile.get("name") or "未知",
                    # Tushare 明确定义 stk_mkv_ratio 为“占股票市值比”，不是占基金净值比。
                    "weight": None,
                    "fund_nav_weight": None,
                    "equity_portfolio_weight": round(ratio / 100, 6) if ratio is not None else None,
                    "weight_basis": "equity_portfolio",
                    "shares": row.get("amount"),
                    "market_cap": market_value,
                    "industry": row.get("industry") or stock_profile.get("industry") or "未知",
                    "announcement_date": self._format_date_value(row.get("ann_date")),
                    "report_date": self._format_date_value(row.get("end_date")),
                    "source": "tushare.fund_portfolio",
                }
                existing = holdings_by_code.get(stock_code)
                if existing is None:
                    holdings_by_code[stock_code] = item
                else:
                    for field in ("stock_name", "industry", "announcement_date", "report_date"):
                        if existing.get(field) in {None, "", "未知"} and item.get(field) not in {None, "", "未知"}:
                            existing[field] = item[field]
                    for field in ("shares", "market_cap", "equity_portfolio_weight"):
                        if _as_float(item.get(field)) is not None and (
                            _as_float(existing.get(field)) is None
                            or float(item[field]) > float(existing[field])
                        ):
                            existing[field] = item[field]
            holdings = list(holdings_by_code.values())
            fund_net_asset, fund_net_asset_basis = self._fund_net_asset_for_period(ts_code, date_str)
            if fund_net_asset and fund_net_asset > 0:
                for item in holdings:
                    market_cap = _as_float(item.get("market_cap"))
                    if market_cap is not None and market_cap >= 0:
                        fund_nav_weight = round(market_cap / fund_net_asset, 6)
                        item["weight"] = fund_nav_weight
                        item["fund_nav_weight"] = fund_nav_weight
                        item["weight_basis"] = "fund_nav"
                        item["fund_net_asset"] = fund_net_asset
                        item["fund_net_asset_basis"] = fund_net_asset_basis
                        item["fund_net_asset_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                        item["weight_source"] = f"tushare.fund_nav.{fund_net_asset_basis}"
            holdings, validation = normalize_holding_weights(holdings)
            if validation.is_invalid:
                logger.warning(
                    "Invalid fund NAV holding weights for %s %s: %s (sum=%.6f); using equity-portfolio weights",
                    wind_code,
                    quarter,
                    validation.reason,
                    validation.total_weight,
                )
            holdings.sort(
                key=lambda item: item.get("fund_nav_weight")
                if item.get("fund_nav_weight") is not None
                else item.get("equity_portfolio_weight") or 0,
                reverse=True,
            )
            return holdings
        except Exception as e:
            logger.error(f"Tushare get_fund_holdings error for {wind_code} {quarter}: {e}")
            return []

    def _fund_net_asset_for_period(self, ts_code: str, period: str) -> tuple[Optional[float], Optional[str]]:
        """读取报告期合计资产净值；多份额基金不能使用单份额净资产作分母。"""
        try:
            frame = self.pro.fund_nav(
                ts_code=ts_code,
                nav_date=period,
                fields="ts_code,nav_date,net_asset,total_netasset",
            )
            if frame is None or frame.empty:
                return None, None
            for column in ("total_netasset", "net_asset"):
                if column not in frame.columns:
                    continue
                values = [
                    value
                    for value in (_as_float(item) for item in frame[column].tolist())
                    if value is not None and value > 0
                ]
                if values:
                    return values[0], column
            return None, None
        except Exception as exc:
            logger.warning("Tushare fund net asset unavailable for %s %s: %s", ts_code, period, exc)
            return None, None

    @staticmethod
    def _format_date_value(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text or None

    @staticmethod
    def _normalize_stock_code(value: Any) -> str:
        code = str(value or "").strip().upper()
        hong_kong = re.fullmatch(r"(\d{1,5})\.HK", code)
        if hong_kong:
            return f"{hong_kong.group(1).zfill(5)}.HK"
        if re.fullmatch(r"\d{6}", code):
            if code.startswith(("4", "8", "92")):
                return f"{code}.BJ"
            if code.startswith(("5", "6", "9")):
                return f"{code}.SH"
            return f"{code}.SZ"
        return code

    def _get_stock_profiles(self, stock_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        cache = getattr(self, "_stock_profile_cache", None)
        if cache is None:
            cache = {}
            self._stock_profile_cache = cache

        if not getattr(self, "_stock_profile_cache_loaded", False):
            try:
                frame = self.pro.stock_basic(
                    exchange="",
                    list_status="L",
                    fields="ts_code,name,industry",
                )
                if frame is not None and not frame.empty:
                    for _, row in frame.iterrows():
                        code = self._normalize_stock_code(row.get("ts_code"))
                        if code:
                            cache[code] = {
                                "name": row.get("name"),
                                "industry": row.get("industry"),
                            }
                self._stock_profile_cache_loaded = True
            except Exception as exc:
                logger.warning("Tushare stock profile cache unavailable: %s", exc)

        hong_kong_codes = {code for code in stock_codes if code.endswith(".HK")}
        hong_kong_industries: Dict[str, str] = {}
        if hong_kong_codes:
            try:
                snapshot = self.get_hang_seng_index_snapshot()
                hong_kong_industries = dict(snapshot.get("industry_map") or {})
                hong_kong_industries.update({
                    str(item.get("constituent_code")): str(item.get("industry"))
                    for item in snapshot.get("constituents") or []
                    if item.get("constituent_code") and item.get("industry")
                })
            except Exception as exc:
                logger.warning("Hang Seng industry map unavailable: %s", exc)

        for stock_code in set(stock_codes):
            if not stock_code or stock_code in cache:
                continue
            try:
                if stock_code.endswith(".HK"):
                    frame = self.pro.hk_basic(
                        ts_code=stock_code,
                        fields="ts_code,name,fullname,market,list_date",
                    )
                else:
                    frame = self.pro.stock_basic(
                        ts_code=stock_code,
                        fields="ts_code,name,industry",
                    )
                if frame is not None and not frame.empty:
                    row = frame.iloc[0]
                    cache[stock_code] = {
                        "name": row.get("name"),
                        "industry": row.get("industry") or hong_kong_industries.get(stock_code),
                    }
            except Exception:
                continue
        return {code: cache.get(code, {}) for code in stock_codes if code}

    def _get_stock_profile(self, stock_code: str) -> Dict[str, Any]:
        normalized = self._normalize_stock_code(stock_code)
        return self._get_stock_profiles([normalized]).get(normalized, {})

    def _get_stock_industry(self, stock_code: str) -> str:
        try:
            df = self.pro.stock_basic(ts_code=stock_code)
            if df is not None and not df.empty:
                return df.iloc[0].get("industry", "未知")
        except:
            pass
        return "未知"

    # ==================== 基金经理数据 ====================

    def get_manager_identity_candidates(self, manager_name: str) -> List[Dict[str, Any]]:
        """按精确姓名返回可审计的基金经理身份候选，不用模糊匹配。"""
        if self.mock_mode:
            return []

        name = str(manager_name or "").strip()
        if not name:
            return []
        try:
            df = self.pro.fund_manager(
                name=name,
                fields="ts_code,name,gender,edu,birth_year,begin_date,end_date,fund_name",
            )
            if df is None or df.empty:
                return []

            exact_rows = [
                row.to_dict()
                for _, row in df.iterrows()
                if str(row.get("name") or "").strip() == name
            ]
            if not exact_rows:
                return []

            known_genders = {
                str(row.get("gender") or "").strip()
                for row in exact_rows
                if str(row.get("gender") or "").strip()
            }
            known_education = {
                str(row.get("edu") or "").strip()
                for row in exact_rows
                if str(row.get("edu") or "").strip()
            }
            shared_gender = next(iter(known_genders)) if len(known_genders) == 1 else ""
            shared_education = next(iter(known_education)) if len(known_education) == 1 else ""
            grouped: Dict[str, Dict[str, Any]] = {}
            for row in exact_rows:
                gender = str(row.get("gender") or shared_gender).strip()
                education = str(row.get("edu") or shared_education).strip()
                manager_id = f"{name}|{gender}|{education}"
                candidate = grouped.setdefault(manager_id, {
                    "manager_id": manager_id,
                    "name": name,
                    "gender": gender,
                    "education": education,
                    "birth_year": row.get("birth_year"),
                    "current_funds": [],
                    "tenures": [],
                    "source": "tushare.fund_manager",
                })
                fund_code = _to_wind_code(str(row.get("ts_code") or "").strip())
                begin_date = _format_tushare_date(row.get("begin_date"))
                end_date = _format_tushare_date(row.get("end_date"))
                if not fund_code or not begin_date:
                    continue
                tenure = {
                    "fund_code": fund_code,
                    "fund_name": row.get("fund_name") or fund_code,
                    "start_date": begin_date,
                    "end_date": end_date,
                    "is_current": end_date is None,
                }
                candidate["tenures"].append(tenure)
                if tenure["is_current"]:
                    candidate["current_funds"].append(fund_code)

            for candidate in grouped.values():
                candidate["current_funds"] = list(dict.fromkeys(candidate["current_funds"]))
                candidate["tenures"] = sorted(
                    candidate["tenures"],
                    key=lambda item: (not item["is_current"], item["start_date"], item["fund_code"]),
                )
            return sorted(grouped.values(), key=lambda item: item["manager_id"])
        except Exception as exc:
            logger.error("Tushare manager identity lookup failed for %s: %s", name, exc)
            return []

    def get_fund_managers(self, wind_code: str) -> List[Dict[str, Any]]:
        """按基金代码获取基金经理任职关系。"""
        if self.mock_mode:
            return []

        try:
            ts_code = _to_ts_code(wind_code)
            df = self.pro.fund_manager(
                ts_code=ts_code,
                fields="ts_code,name,gender,edu,birth_year,begin_date,end_date,fund_name",
            )
            if df is None or df.empty:
                return []

            managers = []
            for _, row in df.iterrows():
                row_data = row.to_dict()
                name = str(row_data.get("name") or "").strip()
                if not name:
                    continue
                gender = str(row_data.get("gender") or "").strip()
                education = str(row_data.get("edu") or "").strip()
                begin_date = _format_tushare_date(row_data.get("begin_date"))
                end_date = _format_tushare_date(row_data.get("end_date"))
                manager_id = f"{name}|{gender}|{education}"
                managers.append({
                    "manager_id": manager_id,
                    "name": name,
                    "gender": gender,
                    "education": education,
                    "birth_year": row_data.get("birth_year"),
                    "fund_name": row_data.get("fund_name") or ts_code,
                    "begin_date": begin_date,
                    "end_date": end_date,
                    "is_current_manager": end_date is None,
                    "raw_data": row_data,
                })
            return managers
        except Exception as e:
            logger.error(f"Tushare get_fund_managers error for {wind_code}: {e}")
            return []

    def get_manager_tenures(self, manager_id: str) -> List[Dict[str, Any]]:
        """按规范经理 ID 获取完整现任与历史产品任职记录。"""
        if self.mock_mode:
            return []

        name, expected_gender, expected_education = (str(manager_id or "").split("|") + ["", ""])[0:3]
        if not name.strip():
            return []
        try:
            df = self.pro.fund_manager(
                name=name.strip(),
                fields="ts_code,name,gender,edu,birth_year,begin_date,end_date,fund_name",
            )
            if df is None or df.empty:
                return []

            rows = []
            for _, row in df.iterrows():
                row_data = row.to_dict()
                row_name = str(row_data.get("name") or "").strip()
                gender = str(row_data.get("gender") or "").strip()
                education = str(row_data.get("edu") or "").strip()
                if row_name != name.strip():
                    continue
                if expected_gender and gender and gender != expected_gender:
                    continue
                if expected_education and education and education != expected_education:
                    continue
                fund_code = _to_wind_code(str(row_data.get("ts_code") or "").strip())
                begin_date = _format_tushare_date(row_data.get("begin_date"))
                end_date = _format_tushare_date(row_data.get("end_date"))
                if not fund_code or not begin_date:
                    continue
                rows.append({
                    "manager_id": f"{row_name}|{gender}|{education}",
                    "fund_code": fund_code,
                    "fund_name": row_data.get("fund_name") or fund_code,
                    "start_date": begin_date,
                    "end_date": end_date,
                    "is_current": end_date is None,
                    "source": "tushare.fund_manager",
                    "raw_data": row_data,
                })
            return sorted(rows, key=lambda item: (not item["is_current"], item["start_date"], item["fund_code"]))
        except Exception as e:
            logger.error(f"Tushare get_manager_tenures error for {manager_id}: {e}")
            return []

    def _local_manager_profile(self, manager_id: str) -> Optional[Dict[str, Any]]:
        """本地 managers/manager_fund_tenures 表优先：避免 Tushare fund_manager
        错行（曾把邹立虎查成王亚伟）与慢查询；company 取真实管理人而非托管行。"""
        try:
            from backend.database import get_engine
        except ImportError:
            from database import get_engine
        from sqlalchemy import text

        parts = str(manager_id or "").split("|")
        name = parts[0] if parts else str(manager_id or "")
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT wind_code, name, company, education, work_years, management_years "
                    "FROM managers WHERE wind_code = :mid OR name = :name LIMIT 1"
                ),
                {"mid": str(manager_id or ""), "name": name},
            ).fetchone()
            if not row:
                return None
            wind_code = str(row[0] or manager_id)
            tenure_rows = conn.execute(
                text(
                    "SELECT fund_code, fund_name, start_date, end_date "
                    "FROM manager_fund_tenures WHERE manager_id = :mid ORDER BY start_date"
                ),
                {"mid": wind_code},
            ).fetchall()
        fund_history = [
            {
                "wind_code": str(t[0]),
                "fund_name": str(t[1] or t[0]),
                "start_date": str(t[2] or ""),
                "end_date": str(t[3] or "") if t[3] else "",
            }
            for t in tenure_rows
        ]
        begin_date = min((f["start_date"] for f in fund_history if f["start_date"]), default="")
        tenure_years = 0
        if begin_date and len(begin_date) >= 4:
            try:
                tenure_years = datetime.now().year - int(begin_date[:4])
            except (ValueError, TypeError):
                tenure_years = 0
        return {
            "manager_id": manager_id,
            "name": str(row[1] or name),
            "gender": parts[1] if len(parts) >= 2 else "",
            "education": str(row[3] or (parts[2] if len(parts) >= 3 else "")),
            "company": str(row[2] or ""),
            "tenure_years": int(row[5] or tenure_years or 0),
            "begin_date": begin_date,
            "birth_year": None,
            "fund_count": len(fund_history),
            "current_funds": [f["wind_code"] for f in fund_history if not f["end_date"]],
            "fund_history": fund_history,
        }

    def get_manager_info(self, manager_id: str) -> Dict[str, Any]:
        """获取基金经理个人信息（本地库优先，避免 Tushare 实时查询错行）"""
        if self.mock_mode:
            return self._mock_manager_info(manager_id)

        local = self._local_manager_profile(manager_id)
        if local:
            return local

        try:
            # manager_id 格式: "name|gender|edu"
            # 解析出 name 后，使用 fund_manager API 直接查询该经理管理的所有基金
            parts = manager_id.split("|")
            name = parts[0] if parts else manager_id

            # 使用 manager_id 直接查询（如果有的话）或 name 查询
            if len(parts) >= 3:
                # 格式正确，尝试直接用 manager_id 查询
                df = self.pro.fund_manager(manager_id=manager_id)
                if df is not None and not df.empty:
                    return self._parse_manager_info(manager_id, df)
                # manager_id 查询失败，回退到 name 查询
                df = self.pro.fund_manager(name=name)
                if df is not None and not df.empty:
                    return self._parse_manager_info(manager_id, df)

            # 降级：尝试纯 name 查询
            df = self.pro.fund_manager(name=name)
            if df is not None and not df.empty:
                return self._parse_manager_info(manager_id, df)

            # 尝试在缓存中查找（缓存已存在时）
            now = time.time()
            if self._manager_cache is not None and (now - self._manager_cache_time) <= self._manager_cache_ttl:
                for m in self._manager_cache.get("managers", []):
                    if m.get("manager_id") == manager_id:
                        funds = m.get("funds", [])
                        active_funds = [f for f in funds if not f.get("end_date")]
                        return {
                            "manager_id": manager_id,
                            "name": m.get("name", ""),
                            "gender": m.get("gender", ""),
                            "education": m.get("edu", ""),
                            "company": m.get("company", ""),
                            "tenure_years": m.get("tenure_years", 0),
                            "begin_date": m.get("begin_date", ""),
                            "birth_year": m.get("birth_year"),
                            "fund_count": m.get("fund_count", 0),
                            "current_funds": [f.get("wind_code") for f in active_funds],
                            "fund_history": funds,
                        }

            return self._mock_manager_info(manager_id)
        except Exception as e:
            logger.error(f"Tushare get_manager_info error for {manager_id}: {e}")
            return self._mock_manager_info(manager_id)

    def _parse_manager_info(self, manager_id: str, df) -> Dict[str, Any]:
        """从 fund_manager DataFrame 解析经理信息"""
        if df is None or df.empty:
            return self._mock_manager_info(manager_id)

        fund_history = []
        for _, row in df.iterrows():
            ts_code = row.get("ts_code", "")
            if ts_code:
                wind_code = _to_wind_code(ts_code)
                fund_history.append({
                    "wind_code": wind_code,
                    "fund_name": row.get("fund_name", ts_code),
                    "start_date": row.get("start_date", ""),
                    "end_date": row.get("end_date", ""),
                })

        # 计算从业年限
        begin = df.iloc[0].get("begin_date", "") if len(df) > 0 else ""
        tenure_years = 0
        if begin and len(str(begin)) == 8:
            try:
                start_year = int(str(begin)[:4])
                tenure_years = datetime.now().year - start_year
            except:
                tenure_years = 5
        else:
            tenure_years = 5

        # 尝试获取公司信息
        company = ""
        try:
            first_fund = df.iloc[0].get("ts_code", "")
            if first_fund:
                basic_df = self.pro.fund_basic(ts_code=first_fund, fields="custodian")
                if basic_df is not None and not basic_df.empty:
                    company = basic_df.iloc[0].get("custodian", "")
        except Exception:
            pass

        return {
            "manager_id": manager_id,
            "name": df.iloc[0].get("name", manager_id.split("|")[0] if "|" in manager_id else manager_id),
            "gender": df.iloc[0].get("gender", ""),
            "education": df.iloc[0].get("edu", ""),
            "company": company,
            "tenure_years": tenure_years,
            "begin_date": begin,
            "birth_year": df.iloc[0].get("birth_year"),
            "fund_count": len(fund_history),
            "current_funds": [f["wind_code"] for f in fund_history if not f.get("end_date")],
            "fund_history": fund_history,
        }

    def get_manager_funds(self, manager_id: str) -> List[Dict]:
        """获取经理管理的基金列表（本地任期表优先）"""
        if self.mock_mode:
            return self._mock_manager_funds(manager_id)

        local = self._local_manager_profile(manager_id)
        if local:
            funds = []
            for item in local.get("fund_history") or []:
                funds.append({
                    "wind_code": item["wind_code"],
                    "name": item["fund_name"],
                    "type": "",
                    "since": item["start_date"],
                    "to_date": item["end_date"],
                })
            return funds

        try:
            df = self.pro.fund_manager(manager_id=manager_id)
            if df is None or df.empty:
                return self._mock_manager_funds(manager_id)

            funds = []
            for _, row in df.iterrows():
                ts_code = row.get("ts_code", "")
                if ts_code:
                    wind_code = _to_wind_code(ts_code)
                    funds.append({
                        "wind_code": wind_code,
                        "name": row.get("fund_name", ts_code),
                        "type": self._normalize_fund_type(row.get("fund_type"), row.get("invest_type"), row.get("fund_name"), ts_code),
                        "since": row.get("start_date", ""),
                        "to_date": row.get("end_date", ""),
                    })
            return funds
        except Exception as e:
            logger.error(f"Tushare get_manager_funds error for {manager_id}: {e}")
            return self._mock_manager_funds(manager_id)

    def get_manager_list(self, page: int = 1, page_size: int = 50, keyword: str = None, company: str = None) -> Dict[str, Any]:
        """
        获取基金经理列表 - 直接从 fund_manager 批量查询（避免逐基金查询的慢速缓存刷新）
        """
        if self.mock_mode:
            return self._mock_manager_list(page, page_size, keyword, company)

        try:
            # 优先使用已有缓存（如果有且未过期）
            now = time.time()
            use_cache = self._manager_cache is not None and (now - self._manager_cache_time) <= self._manager_cache_ttl

            if use_cache:
                managers = self._manager_cache.get("managers", [])
            else:
                # 快速构建缓存：直接查询 fund_manager（不分 fund，避免 30k+ 次 API 调用）
                managers = self._build_manager_cache_fast()
                if managers:
                    self._manager_cache = {"managers": managers}
                    self._manager_cache_time = now

            total = len(managers)

            # 过滤
            filtered = managers
            if keyword:
                kw = keyword.lower()
                filtered = [m for m in filtered if kw in m.get("name", "").lower() or kw in m.get("company", "").lower()]
            if company:
                filtered = [m for m in filtered if company in m.get("company", "")]

            filtered_total = len(filtered)
            start = (page - 1) * page_size
            return {
                "total": filtered_total,
                "page": page,
                "page_size": page_size,
                "managers": filtered[start:start + page_size],
            }
        except Exception as e:
            logger.error(f"Tushare get_manager_list error: {e}")
            return self._mock_manager_list(page, page_size, keyword, company)

    def _build_manager_cache_fast(self) -> List[Dict]:
        """
        快速构建经理缓存：直接查询 fund_manager 全部数据，按 name 去重
        避免逐基金查询（30k+ API 调用 -> 1 次批量查询）
        """
        try:
            # 分批获取所有基金-经理关系
            all_funds_by_manager: Dict[str, Dict] = {}
            offset = 0
            limit = 5000

            while True:
                try:
                    df = self.pro.fund_manager(
                        fields="ts_code,name,gender,edu,birth_year,begin_date,end_date,fund_name",
                        offset=offset,
                        limit=limit
                    )
                    if df is None or df.empty:
                        break

                    for _, row in df.iterrows():
                        name = row.get("name", "")
                        if not name:
                            continue
                        key = f"{name}|{row.get('gender', '')}|{row.get('edu', '')}"
                        ts_code = row.get("ts_code", "")

                        if key not in all_funds_by_manager:
                            all_funds_by_manager[key] = {
                                "manager_id": key,
                                "name": name,
                                "gender": row.get("gender", ""),
                                "edu": row.get("edu", ""),
                                "birth_year": row.get("birth_year"),
                                "begin_date": row.get("begin_date"),
                                "funds": [],
                                "fund_count": 0,
                                "_company": "",
                            }
                        elif row.get("begin_date") and (
                            not all_funds_by_manager[key].get("begin_date")
                            or str(row.get("begin_date")) < str(all_funds_by_manager[key].get("begin_date"))
                        ):
                            all_funds_by_manager[key]["begin_date"] = row.get("begin_date")

                        # 追加基金
                        all_funds_by_manager[key]["funds"].append({
                            "wind_code": _to_wind_code(ts_code),
                            "fund_name": row.get("fund_name", ts_code),
                            "start_date": row.get("begin_date", ""),
                            "end_date": row.get("end_date", ""),
                        })

                    if len(df) < limit:
                        break
                    offset += limit
                    time.sleep(0.05)  # 避免频率限制

                except Exception as e:
                    logger.warning(f"fund_manager batch error at offset {offset}: {e}")
                    break

            # 补充公司信息（只查活跃基金的公司）
            fund_codes_to_check = set()
            for m in all_funds_by_manager.values():
                active = [f for f in m["funds"] if not f.get("end_date")]
                if active:
                    fund_codes_to_check.add(active[0]["wind_code"])

            # 批量查询公司信息
            if fund_codes_to_check:
                try:
                    codes_list = list(fund_codes_to_check)
                    for i in range(0, len(codes_list), 100):
                        batch = codes_list[i:i+100]
                        batch_str = ",".join([_to_ts_code(c) for c in batch])
                        basic_df = self.pro.fund_basic(
                            ts_code=batch_str,
                            fields="ts_code,management"
                        )
                        if basic_df is not None and not basic_df.empty:
                            for _, row in basic_df.iterrows():
                                ts = row.get("ts_code", "")
                                wind = _to_wind_code(ts)
                                comp = row.get("management", "")
                                for m in all_funds_by_manager.values():
                                    for f in m["funds"]:
                                        if f["wind_code"] == wind:
                                            f["company"] = comp
                        time.sleep(0.05)
                except Exception as e:
                    logger.warning(f"fund_basic batch error: {e}")

            # 计算从业年限并整理输出
            now = datetime.now()
            result = []
            for m in all_funds_by_manager.values():
                begin = m.get("begin_date", "")
                if begin and len(str(begin)) == 8:
                    try:
                        start_year = int(str(begin)[:4])
                        m["tenure_years"] = now.year - start_year
                    except:
                        m["tenure_years"] = 5
                else:
                    m["tenure_years"] = 5

                m["fund_count"] = len(m["funds"])
                m["company"] = next(
                    (
                        str(fund.get("company") or "").strip()
                        for fund in m["funds"]
                        if not fund.get("end_date") and str(fund.get("company") or "").strip()
                    ),
                    next(
                        (
                            str(fund.get("company") or "").strip()
                            for fund in m["funds"]
                            if str(fund.get("company") or "").strip()
                        ),
                        "",
                    ),
                )
                m.pop("_company", None)
                result.append(m)

            logger.info(f"Fast manager cache built: {len(result)} managers")
            return result

        except Exception as e:
            logger.error(f"Build fast manager cache error: {e}")
            return []

    def _refresh_manager_cache(self) -> None:
        """刷新基金经理缓存（兼容旧方法，使用快速版本）"""
        managers = self._build_manager_cache_fast()
        self._manager_cache = {"managers": managers}
        self._manager_cache_time = time.time()
        if managers:
            logger.info(f"Manager cache refreshed: {len(managers)} managers")
        else:
            logger.warning("Manager cache refresh returned empty")

    def _mock_manager_list(self, page: int, page_size: int, keyword: str = None, company: str = None) -> Dict[str, Any]:
        """Mock基金经理列表"""
        mock_managers = [
            {"manager_id": "mock_001", "name": "张明", "gender": "M", "edu": "硕士", "company": "华夏基金管理有限公司", "tenure_years": 8, "fund_count": 3},
            {"manager_id": "mock_002", "name": "李华", "gender": "F", "edu": "博士", "company": "易方达基金管理有限公司", "tenure_years": 6, "fund_count": 2},
            {"manager_id": "mock_003", "name": "王强", "gender": "M", "edu": "硕士", "company": "广发基金管理有限公司", "tenure_years": 10, "fund_count": 4},
            {"manager_id": "mock_004", "name": "赵雪", "gender": "F", "edu": "硕士", "company": "南方基金管理有限公司", "tenure_years": 5, "fund_count": 2},
        ]
        total = len(mock_managers)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "managers": mock_managers[start:start + page_size],
        }

    # ==================== 风格分析 ====================

    def get_fund_style(self, wind_code: str) -> Dict[str, Any]:
        """获取基金风格分析"""
        if self.mock_mode:
            return self._mock_style()

        try:
            holdings = self.get_fund_holdings(wind_code, self._get_current_quarter())
            if not holdings:
                return {
                    "data_status": "unavailable",
                    "source": "tushare.fund_portfolio",
                    "style_factors_status": "unavailable",
                    "reason": "未取得可信持仓，不能计算或推断 Barra 风格因子。",
                }

            total_weight = sum(h.get("weight") or 0 for h in holdings)
            if total_weight <= 0:
                return {
                    "data_status": "unavailable",
                    "source": "tushare.fund_portfolio",
                    "style_factors_status": "unavailable",
                    "reason": "持仓权重缺失，不能计算或推断 Barra 风格因子。",
                }

            industry_weights = {}
            for h in holdings:
                ind = h.get("industry", "未知")
                w = h.get("weight", 0) / total_weight if total_weight > 0 else 0
                industry_weights[ind] = industry_weights.get(ind, 0) + w

            return {
                "data_status": "holdings_derived_industry_only",
                "source": "tushare.fund_portfolio",
                "style_factors_status": "unavailable",
                "holdings_count": len(holdings),
                "total_weight": round(total_weight, 6),
                "industry_weights": dict(sorted(industry_weights.items(), key=lambda item: item[1], reverse=True)),
                "note": "仅提供持仓派生行业暴露；未接入 Barra 因子库，不能输出 SIZE/BETA/MOMENTUM 等风格因子。",
            }
        except Exception as e:
            logger.error(f"Tushare get_fund_style error for {wind_code}: {e}")
            return {
                "data_status": "unavailable",
                "source": "tushare.fund_portfolio",
                "style_factors_status": "unavailable",
                "reason": f"风格暴露读取失败：{e}",
            }

    def get_all_funds(self) -> List[Dict[str, Any]]:
        """获取所有基金基础信息（用于导出/批量处理）"""
        if self.mock_mode:
            result = self._mock_fund_list(None, 1, 100)
            return [{"wind_code": code} for code in result["list"]]

        try:
            all_funds = []
            # 遍历所有状态，获取完整基金列表
            for status in ['L', 'D']:  # L=存续/上市，D=摘牌/终止
                offset = 0
                limit = 1000
                while True:
                    df = self.pro.fund_basic(
                        status=status,
                        fields=(
                            "ts_code,name,management,custodian,found_date,state,status,"
                            "fund_type,invest_type,type,purc_startdate,redm_startdate,m_fee,c_fee,benchmark"
                        ),
                        offset=offset,
                        limit=limit
                    )
                    if df is None or df.empty:
                        break
                    for _, row in df.iterrows():
                        ts_code = row.get("ts_code", "")
                        all_funds.append({
                            "wind_code": _to_wind_code(ts_code),
                            "name": row.get("name", ""),
                            "type": self._normalize_fund_type(
                                row.get("fund_type"),
                                row.get("invest_type"),
                                row.get("name"),
                                ts_code,
                            ),
                            "fund_type_raw": row.get("fund_type", ""),
                            "invest_type": row.get("invest_type", ""),
                            "contract_type": row.get("type", ""),
                            "status": row.get("status", ""),
                            "manager": row.get("management", ""),
                            "company": row.get("management", ""),
                            "custodian": row.get("custodian", ""),
                            "establishment_date": _format_tushare_date(row.get("found_date")) or str(row.get("found_date", "")),
                            "purchase_start_date": _format_tushare_date(row.get("purc_startdate")),
                            "redeem_start_date": _format_tushare_date(row.get("redm_startdate")),
                            "management_fee": row.get("m_fee"),
                            "custodian_fee": row.get("c_fee"),
                            "benchmark": row.get("benchmark", ""),
                            "state": row.get("state", ""),
                        })
                    if len(df) < limit:
                        break
                    offset += limit
                    time.sleep(0.05)  # 避免频率限制
            logger.info(f"get_all_funds returned {len(all_funds)} funds")
            return all_funds
        except Exception as e:
            logger.error(f"Tushare get_all_funds error: {e}")
            result = self._mock_fund_list(None, 1, 100)
            return [{"wind_code": code} for code in result["list"]]

    # ==================== 工具方法 ====================

    def _normalize_fund_type(
        self,
        fund_type: Any = "",
        invest_type: Any = "",
        name: Any = "",
        ts_code: Any = "",
    ) -> str:
        """统一基金类型口径，优先使用 Tushare fund_type/invest_type。"""
        text = " ".join(str(item or "") for item in (fund_type, invest_type, name, ts_code)).upper()
        alias_map = {
            "STOCK": "股票型",
            "HYBRID": "混合型",
            "BOND": "债券型",
            "INDEX": "指数型",
            "MONEY": "货币型",
            "QDII": "QDII",
        }
        normalized_key = str(fund_type or "").strip().upper()
        if normalized_key in alias_map:
            return alias_map[normalized_key]
        if "QDII" in text:
            return "QDII"
        if "货币" in text:
            return "货币型"
        if "指数" in text or "ETF" in text:
            return "指数型"
        if "债" in text:
            return "债券型"
        if "股票" in text:
            return "股票型"
        if "混合" in text:
            return "混合型"
        return str(fund_type or "").strip() or "未分类"

    def _infer_fund_type(self, ts_code: str) -> str:
        """兼容旧调用；真实模式应使用 fund_basic 返回的 fund_type/invest_type。"""
        return self._normalize_fund_type(ts_code=ts_code)

    def _get_current_quarter(self) -> str:
        """获取当前季度"""
        now = datetime.now()
        q = (now.month - 1) // 3 + 1
        return f"{now.year}Q{q}"

    def _normalize_nav_series(self, series: List[Dict]) -> List[Dict]:
        """按日期去重并保留首次出现的数据，避免图表出现重复时间点。"""
        seen = set()
        normalized = []
        for item in series:
            date = item.get("date")
            if not date or date in seen:
                continue
            seen.add(date)
            normalized.append(item)
        return normalized

    # ==================== Mock 数据生成 ====================

    def _mock_fund_info(self, wind_code: str) -> Dict[str, Any]:
        return {
            "wind_code": wind_code,
            "name": f"基金{wind_code.split('.')[0]}",
            "full_name": f"某某灵活配置混合型证券投资基金",
            "type": "混合型",
            "manager": "基金经理",
            "management_company": "某某基金管理有限公司",
            "establishment_date": "2019-01-15",
            "total_asset": 1500000000.0,
        }

    def _mock_fund_list(self, fund_type: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
        # 扩展的 Mock 基金列表，模拟真实市场分布
        known_funds = [
            # 头部明星基金
            "000001.OF", "000002.OF", "000003.OF", "000004.OF", "000005.OF",
            "000006.OF", "000007.OF", "000008.OF", "000009.OF", "000010.OF",
            "110011.OF", "110022.OF", "161725.OF", "163402.OF", "163406.OF",
            "240002.OF", "260101.OF", "270008.OF", "320013.OF", "340006.OF",
            "420001.OF", "460005.OF", "519697.OF", "540006.OF", "590008.OF",
            "000071.OF", "000961.OF", "001717.OF", "002407.OF", "003096.OF",
            "005827.OF", "006328.OF", "007994.OF", "008086.OF", "008303.OF",
            "009714.OF", "010326.OF", "011612.OF", "012363.OF", "013203.OF",
            "110015.OF", "161810.OF", "260108.OF", "270041.OF", "320007.OF",
            "519066.OF", "590005.OF", "040004.OF", "050025.OF", "100056.OF",
            # ETF (增强覆盖)
            "510050.SH", "510300.SH", "510500.SH", "159919.SZ", "159915.SZ",
            "510100.SH", "159901.SZ", "159902.SZ", "159903.SZ", "159905.SZ",
            "510010.SH", "510020.SH", "510030.SH", "510050.SH", "510060.SH",
            "510070.SH", "510080.SH", "510090.SH", "510100.SH", "510110.SH",
            "510120.SH", "510130.SH", "510150.SH", "510160.SH", "510170.SH",
            "510180.SH", "510190.SH", "510200.SH", "510210.SH", "510220.SH",
            "510230.SH", "510300.SH", "510310.SH", "510330.SH", "510350.SH",
            "510360.SH", "510370.SH", "510380.SH", "510390.SH", "510400.SH",
            "510410.SH", "510420.SH", "510430.SH", "510440.SH", "510450.SH",
            "510460.SH", "510470.SH", "510480.SH", "510490.SH", "510500.SH",
            # 更多标准基金
            "000015.OF", "000022.OF", "000031.OF", "000041.OF", "000051.OF",
            "000061.OF", "000071.OF", "000081.OF", "000091.OF", "000101.OF",
            "000111.OF", "000121.OF", "000131.OF", "000141.OF", "000151.OF",
            "000161.OF", "000171.OF", "000181.OF", "000191.OF", "000201.OF",
            "000211.OF", "000221.OF", "000231.OF", "000241.OF", "000251.OF",
            "000261.OF", "000271.OF", "000281.OF", "000291.OF", "000301.OF",
            "000311.OF", "000321.OF", "000331.OF", "000341.OF", "000351.OF",
            "000361.OF", "000371.OF", "000381.OF", "000391.OF", "000401.OF",
            "000411.OF", "000421.OF", "000431.OF", "000441.OF", "000451.OF",
            "000461.OF", "000471.OF", "000481.OF", "000491.OF", "000501.OF",
            "000511.OF", "000521.OF", "000531.OF", "000541.OF", "000551.OF",
            "000561.OF", "000571.OF", "000581.OF", "000591.OF", "000601.OF",
            "000611.OF", "000621.OF", "000631.OF", "000641.OF", "000651.OF",
            "000661.OF", "000671.OF", "000681.OF", "000691.OF", "000701.OF",
            "000711.OF", "000721.OF", "000731.OF", "000741.OF", "000751.OF",
            "000761.OF", "000771.OF", "000781.OF", "000791.OF", "000801.OF",
            "000811.OF", "000821.OF", "000831.OF", "000841.OF", "000851.OF",
            "000861.OF", "000871.OF", "000881.OF", "000891.OF", "000901.OF",
            "000911.OF", "000921.OF", "000931.OF", "000941.OF", "000951.OF",
            "000961.OF", "000971.OF", "000981.OF", "000991.OF", "001001.OF",
        ]
        # 扩展到 500 只
        for i in range(100, 600):
            known_funds.append(f"{i:06d}.OF")
        total = len(known_funds)
        start = (page - 1) * page_size
        return {
            "total": total, "list": known_funds[start:start + page_size],
            "page": page, "page_size": page_size,
        }

    def _mock_nav_series(self, wind_code: str, start_date: str, end_date: str) -> List[Dict]:
        result = []
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        nav = 1.0
        while start <= end:
            h = int(hashlib.md5(f"{wind_code}{start.date()}".encode()).hexdigest()[:8], 16)
            nav *= (1 + (h % 100 - 50) / 10000)
            result.append({"date": start.strftime("%Y-%m-%d"), "nav": round(nav, 4)})
            start += timedelta(days=1)
        return result

    def _mock_manager_info(self, manager_id: str) -> Dict[str, Any]:
        return {
            "manager_id": manager_id,
            "name": f"基金经理{manager_id[-4:]}" if len(manager_id) > 4 else manager_id,
            "gender": "男", "education": "硕士",
            "company": "某某基金管理有限公司",
            "experience_years": 8, "management_years": 5.5,
            "background": "曾任研究员、高级研究员、基金经理助理",
        }

    def _mock_manager_funds(self, manager_id: str) -> List[Dict]:
        return [
            {"wind_code": "000001.OF", "name": "某某灵活配置混合A", "type": "混合型", "since": "2020-01-01"},
            {"wind_code": "000002.OF", "name": "某某价值精选混合", "type": "混合型", "since": "2022-03-15"},
        ]

    def _mock_performance(self, wind_code: str) -> Dict[str, Any]:
        h = lambda s: int(hashlib.md5(f"{wind_code}{s}".encode()).hexdigest()[:8], 16) % 500
        return {
            "annualized_return_1y": round((h("1y") % 400 - 100) / 100, 4),
            "annualized_return_3y": round((h("3y") % 500 - 150) / 100, 4),
            "max_drawdown": round((h("md") % 300 - 50) / 1000, 4),
            "sharpe_ratio": round((h("sh") % 200 - 50) / 100, 4),
            "volatility": round((h("vol") % 250 + 50) / 1000, 4),
            "sortino": round((h("so") % 250 - 50) / 100, 4),
            "calmar_ratio": round(h("cal") % 150 / 100, 4),
            "win_rate_1y": round((h("wr") % 40 + 50) / 100, 4),
        }

    def _mock_risk_metrics(self, wind_code: str) -> Dict[str, Any]:
        h = lambda s: int(hashlib.md5(f"{wind_code}{s}".encode()).hexdigest()[:8], 16) % 500
        return {
            "annualized_volatility_1y": round((h("v1") % 200 + 100) / 1000, 4),
            "annualized_volatility_2y": round((h("v2") % 200 + 100) / 1000, 4),
            "max_drawdown_1y": round((h("d1") % 300 - 50) / 1000, 4),
            "max_drawdown_2y": round((h("d2") % 350 - 50) / 1000, 4),
            "var_95": round(h("var") % 150 / 1000, 4),
            "beta": round((h("bt") % 120 - 10) / 100, 4),
            "alpha": round((h("al") % 200 - 80) / 100, 4),
            "tracking_error": round((h("te") % 150 + 20) / 1000, 4),
            "information_ratio": round((h("ir") % 200 - 60) / 100, 4),
        }

    def _mock_holdings(self, wind_code: str, quarter: str) -> List[Dict]:
        stocks = [
            ("600519.SH", "贵州茅台", "食品饮料"),
            ("000858.SZ", "五粮液", "食品饮料"),
            ("300750.SZ", "宁德时代", "电力设备"),
            ("601318.SH", "中国平安", "非银金融"),
            ("600036.SH", "招商银行", "银行"),
            ("002594.SZ", "比亚迪", "汽车"),
            ("600900.SH", "长江电力", "公用事业"),
            ("300059.SZ", "东方财富", "非银金融"),
            ("002415.SZ", "海康威视", "电子"),
            ("601012.SH", "隆基绿能", "电力设备"),
        ]
        h = lambda s: int(hashlib.md5(f"{wind_code}{quarter}{s}".encode()).hexdigest()[:8], 16) % 500
        return [
            {"stock_code": code, "stock_name": name, "industry": ind,
             "weight": round((h(code) + 100) / 10000, 4)}
            for code, name, ind in stocks[:5 + (h("q") % 5)]
        ]

    def _mock_style(self) -> Dict[str, float]:
        return {
            "SIZE": 0.2, "SIZENL": -0.1, "BETA": 0.8, "MOMENTUM": 0.3,
            "RESVOL": -0.2, "SRSIZE": 0.1, "LIQUIDITY": 0.4,
            "BHADGE": -0.3, "LEVERAGE": -0.1, "STORIE": 0.5,
        }
