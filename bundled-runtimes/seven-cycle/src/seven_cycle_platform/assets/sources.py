"""Credential-safe asset sources and explicit legacy conversion."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pandas as pd

from seven_cycle_platform.assets.proxies import (
    AssetReturnSegment,
    OverlapCalibration,
    ProxyStatus,
    ReturnKind,
)
from seven_cycle_platform.registry.models import (
    AssetProxySpec,
    AssetSpec,
    RegistryBundle,
)


class AssetSourceError(RuntimeError):
    """An external asset source failed without exposing sensitive details."""


class TushareCredentialError(AssetSourceError):
    """The required environment-only Tushare credential is unavailable."""


def _nonblank_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-blank string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-blank string")
    return normalized


def _date_only(value: object, name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date without time")
    return value


def _date_interval(start_date: object, end_date: object) -> tuple[date, date]:
    normalized_start = _date_only(start_date, "start_date")
    normalized_end = _date_only(end_date, "end_date")
    if normalized_end < normalized_start:
        raise ValueError("end_date cannot precede start_date")
    return normalized_start, normalized_end


def _return_kind(value: object) -> ReturnKind:
    if isinstance(value, ReturnKind):
        return value
    if isinstance(value, str):
        try:
            return ReturnKind(value)
        except ValueError as error:
            raise ValueError(f"unknown return_kind: {value}") from error
    raise TypeError("return_kind must be a ReturnKind or string")


def _parsed_dates(values: pd.Series, field_name: str) -> pd.DatetimeIndex:
    if values.isna().any():
        raise ValueError(f"{field_name} cannot contain missing dates")
    for value in values:
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError):
            continue
        if timestamp.tzinfo is not None or timestamp.utcoffset() is not None:
            raise ValueError(
                f"{field_name} cannot contain timezone-aware timestamps"
            )
    try:
        parsed = pd.to_datetime(values, errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must contain valid dates") from error
    index = pd.DatetimeIndex(parsed)
    if index.hasnans:
        raise ValueError(f"{field_name} cannot contain missing dates")
    if index.tz is not None:
        raise ValueError(
            f"{field_name} cannot contain timezone-aware timestamps"
        )
    return index


def _filter_daily_interval(
    daily_prices: pd.DataFrame,
    *,
    date_column: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    if date_column not in daily_prices.columns:
        raise ValueError(f"missing required field: {date_column}")
    parsed_dates = _parsed_dates(daily_prices[date_column], date_column)
    mask = (parsed_dates >= pd.Timestamp(start_date)) & (
        parsed_dates <= pd.Timestamp(end_date)
    )
    filtered = daily_prices.loc[mask].copy(deep=True)
    if filtered.empty:
        raise ValueError("daily_prices has no rows inside the requested interval")
    return filtered


def normalize_daily_prices(
    daily_prices: pd.DataFrame,
    *,
    date_column: str,
    price_column: str,
    return_kind: ReturnKind | str,
    total_price_column: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.Series:
    """Normalize valid daily prices to decimal calendar month-end returns."""

    if not isinstance(daily_prices, pd.DataFrame):
        raise TypeError("daily_prices must be a pandas DataFrame")
    if daily_prices.empty:
        raise ValueError("daily_prices cannot be empty")
    normalized_date_column = _nonblank_text(date_column, "date_column")
    normalized_price_column = _nonblank_text(price_column, "price_column")
    normalized_kind = _return_kind(return_kind)

    if normalized_kind is ReturnKind.TOTAL:
        if total_price_column is None:
            raise ValueError("total_price_column is required for total returns")
        value_column = _nonblank_text(total_price_column, "total_price_column")
        if value_column.casefold() in {"close", "收盘", "收盘价"}:
            raise ValueError("close cannot be used as a total return price column")
        if value_column == normalized_price_column:
            raise ValueError(
                "price_column and total_price_column must be different"
            )
    else:
        if total_price_column is not None:
            raise ValueError(
                "total_price_column is valid only when return_kind is total"
            )
        value_column = normalized_price_column

    required_columns = (normalized_date_column, value_column)
    for column in required_columns:
        if column not in daily_prices.columns:
            raise ValueError(f"missing required field: {column}")

    parsed_dates = _parsed_dates(
        daily_prices[normalized_date_column],
        normalized_date_column,
    )
    if parsed_dates.duplicated().any():
        raise ValueError("daily prices cannot contain duplicate dates")
    raw_values = daily_prices[value_column]
    if pd.api.types.is_bool_dtype(raw_values.dtype):
        raise TypeError(f"{value_column} must contain finite numeric prices")
    try:
        numeric_values = pd.to_numeric(raw_values, errors="raise").astype(float)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{value_column} must contain finite numeric prices"
        ) from error
    if numeric_values.isna().any() or not np.isfinite(
        numeric_values.to_numpy()
    ).all():
        raise ValueError(f"{value_column} must contain finite numeric prices")
    if (numeric_values <= 0.0).any():
        raise ValueError(f"{value_column} prices must be positive")

    normalized = pd.DataFrame(
        {"date": parsed_dates, "price": numeric_values.to_numpy(copy=True)}
    )
    normalized_start = (
        _date_only(start_date, "start_date") if start_date is not None else None
    )
    normalized_end = (
        _date_only(end_date, "end_date") if end_date is not None else None
    )
    if (
        normalized_start is not None
        and normalized_end is not None
        and normalized_end < normalized_start
    ):
        raise ValueError("end_date cannot precede start_date")

    normalized = normalized.sort_values("date", kind="stable")
    normalized["month"] = normalized["date"].dt.to_period("M")
    monthly_prices = normalized.groupby("month", sort=True)["price"].last()
    if len(monthly_prices) < 2:
        raise ValueError("at least two calendar months of prices are required")
    monthly_returns = monthly_prices.pct_change(fill_method=None).dropna()
    monthly_returns.index = monthly_returns.index.to_timestamp("M")
    if normalized_start is not None:
        monthly_returns = monthly_returns[
            monthly_returns.index >= pd.Timestamp(normalized_start)
        ]
    if normalized_end is not None:
        monthly_returns = monthly_returns[
            monthly_returns.index <= pd.Timestamp(normalized_end)
        ]
    if monthly_returns.empty:
        raise ValueError("requested interval has no complete monthly returns")
    if not np.isfinite(monthly_returns.to_numpy()).all():
        raise ValueError("monthly returns must be finite")
    monthly_returns = monthly_returns.astype(float)
    monthly_returns.name = "return"
    return monthly_returns.copy(deep=True)


def _require_tushare_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN")
    if token is None or not token.strip():
        raise TushareCredentialError(
            "TUSHARE_TOKEN must be set to a non-blank environment value"
        )
    return token.strip()


def _canonical_registry(
    registry: RegistryBundle,
) -> Mapping[str, str]:
    if not isinstance(registry, RegistryBundle):
        raise TypeError("registry must be a validated RegistryBundle")
    raw_assets = tuple(registry.assets)
    if not raw_assets:
        raise ValueError("registry must contain at least one asset")
    if any(not isinstance(asset, AssetSpec) for asset in raw_assets):
        raise TypeError("registry sequence must contain AssetSpec values")

    canonical_assets = tuple(
        AssetSpec.model_validate(asset.model_dump(mode="python"))
        for asset in raw_assets
    )
    asset_ids = [asset.asset_id for asset in canonical_assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("registry cannot contain duplicate asset_id values")
    proxy_ids: list[str] = []
    for asset in canonical_assets:
        for proxy in asset.proxy_chain:
            if proxy.proxy_for != asset.asset_id:
                raise ValueError(
                    f"proxy {proxy.proxy_id} does not belong to {asset.asset_id}"
                )
            proxy_ids.append(proxy.proxy_id)
    if len(proxy_ids) != len(set(proxy_ids)):
        raise ValueError("registry cannot contain duplicate proxy_id values")
    return MappingProxyType(
        {
            asset.asset_id: asset.model_dump_json()
            for asset in canonical_assets
        }
    )


def _canonical_asset(
    registry: Mapping[str, str],
    *,
    asset_id: str | None,
    asset: AssetSpec | None,
) -> AssetSpec:
    if asset is not None and not isinstance(asset, AssetSpec):
        raise TypeError("asset must be an AssetSpec or None")
    if asset_id is None:
        if asset is None:
            raise ValueError("asset_id is required")
        normalized_asset_id = asset.asset_id
    else:
        normalized_asset_id = _nonblank_text(asset_id, "asset_id")
    if normalized_asset_id not in registry:
        raise ValueError(f"unknown asset_id: {normalized_asset_id}")
    canonical = AssetSpec.model_validate_json(registry[normalized_asset_id])
    if asset is not None:
        supplied = AssetSpec.model_validate(asset.model_dump(mode="python"))
        if supplied.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ValueError(
                f"asset {asset.asset_id} does not match canonical registry"
            )
    return canonical


def _canonical_proxy(
    asset: AssetSpec,
    *,
    proxy_id: str | None,
    proxy: AssetProxySpec | None,
) -> AssetProxySpec | None:
    if proxy is not None and not isinstance(proxy, AssetProxySpec):
        raise TypeError("proxy must be an AssetProxySpec or None")
    if proxy_id is None and proxy is None:
        return None
    if proxy_id is None:
        normalized_proxy_id = proxy.proxy_id
    else:
        normalized_proxy_id = _nonblank_text(proxy_id, "proxy_id")
    proxy_by_id = {
        registered_proxy.proxy_id: registered_proxy
        for registered_proxy in asset.proxy_chain
    }
    if normalized_proxy_id not in proxy_by_id:
        raise ValueError(
            f"unknown proxy_id for {asset.asset_id}: {normalized_proxy_id}"
        )
    canonical = proxy_by_id[normalized_proxy_id]
    if proxy is not None:
        supplied = AssetProxySpec.model_validate(proxy.model_dump(mode="python"))
        if supplied.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ValueError(
                f"proxy {proxy.proxy_id} does not match canonical registry"
            )
    return canonical


def _source_metadata(
    asset: AssetSpec,
    proxy: AssetProxySpec | None,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    if not isinstance(asset, AssetSpec):
        raise TypeError("asset must be an AssetSpec")
    if proxy is None:
        return {
            "segment_id": f"{asset.asset_id}:primary",
            "source": asset.source,
            "backend": asset.backend,
            "symbol": asset.symbol,
            "proxy_status": ProxyStatus.PRIMARY,
            "proxy_for": None,
            "effective_from": start_date,
            "effective_to": end_date,
            "overlap_calibration": OverlapCalibration.not_required(),
            "confidence_discount": 0.0,
        }
    if not isinstance(proxy, AssetProxySpec):
        raise TypeError("proxy must be an AssetProxySpec or None")
    if proxy.proxy_for != asset.asset_id:
        raise ValueError("proxy.proxy_for must equal asset.asset_id")
    return {
        "segment_id": proxy.proxy_id,
        "source": proxy.source,
        "backend": proxy.backend,
        "symbol": proxy.symbol,
        "proxy_status": ProxyStatus.PROXY,
        "proxy_for": proxy.proxy_for,
        "effective_from": proxy.effective_from,
        "effective_to": proxy.effective_to,
        "overlap_calibration": OverlapCalibration.unavailable("not_calibrated"),
        "confidence_discount": proxy.confidence_discount,
    }


def _query_interval(
    start_date: date,
    end_date: date,
    proxy: AssetProxySpec | None,
) -> tuple[date, date]:
    month_start = date(start_date.year, start_date.month, 1)
    previous_month_end = month_start - timedelta(days=1)
    query_start = date(
        previous_month_end.year,
        previous_month_end.month,
        1,
    )
    if proxy is None:
        return query_start, end_date
    query_start = max(query_start, proxy.effective_from)
    query_end = min(end_date, proxy.effective_to or end_date)
    if query_end < query_start:
        raise ValueError("requested dates do not intersect the proxy interval")
    return query_start, query_end


def _build_segment(
    *,
    asset: AssetSpec,
    proxy: AssetProxySpec | None,
    monthly_returns: pd.Series,
    return_kind: ReturnKind,
    benchmark_asset_id: str,
    start_date: date,
    end_date: date,
) -> AssetReturnSegment:
    metadata = _source_metadata(
        asset,
        proxy,
        start_date=start_date,
        end_date=end_date,
    )
    return AssetReturnSegment(
        asset_id=asset.asset_id,
        segment_id=metadata["segment_id"],
        raw_returns=monthly_returns,
        returns=monthly_returns,
        source=metadata["source"],
        backend=metadata["backend"],
        symbol=metadata["symbol"],
        currency=asset.currency,
        calendar=asset.calendar,
        return_kind=return_kind,
        quality_tier=asset.minimum_quality_tier,
        proxy_status=metadata["proxy_status"],
        proxy_for=metadata["proxy_for"],
        effective_from=metadata["effective_from"],
        effective_to=metadata["effective_to"],
        overlap_calibration=metadata["overlap_calibration"],
        confidence_discount=metadata["confidence_discount"],
        benchmark_asset_id=_nonblank_text(
            benchmark_asset_id,
            "benchmark_asset_id",
        ),
        data_start=monthly_returns.index[0].date(),
        data_end=monthly_returns.index[-1].date(),
    )


class TushareAdapter:
    """Tushare adapter with environment-only token handling."""

    _BACKENDS = MappingProxyType(
        {
            "tushare.index_daily": "index_daily",
            "tushare.ci_index_daily": "ci_index_daily",
        }
    )

    def __init__(
        self,
        registry: RegistryBundle,
        *,
        client: object | None = None,
    ) -> None:
        self._canonical_registry = _canonical_registry(registry)
        self._injected_client = client

    def __repr__(self) -> str:
        return (
            "TushareAdapter("
            f"registry_assets={len(self._canonical_registry)}, "
            f"client_injected={self._injected_client is not None})"
        )

    def _client(self) -> object:
        token = _require_tushare_token()
        if self._injected_client is not None:
            return self._injected_client
        try:
            import tushare

            return tushare.pro_api(token)
        except Exception:
            raise AssetSourceError("Unable to initialize Tushare client") from None

    def fetch_segment(
        self,
        *,
        asset_id: str | None = None,
        proxy_id: str | None = None,
        start_date: date,
        end_date: date,
        return_kind: ReturnKind | str,
        date_column: str,
        price_column: str,
        benchmark_asset_id: str,
        total_price_column: str | None = None,
        asset: AssetSpec | None = None,
        proxy: AssetProxySpec | None = None,
    ) -> AssetReturnSegment:
        normalized_start, normalized_end = _date_interval(start_date, end_date)
        normalized_kind = _return_kind(return_kind)
        canonical_asset = _canonical_asset(
            self._canonical_registry,
            asset_id=asset_id,
            asset=asset,
        )
        canonical_proxy = _canonical_proxy(
            canonical_asset,
            proxy_id=proxy_id,
            proxy=proxy,
        )
        metadata = _source_metadata(
            canonical_asset,
            canonical_proxy,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        backend = str(metadata["backend"])
        if backend not in self._BACKENDS:
            raise ValueError(f"unsupported Tushare backend: {backend}")
        query_start, query_end = _query_interval(
            normalized_start,
            normalized_end,
            canonical_proxy,
        )
        client = self._client()
        method_name = self._BACKENDS[backend]
        method = getattr(client, method_name, None)
        if not callable(method):
            raise AssetSourceError(
                f"Tushare client does not provide backend {method_name}"
            )
        try:
            frame = method(
                ts_code=metadata["symbol"],
                start_date=query_start.strftime("%Y%m%d"),
                end_date=query_end.strftime("%Y%m%d"),
            )
        except Exception:
            raise AssetSourceError(
                f"Tushare backend {backend} failed for the requested asset"
            ) from None
        if not isinstance(frame, pd.DataFrame):
            raise AssetSourceError(
                f"Tushare backend {backend} returned an invalid payload"
            )
        monthly_returns = normalize_daily_prices(
            frame,
            date_column=date_column,
            price_column=price_column,
            total_price_column=total_price_column,
            return_kind=normalized_kind,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        return _build_segment(
            asset=canonical_asset,
            proxy=canonical_proxy,
            monthly_returns=monthly_returns,
            return_kind=normalized_kind,
            benchmark_asset_id=benchmark_asset_id,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    fetch = fetch_segment


class AkShareAdapter:
    """AkShare adapter with injectable provider and no credentials."""

    _BACKENDS = MappingProxyType(
        {"akshare.stock_zh_index_daily_em": "stock_zh_index_daily_em"}
    )

    def __init__(
        self,
        registry: RegistryBundle,
        *,
        provider: object | None = None,
    ) -> None:
        self._canonical_registry = _canonical_registry(registry)
        self._injected_provider = provider

    def __repr__(self) -> str:
        return (
            "AkShareAdapter("
            f"registry_assets={len(self._canonical_registry)}, "
            f"provider_injected={self._injected_provider is not None})"
        )

    def _provider(self) -> object:
        if self._injected_provider is not None:
            return self._injected_provider
        try:
            import akshare

            return akshare
        except Exception:
            raise AssetSourceError("Unable to initialize AkShare provider") from None

    def fetch_segment(
        self,
        *,
        asset_id: str | None = None,
        proxy_id: str | None = None,
        start_date: date,
        end_date: date,
        return_kind: ReturnKind | str,
        date_column: str,
        price_column: str,
        benchmark_asset_id: str,
        total_price_column: str | None = None,
        asset: AssetSpec | None = None,
        proxy: AssetProxySpec | None = None,
    ) -> AssetReturnSegment:
        normalized_start, normalized_end = _date_interval(start_date, end_date)
        normalized_kind = _return_kind(return_kind)
        canonical_asset = _canonical_asset(
            self._canonical_registry,
            asset_id=asset_id,
            asset=asset,
        )
        canonical_proxy = _canonical_proxy(
            canonical_asset,
            proxy_id=proxy_id,
            proxy=proxy,
        )
        metadata = _source_metadata(
            canonical_asset,
            canonical_proxy,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        backend = str(metadata["backend"])
        if backend not in self._BACKENDS:
            raise ValueError(f"unsupported AkShare backend: {backend}")
        query_start, query_end = _query_interval(
            normalized_start,
            normalized_end,
            canonical_proxy,
        )
        provider = self._provider()
        method_name = self._BACKENDS[backend]
        method = getattr(provider, method_name, None)
        if not callable(method):
            raise AssetSourceError(
                f"AkShare provider does not provide backend {method_name}"
            )
        try:
            frame = method(symbol=metadata["symbol"])
        except Exception:
            raise AssetSourceError(
                f"AkShare backend {backend} failed for the requested asset"
            ) from None
        if not isinstance(frame, pd.DataFrame):
            raise AssetSourceError(
                f"AkShare backend {backend} returned an invalid payload"
            )
        filtered_frame = _filter_daily_interval(
            frame,
            date_column=date_column,
            start_date=query_start,
            end_date=query_end,
        )
        monthly_returns = normalize_daily_prices(
            filtered_frame,
            date_column=date_column,
            price_column=price_column,
            total_price_column=total_price_column,
            return_kind=normalized_kind,
            start_date=normalized_start,
            end_date=normalized_end,
        )
        return _build_segment(
            asset=canonical_asset,
            proxy=canonical_proxy,
            monthly_returns=monthly_returns,
            return_kind=normalized_kind,
            benchmark_asset_id=benchmark_asset_id,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    fetch = fetch_segment


@dataclass(frozen=True)
class LegacyAssetMapping:
    """Exact mapping from one legacy MultiIndex column to a governed asset."""

    asset_id: str
    segment_id: str
    symbol: str
    return_kind: ReturnKind
    quality_tier: str
    benchmark_asset_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "segment_id",
            "symbol",
            "benchmark_asset_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonblank_text(object.__getattribute__(self, field_name), field_name),
            )
        object.__setattr__(self, "return_kind", _return_kind(self.return_kind))
        if self.quality_tier not in {"A", "B", "C"}:
            raise ValueError("quality_tier must be one of A, B, or C")


LEGACY_CORE_ASSET_MAP = MappingProxyType(
    {
        ("A股宽基指数", "沪深300"): LegacyAssetMapping(
            asset_id="cn_equity_hs300",
            segment_id="legacy:cn_equity_hs300:monthly_returns_20y",
            symbol="000300.SH",
            return_kind=ReturnKind.PRICE,
            quality_tier="A",
            benchmark_asset_id="cn_equity_hs300",
        ),
        ("A股宽基指数", "中证500"): LegacyAssetMapping(
            asset_id="cn_equity_csi500",
            segment_id="legacy:cn_equity_csi500:monthly_returns_20y",
            symbol="000905.SH",
            return_kind=ReturnKind.PRICE,
            quality_tier="A",
            benchmark_asset_id="cn_equity_hs300",
        ),
        ("A股宽基指数", "中证1000"): LegacyAssetMapping(
            asset_id="cn_equity_csi1000",
            segment_id="legacy:cn_equity_csi1000:monthly_returns_20y",
            symbol="000852.SH",
            return_kind=ReturnKind.PRICE,
            quality_tier="A",
            benchmark_asset_id="cn_equity_hs300",
        ),
        ("各类债券指数", "国债指数(上证)"): LegacyAssetMapping(
            asset_id="cn_bond_government_index",
            segment_id="legacy:cn_bond_government_index:monthly_returns_20y",
            symbol="sh000012",
            return_kind=ReturnKind.PRICE,
            quality_tier="A",
            benchmark_asset_id="cny_cash",
        ),
        ("海外指数/ETF", "标普500(SPY)"): LegacyAssetMapping(
            asset_id="us_equity_sp500",
            segment_id="legacy:us_equity_sp500:spy_monthly_returns_20y",
            symbol="SPY",
            return_kind=ReturnKind.PRICE,
            quality_tier="B",
            benchmark_asset_id="us_equity_sp500",
        ),
    }
)


def _asset_specs(assets: Iterable[AssetSpec]) -> dict[str, AssetSpec]:
    if isinstance(assets, (str, bytes)):
        raise TypeError("assets must be an iterable of AssetSpec values")
    try:
        normalized = tuple(assets)
    except TypeError as error:
        raise TypeError("assets must be an iterable of AssetSpec values") from error
    if any(not isinstance(asset, AssetSpec) for asset in normalized):
        raise TypeError("assets must contain AssetSpec values")
    asset_ids = [asset.asset_id for asset in normalized]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("assets cannot contain duplicate asset_id values")
    return {asset.asset_id: asset for asset in normalized}


def _legacy_index(panel: pd.DataFrame) -> pd.DatetimeIndex:
    if not isinstance(panel.index, pd.DatetimeIndex):
        raise TypeError("legacy panel must use a pandas DatetimeIndex")
    if panel.index.hasnans:
        raise ValueError("legacy panel index cannot contain missing dates")
    if panel.index.tz is not None:
        raise ValueError("legacy panel index must be timezone-naive")
    if not panel.index.is_unique:
        raise ValueError("legacy panel index must contain unique dates")
    normalized = panel.index.to_period("M").to_timestamp("M")
    if not normalized.is_unique:
        raise ValueError(
            "legacy panel cannot contain more than one row for a calendar month"
        )
    return normalized


def convert_legacy_monthly_returns(
    panel: pd.DataFrame,
    *,
    assets: Iterable[AssetSpec],
    mapping: Mapping[tuple[str, str], LegacyAssetMapping] = LEGACY_CORE_ASSET_MAP,
    require_complete: bool = True,
) -> tuple[AssetReturnSegment, ...]:
    """Convert exact legacy MultiIndex columns to independent asset segments."""

    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel must be a pandas DataFrame")
    if panel.empty:
        raise ValueError("panel cannot be empty")
    if not isinstance(panel.columns, pd.MultiIndex) or panel.columns.nlevels != 2:
        raise TypeError("legacy panel columns must be a two-level MultiIndex")
    if not panel.columns.is_unique:
        raise ValueError("legacy panel columns must be unique")
    if not isinstance(mapping, Mapping):
        raise TypeError("mapping must be an explicit mapping")
    if not isinstance(require_complete, bool):
        raise TypeError("require_complete must be a boolean")
    asset_by_id = _asset_specs(assets)
    normalized_index = _legacy_index(panel)
    normalized_panel = panel.copy(deep=True)
    normalized_panel.index = normalized_index
    normalized_panel = normalized_panel.sort_index(kind="stable")

    normalized_mapping = tuple(mapping.items())
    for column, legacy_mapping in normalized_mapping:
        if (
            not isinstance(column, tuple)
            or len(column) != 2
            or any(not isinstance(level, str) for level in column)
        ):
            raise TypeError("legacy mapping keys must be two-string tuples")
        if not isinstance(legacy_mapping, LegacyAssetMapping):
            raise TypeError("legacy mapping values must be LegacyAssetMapping values")
    missing_columns = [
        column
        for column, _legacy_mapping in normalized_mapping
        if column not in normalized_panel.columns
    ]
    if require_complete and missing_columns:
        missing = ", ".join(str(column) for column in missing_columns)
        raise ValueError(f"legacy panel is missing mapped columns: {missing}")

    segments: list[AssetReturnSegment] = []
    for column, legacy_mapping in normalized_mapping:
        if column not in normalized_panel.columns:
            continue
        if legacy_mapping.asset_id not in asset_by_id:
            raise ValueError(
                f"legacy mapping references unknown asset: {legacy_mapping.asset_id}"
            )
        asset = asset_by_id[legacy_mapping.asset_id]
        raw_values = normalized_panel[column]
        if pd.api.types.is_bool_dtype(raw_values.dtype):
            raise TypeError(f"legacy column {column} must contain numeric returns")
        try:
            returns = pd.to_numeric(raw_values, errors="raise").astype(float)
        except (TypeError, ValueError) as error:
            raise TypeError(
                f"legacy column {column} must contain numeric returns"
            ) from error
        returns = returns.dropna()
        if returns.empty:
            if require_complete:
                raise ValueError(
                    f"legacy mapped column has no observations: {column}"
                )
            continue
        if not np.isfinite(returns.to_numpy()).all():
            raise ValueError(f"legacy column {column} must contain finite returns")
        if (returns <= -1.0).any():
            raise ValueError(
                f"legacy column {column} returns must be greater than -1"
            )
        returns.name = "return"
        segments.append(
            AssetReturnSegment(
                asset_id=asset.asset_id,
                segment_id=legacy_mapping.segment_id,
                raw_returns=returns,
                returns=returns,
                source="legacy_monthly_returns_20y",
                backend="legacy.parquet_multiindex",
                symbol=legacy_mapping.symbol,
                currency=asset.currency,
                calendar=asset.calendar,
                return_kind=legacy_mapping.return_kind,
                quality_tier=legacy_mapping.quality_tier,
                proxy_status=ProxyStatus.LEGACY_SEED,
                proxy_for=None,
                effective_from=returns.index[0].date(),
                effective_to=returns.index[-1].date(),
                overlap_calibration=OverlapCalibration.not_required(),
                confidence_discount=0.0,
                benchmark_asset_id=legacy_mapping.benchmark_asset_id,
                data_start=returns.index[0].date(),
                data_end=returns.index[-1].date(),
            )
        )
    return tuple(segments)


def load_legacy_monthly_returns(
    path: str | Path,
    *,
    assets: Iterable[AssetSpec],
    mapping: Mapping[tuple[str, str], LegacyAssetMapping] = LEGACY_CORE_ASSET_MAP,
    require_complete: bool = True,
) -> tuple[AssetReturnSegment, ...]:
    """Load and convert an explicitly mapped legacy monthly-return parquet."""

    legacy_path = Path(path)
    if not legacy_path.is_file():
        raise FileNotFoundError(f"legacy monthly return file does not exist: {legacy_path}")
    panel = pd.read_parquet(legacy_path)
    return convert_legacy_monthly_returns(
        panel,
        assets=assets,
        mapping=mapping,
        require_complete=require_complete,
    )
