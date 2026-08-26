"""Tushare loader for A-share daily and intraday bars plus optional fundamentals.

Supports ``interval``: 1D (default) / 1m / 5m / 15m / 30m / 1H.
Minute data uses ``pro.stk_mins()`` (Tushare points >= 2000).
"""

import logging
import time
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders._symbol_utils import _is_etf_listed
from backtest.loaders.base import loader_cache_get, loader_cache_put, validate_date_range
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)


TUSHARE_TOKEN_PLACEHOLDERS = {"", "your-tushare-token"}


def _is_index(code: str) -> bool:
    """Detect A-share index symbols (000xxx.SH, 000300.SH, 399xxx.SZ)."""
    upper = code.upper()
    if upper.endswith(".SH"):
        digits = upper.split(".")[0]
        return len(digits) == 6 and digits.isdigit() and digits.startswith("000")
    if upper.endswith(".SZ"):
        digits = upper.split(".")[0]
        return len(digits) == 6 and digits.isdigit() and digits.startswith("399")
    return False


def _is_hk_equity(code: str) -> bool:
    """Detect Hong Kong equity symbols (e.g. 00700.HK)."""
    return code.upper().endswith(".HK")


def _is_us_equity(code: str) -> bool:
    """Detect US equity symbols (e.g. AAPL.US)."""
    return code.upper().endswith(".US")


def _to_tushare_us_code(code: str) -> str:
    """Convert the project symbol ``AAPL.US`` to Tushare's ``AAPL``."""
    upper = code.strip().upper()
    return upper[:-3] if upper.endswith(".US") else upper


def _to_tushare_hk_code(code: str) -> str:
    """Normalize ``700.HK`` to the five-digit Tushare form ``00700.HK``."""
    upper = code.strip().upper()
    if not upper.endswith(".HK"):
        return upper
    digits = upper[:-3]
    return f"{digits.zfill(5)}.HK" if digits.isdigit() else upper


def _is_crypto(code: str) -> bool:
    """Detect crypto symbols (e.g. BTC-USDT, ETH/USDT)."""
    upper = code.upper()
    return upper.endswith("-USDT") or upper.endswith("/USDT")


def _daily_endpoint_code(code: str) -> tuple[str, str] | None:
    """Return the daily endpoint and provider symbol for one project code."""
    if _is_crypto(code):
        return None
    if _is_us_equity(code):
        return "us_daily", _to_tushare_us_code(code)
    if _is_etf_listed(code):
        return "fund_daily", code.upper()
    if _is_index(code):
        return "index_daily", code.upper()
    if _is_hk_equity(code):
        return "hk_daily", _to_tushare_hk_code(code)
    return "daily", code.upper()


def _chunked(items: List[str], size: int) -> list[list[str]]:
    """Split provider symbols into bounded request batches."""
    return [items[index:index + size] for index in range(0, len(items), size)]


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a Tushare daily-like frame into the project OHLCV schema."""
    frame = df.sort_values("trade_date").copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.set_index("trade_date").rename(columns={"vol": "volume"})
    for col in ["open", "high", "low", "close", "volume"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    return frame[["open", "high", "low", "close", "volume"]].dropna(
        subset=["open", "high", "low", "close"],
    )


@register
class DataLoader:
    """Tushare-backed OHLCV loader."""

    name = "tushare"
    markets = {"a_share", "us_equity", "hk_equity", "futures", "fund"}
    requires_auth = True

    def is_available(self) -> bool:
        """Available when TUSHARE_TOKEN is set."""
        from src.config.accessor import get_env_config

        return get_env_config().data.tushare_token.strip() not in TUSHARE_TOKEN_PLACEHOLDERS

    def __init__(self) -> None:
        """Initialize Tushare pro API."""
        import tushare as ts

        from src.config.accessor import get_env_config

        token = get_env_config().data.tushare_token
        self.api = ts.pro_api(token)

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch A-share bars via Tushare API.

        Args:
            codes: Stock codes (e.g. ``000001.SZ``).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            fields: Extra fundamental columns (daily only).
            interval: Bar size (1D/1m/5m/15m/30m/1H), default ``1D``.

        Returns:
            Mapping code -> OHLCV DataFrame.
        """
        validate_date_range(start_date, end_date)

        if interval != "1D":
            return self._fetch_minutes(codes, start_date, end_date, interval)

        sd = start_date.replace("-", "")
        ed = end_date.replace("-", "")
        cache_fields = list(fields or [])
        result: Dict[str, pd.DataFrame] = {}
        uncached: list[str] = []

        for code in codes:
            cached = loader_cache_get(
                source=self.name,
                symbol=code,
                timeframe="1D",
                start_date=start_date,
                end_date=end_date,
                fields=cache_fields,
            )
            if cached is not None and not cached.empty:
                result[code] = cached
            else:
                uncached.append(code)

        groups: dict[str, dict[str, str]] = {}
        for code in uncached:
            route = _daily_endpoint_code(code)
            if route is None:
                logger.warning("tushare does not support %s (crypto); skipping", code)
                continue
            endpoint_name, api_code = route
            groups.setdefault(endpoint_name, {})[api_code] = code

        from src.config.accessor import get_env_config

        batch_size = max(1, get_env_config().data.tushare_batch_size)
        for endpoint_name, code_map in groups.items():
            endpoint = getattr(self.api, endpoint_name)
            for batch in _chunked(list(code_map), batch_size):
                batch_result: set[str] = set()
                try:
                    frame = endpoint(
                        ts_code=",".join(batch),
                        start_date=sd,
                        end_date=ed,
                    )
                    if frame is not None and not frame.empty and "ts_code" in frame.columns:
                        for api_code, rows in frame.groupby("ts_code"):
                            original = code_map.get(str(api_code).upper())
                            if original:
                                normalized = _normalize_ohlcv(rows)
                                if not normalized.empty:
                                    result[original] = normalized
                                    batch_result.add(original)
                except Exception as exc:
                    logger.warning("Tushare %s batch failed for %s: %s", endpoint_name, batch, exc)

                for api_code in batch:
                    original = code_map[api_code]
                    if original in batch_result:
                        continue
                    try:
                        fallback = self._fetch_daily_frame(original, sd, ed)
                    except Exception as exc:
                        logger.warning("failed to fetch %s: %s", original, exc)
                        fallback = None
                    if fallback is not None and not fallback.empty:
                        result[original] = fallback

        self._merge_basic_fields(result, uncached, start_date, end_date, cache_fields)
        for code in uncached:
            loader_cache_put(
                source=self.name,
                symbol=code,
                timeframe="1D",
                start_date=start_date,
                end_date=end_date,
                fields=cache_fields,
                frame=result.get(code),
            )

        return result

    def _fetch_daily_frame(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> Optional[pd.DataFrame]:
        """Fetch and normalize one daily OHLCV frame, routing by symbol type."""
        route = _daily_endpoint_code(code)
        if route is None:
            logger.warning("tushare does not support %s; skipping", code)
            return None

        endpoint_name, api_code = route
        endpoint = getattr(self.api, endpoint_name)
        df = endpoint(ts_code=api_code, start_date=start_date, end_date=end_date)

        if df is None or df.empty:
            logger.warning("tushare returned empty for %s via %s", code, endpoint_name)
            return None
        return _normalize_ohlcv(df)

    def _merge_basic_fields(
        self,
        result: Dict[str, pd.DataFrame],
        codes: List[str],
        start_date: str,
        end_date: str,
        fields: Optional[List[str]],
    ) -> Dict[str, pd.DataFrame]:
        """Merge fundamental columns from daily_basic API.

        Args:
            result: Existing OHLCV frames.
            codes: All requested codes.
            start_date: Start date.
            end_date: End date.
            fields: Extra column names from daily_basic.

        Returns:
            Updated result map.
        """
        if not fields:
            return result

        sd = start_date.replace("-", "")
        ed = end_date.replace("-", "")
        active_codes = [c for c in codes if c in result]

        for code in active_codes:
            if (
                _is_etf_listed(code)
                or _is_index(code)
                or _is_hk_equity(code)
                or _is_us_equity(code)
                or _is_crypto(code)
            ):
                # daily_basic is stock-only; skip fundamental enrichment for non-stock symbols
                continue
            try:
                basic = self._fetch_daily_basic_with_retry(code, sd, ed, fields)
                if basic is not None and not basic.empty:
                    basic["trade_date"] = pd.to_datetime(basic["trade_date"])
                    basic = basic.set_index("trade_date").sort_index()
                    for f in fields:
                        if f in basic.columns:
                            result[code][f] = basic[f]
            except Exception as exc:
                logger.warning("daily_basic for %s failed: %s", code, exc)

        return result

    def _fetch_daily_basic_with_retry(
        self,
        code: str,
        start_date: str,
        end_date: str,
        fields: List[str],
    ) -> pd.DataFrame:
        """Fetch ``daily_basic`` with bounded retries on frequency limits."""
        from src.config.accessor import get_env_config

        cfg = get_env_config().data
        query_fields = "ts_code,trade_date," + ",".join(fields)
        for attempt in range(cfg.tushare_rate_limit_retries + 1):
            try:
                return self.api.daily_basic(
                    ts_code=code,
                    start_date=start_date,
                    end_date=end_date,
                    fields=query_fields,
                )
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt >= cfg.tushare_rate_limit_retries:
                    raise
                sleep_s = cfg.tushare_rate_limit_sleep_seconds
                logger.warning(
                    "Tushare daily_basic rate-limited; retry %d/%d after %.1fs",
                    attempt + 1,
                    cfg.tushare_rate_limit_retries,
                    sleep_s,
                )
                if sleep_s > 0:
                    time.sleep(sleep_s)
        return pd.DataFrame()

    def _fetch_minutes(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        interval: str,
    ) -> Dict[str, pd.DataFrame]:
        """Intraday bars via stk_mins.

        Args:
            codes: Stock codes.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            interval: Minute bar (1m/5m/15m/30m/1H).

        Returns:
            Mapping code -> DataFrame.
        """
        freq_map = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1H": "60min"}
        freq = freq_map.get(interval)
        if not freq:
            logger.error("unsupported Tushare interval: %s", interval)
            return {}

        sd = start_date.replace("-", "")
        ed = end_date.replace("-", "")
        result: Dict[str, pd.DataFrame] = {}

        for code in codes:
            if _is_etf_listed(code):
                # tushare has no fund_mins endpoint; ETF intraday is unavailable
                logger.warning("tushare does not support intraday data for %s (ETF); skipping", code)
                continue
            if _is_index(code) or _is_hk_equity(code) or _is_us_equity(code) or _is_crypto(code):
                sym_type = (
                    "index" if _is_index(code)
                    else "HK" if _is_hk_equity(code)
                    else "US" if _is_us_equity(code)
                    else "crypto"
                )
                logger.warning("tushare does not support intraday data for %s (%s); skipping", code, sym_type)
                continue
            try:
                df = self.api.stk_mins(ts_code=code, freq=freq, start_date=sd, end_date=ed)
                if df is None or df.empty:
                    logger.warning("empty Tushare minute data: %s (points >= 2000 required)", code)
                    continue
                df = df.sort_values("trade_time")
                df["trade_date"] = pd.to_datetime(df["trade_time"])
                df = df.set_index("trade_date")
                df = df.rename(columns={"vol": "volume"})
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                ohlcv = df[["open", "high", "low", "close", "volume"]].dropna(
                    subset=["open", "high", "low", "close"]
                )
                result[code] = ohlcv
            except Exception as exc:
                logger.warning("failed to fetch minute data %s: %s", code, exc)
        return result


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return whether a Tushare exception represents a frequency limit."""
    message = str(exc).lower()
    return "频率超限" in message or "rate limit" in message or "too many" in message
