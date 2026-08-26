"""Immutable asset segments and explicit proxy calibration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from numbers import Integral, Real

import numpy as np
import pandas as pd


class ReturnKind(StrEnum):
    """Supported monthly return definitions."""

    PRICE = "price"
    TOTAL = "total"


class ProxyStatus(StrEnum):
    """Relationship between a segment and its governed asset."""

    PRIMARY = "primary"
    PROXY = "proxy"
    LEGACY_SEED = "legacy_seed"


class CalibrationStatus(StrEnum):
    """Outcome of overlap calibration."""

    NOT_REQUIRED = "not_required"
    CALIBRATED = "calibrated"
    UNAVAILABLE = "unavailable"


ASSET_RETURN_COLUMNS = (
    "asset_id",
    "segment_id",
    "date",
    "raw_return",
    "return",
    "source",
    "backend",
    "symbol",
    "currency",
    "calendar",
    "return_kind",
    "quality_tier",
    "proxy_status",
    "proxy_for",
    "effective_from",
    "effective_to",
    "overlap_calibration_status",
    "overlap_method",
    "overlap_sample_count",
    "overlap_intercept",
    "overlap_slope",
    "overlap_reason",
    "confidence_discount",
    "effective_confidence",
    "benchmark_asset_id",
    "data_start",
    "data_end",
)


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


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    normalized = float(value)
    if not np.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    return normalized


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a non-negative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return normalized


def _enum_value(value: object, enum_type: type[StrEnum], name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            raise ValueError(f"unknown {name}: {value}") from error
    raise TypeError(f"{name} must be a {enum_type.__name__} or string")


def _return_series(value: object, name: str) -> pd.Series:
    if not isinstance(value, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if not isinstance(value.index, pd.DatetimeIndex):
        raise TypeError(f"{name} must use a pandas DatetimeIndex")
    if value.empty:
        raise ValueError(f"{name} cannot be empty")
    if value.index.hasnans:
        raise ValueError(f"{name} index cannot contain missing dates")
    if value.index.tz is not None:
        raise ValueError(f"{name} index must be timezone-naive")
    if not value.index.is_unique:
        raise ValueError(f"{name} index must contain unique dates")
    if not value.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be sorted")
    month_ends = value.index.to_period("M").to_timestamp("M")
    if not value.index.equals(month_ends):
        raise ValueError(f"{name} index must contain calendar month-end dates")
    if value.isna().any():
        raise ValueError(f"{name} cannot contain missing returns")
    if pd.api.types.is_bool_dtype(value.dtype):
        raise TypeError(f"{name} must contain finite real returns")
    try:
        normalized_values = pd.to_numeric(value, errors="raise").astype(float)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must contain finite real returns") from error
    if not np.isfinite(normalized_values.to_numpy()).all():
        raise ValueError(f"{name} must contain finite real returns")
    if (normalized_values <= -1.0).any():
        raise ValueError(f"{name} returns must be greater than -1")
    normalized_values.name = value.name
    return normalized_values.copy(deep=True)


@dataclass(frozen=True)
class OverlapCalibration:
    """Explicit result of robust proxy-to-primary overlap calibration."""

    status: CalibrationStatus
    method: str | None
    sample_count: int
    intercept: float | None
    slope: float | None
    reason: str | None

    def __post_init__(self) -> None:
        status = _enum_value(
            self.status,
            CalibrationStatus,
            "calibration status",
        )
        sample_count = _nonnegative_integer(self.sample_count, "sample_count")
        method = self.method
        reason = self.reason

        if status is CalibrationStatus.CALIBRATED:
            method = _nonblank_text(method, "method")
            if sample_count < 2:
                raise ValueError("calibrated overlap requires at least two samples")
            intercept = _finite_real(self.intercept, "intercept")
            slope = _finite_real(self.slope, "slope")
            if reason is not None:
                raise ValueError("calibrated overlap cannot define a reason")
        elif status is CalibrationStatus.UNAVAILABLE:
            if method is not None or self.intercept is not None or self.slope is not None:
                raise ValueError(
                    "unavailable overlap cannot define a method or coefficients"
                )
            reason = _nonblank_text(reason, "reason")
            intercept = None
            slope = None
        else:
            if sample_count != 0:
                raise ValueError("not-required overlap must have zero samples")
            if any(
                value is not None
                for value in (method, self.intercept, self.slope, reason)
            ):
                raise ValueError("not-required overlap cannot define parameters")
            intercept = None
            slope = None
            method = None
            reason = None

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "sample_count", sample_count)
        object.__setattr__(self, "intercept", intercept)
        object.__setattr__(self, "slope", slope)
        object.__setattr__(self, "reason", reason)

    @classmethod
    def not_required(cls) -> OverlapCalibration:
        return cls(
            status=CalibrationStatus.NOT_REQUIRED,
            method=None,
            sample_count=0,
            intercept=None,
            slope=None,
            reason=None,
        )

    @classmethod
    def unavailable(
        cls,
        reason: str,
        *,
        sample_count: int = 0,
    ) -> OverlapCalibration:
        return cls(
            status=CalibrationStatus.UNAVAILABLE,
            method=None,
            sample_count=sample_count,
            intercept=None,
            slope=None,
            reason=reason,
        )

    @classmethod
    def calibrated(
        cls,
        *,
        method: str,
        sample_count: int,
        intercept: float,
        slope: float,
    ) -> OverlapCalibration:
        return cls(
            status=CalibrationStatus.CALIBRATED,
            method=method,
            sample_count=sample_count,
            intercept=intercept,
            slope=slope,
            reason=None,
        )

    @property
    def scale(self) -> float | None:
        return self.slope


@dataclass(frozen=True)
class AssetReturnSegment:
    """One governed monthly-return segment with complete provenance."""

    asset_id: str
    segment_id: str
    raw_returns: pd.Series
    returns: pd.Series
    source: str
    backend: str
    symbol: str
    currency: str
    calendar: str
    return_kind: ReturnKind
    quality_tier: str
    proxy_status: ProxyStatus
    proxy_for: str | None
    effective_from: date
    effective_to: date | None
    overlap_calibration: OverlapCalibration
    confidence_discount: float
    benchmark_asset_id: str
    data_start: date
    data_end: date

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "segment_id",
            "source",
            "backend",
            "symbol",
            "currency",
            "calendar",
            "benchmark_asset_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonblank_text(object.__getattribute__(self, field_name), field_name),
            )

        raw_returns = _return_series(
            object.__getattribute__(self, "raw_returns"),
            "raw_returns",
        )
        adjusted_returns = _return_series(
            object.__getattribute__(self, "returns"),
            "returns",
        )
        if not raw_returns.index.equals(adjusted_returns.index):
            raise ValueError("raw_returns and returns must use the same dates")

        return_kind = _enum_value(self.return_kind, ReturnKind, "return_kind")
        proxy_status = _enum_value(
            self.proxy_status,
            ProxyStatus,
            "proxy_status",
        )
        if self.quality_tier not in {"A", "B", "C"}:
            raise ValueError("quality_tier must be one of A, B, or C")
        effective_from = _date_only(self.effective_from, "effective_from")
        effective_to = self.effective_to
        if effective_to is not None:
            effective_to = _date_only(effective_to, "effective_to")
            if effective_to < effective_from:
                raise ValueError("effective_to cannot precede effective_from")
        data_start = _date_only(self.data_start, "data_start")
        data_end = _date_only(self.data_end, "data_end")
        if data_end < data_start:
            raise ValueError("data_end cannot precede data_start")
        actual_start = raw_returns.index[0].date()
        actual_end = raw_returns.index[-1].date()
        if data_start != actual_start or data_end != actual_end:
            raise ValueError("data_start and data_end must match the return series")
        if data_start < effective_from or (
            effective_to is not None and data_end > effective_to
        ):
            raise ValueError("segment data falls outside its effective interval")

        if not isinstance(self.overlap_calibration, OverlapCalibration):
            raise TypeError("overlap_calibration must be an OverlapCalibration")
        discount = _finite_real(self.confidence_discount, "confidence_discount")
        if not 0.0 <= discount < 1.0:
            raise ValueError("confidence_discount must be between 0 and 1")

        proxy_for = self.proxy_for
        if proxy_status is ProxyStatus.PROXY:
            proxy_for = _nonblank_text(proxy_for, "proxy_for")
            if proxy_for != self.asset_id:
                raise ValueError("proxy_for must equal asset_id for proxy segments")
            if self.overlap_calibration.status is CalibrationStatus.NOT_REQUIRED:
                raise ValueError("proxy segments require an explicit calibration result")
        else:
            if proxy_for is not None:
                raise ValueError("non-proxy segments cannot define proxy_for")
            if discount != 0.0:
                raise ValueError("non-proxy segments cannot define a discount")
            if self.overlap_calibration.status is not CalibrationStatus.NOT_REQUIRED:
                raise ValueError(
                    "non-proxy segments must mark overlap calibration not_required"
                )

        object.__setattr__(self, "raw_returns", raw_returns)
        object.__setattr__(self, "returns", adjusted_returns)
        object.__setattr__(self, "return_kind", return_kind)
        object.__setattr__(self, "proxy_status", proxy_status)
        object.__setattr__(self, "proxy_for", proxy_for)
        object.__setattr__(self, "effective_from", effective_from)
        object.__setattr__(self, "effective_to", effective_to)
        object.__setattr__(self, "confidence_discount", discount)
        object.__setattr__(self, "data_start", data_start)
        object.__setattr__(self, "data_end", data_end)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in {"raw_returns", "returns"} and isinstance(value, pd.Series):
            return value.copy(deep=True)
        return value

    @property
    def effective_confidence(self) -> float:
        return 1.0 - self.confidence_discount

    def to_frame(self) -> pd.DataFrame:
        raw_returns = object.__getattribute__(self, "raw_returns")
        adjusted_returns = object.__getattribute__(self, "returns")
        calibration = self.overlap_calibration
        frame = pd.DataFrame(
            {
                "asset_id": self.asset_id,
                "segment_id": self.segment_id,
                "date": adjusted_returns.index,
                "raw_return": raw_returns.to_numpy(copy=True),
                "return": adjusted_returns.to_numpy(copy=True),
                "source": self.source,
                "backend": self.backend,
                "symbol": self.symbol,
                "currency": self.currency,
                "calendar": self.calendar,
                "return_kind": self.return_kind.value,
                "quality_tier": self.quality_tier,
                "proxy_status": self.proxy_status.value,
                "proxy_for": self.proxy_for,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
                "overlap_calibration_status": calibration.status.value,
                "overlap_method": calibration.method,
                "overlap_sample_count": calibration.sample_count,
                "overlap_intercept": calibration.intercept,
                "overlap_slope": calibration.slope,
                "overlap_reason": calibration.reason,
                "confidence_discount": self.confidence_discount,
                "effective_confidence": self.effective_confidence,
                "benchmark_asset_id": self.benchmark_asset_id,
                "data_start": self.data_start,
                "data_end": self.data_end,
            },
            columns=ASSET_RETURN_COLUMNS,
        )
        return frame.copy(deep=True)


def calibrate_overlap(
    primary: AssetReturnSegment,
    proxy: AssetReturnSegment,
) -> OverlapCalibration:
    """Estimate a deterministic Theil-Sen line on overlapping returns."""

    if not isinstance(primary, AssetReturnSegment):
        raise TypeError("primary must be an AssetReturnSegment")
    if not isinstance(proxy, AssetReturnSegment):
        raise TypeError("proxy must be an AssetReturnSegment")
    if primary.proxy_status is not ProxyStatus.PRIMARY:
        raise ValueError("primary segment must have proxy_status=primary")
    if proxy.proxy_status is not ProxyStatus.PROXY:
        raise ValueError("proxy segment must have proxy_status=proxy")
    if primary.asset_id != proxy.asset_id or proxy.proxy_for != primary.asset_id:
        raise ValueError("primary and proxy must reference the same asset")

    primary_returns = object.__getattribute__(primary, "raw_returns")
    proxy_returns = object.__getattribute__(proxy, "raw_returns")
    overlap = primary_returns.index.intersection(proxy_returns.index).sort_values()
    sample_count = len(overlap)
    if sample_count == 0:
        return OverlapCalibration.unavailable("no_overlap")
    if sample_count == 1:
        return OverlapCalibration.unavailable(
            "insufficient_overlap",
            sample_count=sample_count,
        )

    x_values = proxy_returns.loc[overlap].to_numpy(dtype=float)
    y_values = primary_returns.loc[overlap].to_numpy(dtype=float)
    slopes: list[float] = []
    for left in range(sample_count - 1):
        x_differences = x_values[left + 1 :] - x_values[left]
        y_differences = y_values[left + 1 :] - y_values[left]
        valid = x_differences != 0.0
        slopes.extend((y_differences[valid] / x_differences[valid]).tolist())
    if not slopes:
        return OverlapCalibration.unavailable(
            "degenerate_overlap",
            sample_count=sample_count,
        )
    slope = float(np.median(np.asarray(slopes, dtype=float)))
    intercept = float(np.median(y_values - slope * x_values))
    if not np.isfinite([intercept, slope]).all():
        return OverlapCalibration.unavailable(
            "nonfinite_calibration",
            sample_count=sample_count,
        )
    return OverlapCalibration.calibrated(
        method="theil_sen",
        sample_count=sample_count,
        intercept=intercept,
        slope=slope,
    )


def calibrate_proxy_segment(
    primary: AssetReturnSegment,
    proxy: AssetReturnSegment,
) -> AssetReturnSegment:
    """Return a detached proxy segment carrying explicit calibration."""

    calibration = calibrate_overlap(primary, proxy)
    raw_returns = object.__getattribute__(proxy, "raw_returns").copy(deep=True)
    if calibration.status is CalibrationStatus.CALIBRATED:
        adjusted_returns = calibration.intercept + calibration.slope * raw_returns
        adjusted_returns.name = raw_returns.name
    else:
        adjusted_returns = raw_returns.copy(deep=True)
    return replace(
        proxy,
        raw_returns=raw_returns,
        returns=adjusted_returns,
        overlap_calibration=calibration,
    )


def build_proxy_chain(
    primary: AssetReturnSegment,
    proxies: Iterable[AssetReturnSegment],
) -> tuple[AssetReturnSegment, ...]:
    """Calibrate proxies while preserving every segment independently."""

    if isinstance(proxies, (str, bytes)):
        raise TypeError("proxies must be an iterable of AssetReturnSegment values")
    try:
        normalized = tuple(proxies)
    except TypeError as error:
        raise TypeError(
            "proxies must be an iterable of AssetReturnSegment values"
        ) from error
    if any(not isinstance(proxy, AssetReturnSegment) for proxy in normalized):
        raise TypeError("proxies must contain AssetReturnSegment values")
    segment_ids = [proxy.segment_id for proxy in normalized]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError("proxy segment_id values must be unique")
    ordered = sorted(
        normalized,
        key=lambda proxy: (proxy.effective_from, proxy.segment_id),
    )
    return tuple(calibrate_proxy_segment(primary, proxy) for proxy in ordered)


def segments_to_long_frame(
    segments: Iterable[AssetReturnSegment],
) -> pd.DataFrame:
    """Convert explicit segments to a stable unique long-form frame."""

    if isinstance(segments, (str, bytes)):
        raise TypeError("segments must be an iterable of AssetReturnSegment values")
    try:
        normalized = tuple(segments)
    except TypeError as error:
        raise TypeError(
            "segments must be an iterable of AssetReturnSegment values"
        ) from error
    if any(not isinstance(segment, AssetReturnSegment) for segment in normalized):
        raise TypeError("segments must contain AssetReturnSegment values")
    if not normalized:
        return pd.DataFrame(columns=ASSET_RETURN_COLUMNS)
    records = [
        record
        for segment in normalized
        for record in segment.to_frame().to_dict(orient="records")
    ]
    frame = pd.DataFrame.from_records(
        records,
        columns=ASSET_RETURN_COLUMNS,
    )
    key = ["asset_id", "segment_id", "date"]
    if frame.duplicated(key).any():
        raise ValueError("asset_id × segment_id × date must be unique")
    frame = frame.sort_values(key, kind="stable").reset_index(drop=True)
    return frame.copy(deep=True)
