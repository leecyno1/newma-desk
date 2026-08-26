"""Governed long-form core asset return panel."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

import pandas as pd

from seven_cycle_platform.assets.proxies import (
    ASSET_RETURN_COLUMNS,
    AssetReturnSegment,
    OverlapCalibration,
    ProxyStatus,
    build_proxy_chain,
    segments_to_long_frame,
)
from seven_cycle_platform.registry.models import AssetSpec, RegistryBundle


DEFAULT_BENCHMARK_MAP = MappingProxyType(
    {
        "cn_equity_hs300": "cn_equity_hs300",
        "cn_equity_csi500": "cn_equity_hs300",
        "cn_equity_csi1000": "cn_equity_hs300",
        "cn_equity_baijiu": "cn_equity_hs300",
        "cn_bond_government_index": "cny_cash",
        "gold": "cny_cash",
        "copper": "cny_cash",
        "crude_oil": "cny_cash",
        "usd_cny": "cny_cash",
        "us_equity_sp500": "us_equity_sp500",
        "cny_cash": "cny_cash",
    }
)

PANEL_RETURN_COLUMNS = ASSET_RETURN_COLUMNS + (
    "asset_status",
    "asset_status_reason",
)

ASSET_AVAILABILITY_COLUMNS = (
    "asset_id",
    "status",
    "reason",
    "observed_months",
    "required_months",
    "missing_ratio",
    "maximum_missing_ratio",
    "quality_tier",
    "minimum_quality_tier",
    "segment_count",
    "proxy_only",
    "legacy_only",
    "benchmark_asset_id",
)

_QUALITY_RANK = {"A": 0, "B": 1, "C": 2}


class CoreAssetPanelError(ValueError):
    """The governed core asset panel failed strict availability gates."""


def _copy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.copy(deep=True)


@dataclass(frozen=True)
class CoreAssetPanel:
    """Detached long-form returns and one audit record per core asset."""

    returns: pd.DataFrame
    availability: pd.DataFrame
    core_asset_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.returns, pd.DataFrame):
            raise TypeError("returns must be a pandas DataFrame")
        if not isinstance(self.availability, pd.DataFrame):
            raise TypeError("availability must be a pandas DataFrame")
        if list(self.returns.columns) != list(PANEL_RETURN_COLUMNS):
            raise ValueError("returns columns do not match the asset panel contract")
        if list(self.availability.columns) != list(ASSET_AVAILABILITY_COLUMNS):
            raise ValueError(
                "availability columns do not match the asset panel contract"
            )
        if not isinstance(self.core_asset_ids, tuple) or any(
            not isinstance(asset_id, str) or not asset_id
            for asset_id in self.core_asset_ids
        ):
            raise TypeError("core_asset_ids must be a tuple of non-empty strings")
        if len(self.core_asset_ids) != len(set(self.core_asset_ids)):
            raise ValueError("core_asset_ids must be unique")
        if self.returns.duplicated(["asset_id", "segment_id", "date"]).any():
            raise ValueError("asset_id × segment_id × date must be unique")
        availability_ids = tuple(self.availability["asset_id"])
        if availability_ids != self.core_asset_ids:
            raise ValueError(
                "availability must contain one ordered row per core asset"
            )
        if not set(self.returns["asset_id"]).issubset(self.core_asset_ids):
            raise ValueError("returns contains an asset outside the core registry")
        object.__setattr__(self, "returns", _copy_frame(self.returns))
        object.__setattr__(self, "availability", _copy_frame(self.availability))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in {"returns", "availability"} and isinstance(
            value,
            pd.DataFrame,
        ):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.returns

    @property
    def audit(self) -> pd.DataFrame:
        return self.availability


def _registry_assets(
    assets: RegistryBundle | Sequence[AssetSpec],
) -> tuple[AssetSpec, ...]:
    if isinstance(assets, RegistryBundle):
        normalized = tuple(assets.assets)
    else:
        if isinstance(assets, (str, bytes)):
            raise TypeError("assets must be a registry bundle or AssetSpec sequence")
        try:
            normalized = tuple(assets)
        except TypeError as error:
            raise TypeError(
                "assets must be a registry bundle or AssetSpec sequence"
            ) from error
    if any(not isinstance(asset, AssetSpec) for asset in normalized):
        raise TypeError("assets must contain AssetSpec values")
    asset_ids = [asset.asset_id for asset in normalized]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("assets cannot contain duplicate asset_id values")
    core_assets = tuple(
        asset for asset in normalized if asset.active and asset.tier == "core"
    )
    if not core_assets:
        raise ValueError("registry has no active core assets")
    return core_assets


def _segments(
    values: Iterable[AssetReturnSegment],
    *,
    name: str,
) -> tuple[AssetReturnSegment, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of AssetReturnSegment values")
    try:
        normalized = tuple(values)
    except TypeError as error:
        raise TypeError(
            f"{name} must be an iterable of AssetReturnSegment values"
        ) from error
    if any(not isinstance(segment, AssetReturnSegment) for segment in normalized):
        raise TypeError(f"{name} must contain AssetReturnSegment values")
    return normalized


def _benchmark_map(
    benchmark_map: Mapping[str, str],
    core_assets: tuple[AssetSpec, ...],
) -> dict[str, str]:
    if not isinstance(benchmark_map, Mapping):
        raise TypeError("benchmark_map must be a mapping")
    core_ids = {asset.asset_id for asset in core_assets}
    normalized: dict[str, str] = {}
    for asset in core_assets:
        benchmark = benchmark_map.get(asset.asset_id)
        if not isinstance(benchmark, str) or not benchmark.strip():
            raise ValueError(
                f"benchmark_map is missing asset: {asset.asset_id}"
            )
        benchmark = benchmark.strip()
        if benchmark not in core_ids:
            raise ValueError(
                f"benchmark for {asset.asset_id} is not a core asset: {benchmark}"
            )
        normalized[asset.asset_id] = benchmark
    if (
        "cn_equity_baijiu" in normalized
        and normalized["cn_equity_baijiu"] != "cn_equity_hs300"
    ):
        raise ValueError(
            "cn_equity_baijiu benchmark must be cn_equity_hs300"
        )
    return normalized


def _validate_primary(segment: AssetReturnSegment, asset: AssetSpec) -> None:
    expected = (asset.source, asset.backend, asset.symbol)
    actual = (segment.source, segment.backend, segment.symbol)
    if actual != expected:
        raise ValueError(
            f"primary segment {segment.segment_id} does not match registry source metadata"
        )


def _validate_proxy(segment: AssetReturnSegment, asset: AssetSpec) -> None:
    proxy_by_id = {proxy.proxy_id: proxy for proxy in asset.proxy_chain}
    if segment.segment_id not in proxy_by_id:
        raise ValueError(
            f"proxy segment {segment.segment_id} is not registered for {asset.asset_id}"
        )
    proxy = proxy_by_id[segment.segment_id]
    actual = (
        segment.proxy_for,
        segment.source,
        segment.backend,
        segment.symbol,
        segment.effective_from,
        segment.effective_to,
        segment.confidence_discount,
    )
    expected = (
        proxy.proxy_for,
        proxy.source,
        proxy.backend,
        proxy.symbol,
        proxy.effective_from,
        proxy.effective_to,
        proxy.confidence_discount,
    )
    if actual != expected:
        raise ValueError(
            f"proxy segment {segment.segment_id} does not match registry metadata"
        )


def _validate_legacy(segment: AssetReturnSegment, asset: AssetSpec) -> None:
    live_metadata = (asset.source, asset.backend, asset.symbol)
    legacy_metadata = (segment.source, segment.backend, segment.symbol)
    if legacy_metadata == live_metadata:
        raise ValueError(
            f"legacy segment {segment.segment_id} cannot impersonate live data"
        )


def _validate_segment(
    segment: AssetReturnSegment,
    asset: AssetSpec,
    benchmark_asset_id: str,
) -> None:
    if segment.currency != asset.currency:
        raise ValueError(
            f"segment {segment.segment_id} currency does not match the registry"
        )
    if segment.calendar != asset.calendar:
        raise ValueError(
            f"segment {segment.segment_id} calendar does not match the registry"
        )
    if segment.benchmark_asset_id != benchmark_asset_id:
        raise ValueError(
            f"segment {segment.segment_id} benchmark does not match benchmark_map"
        )
    if segment.proxy_status is ProxyStatus.PRIMARY:
        _validate_primary(segment, asset)
    elif segment.proxy_status is ProxyStatus.PROXY:
        _validate_proxy(segment, asset)
    else:
        _validate_legacy(segment, asset)


def _calibrated_segments(
    asset: AssetSpec,
    segments: tuple[AssetReturnSegment, ...],
) -> tuple[AssetReturnSegment, ...]:
    primary = tuple(
        segment
        for segment in segments
        if segment.proxy_status is ProxyStatus.PRIMARY
    )
    if len(primary) > 1:
        raise ValueError(f"asset {asset.asset_id} has multiple primary segments")
    proxies = tuple(
        segment
        for segment in segments
        if segment.proxy_status is ProxyStatus.PROXY
    )
    legacy = tuple(
        segment
        for segment in segments
        if segment.proxy_status is ProxyStatus.LEGACY_SEED
    )
    if primary:
        calibrated_proxies = build_proxy_chain(primary[0], proxies)
    else:
        calibrated_proxies = tuple(
            replace(
                proxy,
                raw_returns=proxy.raw_returns,
                returns=proxy.raw_returns,
                overlap_calibration=OverlapCalibration.unavailable(
                    "primary_unavailable"
                ),
            )
            for proxy in proxies
        )
    return tuple((*legacy, *calibrated_proxies, *primary))


def _quality_record(
    asset: AssetSpec,
    segments: tuple[AssetReturnSegment, ...],
    benchmark_asset_id: str,
) -> dict[str, object]:
    if not segments:
        return {
            "asset_id": asset.asset_id,
            "status": "missing",
            "reason": "no_segments",
            "observed_months": 0,
            "required_months": asset.minimum_history_months,
            "missing_ratio": 1.0,
            "maximum_missing_ratio": asset.maximum_missing_ratio,
            "quality_tier": None,
            "minimum_quality_tier": asset.minimum_quality_tier,
            "segment_count": 0,
            "proxy_only": False,
            "legacy_only": False,
            "benchmark_asset_id": benchmark_asset_id,
        }

    monthly_quality_ranks: dict[pd.Timestamp, int] = {}
    for segment in segments:
        quality_rank = _QUALITY_RANK[segment.quality_tier]
        for timestamp in segment.returns.index:
            existing_rank = monthly_quality_ranks.get(timestamp)
            monthly_quality_ranks[timestamp] = (
                quality_rank
                if existing_rank is None
                else min(existing_rank, quality_rank)
            )
    observed_dates = pd.DatetimeIndex(sorted(monthly_quality_ranks))
    observed_months = len(observed_dates)
    expected_months = len(
        pd.period_range(
            observed_dates[0].to_period("M"),
            observed_dates[-1].to_period("M"),
            freq="M",
        )
    )
    missing_ratio = 1.0 - observed_months / expected_months
    effective_quality_rank = max(monthly_quality_ranks.values())
    effective_quality = next(
        quality_tier
        for quality_tier, rank in _QUALITY_RANK.items()
        if rank == effective_quality_rank
    )
    reasons: list[str] = []
    if observed_months < asset.minimum_history_months:
        reasons.append(
            "minimum_history_months: "
            f"observed {observed_months} < required {asset.minimum_history_months}"
        )
    if missing_ratio > asset.maximum_missing_ratio:
        reasons.append(
            "maximum_missing_ratio: "
            f"observed {missing_ratio:.6f} > allowed {asset.maximum_missing_ratio:.6f}"
        )
    if effective_quality_rank > _QUALITY_RANK[asset.minimum_quality_tier]:
        reasons.append(
            "minimum_quality_tier: "
            f"observed {effective_quality} < required {asset.minimum_quality_tier}"
        )
    status = "available" if not reasons else "unavailable"
    segment_statuses = {segment.proxy_status for segment in segments}
    has_primary = ProxyStatus.PRIMARY in segment_statuses
    has_proxy = ProxyStatus.PROXY in segment_statuses
    has_legacy = ProxyStatus.LEGACY_SEED in segment_statuses
    return {
        "asset_id": asset.asset_id,
        "status": status,
        "reason": "; ".join(reasons) if reasons else "accepted",
        "observed_months": observed_months,
        "required_months": asset.minimum_history_months,
        "missing_ratio": float(missing_ratio),
        "maximum_missing_ratio": asset.maximum_missing_ratio,
        "quality_tier": effective_quality,
        "minimum_quality_tier": asset.minimum_quality_tier,
        "segment_count": len(segments),
        "proxy_only": has_proxy and not has_primary and not has_legacy,
        "legacy_only": has_legacy and not has_primary and not has_proxy,
        "benchmark_asset_id": benchmark_asset_id,
    }


def _empty_returns() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_RETURN_COLUMNS)


def build_core_asset_panel(
    assets: RegistryBundle | Sequence[AssetSpec],
    *,
    source_segments: Iterable[AssetReturnSegment] = (),
    legacy_seeds: Iterable[AssetReturnSegment] = (),
    benchmark_map: Mapping[str, str] = DEFAULT_BENCHMARK_MAP,
    strict: bool = False,
) -> CoreAssetPanel:
    """Build the complete active-core panel without silently dropping assets."""

    if not isinstance(strict, bool):
        raise TypeError("strict must be a boolean")
    core_assets = _registry_assets(assets)
    benchmark_by_asset = _benchmark_map(benchmark_map, core_assets)
    normalized_sources = _segments(source_segments, name="source_segments")
    normalized_legacy = _segments(legacy_seeds, name="legacy_seeds")
    if any(
        segment.proxy_status is ProxyStatus.LEGACY_SEED
        for segment in normalized_sources
    ):
        raise ValueError("source_segments cannot contain legacy_seed segments")
    if any(
        segment.proxy_status is not ProxyStatus.LEGACY_SEED
        for segment in normalized_legacy
    ):
        raise ValueError("legacy_seeds must contain only legacy_seed segments")
    all_segments = tuple((*normalized_sources, *normalized_legacy))
    segment_keys = [
        (segment.asset_id, segment.segment_id) for segment in all_segments
    ]
    if len(segment_keys) != len(set(segment_keys)):
        raise ValueError("asset_id × segment_id values must be unique")

    asset_by_id = {asset.asset_id: asset for asset in core_assets}
    for segment in all_segments:
        if segment.asset_id not in asset_by_id:
            raise ValueError(
                f"segment references an unknown active core asset: {segment.asset_id}"
            )
        _validate_segment(
            segment,
            asset_by_id[segment.asset_id],
            benchmark_by_asset[segment.asset_id],
        )

    prepared_by_asset: dict[str, tuple[AssetReturnSegment, ...]] = {}
    availability_records: list[dict[str, object]] = []
    for asset in core_assets:
        asset_segments = tuple(
            segment for segment in all_segments if segment.asset_id == asset.asset_id
        )
        prepared = _calibrated_segments(asset, asset_segments)
        prepared_by_asset[asset.asset_id] = prepared
        availability_records.append(
            _quality_record(
                asset,
                prepared,
                benchmark_by_asset[asset.asset_id],
            )
        )

    availability = pd.DataFrame(
        availability_records,
        columns=ASSET_AVAILABILITY_COLUMNS,
    )
    status_by_asset = availability.set_index("asset_id")
    frames: list[pd.DataFrame] = []
    for asset in core_assets:
        prepared = prepared_by_asset[asset.asset_id]
        if not prepared:
            continue
        frame = segments_to_long_frame(prepared)
        frame["asset_status"] = status_by_asset.loc[asset.asset_id, "status"]
        frame["asset_status_reason"] = status_by_asset.loc[
            asset.asset_id,
            "reason",
        ]
        frames.append(frame)
    if frames:
        records = [
            record
            for frame in frames
            for record in frame.to_dict(orient="records")
        ]
        returns = pd.DataFrame.from_records(
            records,
            columns=PANEL_RETURN_COLUMNS,
        )
        returns = returns.sort_values(
            ["asset_id", "segment_id", "date"],
            kind="stable",
        ).reset_index(drop=True)
    else:
        returns = _empty_returns()

    unavailable = availability[availability["status"] != "available"]
    if strict and not unavailable.empty:
        details = "; ".join(
            f"{row.asset_id} ({row.status}: {row.reason})"
            for row in unavailable.itertuples(index=False)
        )
        raise CoreAssetPanelError(f"Core asset panel unavailable: {details}")

    return CoreAssetPanel(
        returns=returns,
        availability=availability,
        core_asset_ids=tuple(asset.asset_id for asset in core_assets),
    )
