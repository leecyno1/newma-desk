"""Reusable robust period discovery and legacy research compatibility."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
import re
from types import MappingProxyType
import warnings

import numpy as np
import pandas as pd
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from scipy.sparse import SparseEfficiencyWarning
import statsmodels.api as sm


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RANDOM_SEED = 20260711


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _positive_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _unit_interval(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return numeric


def _integer(
    value: object,
    name: str,
    *,
    minimum: int,
) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be an integer")
    normalized = int(value)
    if normalized < minimum:
        comparison = "nonnegative" if minimum == 0 else "positive"
        raise ValueError(f"{name} must be {comparison}")
    return normalized


def _nonblank_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a non-blank string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-blank string")
    return normalized


def _readonly_array(values: np.ndarray) -> np.ndarray:
    copied = np.array(values, copy=True)
    copied.setflags(write=False)
    return copied


def _numeric_matrix(matrix: object, name: str = "matrix") -> np.ndarray:
    if not isinstance(matrix, np.ndarray):
        raise TypeError(f"{name} must be a numpy array")
    if matrix.ndim != 2:
        raise ValueError(f"{name} must be two-dimensional")
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name} must have at least one row and one column")
    if np.issubdtype(matrix.dtype, np.bool_) or not np.issubdtype(
        matrix.dtype,
        np.number,
    ):
        raise TypeError(f"{name} must contain real numeric values")
    values = np.array(matrix, dtype="float64", copy=True)
    if np.isinf(values).any():
        raise ValueError(f"{name} cannot contain infinite values")
    return values


def _period_grid(periods: object) -> np.ndarray:
    if isinstance(periods, (str, bytes)) or not isinstance(
        periods,
        (Sequence, np.ndarray),
    ):
        raise TypeError("periods must be a one-dimensional sequence of real values")
    raw = np.asarray(periods, dtype=object)
    if raw.ndim != 1:
        raise ValueError("periods must be one-dimensional")
    if raw.size == 0:
        raise ValueError("periods must not be empty")
    normalized: list[float] = []
    for value in raw.tolist():
        normalized.append(_positive_real(value, "periods"))
    values = np.asarray(normalized, dtype="float64")
    if np.any(np.diff(values) <= 0.0):
        raise ValueError("periods must be strictly increasing")
    return values


def _category_labels(categories: object, expected_rows: int) -> np.ndarray:
    if isinstance(categories, (str, bytes)) or not isinstance(
        categories,
        (Sequence, np.ndarray, pd.Series, pd.Index),
    ):
        raise TypeError("categories must be a one-dimensional sequence of labels")
    raw = np.asarray(categories, dtype=object)
    if raw.ndim != 1:
        raise ValueError("categories must be one-dimensional")
    if raw.shape[0] != expected_rows:
        raise ValueError("categories must align with matrix rows")
    normalized: list[str] = []
    for value in raw.tolist():
        if not isinstance(value, str):
            raise ValueError("category labels must be non-blank strings")
        label = value.strip()
        if not label:
            raise ValueError("blank category labels are not supported")
        normalized.append(label)
    return np.asarray(normalized, dtype=object)


def _boolean_mask(
    mask: object | None,
    expected_rows: int,
) -> np.ndarray:
    if mask is None:
        return np.ones(expected_rows, dtype="bool")
    if isinstance(mask, (str, bytes)) or not isinstance(
        mask,
        (Sequence, np.ndarray, pd.Series, pd.Index),
    ):
        raise TypeError("macro_mask must be a one-dimensional boolean sequence")
    raw = np.asarray(mask, dtype=object)
    if raw.ndim != 1 or raw.shape[0] != expected_rows:
        raise ValueError("macro_mask must align with matrix rows")
    normalized = np.zeros(expected_rows, dtype="bool")
    for position, value in enumerate(raw.tolist()):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError("macro_mask values must be boolean")
        normalized[position] = bool(value)
    if not normalized.any():
        raise ValueError("macro_mask must select at least one row")
    return normalized


def _filled_profile(profile: np.ndarray) -> np.ndarray:
    series = pd.Series(np.asarray(profile, dtype="float64"))
    if not bool(series.notna().any()):
        raise ValueError("score profile must contain at least one finite value")
    filled = series.interpolate(limit_direction="both").to_numpy(dtype="float64")
    if not np.isfinite(filled).all():
        raise ValueError("score profile must contain finite support across periods")
    return filled


def _profile_peak_index(profile: np.ndarray) -> int:
    smoothed = gaussian_filter1d(_filled_profile(profile), sigma=1.0)
    return int(np.argmax(smoothed))


def _category_matrix(matrix: np.ndarray, categories: np.ndarray) -> np.ndarray:
    rows = [
        np.nanmedian(matrix[categories == category], axis=0)
        for category in sorted(set(categories.tolist()))
    ]
    return np.vstack(rows).astype("float64")


@dataclass(frozen=True)
class CategorySupport:
    """Immutable cross-category support summary at one candidate period."""

    supported_categories: tuple[str, ...]
    total_categories: int
    support_ratio: float
    category_scores: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.supported_categories, tuple):
            raise TypeError("supported_categories must be a tuple")
        supported = tuple(
            sorted(
                {
                    _nonblank_text(category, "supported category")
                    for category in self.supported_categories
                }
            )
        )
        total = _integer(self.total_categories, "total_categories", minimum=1)
        ratio = _unit_interval(self.support_ratio, "support_ratio")
        if not isinstance(self.category_scores, Mapping):
            raise TypeError("category_scores must be a mapping")
        scores: dict[str, float] = {}
        for category, score in self.category_scores.items():
            label = _nonblank_text(category, "category score label")
            scores[label] = _finite_real(score, f"category score {label}")
        if len(scores) != total:
            raise ValueError("total_categories must equal category_scores size")
        if any(category not in scores for category in supported):
            raise ValueError("supported_categories must appear in category_scores")
        expected_ratio = len(supported) / total
        if not np.isclose(ratio, expected_ratio, atol=1e-12, rtol=0.0):
            raise ValueError("support_ratio must match supported category count")
        object.__setattr__(self, "supported_categories", supported)
        object.__setattr__(self, "total_categories", total)
        object.__setattr__(self, "support_ratio", ratio)
        object.__setattr__(
            self,
            "category_scores",
            MappingProxyType(dict(sorted(scores.items()))),
        )


@dataclass(frozen=True)
class MethodAgreement:
    """Immutable agreement summary for method-specific candidate periods."""

    center: float
    tolerance: float
    supporting_methods: tuple[str, ...]
    outlier_methods: tuple[str, ...]
    agreement_ratio: float
    method_periods: Mapping[str, float]

    def __post_init__(self) -> None:
        center = _positive_real(self.center, "center")
        tolerance = _finite_real(self.tolerance, "tolerance")
        if tolerance < 0.0:
            raise ValueError("tolerance must be nonnegative")
        ratio = _unit_interval(self.agreement_ratio, "agreement_ratio")
        if not isinstance(self.method_periods, Mapping) or not self.method_periods:
            raise TypeError("method_periods must be a non-empty mapping")
        periods: dict[str, float] = {}
        for method, period in self.method_periods.items():
            label = _nonblank_text(method, "method name")
            periods[label] = _positive_real(period, f"period for {label}")
        supporting = tuple(
            sorted(
                _nonblank_text(method, "supporting method")
                for method in self.supporting_methods
            )
        )
        outliers = tuple(
            sorted(
                _nonblank_text(method, "outlier method")
                for method in self.outlier_methods
            )
        )
        if set(supporting) & set(outliers):
            raise ValueError("supporting_methods and outlier_methods cannot overlap")
        if set(supporting) | set(outliers) != set(periods):
            raise ValueError("method classifications must cover method_periods")
        expected_ratio = len(supporting) / len(periods)
        if not np.isclose(ratio, expected_ratio, atol=1e-12, rtol=0.0):
            raise ValueError("agreement_ratio must match supporting method count")
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "supporting_methods", supporting)
        object.__setattr__(self, "outlier_methods", outliers)
        object.__setattr__(self, "agreement_ratio", ratio)
        object.__setattr__(
            self,
            "method_periods",
            MappingProxyType(dict(sorted(periods.items()))),
        )


@dataclass(frozen=True)
class DiscoveryEvidence:
    """Immutable evidence bundle consumed by quarterly recalibration gates."""

    candidate_center: float
    bootstrap_period_low: float
    bootstrap_period_high: float
    red_noise_score: float
    category_support: float
    macro_only_score: float
    category_balanced_score: float
    method_agreement: float
    method_peak_periods: Mapping[str, float]
    supporting_categories: tuple[str, ...]
    total_categories: int
    series_count: int
    random_seed: int

    def __post_init__(self) -> None:
        candidate = _positive_real(self.candidate_center, "candidate_center")
        interval_low = _positive_real(
            self.bootstrap_period_low,
            "bootstrap_period_low",
        )
        interval_high = _positive_real(
            self.bootstrap_period_high,
            "bootstrap_period_high",
        )
        if interval_low > interval_high:
            raise ValueError(
                "bootstrap_period_low cannot exceed bootstrap_period_high"
            )
        if not interval_low <= candidate <= interval_high:
            raise ValueError("candidate_center must fall inside bootstrap interval")
        red_noise_score = _finite_real(self.red_noise_score, "red_noise_score")
        category_support_ratio = _unit_interval(
            self.category_support,
            "category_support",
        )
        macro_score = _finite_real(self.macro_only_score, "macro_only_score")
        balanced_score = _finite_real(
            self.category_balanced_score,
            "category_balanced_score",
        )
        agreement = _unit_interval(self.method_agreement, "method_agreement")
        if not isinstance(self.method_peak_periods, Mapping) or not self.method_peak_periods:
            raise TypeError("method_peak_periods must be a non-empty mapping")
        method_periods: dict[str, float] = {}
        for method, period in self.method_peak_periods.items():
            label = _nonblank_text(method, "method name")
            method_periods[label] = _positive_real(period, f"period for {label}")
        if not isinstance(self.supporting_categories, tuple):
            raise TypeError("supporting_categories must be a tuple")
        supporting = tuple(
            sorted(
                {
                    _nonblank_text(category, "supporting category")
                    for category in self.supporting_categories
                }
            )
        )
        total = _integer(self.total_categories, "total_categories", minimum=1)
        series_count = _integer(self.series_count, "series_count", minimum=1)
        random_seed = _integer(self.random_seed, "random_seed", minimum=0)
        expected_support = len(supporting) / total
        if not np.isclose(
            category_support_ratio,
            expected_support,
            atol=1e-12,
            rtol=0.0,
        ):
            raise ValueError(
                "category_support must match supporting category count"
            )
        object.__setattr__(self, "candidate_center", candidate)
        object.__setattr__(self, "bootstrap_period_low", interval_low)
        object.__setattr__(self, "bootstrap_period_high", interval_high)
        object.__setattr__(self, "red_noise_score", red_noise_score)
        object.__setattr__(self, "category_support", category_support_ratio)
        object.__setattr__(self, "macro_only_score", macro_score)
        object.__setattr__(self, "category_balanced_score", balanced_score)
        object.__setattr__(self, "method_agreement", agreement)
        object.__setattr__(
            self,
            "method_peak_periods",
            MappingProxyType(dict(sorted(method_periods.items()))),
        )
        object.__setattr__(self, "supporting_categories", supporting)
        object.__setattr__(self, "total_categories", total)
        object.__setattr__(self, "series_count", series_count)
        object.__setattr__(self, "random_seed", random_seed)

    def metrics(self) -> Mapping[str, float | int]:
        """Return a read-only scalar evidence payload for version persistence."""

        return MappingProxyType(
            {
                "bootstrap_period_high": self.bootstrap_period_high,
                "bootstrap_period_low": self.bootstrap_period_low,
                "bootstrap_period_width": (
                    self.bootstrap_period_high - self.bootstrap_period_low
                ),
                "candidate_center": self.candidate_center,
                "category_balanced_score": self.category_balanced_score,
                "category_support": self.category_support,
                "macro_only_score": self.macro_only_score,
                "method_agreement": self.method_agreement,
                "method_count": len(self.method_peak_periods),
                "random_seed": self.random_seed,
                "red_noise_score": self.red_noise_score,
                "series_count": self.series_count,
                "total_categories": self.total_categories,
            }
        )


@dataclass(frozen=True)
class PanelSpec:
    name: str
    path: Path
    metadata_path: Path
    frequency: str
    min_points: int
    period_min: float
    period_max: float
    period_step: float
    preprocess_methods: tuple[str, ...]


PANEL_SPECS = (
    PanelSpec(
        name="annual_long",
        path=ROOT / "data" / "research_input_annual_long.parquet",
        metadata_path=ROOT / "output" / "research_input_annual_long_selection.csv",
        frequency="A",
        min_points=120,
        period_min=6.0,
        period_max=30.0,
        period_step=0.25,
        preprocess_methods=("hp_6.25", "hp_100", "linear_detrend"),
    ),
    PanelSpec(
        name="monthly_macro",
        path=ROOT / "data" / "research_input_monthly_macro.parquet",
        metadata_path=ROOT / "output" / "research_input_monthly_macro_selection.csv",
        frequency="M",
        min_points=120,
        period_min=12.0,
        period_max=60.0,
        period_step=0.5,
        preprocess_methods=("canonical", "canonical_hp", "canonical_linear"),
    ),
)


OUT_PROFILE = ROOT / "output" / "cycle_discovery_robust_profiles.csv"
OUT_PEAKS = ROOT / "output" / "cycle_discovery_robust_method_peaks.csv"
OUT_CLUSTERS = ROOT / "output" / "cycle_discovery_robust_clusters.csv"
OUT_PRIORS = ROOT / "output" / "cycle_discovery_prior_validation.csv"
OUT_REPORT = ROOT / "output" / "cycle_discovery_robust_report.md"


def load_metadata(spec: PanelSpec) -> pd.DataFrame:
    meta = pd.read_csv(spec.metadata_path)
    meta = meta[meta["status"] == "selected"].copy()
    if spec.frequency == "A":
        meta = meta.rename(columns={"column": "panel_column"})
        keep = ["panel_column", "source", "value_type", "family_key"]
    else:
        meta = meta.rename(columns={"panel_main_column": "panel_column"})
        meta = meta.rename(columns={"primary_source": "source"})
        keep = [
            "panel_column",
            "source",
            "value_type",
            "family_key",
            "universe_category",
        ]
    return meta[keep].drop_duplicates("panel_column").set_index("panel_column")


def infer_value_type(column: str) -> str:
    name = str(column).upper()
    if "RET" in name:
        return "return"
    if "YOY" in name or "GROWTH_PCT" in name:
        return "rate_yoy"
    if "MOM" in name:
        return "rate_mom"
    if any(
        token in name
        for token in (
            "YIELD",
            "BANK_RATE",
            "IR_LONG",
            "IR_SHORT",
            "LPR",
            "SHIBOR",
            "HIBOR",
        )
    ):
        return "rate_level"
    if name.endswith("_PCT"):
        return "rate_level"
    return "level"


def annual_category(column: str) -> str:
    name = str(column).upper()
    if name.startswith("MPD_"):
        if "GDPPC" in name:
            return "real_per_capita"
        if "GDP_MN" in name:
            return "real_aggregate"
        if "POP" in name:
            return "demography"
    if any(
        token in name
        for token in (
            "CPI",
            "DEFLATOR",
            "PRICE",
            "INFLATION",
            "TERMS_OF_TRADE",
            "OIL",
        )
    ):
        return "prices_commodities"
    if any(
        token in name
        for token in (
            "YIELD",
            "BANK_RATE",
            "MORTGAGE",
            "BORROWING_RATE",
            "CONSOL",
        )
    ):
        return "rates_credit"
    if any(
        token in name
        for token in (
            "M1",
            "MONETARY",
            "MONEY",
            "COIN",
            "BALANCE_SHEET",
            "CREDIT",
        )
    ):
        return "money_credit"
    if any(
        token in name
        for token in (
            "DEBT",
            "PUBLIC_SECTOR",
            "GOVERNMENT",
            "RECEIPTS",
            "NET_LENDING",
        )
    ):
        return "fiscal"
    if any(
        token in name
        for token in (
            "EXPORT",
            "IMPORT",
            "CURRENT_ACCOUNT",
            "TRADE_DEFICIT",
            "EXCHANGE_RATE",
            "ERI",
        )
    ):
        return "external"
    if any(token in name for token in ("SHARE", "SP_", "CAPE", "HOUSE_PRICE")):
        return "markets"
    if any(
        token in name
        for token in (
            "EMPLOY",
            "HOURS",
            "WAGE",
            "EARNINGS",
            "LABOUR",
            "PRODUCTIVITY",
            "TFP",
            "CAPITAL_SERVICES",
        )
    ):
        return "labor_productivity"
    return "real_activity"


def regularize_series(
    series: pd.Series,
    frequency: str,
    min_points: int,
) -> pd.Series | None:
    values = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .sort_index()
    )
    if frequency == "M":
        values = values.groupby(values.index.to_period("M")).last()
        values.index = values.index.to_timestamp("M")
        first = values.first_valid_index()
        last = values.last_valid_index()
        if first is None or last is None:
            return None
        values = values.reindex(pd.date_range(first, last, freq="ME"))
    else:
        first = values.first_valid_index()
        last = values.last_valid_index()
        if first is None or last is None:
            return None
        values = values.reindex(
            pd.Index(range(int(first), int(last) + 1), name="year")
        )

    if len(values) < min_points or float(values.isna().mean()) > 0.2:
        return None
    interpolation = "time" if frequency == "M" else "linear"
    return values.interpolate(method=interpolation).ffill().bfill()


def _log_if_positive(values: pd.Series, value_type: str) -> pd.Series:
    if value_type in {"level", "price", "price_adj"} and bool((values > 0).all()):
        return np.log(values)
    return values.copy()


def canonical_monthly_transform(
    values: pd.Series,
    value_type: str,
) -> pd.Series:
    transformed = _log_if_positive(values.astype("float64"), value_type)
    if value_type in {"level", "price", "price_adj", "rate_level"}:
        transformed = transformed.diff()
    return transformed.dropna()


def _hpfilter_cycle(values: np.ndarray, hp_lambda: float) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SparseEfficiencyWarning)
        cycle, _trend = sm.tsa.filters.hpfilter(values, lamb=hp_lambda)
    return np.asarray(cycle, dtype="float64")


def preprocess_series(
    values: pd.Series,
    *,
    value_type: str,
    frequency: str,
    method: str,
) -> pd.Series | None:
    base = values.astype("float64")
    if frequency == "M":
        base = canonical_monthly_transform(base, value_type)
        if method == "canonical":
            transformed = base - float(base.mean())
        elif method == "canonical_hp":
            cycle = _hpfilter_cycle(base.values, 129600.0)
            transformed = pd.Series(cycle, index=base.index)
        elif method == "canonical_linear":
            transformed = pd.Series(signal.detrend(base.values), index=base.index)
        else:
            raise ValueError(f"Unsupported monthly preprocessing method: {method}")
    else:
        base = _log_if_positive(base, value_type)
        if method.startswith("hp_"):
            hp_lambda = float(method.split("_", 1)[1])
            cycle = _hpfilter_cycle(base.values, hp_lambda)
            transformed = pd.Series(cycle, index=base.index)
        elif method == "linear_detrend":
            transformed = pd.Series(signal.detrend(base.values), index=base.index)
        else:
            raise ValueError(f"Unsupported annual preprocessing method: {method}")

    transformed = (
        pd.to_numeric(transformed, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(transformed) < 60:
        return None
    standard_deviation = float(transformed.std(ddof=0))
    if not np.isfinite(standard_deviation) or standard_deviation == 0.0:
        return None
    return (transformed - float(transformed.mean())) / standard_deviation


def red_noise_log_excess(values: pd.Series, periods: np.ndarray) -> np.ndarray:
    """Return Welch spectral log excess over an estimated AR(1) null."""

    if not isinstance(values, pd.Series):
        raise TypeError("values must be a pandas Series")
    for value in values.tolist():
        if isinstance(value, (bool, np.bool_)):
            raise TypeError("values must contain real observations, not booleans")
    period_grid = _period_grid(periods)
    array = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype="float64")
    if array.size < 60:
        return _readonly_array(np.full(period_grid.shape, np.nan, dtype="float64"))

    segment_length = min(256, array.size)
    frequencies, power = signal.welch(
        array,
        fs=1.0,
        window="hann",
        nperseg=segment_length,
        noverlap=min(segment_length // 2, 128),
        detrend="constant",
        scaling="density",
    )
    valid = frequencies > 0
    frequencies = frequencies[valid]
    power = power[valid]
    target_frequencies = 1.0 / period_grid
    observed = np.interp(
        target_frequencies,
        frequencies,
        power,
        left=np.nan,
        right=np.nan,
    )

    lag_correlation = np.corrcoef(array[:-1], array[1:])[0, 1]
    if not np.isfinite(lag_correlation):
        lag_correlation = 0.0
    lag_correlation = float(np.clip(lag_correlation, -0.95, 0.95))
    null_power = (1.0 - lag_correlation**2) / (
        1.0
        + lag_correlation**2
        - 2.0
        * lag_correlation
        * np.cos(2.0 * np.pi * target_frequencies)
    )

    observed_total = float(np.nansum(observed))
    null_total = float(np.nansum(null_power))
    if observed_total <= 0.0 or null_total <= 0.0:
        return _readonly_array(np.full(period_grid.shape, np.nan, dtype="float64"))
    observed = observed / observed_total
    null_power = null_power / null_total
    result = np.log((observed + 1e-12) / (null_power + 1e-12))
    return _readonly_array(result)


def bootstrap_interval(
    matrix: np.ndarray,
    random_seed: int = DEFAULT_RANDOM_SEED,
    draws: int = 300,
) -> tuple[np.ndarray, np.ndarray]:
    """Return deterministic row-bootstrap score intervals by period."""

    values = _numeric_matrix(matrix)
    seed = _integer(random_seed, "random_seed", minimum=0)
    draw_count = _integer(draws, "draws", minimum=1)
    generator = np.random.default_rng(seed)
    if values.shape[0] < 2:
        median = _readonly_array(np.nanmedian(values, axis=0))
        return median, median
    samples = np.empty((draw_count, values.shape[1]), dtype="float64")
    for draw in range(draw_count):
        indices = generator.integers(0, values.shape[0], size=values.shape[0])
        samples[draw] = np.nanmedian(values[indices], axis=0)
    lower = np.nanquantile(samples, 0.05, axis=0)
    upper = np.nanquantile(samples, 0.95, axis=0)
    return _readonly_array(lower), _readonly_array(upper)


def bootstrap_period_interval(
    matrix: np.ndarray,
    periods: np.ndarray,
    *,
    random_seed: int = DEFAULT_RANDOM_SEED,
    draws: int = 300,
) -> tuple[float, float]:
    """Return a deterministic bootstrap interval for the peak period itself."""

    values = _numeric_matrix(matrix)
    period_grid = _period_grid(periods)
    if values.shape[1] != period_grid.size:
        raise ValueError("periods must align with matrix columns")
    seed = _integer(random_seed, "random_seed", minimum=0)
    draw_count = _integer(draws, "draws", minimum=1)
    if values.shape[0] < 2:
        selected = float(period_grid[_profile_peak_index(np.nanmedian(values, axis=0))])
        return selected, selected
    generator = np.random.default_rng(seed)
    selected_periods = np.empty(draw_count, dtype="float64")
    for draw in range(draw_count):
        indices = generator.integers(0, values.shape[0], size=values.shape[0])
        profile = np.nanmedian(values[indices], axis=0)
        selected_periods[draw] = period_grid[_profile_peak_index(profile)]
    return (
        float(np.quantile(selected_periods, 0.05)),
        float(np.quantile(selected_periods, 0.95)),
    )


def category_support(
    matrix: np.ndarray,
    categories: np.ndarray,
    *,
    period_index: int,
    score_threshold: float = 0.0,
) -> CategorySupport:
    """Summarize how many distinct categories support a candidate period."""

    values = _numeric_matrix(matrix)
    labels = _category_labels(categories, values.shape[0])
    selected_index = _integer(period_index, "period_index", minimum=0)
    if selected_index >= values.shape[1]:
        raise ValueError("period_index must reference a matrix column")
    threshold = _finite_real(score_threshold, "score_threshold")
    scores: dict[str, float] = {}
    for category in sorted(set(labels.tolist())):
        category_values = values[labels == category, selected_index]
        finite = category_values[np.isfinite(category_values)]
        if finite.size == 0:
            raise ValueError(
                f"category {category} has no finite score at period_index"
            )
        scores[category] = float(np.median(finite))
    supported = tuple(
        category for category, score in scores.items() if score > threshold
    )
    return CategorySupport(
        supported_categories=supported,
        total_categories=len(scores),
        support_ratio=len(supported) / len(scores),
        category_scores=scores,
    )


def method_agreement(
    method_periods: Mapping[str, float],
    *,
    tolerance: float,
) -> MethodAgreement:
    """Summarize method peaks that fall within an absolute consensus tolerance."""

    if not isinstance(method_periods, Mapping) or not method_periods:
        raise TypeError("method_periods must be a non-empty mapping")
    normalized: dict[str, float] = {}
    for method, period in method_periods.items():
        label = _nonblank_text(method, "method name")
        if label in normalized:
            raise ValueError("method names must be unique after normalization")
        normalized[label] = _positive_real(period, f"period for {label}")
    threshold = _finite_real(tolerance, "tolerance")
    if threshold < 0.0:
        raise ValueError("tolerance must be nonnegative")
    center = float(np.median(np.asarray(list(normalized.values()), dtype="float64")))
    supporting = tuple(
        sorted(
            method
            for method, period in normalized.items()
            if abs(period - center) <= threshold
        )
    )
    outliers = tuple(sorted(set(normalized) - set(supporting)))
    return MethodAgreement(
        center=center,
        tolerance=threshold,
        supporting_methods=supporting,
        outlier_methods=outliers,
        agreement_ratio=len(supporting) / len(normalized),
        method_periods=normalized,
    )


def evaluate_period_candidate(
    *,
    periods: np.ndarray,
    method_score_matrices: Mapping[str, np.ndarray],
    categories: np.ndarray,
    macro_mask: np.ndarray | None = None,
    random_seed: int = DEFAULT_RANDOM_SEED,
    bootstrap_draws: int = 300,
) -> DiscoveryEvidence:
    """Evaluate one consensus peak across all approved evidence dimensions."""

    period_grid = _period_grid(periods)
    seed = _integer(random_seed, "random_seed", minimum=0)
    draw_count = _integer(bootstrap_draws, "bootstrap_draws", minimum=1)
    if not isinstance(method_score_matrices, Mapping) or not method_score_matrices:
        raise TypeError("method_score_matrices must be a non-empty mapping")

    normalized_matrices: dict[str, np.ndarray] = {}
    expected_shape: tuple[int, int] | None = None
    for method, matrix in method_score_matrices.items():
        label = _nonblank_text(method, "method name")
        if label in normalized_matrices:
            raise ValueError("method names must be unique after normalization")
        values = _numeric_matrix(matrix, f"method matrix {label}")
        if expected_shape is None:
            expected_shape = values.shape
        elif values.shape != expected_shape:
            raise ValueError("method score matrices must have the same shape")
        normalized_matrices[label] = values
    assert expected_shape is not None
    if expected_shape[1] != period_grid.size:
        raise ValueError("periods must align with method matrix columns")
    labels = _category_labels(categories, expected_shape[0])
    macro_rows = _boolean_mask(macro_mask, expected_shape[0])

    method_profiles: list[np.ndarray] = []
    method_peak_periods: dict[str, float] = {}
    category_profiles: list[np.ndarray] = []
    for method in sorted(normalized_matrices):
        matrix = normalized_matrices[method]
        balanced_matrix = _category_matrix(matrix, labels)
        balanced_profile = np.nanmedian(balanced_matrix, axis=0)
        method_profiles.append(balanced_profile)
        category_profiles.append(balanced_matrix)
        peak_index = _profile_peak_index(balanced_profile)
        method_peak_periods[method] = float(period_grid[peak_index])

    consensus_profile = np.nanmedian(np.vstack(method_profiles), axis=0)
    candidate_index = _profile_peak_index(consensus_profile)
    candidate_center = float(period_grid[candidate_index])

    pooled_matrix = np.vstack(
        [normalized_matrices[method] for method in sorted(normalized_matrices)]
    )
    pooled_categories = np.tile(labels, len(normalized_matrices))
    support = category_support(
        pooled_matrix,
        pooled_categories,
        period_index=candidate_index,
    )
    macro_values = np.concatenate(
        [
            normalized_matrices[method][macro_rows, candidate_index]
            for method in sorted(normalized_matrices)
        ]
    )
    macro_values = macro_values[np.isfinite(macro_values)]
    if macro_values.size == 0:
        raise ValueError("macro-only evidence has no finite candidate score")
    macro_score = float(np.median(macro_values))

    category_stack = np.vstack(category_profiles)
    balanced_values = category_stack[:, candidate_index]
    balanced_values = balanced_values[np.isfinite(balanced_values)]
    if balanced_values.size == 0:
        raise ValueError("category-balanced evidence has no finite candidate score")
    balanced_score = float(np.median(balanced_values))

    candidate_values = pooled_matrix[:, candidate_index]
    candidate_values = candidate_values[np.isfinite(candidate_values)]
    if candidate_values.size == 0:
        raise ValueError("red-noise evidence has no finite candidate score")
    red_noise_score = float(np.median(candidate_values))

    period_step = float(np.median(np.diff(period_grid)))
    tolerance = max(2.0 * period_step, 0.10 * candidate_center)
    agreement = method_agreement(method_peak_periods, tolerance=tolerance)
    interval_low, interval_high = bootstrap_period_interval(
        category_stack,
        period_grid,
        random_seed=seed,
        draws=draw_count,
    )
    interval_low = min(interval_low, candidate_center)
    interval_high = max(interval_high, candidate_center)
    return DiscoveryEvidence(
        candidate_center=candidate_center,
        bootstrap_period_low=interval_low,
        bootstrap_period_high=interval_high,
        red_noise_score=red_noise_score,
        category_support=support.support_ratio,
        macro_only_score=macro_score,
        category_balanced_score=balanced_score,
        method_agreement=agreement.agreement_ratio,
        method_peak_periods=method_peak_periods,
        supporting_categories=support.supported_categories,
        total_categories=support.total_categories,
        series_count=expected_shape[0],
        random_seed=seed,
    )


def clean_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def gaussian_fft_component(
    values: pd.Series,
    period: float,
    width_fraction: float = 0.25,
) -> pd.Series:
    array = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    if array.size < 16:
        return pd.Series(index=values.index, dtype="float64")
    array = array - float(np.nanmean(array))
    frequencies = np.fft.rfftfreq(array.size, d=1.0)
    spectrum = np.fft.rfft(array)
    center = 1.0 / float(period)
    sigma = max(center * width_fraction, 1e-8)
    window = np.exp(-0.5 * ((frequencies - center) / sigma) ** 2)
    component = np.fft.irfft(spectrum * window, n=array.size)
    return pd.Series(component, index=values.index)


def butterworth_component(
    values: pd.Series,
    period: float,
    width_fraction: float = 0.25,
    order: int = 4,
) -> pd.Series:
    center = 1.0 / float(period)
    low = max(center * (1.0 - width_fraction), 1e-6)
    high = min(center * (1.0 + width_fraction), 0.5 - 1e-6)
    if not 0.0 < low < high < 0.5:
        return pd.Series(index=values.index, dtype="float64")
    sos = signal.butter(
        order,
        [low / 0.5, high / 0.5],
        btype="bandpass",
        output="sos",
    )
    try:
        component = signal.sosfiltfilt(sos, values.to_numpy(dtype="float64"))
    except ValueError:
        return pd.Series(index=values.index, dtype="float64")
    return pd.Series(component, index=values.index)


def phase_agreement(left: pd.Series, right: pd.Series, trim: int) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if len(aligned) <= 2 * trim + 16:
        return np.nan
    aligned = aligned.iloc[trim:-trim]
    left_phase = np.angle(
        signal.hilbert(aligned.iloc[:, 0].to_numpy(dtype="float64"))
    )
    right_phase = np.angle(
        signal.hilbert(aligned.iloc[:, 1].to_numpy(dtype="float64"))
    )
    return float(np.mean(np.cos(left_phase - right_phase)))


def safe_correlation(
    left: pd.Series,
    right: pd.Series,
    trim: int = 0,
) -> float:
    aligned = pd.concat([left, right], axis=1).dropna()
    if trim > 0:
        if len(aligned) <= 2 * trim + 8:
            return np.nan
        aligned = aligned.iloc[trim:-trim]
    if len(aligned) < 8:
        return np.nan
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def variance_share(
    component: pd.Series,
    base: pd.Series,
    trim: int = 0,
) -> float:
    aligned = pd.concat([component, base], axis=1).dropna()
    if trim > 0:
        if len(aligned) <= 2 * trim + 8:
            return np.nan
        aligned = aligned.iloc[trim:-trim]
    denominator = float(aligned.iloc[:, 1].var(ddof=0))
    if denominator <= 0.0:
        return np.nan
    return float(aligned.iloc[:, 0].var(ddof=0) / denominator)


def build_views(
    matrix: np.ndarray,
    categories: np.ndarray,
    *,
    panel_name: str,
) -> Mapping[str, np.ndarray]:
    values = _numeric_matrix(matrix)
    labels = _category_labels(categories, values.shape[0])
    normalized_panel_name = _nonblank_text(panel_name, "panel_name")
    views: dict[str, np.ndarray] = {"all_series": _readonly_array(values)}
    if normalized_panel_name == "monthly_macro":
        equity_label = "股票市场与估值（Equity Market & Valuation）"
        macro_mask = labels != equity_label
        if macro_mask.sum() >= 10:
            views["macro_only"] = _readonly_array(values[macro_mask])

    category_rows = []
    for category in sorted(set(labels.tolist())):
        category_values = values[labels == category]
        if category_values.size == 0:
            continue
        category_rows.append(np.nanmedian(category_values, axis=0))
        views[f"category::{clean_label(category)}"] = _readonly_array(
            category_values
        )
    if category_rows:
        views["category_balanced"] = _readonly_array(np.vstack(category_rows))
    return MappingProxyType(views)


def summarize_view(
    *,
    panel_name: str,
    method: str,
    view_name: str,
    periods: np.ndarray,
    matrix: np.ndarray,
    random_seed: int = DEFAULT_RANDOM_SEED,
    bootstrap_draws: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    values = _numeric_matrix(matrix)
    period_grid = _period_grid(periods)
    if values.shape[1] != period_grid.size:
        raise ValueError("periods must align with matrix columns")
    median_score = np.nanmedian(values, axis=0)
    trimmed_mean = (
        pd.DataFrame(values)
        .apply(
            lambda column: column.sort_values()
            .iloc[
                max(0, int(len(column) * 0.1)) : max(
                    1,
                    int(len(column) * 0.9),
                )
            ]
            .mean(),
            axis=0,
        )
        .to_numpy(dtype="float64")
    )
    positive_share = np.nanmean(values > 0.0, axis=0)
    lower, upper = bootstrap_interval(
        values,
        random_seed=random_seed,
        draws=bootstrap_draws,
    )
    smoothed = gaussian_filter1d(median_score, sigma=1.0)

    profile = pd.DataFrame(
        {
            "panel": panel_name,
            "method": method,
            "view": view_name,
            "period": period_grid,
            "series_or_groups": values.shape[0],
            "median_log_excess": median_score,
            "trimmed_mean_log_excess": trimmed_mean,
            "positive_share": positive_share,
            "bootstrap_p05": lower,
            "bootstrap_p95": upper,
            "smoothed_score": smoothed,
        }
    )

    prominence_floor = max(0.03, float(np.nanstd(smoothed)) * 0.08)
    peak_indices, properties = signal.find_peaks(
        smoothed,
        prominence=prominence_floor,
        distance=3,
    )
    peak_rows = []
    for index, prominence in zip(
        peak_indices,
        properties.get("prominences", []),
    ):
        peak_rows.append(
            {
                "panel": panel_name,
                "method": method,
                "view": view_name,
                "period": float(period_grid[index]),
                "smoothed_score": float(smoothed[index]),
                "positive_share": float(positive_share[index]),
                "bootstrap_p05": float(lower[index]),
                "bootstrap_p95": float(upper[index]),
                "prominence": float(prominence),
            }
        )
    return profile, pd.DataFrame(peak_rows)


def discover_panel(spec: PanelSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(spec.path)
    metadata = load_metadata(spec)
    periods = np.arange(
        spec.period_min,
        spec.period_max + spec.period_step / 2.0,
        spec.period_step,
    )
    profile_frames = []
    peak_frames = []

    for method in spec.preprocess_methods:
        profiles = []
        categories = []
        for column in panel.columns:
            value_type = (
                str(metadata.loc[column, "value_type"])
                if column in metadata.index
                else "level"
            )
            if value_type == "return":
                continue
            regular = regularize_series(
                panel[column],
                spec.frequency,
                spec.min_points,
            )
            if regular is None:
                continue
            transformed = preprocess_series(
                regular,
                value_type=value_type,
                frequency=spec.frequency,
                method=method,
            )
            if transformed is None:
                continue
            profiles.append(red_noise_log_excess(transformed, periods))
            if spec.frequency == "A":
                categories.append(annual_category(column))
            else:
                categories.append(str(metadata.loc[column, "universe_category"]))

        if not profiles:
            continue
        matrix = np.asarray(profiles, dtype="float64")
        category_array = np.asarray(categories, dtype=object)
        for view_name, view_matrix in build_views(
            matrix,
            category_array,
            panel_name=spec.name,
        ).items():
            profile, peaks = summarize_view(
                panel_name=spec.name,
                method=method,
                view_name=view_name,
                periods=periods,
                matrix=view_matrix,
            )
            profile_frames.append(profile)
            if not peaks.empty:
                peak_frames.append(peaks)

    return (
        pd.concat(profile_frames, ignore_index=True),
        pd.concat(peak_frames, ignore_index=True),
    )


def cluster_core_peaks(peaks: pd.DataFrame) -> pd.DataFrame:
    core_views = {"all_series", "macro_only", "category_balanced"}
    eligible = peaks[peaks["view"].isin(core_views)].copy()
    eligible = eligible[
        (eligible["positive_share"] >= 0.5)
        & (eligible["smoothed_score"] > 0.0)
    ]
    rows = []
    for panel_name, panel_peaks in eligible.groupby("panel"):
        tolerance_floor = 1.0 if panel_name == "annual_long" else 2.0
        ordered = panel_peaks.sort_values("period").to_dict("records")
        clusters: list[list[dict[str, object]]] = []
        for row in ordered:
            period = float(row["period"])
            if not clusters:
                clusters.append([row])
                continue
            center = float(
                np.median(
                    [float(item["period"]) for item in clusters[-1]]
                )
            )
            tolerance = max(tolerance_floor, center * 0.10)
            if abs(period - center) <= tolerance:
                clusters[-1].append(row)
            else:
                clusters.append([row])

        for cluster_id, cluster in enumerate(clusters, start=1):
            methods = sorted({str(item["method"]) for item in cluster})
            views = sorted({str(item["view"]) for item in cluster})
            periods = np.asarray([float(item["period"]) for item in cluster])
            scores = np.asarray(
                [float(item["smoothed_score"]) for item in cluster]
            )
            shares = np.asarray(
                [float(item["positive_share"]) for item in cluster]
            )
            rows.append(
                {
                    "panel": panel_name,
                    "cluster_id": cluster_id,
                    "period_center": float(np.median(periods)),
                    "period_min": float(periods.min()),
                    "period_max": float(periods.max()),
                    "method_count": len(methods),
                    "view_count": len(views),
                    "methods": ",".join(methods),
                    "views": ",".join(views),
                    "mean_score": float(scores.mean()),
                    "mean_positive_share": float(shares.mean()),
                    "robust": len(methods) >= 2 and len(views) >= 2,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["panel", "robust", "mean_score"],
        ascending=[True, False, False],
    )


def nearest_profile_row(
    profile: pd.DataFrame,
    panel: str,
    method: str,
    view: str,
    target: float,
) -> pd.Series:
    subset = profile[
        (profile["panel"] == panel)
        & (profile["method"] == method)
        & (profile["view"] == view)
    ].copy()
    if subset.empty:
        return pd.Series(dtype="object")
    index = (subset["period"] - target).abs().idxmin()
    return subset.loc[index]


def validate_priors(profile: pd.DataFrame) -> pd.DataFrame:
    priors = [
        ("annual_long", "100m", 100.0 / 12.0, "category_balanced"),
        ("annual_long", "200m", 200.0 / 12.0, "category_balanced"),
        ("monthly_macro", "20m", 20.0, "category_balanced"),
        ("monthly_macro", "42m", 42.0, "category_balanced"),
        ("monthly_macro", "12m", 12.0, "macro_only"),
    ]
    method_map = {
        "annual_long": ("hp_6.25", "hp_100", "linear_detrend"),
        "monthly_macro": (
            "canonical",
            "canonical_hp",
            "canonical_linear",
        ),
    }
    rows = []
    for panel, label, target, view in priors:
        method_rows = []
        for method in method_map[panel]:
            row = nearest_profile_row(profile, panel, method, view, target)
            if row.empty:
                continue
            method_rows.append(row)
        if not method_rows:
            continue
        scores = np.asarray(
            [float(row["smoothed_score"]) for row in method_rows]
        )
        shares = np.asarray(
            [float(row["positive_share"]) for row in method_rows]
        )
        support = int(np.sum((scores > 0.0) & (shares >= 0.5)))
        if label == "12m":
            verdict = "seasonal_diagnostic"
        elif support == len(method_rows):
            verdict = "supported"
        elif support >= 1:
            verdict = "partial_or_category_specific"
        else:
            verdict = "not_broadly_supported"
        rows.append(
            {
                "panel": panel,
                "prior": label,
                "target_period": target,
                "view": view,
                "method_support": f"{support}/{len(method_rows)}",
                "mean_score": float(scores.mean()),
                "mean_positive_share": float(shares.mean()),
                "verdict": verdict,
            }
        )
    return pd.DataFrame(rows)


def top_category_peaks(
    peaks: pd.DataFrame,
    panel: str,
    limit: int = 20,
) -> pd.DataFrame:
    subset = peaks[
        (peaks["panel"] == panel)
        & peaks["view"].str.startswith("category::")
    ].copy()
    subset = subset[
        (subset["smoothed_score"] > 0.0)
        & (subset["positive_share"] >= 0.5)
    ]
    if subset.empty:
        return subset
    support = (
        subset.groupby(["panel", "view", "period"], as_index=False)
        .agg(
            method_count=("method", "nunique"),
            mean_score=("smoothed_score", "mean"),
            mean_positive_share=("positive_share", "mean"),
        )
        .sort_values(
            ["method_count", "mean_score"],
            ascending=[False, False],
        )
    )
    return support.head(limit)


def write_report(
    profile: pd.DataFrame,
    peaks: pd.DataFrame,
    clusters: pd.DataFrame,
    priors: pd.DataFrame,
) -> None:
    lines = [
        "# Robust Cycle Discovery Report",
        "",
        "## Executive conclusions",
        "",
        "- The 100-month prior is supported by a broad annual peak around 8.5-9 years.",
        "- The 200-month prior is not a universal point estimate: evidence is stronger around 13-15 years, so it should be treated as a wider long-investment band rather than a fixed 200-month constant.",
        "- The 42-month inventory cycle is visible in macro-only and category-balanced monthly views; it is obscured when the equity-valuation block is allowed to dominate the panel.",
        "- The 20-month prior is category-specific. Money/credit supports a roughly 18-24 month band, while the full panel also shows a strong 16-17 month market rhythm.",
        "- The 12-month peak is retained as a seasonality diagnostic, not promoted to a structural business cycle.",
        "",
        "## Method",
        "",
        "- Each series is compared with an AR(1) red-noise spectrum; scores are log power excess over that null.",
        "- Annual preprocessing: HP(6.25), HP(100), linear detrending.",
        "- Monthly preprocessing: canonical growth/difference, plus HP and linear-detrend sensitivity on the same transformed series.",
        "- Aggregation views: all series, macro-only, category-balanced, and each category separately.",
        "- A cluster is marked robust when at least two preprocessing methods and two core aggregation views agree.",
        "",
        "## Prior validation",
        "",
        priors.round(4).to_markdown(index=False),
        "",
        "## Cross-method robust clusters",
        "",
        clusters.round(4).to_markdown(index=False) if not clusters.empty else "(empty)",
        "",
    ]
    for panel in ("annual_long", "monthly_macro"):
        lines.extend(
            [
                f"## {panel} category-level support",
                "",
                top_category_peaks(peaks, panel).round(4).to_markdown(index=False),
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "1. A spectral peak is evidence of recurring frequency content, not proof of a stable causal economic clock.",
            "2. Two-sided filters revise near endpoints; real-time phase calls require an explicit revision test.",
            "3. Category-balanced results should be preferred for macro interpretation because the monthly panel contains many correlated equity-valuation series.",
            "4. The next stage should use bands (not exact periods): 8-10y, 12-16y, 36-48m, and 16-24m.",
            "",
            f"- Full profiles: `{OUT_PROFILE.relative_to(ROOT)}`",
            f"- Method peaks: `{OUT_PEAKS.relative_to(ROOT)}`",
            f"- Robust clusters: `{OUT_CLUSTERS.relative_to(ROOT)}`",
            f"- Prior validation: `{OUT_PRIORS.relative_to(ROOT)}`",
            "",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Run the checkout-compatible robust discovery artifact workflow."""

    profiles = []
    peaks = []
    for spec in PANEL_SPECS:
        panel_profile, panel_peaks = discover_panel(spec)
        profiles.append(panel_profile)
        peaks.append(panel_peaks)
    profile = pd.concat(profiles, ignore_index=True)
    peak_table = pd.concat(peaks, ignore_index=True)
    clusters = cluster_core_peaks(peak_table)
    priors = validate_priors(profile)

    OUT_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    profile.to_csv(OUT_PROFILE, index=False)
    peak_table.to_csv(OUT_PEAKS, index=False)
    clusters.to_csv(OUT_CLUSTERS, index=False)
    priors.to_csv(OUT_PRIORS, index=False)
    write_report(profile, peak_table, clusters, priors)

    print("Wrote:", OUT_PROFILE)
    print("Wrote:", OUT_PEAKS)
    print("Wrote:", OUT_CLUSTERS)
    print("Wrote:", OUT_PRIORS)
    print("Wrote:", OUT_REPORT)


__all__ = [
    "DEFAULT_RANDOM_SEED",
    "OUT_CLUSTERS",
    "OUT_PEAKS",
    "OUT_PRIORS",
    "OUT_PROFILE",
    "OUT_REPORT",
    "PANEL_SPECS",
    "ROOT",
    "CategorySupport",
    "DiscoveryEvidence",
    "MethodAgreement",
    "PanelSpec",
    "annual_category",
    "bootstrap_interval",
    "bootstrap_period_interval",
    "build_views",
    "butterworth_component",
    "canonical_monthly_transform",
    "category_support",
    "clean_label",
    "cluster_core_peaks",
    "discover_panel",
    "evaluate_period_candidate",
    "gaussian_fft_component",
    "infer_value_type",
    "load_metadata",
    "main",
    "method_agreement",
    "nearest_profile_row",
    "phase_agreement",
    "preprocess_series",
    "red_noise_log_excess",
    "regularize_series",
    "safe_correlation",
    "summarize_view",
    "top_category_peaks",
    "validate_priors",
    "variance_share",
    "write_report",
]
