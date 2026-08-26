"""Direct, duration-aware C2 housing-cycle state dating."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


PHASE_ORDER = ("recovery", "expansion", "slowdown", "contraction")
DEFAULT_MOMENTUM_WINDOWS = (1, 2, 3)
DEFAULT_DATING_SIGMAS = (1.0, 1.5, 2.0)
DEFAULT_DATING_PROMINENCE_SCALES = (0.20, 0.30, 0.40)
DEFAULT_DATING_DISTANCES = (6, 8)
BIS_AREA_BY_ISO = {
    "CHN": "CN",
    "USA": "US",
    "JPN": "JP",
    "GBR": "GB",
}


def bis_area_code(iso: str) -> str:
    """Translate project ISO3 identities to BIS two-letter area codes."""

    return BIS_AREA_BY_ISO.get(iso, iso)


def estimate_c2_lead_lag(
    source: pd.Series,
    target: pd.Series,
    *,
    maximum_lag_years: int = 5,
    minimum_overlap: int = 12,
) -> dict[str, object]:
    """Estimate whether the source C2 track leads or lags the target track."""

    source_numeric = pd.to_numeric(source, errors="coerce")
    target_numeric = pd.to_numeric(target, errors="coerce")
    candidates: list[tuple[int, int, float]] = []
    for lead_years in range(-maximum_lag_years, maximum_lag_years + 1):
        aligned = pd.concat(
            {
                "source": source_numeric.shift(lead_years),
                "target": target_numeric,
            },
            axis=1,
        ).dropna()
        if len(aligned) < minimum_overlap:
            continue
        correlation = float(aligned["source"].corr(aligned["target"]))
        if np.isfinite(correlation):
            candidates.append((lead_years, len(aligned), correlation))
    if not candidates:
        return {
            "leadYears": None,
            "observations": 0,
            "correlation": None,
            "simultaneousCorrelation": None,
            "correlationImprovement": None,
            "materialLag": False,
        }
    best = max(candidates, key=lambda row: (row[2], row[1], -abs(row[0])))
    simultaneous = next(
        (correlation for lag, _, correlation in candidates if lag == 0),
        None,
    )
    improvement = (
        best[2] - simultaneous if simultaneous is not None else None
    )
    material_lag = bool(
        best[0] != 0
        and best[2] >= 0.40
        and improvement is not None
        and improvement >= 0.10
    )
    return {
        "leadYears": best[0],
        "observations": best[1],
        "correlation": best[2],
        "simultaneousCorrelation": simultaneous,
        "correlationImprovement": improvement,
        "materialLag": material_lag,
    }


def _persistent_sign(values: pd.Series, deadband: pd.Series) -> pd.Series:
    state = 0
    signs: list[int] = []
    for value, threshold in zip(values, deadband.reindex(values.index), strict=True):
        if not np.isfinite(value):
            signs.append(state)
            continue
        bound = float(threshold) if np.isfinite(threshold) else 0.0
        if value > bound:
            state = 1
        elif value < -bound:
            state = -1
        elif state == 0:
            state = 1 if value >= 0 else -1
        signs.append(state)
    return pd.Series(signs, index=values.index, dtype="int64")


def _phase(level_sign: int, slope_sign: int) -> str:
    if level_sign < 0 and slope_sign >= 0:
        return "recovery"
    if level_sign >= 0 and slope_sign >= 0:
        return "expansion"
    if level_sign >= 0 and slope_sign < 0:
        return "slowdown"
    return "contraction"


def _adjacent_phase_candidate(current: str, candidate: str) -> str:
    if candidate == current:
        return candidate
    current_index = PHASE_ORDER.index(current)
    candidate_index = PHASE_ORDER.index(candidate)
    if (candidate_index - current_index) % len(PHASE_ORDER) == 2:
        return PHASE_ORDER[(current_index + 1) % len(PHASE_ORDER)]
    return candidate


def _confirm_transitions(
    raw_phase: pd.Series,
    *,
    confirmation_periods: int = 2,
) -> tuple[pd.Series, pd.Series]:
    confirmed: list[str] = []
    confirmed_at: list[object] = []
    current = str(raw_phase.iloc[0])
    pending: str | None = None
    pending_count = 0
    transition_date: object = raw_phase.index[0]
    for date, phase in raw_phase.items():
        candidate = _adjacent_phase_candidate(current, str(phase))
        if candidate == current:
            pending = None
            pending_count = 0
        elif candidate == pending:
            pending_count += 1
        else:
            pending = candidate
            pending_count = 1
        if pending is not None and pending_count >= confirmation_periods:
            current = pending
            transition_date = date
            pending = None
            pending_count = 0
        confirmed.append(current)
        confirmed_at.append(transition_date)
    return (
        pd.Series(confirmed, index=raw_phase.index, dtype="object"),
        pd.Series(confirmed_at, index=raw_phase.index, dtype="object"),
    )


def build_direct_c2_state(
    activity: pd.Series,
    *,
    confirmation_periods: int = 2,
    minimum_history: int = 20,
    momentum_windows: tuple[int, ...] = DEFAULT_MOMENTUM_WINDOWS,
) -> pd.DataFrame:
    """Date C2 from activity and momentum without imposing a sine-wave period."""

    numeric = pd.to_numeric(activity, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    if not momentum_windows or any(window <= 0 for window in momentum_windows):
        raise ValueError("momentum_windows must contain positive integers")
    slopes = pd.DataFrame(
        {
            f"slope{window}Y": numeric.diff(window) / float(window)
            for window in momentum_windows
        },
        index=numeric.index,
    )
    slope_signs = pd.DataFrame(index=numeric.index)
    for column in slopes:
        scale = slopes[column].expanding(
            min_periods=minimum_history
        ).std(ddof=0).shift(1)
        band = (scale * 0.15).clip(lower=0.025).fillna(0.0)
        slope_signs[column] = _persistent_sign(slopes[column], band)
    slope_consensus = slope_signs.mean(axis=1)
    consensus_band = pd.Series(0.25, index=numeric.index)
    slope_sign = _persistent_sign(slope_consensus, consensus_band)
    slope = slopes.median(axis=1, skipna=True)
    curvature = slope.diff()
    level_scale = numeric.expanding(min_periods=minimum_history).std(ddof=0).shift(1)
    level_band = (level_scale * 0.12).clip(lower=0.08).fillna(0.0)
    level_sign = _persistent_sign(numeric, level_band)
    raw_phase = pd.Series(
        [_phase(int(level_sign.loc[date]), int(slope_sign.loc[date])) for date in numeric.index],
        index=numeric.index,
        dtype="object",
    )
    phase, confirmed_at = _confirm_transitions(
        raw_phase,
        confirmation_periods=confirmation_periods,
    )
    duration = phase.groupby(phase.ne(phase.shift()).cumsum()).cumcount() + 1
    return pd.DataFrame(
        {
            "activity": numeric,
            "slope": slope,
            "curvature": curvature,
            "levelDeadband": level_band,
            "levelDirection": level_sign,
            "slopeDirection": slope_sign,
            "slopeConsensus": slope_consensus,
            "rawPhase": raw_phase,
            "phase": phase,
            "phaseConfirmedAt": confirmed_at,
            "phaseDurationYears": duration.astype(int),
            **{column: slopes[column] for column in slopes},
        },
        index=numeric.index,
    )


def _cluster_turning_candidates(
    candidates: list[dict[str, object]],
    *,
    specification_count: int,
    minimum_support: float,
    tolerance_years: int,
) -> list[dict[str, object]]:
    accepted: list[dict[str, object]] = []
    for kind in ("peak", "trough"):
        clusters: list[list[dict[str, object]]] = []
        for candidate in sorted(
            (row for row in candidates if row["kind"] == kind),
            key=lambda row: int(row["year"]),
        ):
            matched: list[dict[str, object]] | None = None
            for cluster in reversed(clusters):
                center = float(np.median([int(row["year"]) for row in cluster]))
                if int(candidate["year"]) - center > tolerance_years:
                    break
                if abs(int(candidate["year"]) - center) <= tolerance_years:
                    matched = cluster
                    break
            if matched is None:
                clusters.append([candidate])
            else:
                matched.append(candidate)

        for cluster in clusters:
            specifications = {str(row["specification"]) for row in cluster}
            support = len(specifications) / specification_count
            if support < minimum_support:
                continue
            years = [int(row["year"]) for row in cluster]
            accepted.append(
                {
                    "year": int(round(float(np.median(years)))),
                    "yearLow": min(years),
                    "yearHigh": max(years),
                    "kind": kind,
                    "support": support,
                    "supportCount": len(specifications),
                    "specificationCount": specification_count,
                    "prominence": float(
                        np.median([float(row["prominence"]) for row in cluster])
                    ),
                    "value": float(
                        np.median([float(row["value"]) for row in cluster])
                    ),
                }
            )

    turns: list[dict[str, object]] = []
    for candidate in sorted(accepted, key=lambda row: int(row["year"])):
        if not turns or turns[-1]["kind"] != candidate["kind"]:
            turns.append(candidate)
            continue
        current_rank = (
            float(candidate["support"]),
            float(candidate["prominence"]),
            float(candidate["value"])
            if candidate["kind"] == "peak"
            else -float(candidate["value"]),
        )
        previous_rank = (
            float(turns[-1]["support"]),
            float(turns[-1]["prominence"]),
            float(turns[-1]["value"])
            if turns[-1]["kind"] == "peak"
            else -float(turns[-1]["value"]),
        )
        if current_rank > previous_rank:
            turns[-1] = candidate
    return turns


def build_c2_historical_dating(
    activity: pd.Series,
    *,
    sigmas: tuple[float, ...] = DEFAULT_DATING_SIGMAS,
    prominence_scales: tuple[float, ...] = DEFAULT_DATING_PROMINENCE_SCALES,
    minimum_distances: tuple[int, ...] = DEFAULT_DATING_DISTANCES,
    minimum_support: float = 0.50,
    tolerance_years: int = 2,
) -> dict[str, object]:
    """Date retrospective C2 peaks and troughs from robust filter consensus."""

    numeric = pd.to_numeric(activity, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    numeric = numeric.interpolate(limit_direction="both")
    if len(numeric) < 30:
        raise ValueError("C2 historical dating needs at least 30 observations")
    if not sigmas or not prominence_scales or not minimum_distances:
        raise ValueError("historical dating specifications cannot be empty")

    robust_scale = float(
        np.median(np.abs(numeric - float(np.median(numeric)))) * 1.4826
    )
    candidates: list[dict[str, object]] = []
    specification_count = 0
    for sigma in sigmas:
        smoothed = pd.Series(
            gaussian_filter1d(
                numeric.to_numpy(dtype="float64"),
                sigma=float(sigma),
                mode="nearest",
            ),
            index=numeric.index,
        )
        for prominence_scale in prominence_scales:
            prominence = max(0.10, robust_scale * float(prominence_scale))
            for distance in minimum_distances:
                specification_count += 1
                specification = f"g{sigma:.1f}-p{prominence_scale:.2f}-d{distance}"
                for kind, values in (
                    ("peak", smoothed.to_numpy()),
                    ("trough", -smoothed.to_numpy()),
                ):
                    positions, properties = find_peaks(
                        values,
                        distance=int(distance),
                        prominence=prominence,
                    )
                    for position, detected_prominence in zip(
                        positions,
                        properties["prominences"],
                        strict=True,
                    ):
                        if position < 3 or position > len(smoothed) - 4:
                            continue
                        candidates.append(
                            {
                                "year": int(smoothed.index[position]),
                                "kind": kind,
                                "value": float(smoothed.iloc[position]),
                                "prominence": float(detected_prominence),
                                "specification": specification,
                            }
                        )

    turns = _cluster_turning_candidates(
        candidates,
        specification_count=specification_count,
        minimum_support=minimum_support,
        tolerance_years=tolerance_years,
    )
    intervals: list[int] = []
    for kind in ("peak", "trough"):
        years = [int(row["year"]) for row in turns if row["kind"] == kind]
        intervals.extend(np.diff(years).astype(int).tolist())
    return {
        "turningPoints": turns,
        "specificationCount": specification_count,
        "minimumSupport": minimum_support,
        "medianIntervalYears": (
            float(np.median(intervals)) if intervals else None
        ),
        "intervalIqrYears": (
            [float(np.quantile(intervals, 0.25)), float(np.quantile(intervals, 0.75))]
            if intervals
            else [None, None]
        ),
        "method": (
            "多组高斯平滑尺度、显著度和最小间隔共同投票；只有多数参数均识别的峰谷才进入历史定年。"
        ),
        "lookAhead": True,
        "usage": "仅用于历史复盘和专家校准，不用于实时转相信号。",
    }


def date_c2_turning_points(state: pd.DataFrame) -> list[dict[str, object]]:
    """Convert persistent momentum reversals into real-time identifiable turns."""

    candidates: list[dict[str, object]] = []
    direction = pd.to_numeric(state["slopeDirection"], errors="coerce").fillna(0)
    for position in range(1, len(state) - 1):
        previous_direction = int(direction.iloc[position - 1])
        candidate_direction = int(direction.iloc[position])
        if (
            previous_direction == candidate_direction
            or int(direction.iloc[position + 1]) != candidate_direction
        ):
            continue
        kind = (
            "peak"
            if previous_direction > 0 and candidate_direction < 0
            else "trough"
            if previous_direction < 0 and candidate_direction > 0
            else None
        )
        if kind is None:
            continue
        window = state.iloc[max(0, position - 3) : position + 2]
        turning_date = (
            window["activity"].idxmax()
            if kind == "peak"
            else window["activity"].idxmin()
        )
        candidates.append(
            {
                "year": int(turning_date),
                "identifiedAt": int(state.index[position + 1]),
                "kind": kind,
                "value": float(state.loc[turning_date, "activity"]),
            }
        )
    turns: list[dict[str, object]] = []
    for candidate in candidates:
        if not turns or turns[-1]["kind"] != candidate["kind"]:
            turns.append(candidate)
            continue
        replace = (
            candidate["value"] > turns[-1]["value"]
            if candidate["kind"] == "peak"
            else candidate["value"] < turns[-1]["value"]
        )
        if replace:
            turns[-1] = candidate
    return turns


def future_transition_target(phases: pd.Series, horizon: int) -> pd.Series:
    """Flag whether the confirmed C2 phase changes within the next horizon."""

    future = pd.concat(
        [phases.shift(-step).ne(phases) for step in range(1, horizon + 1)],
        axis=1,
    )
    available = pd.concat(
        [phases.shift(-step).notna() for step in range(1, horizon + 1)],
        axis=1,
    ).all(axis=1)
    return future.any(axis=1).astype(float).where(available)
