from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
import math

import numpy as np
import pandas as pd


CYCLE_PERIODS = {
    "C2": 200.0,
    "C3": 100.0,
    "C4": 42.0,
    "C5": 20.0,
    "C6": 12.0,
    "C7": 6.0,
}
RIDGE_ALPHAS = (0.1, 1.0, 10.0, 100.0)
MINIMUM_OBSERVATIONS = 60
MINIMUM_CYCLE_REPEATS = 3.0
CROSS_FILTER_MIN_PATH_CORRELATION = 0.70
CROSS_FILTER_MAX_RELATIVE_POINT_DIFFERENCE = 0.75
CROSS_FILTER_MAX_ABSOLUTE_SHARE_DIFFERENCE = 0.15
CROSS_FILTER_MAX_VARIANCE_SHARE_DIFFERENCE = 0.15
CROSS_FILTER_GAIN_MINIMUM_TRACKS = 4
CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS = 24
CROSS_FILTER_GAIN_MINIMUM_VALIDATION_IMPROVEMENT = 0.02
CROSS_FILTER_GAIN_MINIMUM_AUDIT_IMPROVEMENT = 0.0
CROSS_FILTER_GAIN_FLOOR = 0.25
CROSS_FILTER_GAIN_CEILING = 4.0


def _period_text(value: object) -> str:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m")
    return str(value)


def _filter_label(value: str) -> str:
    return {
        "gaussian_fft": "Gaussian FFT",
        "gaussian_dog": "Gaussian DoG",
        "butterworth_zero_phase": "Butterworth零相位",
    }.get(value, value)


def _safe_r2(actual: np.ndarray, predicted: np.ndarray) -> float:
    total = float(np.square(actual - actual.mean()).sum())
    if total <= 1e-12:
        return float("nan")
    residual = float(np.square(actual - predicted).sum())
    return 1.0 - residual / total


def _safe_correlation(left: pd.Series, right: pd.Series, trim: int = 0) -> float:
    frame = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if trim > 0 and len(frame) > trim * 2 + 12:
        frame = frame.iloc[trim:-trim]
    if len(frame) < 12:
        return float("nan")
    if float(frame["left"].std(ddof=0)) <= 1e-12:
        return float("nan")
    if float(frame["right"].std(ddof=0)) <= 1e-12:
        return float("nan")
    return float(frame["left"].corr(frame["right"]))


def _relative_difference(left: float, right: float) -> float:
    denominator = abs(left) + abs(right)
    if denominator <= 1e-12:
        return 0.0
    return abs(left - right) / denominator


def _finite_median(values: list[object]) -> float:
    numeric = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    return float(numeric.median())


def _normalized_absolute_error(
    primary: np.ndarray,
    comparison: np.ndarray,
) -> float:
    if primary.size == 0 or comparison.size != primary.size:
        return float("nan")
    return float(np.mean(np.abs(primary - comparison)))


def _relative_improvement(baseline: float, challenger: float) -> float:
    if not np.isfinite(baseline) or not np.isfinite(challenger):
        return float("nan")
    if baseline <= 1e-12:
        return 0.0
    return float((baseline - challenger) / baseline)


def _ridge_fit(
    features: np.ndarray,
    target: np.ndarray,
    alpha: float,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    feature_center = features.mean(axis=0)
    feature_scale = features.std(axis=0)
    feature_scale = np.where(feature_scale > 1e-12, feature_scale, 1.0)
    standardized = (features - feature_center) / feature_scale
    target_center = float(target.mean())
    centered_target = target - target_center
    gram = standardized.T @ standardized
    coefficients_scaled = np.linalg.solve(
        gram + alpha * np.eye(gram.shape[0]),
        standardized.T @ centered_target,
    )
    coefficients = coefficients_scaled / feature_scale
    intercept = target_center - float(feature_center @ coefficients)
    return intercept, coefficients, feature_center, feature_scale


def _select_alpha_with_minimum(
    frame: pd.DataFrame,
    cycle_ids: list[str],
    minimum_observations: int,
) -> tuple[float, float]:
    validation_observations = max(12, minimum_observations // 2)
    split = max(minimum_observations, int(math.floor(len(frame) * 0.70)))
    split = min(split, len(frame) - validation_observations)
    if split < minimum_observations or len(frame) - split < validation_observations:
        return RIDGE_ALPHAS[1], float("nan")
    train = frame.iloc[:split]
    validation = frame.iloc[split:]
    train_features = train[cycle_ids].to_numpy(dtype=float)
    train_target = train["target"].to_numpy(dtype=float)
    validation_features = validation[cycle_ids].to_numpy(dtype=float)
    validation_target = validation["target"].to_numpy(dtype=float)
    scores: list[tuple[float, float]] = []
    for alpha in RIDGE_ALPHAS:
        intercept, coefficients, _, _ = _ridge_fit(
            train_features,
            train_target,
            alpha,
        )
        predicted = intercept + validation_features @ coefficients
        score = _safe_r2(validation_target, predicted)
        scores.append((score if np.isfinite(score) else -np.inf, alpha))
    best_score, best_alpha = max(scores, key=lambda item: (item[0], -item[1]))
    return best_alpha, best_score


def _coefficient_sign_agreement(
    frame: pd.DataFrame,
    cycle_ids: list[str],
    alpha: float,
    final_coefficients: np.ndarray,
    minimum_observations: int = MINIMUM_OBSERVATIONS,
) -> float:
    signs = np.sign(final_coefficients)
    agreements: list[float] = []
    for fraction in (0.60, 0.80):
        count = int(math.floor(len(frame) * fraction))
        if count < minimum_observations:
            continue
        subset = frame.iloc[:count]
        _, coefficients, _, _ = _ridge_fit(
            subset[cycle_ids].to_numpy(dtype=float),
            subset["target"].to_numpy(dtype=float),
            alpha,
        )
        subset_signs = np.sign(coefficients)
        agreements.append(float(np.mean((subset_signs == signs) | (signs == 0.0))))
    return float(np.mean(agreements)) if agreements else float("nan")


def _subset_r2(target: np.ndarray, features: np.ndarray, subset: tuple[int, ...]) -> float:
    if not subset:
        return 0.0
    design = np.column_stack(
        [np.ones(len(target), dtype=float), features[:, list(subset)]]
    )
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    score = _safe_r2(target, design @ coefficients)
    if not np.isfinite(score):
        return 0.0
    return min(1.0, max(0.0, float(score)))


def _variance_influence(
    target: pd.Series,
    contributions: Mapping[str, pd.Series],
    residual: pd.Series,
    window: int = 120,
) -> tuple[dict[str, float], float]:
    frame = pd.concat(
        [target.rename("target")]
        + [series.rename(cycle_id) for cycle_id, series in contributions.items()]
        + [residual.rename("residual")],
        axis=1,
    ).dropna()
    frame = frame.iloc[-window:]
    target_values = frame["target"].to_numpy(dtype=float)
    if float(np.var(target_values)) <= 1e-12:
        return {cycle_id: float("nan") for cycle_id in contributions}, float("nan")
    cycle_ids = list(contributions)
    features = frame[cycle_ids].to_numpy(dtype=float)
    count = len(cycle_ids)
    r2_cache: dict[int, float] = {0: 0.0}
    for size in range(1, count + 1):
        for subset in combinations(range(count), size):
            mask = sum(1 << index for index in subset)
            r2_cache[mask] = _subset_r2(target_values, features, subset)
    denominator = math.factorial(count)
    raw_shares = np.zeros(count, dtype=float)
    for cycle_index in range(count):
        other_indices = [index for index in range(count) if index != cycle_index]
        for size in range(count):
            weight = (
                math.factorial(size)
                * math.factorial(count - size - 1)
                / denominator
            )
            for subset in combinations(other_indices, size):
                mask = sum(1 << index for index in subset)
                increment = r2_cache[mask | (1 << cycle_index)] - r2_cache[mask]
                raw_shares[cycle_index] += weight * max(0.0, increment)
    full_r2 = r2_cache[(1 << count) - 1]
    raw_total = float(raw_shares.sum())
    if raw_total > 1e-12:
        raw_shares *= full_r2 / raw_total
    shares = {
        cycle_id: float(raw_shares[index])
        for index, cycle_id in enumerate(cycle_ids)
    }
    return shares, max(0.0, 1.0 - full_r2)


def build_indicator_cycle_contribution(
    standardized: pd.Series,
    components: Mapping[str, pd.Series],
    *,
    periods: Mapping[str, float] | None = None,
    minimum_observations: int = MINIMUM_OBSERVATIONS,
) -> dict[str, object]:
    period_map = dict(periods or CYCLE_PERIODS)
    target = pd.to_numeric(standardized, errors="coerce").rename("target")
    excluded: list[dict[str, object]] = []
    if "C1" not in period_map:
        excluded.append(
            {
                "cycleId": "C1",
                "reason": "月频轨道长度不足以支持600个月频带的稳定贡献估计",
            }
        )
    eligible: list[str] = []
    for cycle_id, period in period_map.items():
        component = pd.to_numeric(components[cycle_id], errors="coerce")
        observations = int(pd.concat([target, component], axis=1).dropna().shape[0])
        required = max(
            minimum_observations,
            int(math.ceil(period * MINIMUM_CYCLE_REPEATS)),
        )
        if observations < required:
            excluded.append(
                {
                    "cycleId": cycle_id,
                    "reason": "历史长度不足三轮完整周期",
                    "observations": observations,
                    "requiredObservations": required,
                }
            )
            continue
        eligible.append(cycle_id)
    if not eligible:
        return {
            "status": "unavailable",
            "method": "ridge_frequency_reconstruction_with_explicit_residual",
            "eligibleCycles": [],
            "excludedCycles": excluded,
            "caveat": "没有周期满足至少三轮完整历史，拒绝生成频带贡献。",
        }

    frame = pd.concat(
        [target] + [pd.to_numeric(components[cycle_id], errors="coerce").rename(cycle_id) for cycle_id in eligible],
        axis=1,
    ).dropna()
    edge_trim = max(3, int(math.ceil(max(period_map[cycle_id] for cycle_id in eligible) / 3.0)))
    if len(frame) <= edge_trim * 2 + minimum_observations:
        edge_trim = max(3, int((len(frame) - minimum_observations) / 2))
    fit_frame = frame.iloc[edge_trim:-edge_trim] if edge_trim > 0 else frame
    if len(fit_frame) < minimum_observations:
        return {
            "status": "unavailable",
            "method": "ridge_frequency_reconstruction_with_explicit_residual",
            "eligibleCycles": eligible,
            "excludedCycles": excluded,
            "caveat": "剔除双边滤波端点后有效历史不足，拒绝生成频带贡献。",
        }

    alpha, holdout_r2 = _select_alpha_with_minimum(
        fit_frame,
        eligible,
        minimum_observations,
    )
    intercept, coefficients, _, _ = _ridge_fit(
        fit_frame[eligible].to_numpy(dtype=float),
        fit_frame["target"].to_numpy(dtype=float),
        alpha,
    )
    fitted = intercept + fit_frame[eligible].to_numpy(dtype=float) @ coefficients
    reconstruction_r2 = _safe_r2(fit_frame["target"].to_numpy(dtype=float), fitted)
    sign_agreement = _coefficient_sign_agreement(
        fit_frame,
        eligible,
        alpha,
        coefficients,
        minimum_observations,
    )

    aligned_components = pd.concat(
        [pd.to_numeric(components[cycle_id], errors="coerce").rename(cycle_id) for cycle_id in eligible],
        axis=1,
    ).reindex(target.index)
    contribution_paths = {
        cycle_id: aligned_components[cycle_id] * float(coefficients[index])
        for index, cycle_id in enumerate(eligible)
    }
    cycle_total = pd.concat(contribution_paths.values(), axis=1).sum(axis=1, min_count=len(eligible))
    residual = target - intercept - cycle_total
    valid = pd.concat([target, cycle_total, residual], axis=1).dropna()
    if valid.empty:
        return {
            "status": "unavailable",
            "method": "ridge_frequency_reconstruction_with_explicit_residual",
            "eligibleCycles": eligible,
            "excludedCycles": excluded,
            "caveat": "当前指标与周期频带没有共同有效时点。",
        }
    latest_date = valid.index[-1]
    point_values = {
        cycle_id: float(series.loc[latest_date])
        for cycle_id, series in contribution_paths.items()
    }
    absolute_total = float(sum(abs(value) for value in point_values.values()))
    variance_shares, residual_variance_share = _variance_influence(
        target,
        contribution_paths,
        residual,
    )
    current_components = {}
    for index, cycle_id in enumerate(eligible):
        path = contribution_paths[cycle_id]
        position = path.index.get_loc(latest_date)
        slope3 = (
            float(path.iloc[position] - path.iloc[position - 3])
            if isinstance(position, int) and position >= 3 and pd.notna(path.iloc[position - 3])
            else float("nan")
        )
        point = point_values[cycle_id]
        current_components[cycle_id] = {
            "pointContribution": point,
            "absoluteShare": abs(point) / absolute_total if absolute_total > 1e-12 else 0.0,
            "signedShare": point / absolute_total if absolute_total > 1e-12 else 0.0,
            "slope3": slope3,
            "varianceShare120": variance_shares[cycle_id],
            "coefficient": float(coefficients[index]),
        }
    indicator_value = float(target.loc[latest_date])
    cycle_value = float(cycle_total.loc[latest_date])
    residual_value = float(residual.loc[latest_date])
    conservation_error = indicator_value - intercept - cycle_value - residual_value
    quality = (
        "stable"
        if np.isfinite(holdout_r2)
        and holdout_r2 > 0.0
        and np.isfinite(sign_agreement)
        and sign_agreement >= 0.75
        else "weak"
    )
    dominant_cycle = max(point_values, key=lambda cycle_id: abs(point_values[cycle_id]))
    return {
        "status": "retrospective_diagnostic",
        "quality": quality,
        "method": "ridge_frequency_reconstruction_with_explicit_residual",
        "eligibleCycles": eligible,
        "excludedCycles": excluded,
        "current": {
            "date": _period_text(latest_date),
            "indicatorValue": indicator_value,
            "baseline": float(intercept),
            "cycleTotal": cycle_value,
            "residual": residual_value,
            "conservationError": float(conservation_error),
            "dominantCycle": dominant_cycle,
            "components": current_components,
        },
        "diagnostics": {
            "fitStart": _period_text(fit_frame.index.min()),
            "fitEnd": _period_text(fit_frame.index.max()),
            "fitObservations": int(len(fit_frame)),
            "edgeTrimMonths": edge_trim,
            "selectedAlpha": alpha,
            "reconstructionR2": reconstruction_r2,
            "holdoutReconstructionR2": holdout_r2,
            "coefficientSignAgreement": sign_agreement,
            "residualVarianceShare120": residual_variance_share,
        },
        "paths": {
            "baseline": float(intercept),
            "cycleTotal": cycle_total,
            "residual": residual,
            "components": contribution_paths,
        },
        "caveat": "这是双边滤波后的回溯频带分解，不是经济因果归因，也不能直接转换为资产权重。",
    }


def build_cross_filter_indicator_cycle_contribution(
    standardized: pd.Series,
    primary_components: Mapping[str, pd.Series],
    comparison_components: Mapping[str, pd.Series],
    *,
    periods: Mapping[str, float] | None = None,
    minimum_observations: int = MINIMUM_OBSERVATIONS,
    primary_filter: str = "gaussian_dog",
    comparison_filter: str = "butterworth_zero_phase",
) -> dict[str, object]:
    primary = build_indicator_cycle_contribution(
        standardized,
        primary_components,
        periods=periods,
        minimum_observations=minimum_observations,
    )
    comparison = build_indicator_cycle_contribution(
        standardized,
        comparison_components,
        periods=periods,
        minimum_observations=minimum_observations,
    )
    if primary.get("status") != "retrospective_diagnostic":
        return primary
    primary["method"] = "cross_filter_ridge_frequency_reconstruction_with_explicit_residual"
    if comparison.get("status") != "retrospective_diagnostic":
        primary["quality"] = "weak"
        primary["filterRobustness"] = {
            "status": "unavailable",
            "primaryFilter": primary_filter,
            "comparisonFilter": comparison_filter,
            "stableCycles": 0,
            "comparableCycles": 0,
            "reason": comparison.get("caveat", "第二套滤波贡献不可用。"),
        }
        primary["caveat"] = (
            f"{primary['caveat']} 第二套滤波未形成可比较结果，因此全部贡献仅标记为偏弱。"
        )
        return primary

    primary_model_quality = str(primary.get("quality", "weak"))
    comparison_model_quality = str(comparison.get("quality", "weak"))
    common_cycles = [
        cycle_id
        for cycle_id in primary["eligibleCycles"]
        if cycle_id in comparison["eligibleCycles"]
    ]
    primary_paths = primary["paths"]["components"]
    comparison_paths = comparison["paths"]["components"]
    primary["_crossFilterCalibrationInputs"] = {
        "target": pd.to_numeric(standardized, errors="coerce"),
        "primaryComponents": {
            cycle_id: pd.to_numeric(primary_components[cycle_id], errors="coerce")
            for cycle_id in common_cycles
        },
        "comparisonComponents": {
            cycle_id: pd.to_numeric(comparison_components[cycle_id], errors="coerce")
            for cycle_id in common_cycles
        },
        "minimumObservations": minimum_observations,
    }
    trim = max(
        int(primary["diagnostics"]["edgeTrimMonths"]),
        int(comparison["diagnostics"]["edgeTrimMonths"]),
    )
    stable_cycles = 0
    path_correlations: list[float] = []
    direction_agreements = 0
    for cycle_id in common_cycles:
        primary_component = primary["current"]["components"][cycle_id]
        comparison_component = comparison["current"]["components"][cycle_id]
        primary_point = float(primary_component["pointContribution"])
        comparison_point = float(comparison_component["pointContribution"])
        direction_agreement = bool(np.sign(primary_point) == np.sign(comparison_point))
        path_correlation = _safe_correlation(
            primary_paths[cycle_id],
            comparison_paths[cycle_id],
            trim,
        )
        relative_point_difference = _relative_difference(
            primary_point,
            comparison_point,
        )
        absolute_share_difference = abs(
            float(primary_component["absoluteShare"])
            - float(comparison_component["absoluteShare"])
        )
        variance_share_difference = abs(
            float(primary_component["varianceShare120"])
            - float(comparison_component["varianceShare120"])
        )
        stable = (
            primary_model_quality == "stable"
            and comparison_model_quality == "stable"
            and direction_agreement
            and np.isfinite(path_correlation)
            and path_correlation >= CROSS_FILTER_MIN_PATH_CORRELATION
            and relative_point_difference
            <= CROSS_FILTER_MAX_RELATIVE_POINT_DIFFERENCE
            and absolute_share_difference
            <= CROSS_FILTER_MAX_ABSOLUTE_SHARE_DIFFERENCE
            and variance_share_difference
            <= CROSS_FILTER_MAX_VARIANCE_SHARE_DIFFERENCE
        )
        if stable:
            stable_cycles += 1
        if direction_agreement:
            direction_agreements += 1
        if np.isfinite(path_correlation):
            path_correlations.append(path_correlation)
        primary_component["filterRobustness"] = {
            "status": "stable" if stable else "weak",
            "primaryFilter": primary_filter,
            "comparisonFilter": comparison_filter,
            "directionAgreement": direction_agreement,
            "pathCorrelation": path_correlation,
            "relativePointDifference": relative_point_difference,
            "absoluteShareDifference": absolute_share_difference,
            "varianceShareDifference": variance_share_difference,
            "comparisonPointContribution": comparison_point,
            "comparisonAbsoluteShare": float(comparison_component["absoluteShare"]),
            "comparisonVarianceShare120": float(comparison_component["varianceShare120"]),
        }

    stable_share = stable_cycles / len(common_cycles) if common_cycles else 0.0
    primary["quality"] = (
        "stable"
        if primary_model_quality == "stable"
        and comparison_model_quality == "stable"
        and stable_share >= 0.75
        else "weak"
    )
    primary["filterRobustness"] = {
        "status": "stable" if primary["quality"] == "stable" else "weak",
        "primaryFilter": primary_filter,
        "comparisonFilter": comparison_filter,
        "primaryModelQuality": primary_model_quality,
        "comparisonModelQuality": comparison_model_quality,
        "stableCycles": stable_cycles,
        "comparableCycles": len(common_cycles),
        "directionAgreementCycles": direction_agreements,
        "medianPathCorrelation": (
            float(np.median(path_correlations)) if path_correlations else float("nan")
        ),
        "thresholds": {
            "minimumPathCorrelation": CROSS_FILTER_MIN_PATH_CORRELATION,
            "maximumRelativePointDifference": CROSS_FILTER_MAX_RELATIVE_POINT_DIFFERENCE,
            "maximumAbsoluteShareDifference": CROSS_FILTER_MAX_ABSOLUTE_SHARE_DIFFERENCE,
            "maximumVarianceShareDifference": CROSS_FILTER_MAX_VARIANCE_SHARE_DIFFERENCE,
        },
        "comparisonDiagnostics": comparison["diagnostics"],
    }
    primary["caveat"] = (
        f"这是{_filter_label(primary_filter)}与{_filter_label(comparison_filter)}"
        "双边滤波交叉复核后的回溯频带分解；"
        "两套滤波都使用未来样本，端点会随新数据修订；不是经济因果归因，"
        "也不能直接转换为资产权重。"
    )
    return primary


def _cross_filter_gain_segments(
    primary: pd.Series,
    comparison: pd.Series,
) -> dict[str, tuple[np.ndarray, np.ndarray]] | None:
    frame = pd.concat(
        [primary.rename("primary"), comparison.rename("comparison")],
        axis=1,
    ).dropna()
    minimum_total = CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS * 3
    if len(frame) < minimum_total:
        return None
    training_end = int(math.floor(len(frame) * 0.60))
    validation_end = int(math.floor(len(frame) * 0.80))
    if (
        training_end < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
        or validation_end - training_end
        < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
        or len(frame) - validation_end
        < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
    ):
        return None
    training_scale = float(
        np.sqrt(np.mean(np.square(frame["primary"].iloc[:training_end])))
    )
    if not np.isfinite(training_scale) or training_scale <= 1e-12:
        return None
    normalized = frame / training_scale
    return {
        "training": (
            normalized["primary"].iloc[:training_end].to_numpy(dtype=float),
            normalized["comparison"].iloc[:training_end].to_numpy(dtype=float),
        ),
        "validation": (
            normalized["primary"].iloc[training_end:validation_end].to_numpy(dtype=float),
            normalized["comparison"].iloc[training_end:validation_end].to_numpy(dtype=float),
        ),
        "audit": (
            normalized["primary"].iloc[validation_end:].to_numpy(dtype=float),
            normalized["comparison"].iloc[validation_end:].to_numpy(dtype=float),
        ),
    }


def _cross_filter_gain_track_candidates(
    inputs: Mapping[str, object],
    cycle_ids: list[str],
    trim: int,
) -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    target = pd.to_numeric(inputs["target"], errors="coerce").rename("target")
    primary_components = inputs["primaryComponents"]
    comparison_components = inputs["comparisonComponents"]
    frame = pd.concat(
        [target]
        + [
            pd.to_numeric(primary_components[cycle_id], errors="coerce").rename(
                f"primary_{cycle_id}"
            )
            for cycle_id in cycle_ids
        ]
        + [
            pd.to_numeric(comparison_components[cycle_id], errors="coerce").rename(
                f"comparison_{cycle_id}"
            )
            for cycle_id in cycle_ids
        ],
        axis=1,
    ).dropna()
    if trim > 0 and len(frame) > trim:
        frame = frame.iloc[trim:]
    minimum_total = CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS * 3
    if len(frame) < minimum_total:
        return {}
    training_end = int(math.floor(len(frame) * 0.60))
    validation_end = int(math.floor(len(frame) * 0.80))
    if (
        training_end < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
        or validation_end - training_end
        < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
        or len(frame) - validation_end
        < CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
    ):
        return {}
    training = frame.iloc[:training_end]
    minimum_observations = min(
        int(inputs.get("minimumObservations", MINIMUM_OBSERVATIONS)),
        max(24, training_end // 2),
    )
    primary_columns = [f"primary_{cycle_id}" for cycle_id in cycle_ids]
    comparison_columns = [f"comparison_{cycle_id}" for cycle_id in cycle_ids]
    primary_alpha, _ = _select_alpha_with_minimum(
        training.rename(columns=dict(zip(primary_columns, cycle_ids, strict=True)))[
            ["target", *cycle_ids]
        ],
        cycle_ids,
        minimum_observations,
    )
    comparison_alpha, _ = _select_alpha_with_minimum(
        training.rename(
            columns=dict(zip(comparison_columns, cycle_ids, strict=True))
        )[["target", *cycle_ids]],
        cycle_ids,
        minimum_observations,
    )
    _, primary_coefficients, _, _ = _ridge_fit(
        training[primary_columns].to_numpy(dtype=float),
        training["target"].to_numpy(dtype=float),
        primary_alpha,
    )
    _, comparison_coefficients, _, _ = _ridge_fit(
        training[comparison_columns].to_numpy(dtype=float),
        training["target"].to_numpy(dtype=float),
        comparison_alpha,
    )
    candidates = {}
    for index, cycle_id in enumerate(cycle_ids):
        primary_path = frame[f"primary_{cycle_id}"] * float(
            primary_coefficients[index]
        )
        comparison_path = frame[f"comparison_{cycle_id}"] * float(
            comparison_coefficients[index]
        )
        segments = _cross_filter_gain_segments(primary_path, comparison_path)
        if segments is not None:
            candidates[cycle_id] = segments
    return candidates


def _evaluate_cross_filter_gain(
    candidates: list[dict[str, tuple[np.ndarray, np.ndarray]]],
) -> dict[str, object]:
    training_primary = np.concatenate(
        [candidate["training"][0] for candidate in candidates]
    )
    training_comparison = np.concatenate(
        [candidate["training"][1] for candidate in candidates]
    )
    denominator = float(training_comparison @ training_comparison)
    if denominator <= 1e-12:
        return {"status": "unavailable", "reason": "训练段对照贡献没有有效方差"}
    gain = float(
        np.clip(
            float(training_comparison @ training_primary) / denominator,
            CROSS_FILTER_GAIN_FLOOR,
            CROSS_FILTER_GAIN_CEILING,
        )
    )
    evaluation: dict[str, object] = {
        "gain": gain,
        "eligibleTracks": len(candidates),
    }
    for segment in ("validation", "audit"):
        primary_values = np.concatenate(
            [candidate[segment][0] for candidate in candidates]
        )
        comparison_values = np.concatenate(
            [candidate[segment][1] for candidate in candidates]
        )
        baseline_error = _normalized_absolute_error(
            primary_values,
            comparison_values,
        )
        calibrated_error = _normalized_absolute_error(
            primary_values,
            comparison_values * gain,
        )
        improvements = []
        for candidate in candidates:
            candidate_primary, candidate_comparison = candidate[segment]
            candidate_baseline = _normalized_absolute_error(
                candidate_primary,
                candidate_comparison,
            )
            candidate_calibrated = _normalized_absolute_error(
                candidate_primary,
                candidate_comparison * gain,
            )
            improvements.append(
                _relative_improvement(candidate_baseline, candidate_calibrated)
            )
        evaluation[f"{segment}BaselineMae"] = baseline_error
        evaluation[f"{segment}CalibratedMae"] = calibrated_error
        evaluation[f"{segment}RelativeImprovement"] = _relative_improvement(
            baseline_error,
            calibrated_error,
        )
        evaluation[f"{segment}ImprovedTrackShare"] = float(
            np.mean(np.asarray(improvements, dtype=float) > 0.0)
        )
    adopted = (
        evaluation["validationRelativeImprovement"]
        >= CROSS_FILTER_GAIN_MINIMUM_VALIDATION_IMPROVEMENT
        and evaluation["auditRelativeImprovement"]
        >= CROSS_FILTER_GAIN_MINIMUM_AUDIT_IMPROVEMENT
        and evaluation["validationImprovedTrackShare"] >= 0.60
        and evaluation["auditImprovedTrackShare"] >= 0.50
    )
    evaluation["status"] = "adopted" if adopted else "rejected"
    evaluation["thresholds"] = {
        "minimumTracks": CROSS_FILTER_GAIN_MINIMUM_TRACKS,
        "minimumSegmentObservations": (
            CROSS_FILTER_GAIN_MINIMUM_VALIDATION_OBSERVATIONS
        ),
        "minimumValidationImprovement": (
            CROSS_FILTER_GAIN_MINIMUM_VALIDATION_IMPROVEMENT
        ),
        "minimumAuditImprovement": CROSS_FILTER_GAIN_MINIMUM_AUDIT_IMPROVEMENT,
        "minimumValidationImprovedTrackShare": 0.60,
        "minimumAuditImprovedTrackShare": 0.50,
        "gainFloor": CROSS_FILTER_GAIN_FLOOR,
        "gainCeiling": CROSS_FILTER_GAIN_CEILING,
    }
    return evaluation


def apply_cross_filter_gain_calibration(
    tracks: list[dict[str, object]],
) -> dict[str, object]:
    cycle_candidates: dict[str, list[dict[str, tuple[np.ndarray, np.ndarray]]]] = {}
    for track in tracks:
        study = track.get("cycleContribution")
        if not isinstance(study, dict):
            continue
        inputs = study.get("_crossFilterCalibrationInputs")
        if not isinstance(inputs, Mapping):
            continue
        trim = int(study.get("diagnostics", {}).get("edgeTrimMonths", 0))
        candidates = _cross_filter_gain_track_candidates(
            inputs,
            list(study.get("eligibleCycles", [])),
            trim,
        )
        for cycle_id, segments in candidates.items():
            cycle_candidates.setdefault(cycle_id, []).append(segments)

    calibration: dict[str, object] = {}
    for cycle_id in CYCLE_PERIODS:
        candidates = cycle_candidates.get(cycle_id, [])
        if len(candidates) < CROSS_FILTER_GAIN_MINIMUM_TRACKS:
            calibration[cycle_id] = {
                "status": "unavailable",
                "eligibleTracks": len(candidates),
                "reason": "满足固定训练/验证/审计分段的轨道不足",
            }
            continue
        calibration[cycle_id] = _evaluate_cross_filter_gain(candidates)

    for track in tracks:
        study = track.get("cycleContribution")
        if not isinstance(study, dict):
            continue
        inputs = study.pop("_crossFilterCalibrationInputs", None)
        if not isinstance(inputs, Mapping):
            continue
        overall = study.get("filterRobustness", {})
        common_cycles = [
            cycle_id
            for cycle_id in study.get("eligibleCycles", [])
            if cycle_id in study.get("current", {}).get("components", {})
        ]
        calibrated_points: dict[str, float] = {}
        for cycle_id in common_cycles:
            robustness = study["current"]["components"][cycle_id].get(
                "filterRobustness",
                {},
            )
            evidence = calibration.get(cycle_id, {})
            gain = (
                float(evidence["gain"])
                if evidence.get("status") == "adopted"
                else 1.0
            )
            calibrated_points[cycle_id] = (
                float(robustness.get("comparisonPointContribution", 0.0)) * gain
            )
        calibrated_absolute_total = sum(
            abs(value) for value in calibrated_points.values()
        )
        stable_cycles = 0
        direction_agreements = 0
        for cycle_id in common_cycles:
            component = study["current"]["components"][cycle_id]
            robustness = component.get("filterRobustness", {})
            evidence = calibration.get(cycle_id, {})
            gain = (
                float(evidence["gain"])
                if evidence.get("status") == "adopted"
                else 1.0
            )
            comparison_point = calibrated_points[cycle_id]
            comparison_share = (
                abs(comparison_point) / calibrated_absolute_total
                if calibrated_absolute_total > 1e-12
                else 0.0
            )
            robustness["uncalibratedComparisonPointContribution"] = robustness.get(
                "comparisonPointContribution"
            )
            robustness["uncalibratedRelativePointDifference"] = robustness.get(
                "relativePointDifference"
            )
            robustness["uncalibratedAbsoluteShareDifference"] = robustness.get(
                "absoluteShareDifference"
            )
            robustness["gainCalibrationStatus"] = evidence.get("status", "unavailable")
            robustness["gainCalibrationFactor"] = gain
            robustness["comparisonPointContribution"] = comparison_point
            robustness["comparisonAbsoluteShare"] = comparison_share
            robustness["relativePointDifference"] = _relative_difference(
                float(component["pointContribution"]),
                comparison_point,
            )
            robustness["absoluteShareDifference"] = abs(
                float(component["absoluteShare"]) - comparison_share
            )
            stable = (
                overall.get("primaryModelQuality") == "stable"
                and overall.get("comparisonModelQuality") == "stable"
                and robustness.get("directionAgreement") is True
                and np.isfinite(robustness.get("pathCorrelation", np.nan))
                and robustness["pathCorrelation"]
                >= CROSS_FILTER_MIN_PATH_CORRELATION
                and robustness["relativePointDifference"]
                <= CROSS_FILTER_MAX_RELATIVE_POINT_DIFFERENCE
                and robustness["absoluteShareDifference"]
                <= CROSS_FILTER_MAX_ABSOLUTE_SHARE_DIFFERENCE
                and robustness.get("varianceShareDifference", np.inf)
                <= CROSS_FILTER_MAX_VARIANCE_SHARE_DIFFERENCE
            )
            robustness["status"] = "stable" if stable else "weak"
            stable_cycles += int(stable)
            direction_agreements += int(
                robustness.get("directionAgreement") is True
            )
        comparable_cycles = len(common_cycles)
        stable_share = stable_cycles / comparable_cycles if comparable_cycles else 0.0
        study["quality"] = (
            "stable"
            if overall.get("primaryModelQuality") == "stable"
            and overall.get("comparisonModelQuality") == "stable"
            and stable_share >= 0.75
            else "weak"
        )
        overall["stableCycles"] = stable_cycles
        overall["comparableCycles"] = comparable_cycles
        overall["directionAgreementCycles"] = direction_agreements
        overall["gainCalibration"] = {
            cycle_id: calibration.get(cycle_id, {}) for cycle_id in common_cycles
        }
    return {
        "status": "cross_track_fixed_gain_challenger",
        "method": (
            "每条轨道历史中段前60%训练、后20%验证、末20%审计；"
            "按周期跨轨道固定增益，只有验证与审计均改善才采用"
        ),
        "cycles": calibration,
    }


def summarize_indicator_cycle_contributions(
    tracks: list[dict[str, object]],
    *,
    cycle_ids: tuple[str, ...] = ("C1", "C2", "C3", "C4", "C5", "C6", "C7"),
) -> dict[str, object]:
    cycles: dict[str, object] = {}
    for cycle_id in cycle_ids:
        rows = []
        for track in tracks:
            study = track.get("cycleContribution")
            if not isinstance(study, dict) or study.get("status") != "retrospective_diagnostic":
                continue
            current = study["current"]
            component = current["components"].get(cycle_id)
            if component is None:
                continue
            filter_robustness = component.get("filterRobustness", {})
            overall_robustness = study.get("filterRobustness", {})
            realtime_confirmation = study.get("realtimeConfirmation", {})
            realtime_component = (
                realtime_confirmation.get("current", {})
                .get("components", {})
                .get(cycle_id)
                if isinstance(realtime_confirmation, dict)
                else None
            )
            rows.append(
                {
                    "trackId": track["id"],
                    "label": track["label"],
                    "category": track["category"],
                    "group": track["group"],
                    "date": current["date"],
                    "pointContribution": component["pointContribution"],
                    "absoluteShare": component["absoluteShare"],
                    "signedShare": component["signedShare"],
                    "slope3": component["slope3"],
                    "varianceShare120": component["varianceShare120"],
                    "quality": filter_robustness.get("status", study["quality"]),
                    "filterDirectionAgreement": filter_robustness.get("directionAgreement"),
                    "filterPathCorrelation": filter_robustness.get("pathCorrelation"),
                    "filterRelativePointDifference": filter_robustness.get("relativePointDifference"),
                    "filterAbsoluteShareDifference": filter_robustness.get("absoluteShareDifference"),
                    "filterVarianceShareDifference": filter_robustness.get("varianceShareDifference"),
                    "modelQualityPass": (
                        overall_robustness.get("primaryModelQuality") == "stable"
                        and overall_robustness.get("comparisonModelQuality") == "stable"
                    ),
                    "realtimeStatus": (
                        realtime_component.get("status")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateWeightModel": (
                        realtime_component.get("stateWeightModel")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimePeerSharedFamilyLevel": (
                        realtime_component.get("peerSharedFamilyLevel")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimePeerSharedPeerCount": (
                        realtime_component.get("peerSharedPeerCount")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeOrthogonalizationUncertaintyShare": (
                        realtime_component.get(
                            "orthogonalizationUncertaintyShare"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeOrthogonalizationSpanUncertaintyShare": (
                        realtime_component.get(
                            "orthogonalizationSpanUncertaintyShare"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimePointContribution": (
                        realtime_component.get("pointContribution")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeDirection": (
                        realtime_component.get("direction")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeSignalToUncertainty": (
                        realtime_component.get("signalToUncertainty")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeCoefficientSignAgreement": (
                        realtime_component.get("coefficientSignAgreement")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeCoefficientUncertaintyShare": (
                        realtime_component.get("coefficientUncertaintyShare")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateSpecificationDirectionAgreement": (
                        realtime_component.get(
                            "stateSpecificationDirectionAgreement"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeRollingStateSpecificationDirectionAgreement": (
                        realtime_component.get(
                            "rollingStateSpecificationDirectionAgreement"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateSpecificationUncertaintyShare": (
                        realtime_component.get(
                            "stateSpecificationUncertaintyShare"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateSpecificationWeights": (
                        realtime_component.get("stateSpecificationWeights")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateSpecificationEffectiveCount": (
                        realtime_component.get(
                            "stateSpecificationEffectiveCount"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeStateSpecificationWeightEntropy": (
                        realtime_component.get(
                            "stateSpecificationWeightEntropy"
                        )
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeRollingDirectionAgreement": (
                        realtime_component.get("rollingDirectionAgreement")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeRollingContributionCorrelation": (
                        realtime_component.get("rollingContributionCorrelation")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeMedianAbsoluteRevision": (
                        realtime_component.get("medianAbsoluteRevision")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "realtimeRollingReconstructionR2": (
                        realtime_confirmation.get("training", {}).get(
                            "rollingReconstructionR2"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeEqualMedianRollingReconstructionR2": (
                        realtime_confirmation.get("training", {}).get(
                            "equalMedianRollingReconstructionR2"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeRollingR2ImprovementVsEqualMedian": (
                        realtime_confirmation.get("training", {}).get(
                            "rollingR2ImprovementVsEqualMedian"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimePeerSharedStatus": (
                        realtime_confirmation.get("training", {}).get(
                            "peerSharedStatus"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimePeerSharedRollingR2Improvement": (
                        realtime_confirmation.get("training", {}).get(
                            "peerSharedRollingR2Improvement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimePeerSharedMaeImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "peerSharedMaeImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimePeerSharedDirectionImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "peerSharedDirectionImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeDynamicFactorStatus": (
                        realtime_confirmation.get("training", {}).get(
                            "dynamicFactorStatus"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeDynamicFactorRollingR2Improvement": (
                        realtime_confirmation.get("training", {}).get(
                            "dynamicFactorRollingR2Improvement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeDynamicFactorMaeImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "dynamicFactorMaeImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeDynamicFactorDirectionImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "dynamicFactorDirectionImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorStatus": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorStatus"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorRollingR2Improvement": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorRollingR2Improvement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorMaeImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorMaeImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorDirectionImprovement": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorDirectionImprovement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorSpecificationStable": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorSpecificationStable"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorRobustlyAdopted": (
                        realtime_confirmation.get("training", {}).get(
                            "nearestFactorRobustlyAdopted"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorEarlyVintageR2Improvement": (
                        realtime_confirmation.get("training", {})
                        .get("nearestFactorVintageSplits", {})
                        .get("early", {})
                        .get("r2Improvement")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeNearestFactorLateVintageR2Improvement": (
                        realtime_confirmation.get("training", {})
                        .get("nearestFactorVintageSplits", {})
                        .get("late", {})
                        .get("r2Improvement")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeLowTargetVarianceWarning": (
                        realtime_confirmation.get("training", {}).get(
                            "lowTargetVarianceWarning"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeCausalOrthogonalStatus": (
                        realtime_confirmation.get("training", {}).get(
                            "causalOrthogonalStatus"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeOrthogonalPrimaryR2Improvement": (
                        realtime_confirmation.get("training", {}).get(
                            "orthogonalPrimaryRollingR2Improvement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeOrthogonalComparisonR2Improvement": (
                        realtime_confirmation.get("training", {}).get(
                            "orthogonalComparisonRollingR2Improvement"
                        )
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeBaseMaximumCorrelation": (
                        realtime_confirmation.get("training", {})
                        .get("baseComponentCollinearity", {})
                        .get("maximumAbsoluteCorrelation")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeOrthogonalMaximumCorrelation": (
                        realtime_confirmation.get("training", {})
                        .get("orthogonalPrimaryComponentCollinearity", {})
                        .get("maximumAbsoluteCorrelation")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeBaseConditionNumber": (
                        realtime_confirmation.get("training", {})
                        .get("baseComponentCollinearity", {})
                        .get("conditionNumber")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeOrthogonalConditionNumber": (
                        realtime_confirmation.get("training", {})
                        .get("orthogonalPrimaryComponentCollinearity", {})
                        .get("conditionNumber")
                        if isinstance(realtime_confirmation, dict)
                        else None
                    ),
                    "realtimeEndpointDirectionAgreement": (
                        realtime_component.get("endpointDirectionAgreement")
                        if isinstance(realtime_component, dict)
                        else None
                    ),
                    "reconstructionR2": study["diagnostics"]["reconstructionR2"],
                    "holdoutReconstructionR2": study["diagnostics"]["holdoutReconstructionR2"],
                    "residualVarianceShare120": study["diagnostics"]["residualVarianceShare120"],
                }
            )
        if not rows:
            reason = (
                "月频指标轨道不足以稳定估计600个月频带贡献，C1继续使用年频长历史情景研究。"
                if cycle_id == "C1"
                else "没有指标满足三轮完整历史与端点剔除要求。"
            )
            cycles[cycle_id] = {
                "status": "excluded" if cycle_id == "C1" else "unavailable",
                "eligibleTracks": 0,
                "reason": reason,
            }
            continue
        stable_rows = [row for row in rows if row["quality"] == "stable"]
        realtime_rows = [row for row in rows if row["realtimeStatus"] is not None]
        orthogonal_rows = [
            row
            for row in realtime_rows
            if row["realtimeCausalOrthogonalStatus"] == "adopted"
        ]
        positive = sorted(
            rows,
            key=lambda row: (
                row["quality"] != "stable",
                -row["pointContribution"],
            ),
        )
        negative = sorted(
            rows,
            key=lambda row: (
                row["quality"] != "stable",
                row["pointContribution"],
            ),
        )
        influence = sorted(
            rows,
            key=lambda row: (
                row["quality"] != "stable",
                -abs(row["pointContribution"]),
            ),
        )
        cycles[cycle_id] = {
            "status": "retrospective_diagnostic",
            "eligibleTracks": len(rows),
            "stableTracks": len(stable_rows),
            "modelStableTracks": sum(row["modelQualityPass"] for row in rows),
            "pathStableTracks": sum(
                row["filterPathCorrelation"] is not None
                and np.isfinite(row["filterPathCorrelation"])
                and row["filterPathCorrelation"] >= CROSS_FILTER_MIN_PATH_CORRELATION
                for row in rows
            ),
            "pointAmplitudeStableTracks": sum(
                row["filterRelativePointDifference"] is not None
                and np.isfinite(row["filterRelativePointDifference"])
                and row["filterRelativePointDifference"]
                <= CROSS_FILTER_MAX_RELATIVE_POINT_DIFFERENCE
                for row in rows
            ),
            "absoluteShareStableTracks": sum(
                row["filterAbsoluteShareDifference"] is not None
                and np.isfinite(row["filterAbsoluteShareDifference"])
                and row["filterAbsoluteShareDifference"]
                <= CROSS_FILTER_MAX_ABSOLUTE_SHARE_DIFFERENCE
                for row in rows
            ),
            "varianceShareStableTracks": sum(
                row["filterVarianceShareDifference"] is not None
                and np.isfinite(row["filterVarianceShareDifference"])
                and row["filterVarianceShareDifference"]
                <= CROSS_FILTER_MAX_VARIANCE_SHARE_DIFFERENCE
                for row in rows
            ),
            "realtimeEligibleTracks": len(realtime_rows),
            "realtimeConfirmedTracks": sum(
                row["realtimeStatus"] == "limited_confirmed"
                for row in realtime_rows
            ),
            "realtimePositiveTracks": sum(
                row["realtimeDirection"] == "positive" for row in realtime_rows
            ),
            "realtimeNegativeTracks": sum(
                row["realtimeDirection"] == "negative" for row in realtime_rows
            ),
            "medianRealtimeSignalToUncertainty": _finite_median(
                [row["realtimeSignalToUncertainty"] for row in realtime_rows]
            ),
            "medianRealtimeCoefficientSignAgreement": _finite_median(
                [row["realtimeCoefficientSignAgreement"] for row in realtime_rows]
            ),
            "medianRealtimeCoefficientUncertaintyShare": _finite_median(
                [row["realtimeCoefficientUncertaintyShare"] for row in realtime_rows]
            ),
            "medianRealtimeStateSpecificationDirectionAgreement": _finite_median(
                [
                    row["realtimeStateSpecificationDirectionAgreement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeRollingStateSpecificationDirectionAgreement": (
                _finite_median(
                    [
                        row[
                            "realtimeRollingStateSpecificationDirectionAgreement"
                        ]
                        for row in realtime_rows
                    ]
                )
            ),
            "medianRealtimeStateSpecificationUncertaintyShare": _finite_median(
                [
                    row["realtimeStateSpecificationUncertaintyShare"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeStateSpecificationWeights": {
                specification_id: _finite_median(
                    [
                        (
                            row["realtimeStateSpecificationWeights"].get(
                                specification_id
                            )
                            if isinstance(
                                row["realtimeStateSpecificationWeights"],
                                dict,
                            )
                            else None
                        )
                        for row in realtime_rows
                    ]
                )
                for specification_id in ("responsive", "baseline", "smooth")
            },
            "medianRealtimeStateSpecificationEffectiveCount": _finite_median(
                [
                    row["realtimeStateSpecificationEffectiveCount"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeStateSpecificationWeightEntropy": _finite_median(
                [
                    row["realtimeStateSpecificationWeightEntropy"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeRollingDirectionAgreement": _finite_median(
                [row["realtimeRollingDirectionAgreement"] for row in realtime_rows]
            ),
            "medianRealtimeRollingContributionCorrelation": _finite_median(
                [row["realtimeRollingContributionCorrelation"] for row in realtime_rows]
            ),
            "medianRealtimeAbsoluteRevision": _finite_median(
                [row["realtimeMedianAbsoluteRevision"] for row in realtime_rows]
            ),
            "medianRealtimeRollingReconstructionR2": _finite_median(
                [row["realtimeRollingReconstructionR2"] for row in realtime_rows]
            ),
            "medianRealtimeEqualMedianRollingReconstructionR2": _finite_median(
                [
                    row["realtimeEqualMedianRollingReconstructionR2"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeDynamicWeightR2Improvement": _finite_median(
                [
                    row["realtimeRollingR2ImprovementVsEqualMedian"]
                    for row in realtime_rows
                ]
            ),
            "realtimeDynamicWeightImprovedTracks": sum(
                row["realtimeRollingR2ImprovementVsEqualMedian"] is not None
                and np.isfinite(
                    row["realtimeRollingR2ImprovementVsEqualMedian"]
                )
                and row["realtimeRollingR2ImprovementVsEqualMedian"] > 0.0
                for row in realtime_rows
            ),
            "realtimePeerSharedEligibleTracks": sum(
                row["realtimePeerSharedStatus"] in {"adopted", "rejected"}
                for row in realtime_rows
            ),
            "realtimePeerSharedAdoptedTracks": sum(
                row["realtimePeerSharedStatus"] == "adopted"
                for row in realtime_rows
            ),
            "realtimePeerSharedPositiveR2Tracks": sum(
                row["realtimePeerSharedRollingR2Improvement"] is not None
                and np.isfinite(
                    row["realtimePeerSharedRollingR2Improvement"]
                )
                and row["realtimePeerSharedRollingR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "medianRealtimePeerSharedR2Improvement": _finite_median(
                [
                    row["realtimePeerSharedRollingR2Improvement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimePeerSharedMaeImprovement": _finite_median(
                [
                    row["realtimePeerSharedMaeImprovement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimePeerSharedDirectionImprovement": _finite_median(
                [
                    row["realtimePeerSharedDirectionImprovement"]
                    for row in realtime_rows
                ]
            ),
            "realtimeDynamicFactorEligibleTracks": sum(
                row["realtimeDynamicFactorStatus"] in {"adopted", "rejected"}
                for row in realtime_rows
            ),
            "realtimeDynamicFactorAdoptedTracks": sum(
                row["realtimeDynamicFactorStatus"] == "adopted"
                for row in realtime_rows
            ),
            "realtimeDynamicFactorPositiveR2Tracks": sum(
                row["realtimeDynamicFactorRollingR2Improvement"] is not None
                and np.isfinite(
                    row["realtimeDynamicFactorRollingR2Improvement"]
                )
                and row["realtimeDynamicFactorRollingR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "medianRealtimeDynamicFactorR2Improvement": _finite_median(
                [
                    row["realtimeDynamicFactorRollingR2Improvement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeDynamicFactorMaeImprovement": _finite_median(
                [
                    row["realtimeDynamicFactorMaeImprovement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeDynamicFactorDirectionImprovement": _finite_median(
                [
                    row["realtimeDynamicFactorDirectionImprovement"]
                    for row in realtime_rows
                ]
            ),
            "realtimeNearestFactorEligibleTracks": sum(
                row["realtimeNearestFactorStatus"] in {"adopted", "rejected"}
                and row["realtimeLowTargetVarianceWarning"] is not True
                for row in realtime_rows
            ),
            "realtimeNearestFactorAdoptedTracks": sum(
                row["realtimeNearestFactorStatus"] == "adopted"
                for row in realtime_rows
            ),
            "realtimeNearestFactorPositiveR2Tracks": sum(
                row["realtimeNearestFactorRollingR2Improvement"] is not None
                and np.isfinite(
                    row["realtimeNearestFactorRollingR2Improvement"]
                )
                and row["realtimeLowTargetVarianceWarning"] is not True
                and row["realtimeNearestFactorRollingR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "medianRealtimeNearestFactorR2Improvement": _finite_median(
                [
                    (
                        row["realtimeNearestFactorRollingR2Improvement"]
                        if row["realtimeLowTargetVarianceWarning"] is not True
                        else None
                    )
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeNearestFactorMaeImprovement": _finite_median(
                [
                    row["realtimeNearestFactorMaeImprovement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeNearestFactorDirectionImprovement": _finite_median(
                [
                    row["realtimeNearestFactorDirectionImprovement"]
                    for row in realtime_rows
                ]
            ),
            "realtimeNearestFactorSpecificationStableTracks": sum(
                row["realtimeNearestFactorSpecificationStable"] is True
                and row["realtimeLowTargetVarianceWarning"] is not True
                for row in realtime_rows
            ),
            "realtimeNearestFactorRobustlyAdoptedTracks": sum(
                row["realtimeNearestFactorRobustlyAdopted"] is True
                for row in realtime_rows
            ),
            "realtimeNearestFactorPositiveEarlyVintageTracks": sum(
                row["realtimeNearestFactorEarlyVintageR2Improvement"] is not None
                and row["realtimeLowTargetVarianceWarning"] is not True
                and np.isfinite(
                    row["realtimeNearestFactorEarlyVintageR2Improvement"]
                )
                and row["realtimeNearestFactorEarlyVintageR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "realtimeNearestFactorPositiveLateVintageTracks": sum(
                row["realtimeNearestFactorLateVintageR2Improvement"] is not None
                and row["realtimeLowTargetVarianceWarning"] is not True
                and np.isfinite(
                    row["realtimeNearestFactorLateVintageR2Improvement"]
                )
                and row["realtimeNearestFactorLateVintageR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "medianRealtimeNearestFactorEarlyVintageR2Improvement": (
                _finite_median(
                    [
                        row[
                            "realtimeNearestFactorEarlyVintageR2Improvement"
                        ]
                        if row["realtimeLowTargetVarianceWarning"] is not True
                        else None
                        for row in realtime_rows
                    ]
                )
            ),
            "medianRealtimeNearestFactorLateVintageR2Improvement": (
                _finite_median(
                    [
                        row[
                            "realtimeNearestFactorLateVintageR2Improvement"
                        ]
                        if row["realtimeLowTargetVarianceWarning"] is not True
                        else None
                        for row in realtime_rows
                    ]
                )
            ),
            "realtimeLowTargetVarianceWarningTracks": sum(
                row["realtimeLowTargetVarianceWarning"] is True
                for row in realtime_rows
            ),
            "realtimeCausalOrthogonalAdoptedTracks": sum(
                row["realtimeCausalOrthogonalStatus"] == "adopted"
                for row in realtime_rows
            ),
            "realtimeCausalOrthogonalPositiveR2Tracks": sum(
                row["realtimeOrthogonalPrimaryR2Improvement"] is not None
                and np.isfinite(
                    row["realtimeOrthogonalPrimaryR2Improvement"]
                )
                and row["realtimeOrthogonalPrimaryR2Improvement"] > 0.0
                for row in realtime_rows
            ),
            "medianRealtimeOrthogonalPrimaryR2Improvement": _finite_median(
                [
                    row["realtimeOrthogonalPrimaryR2Improvement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeOrthogonalComparisonR2Improvement": _finite_median(
                [
                    row["realtimeOrthogonalComparisonR2Improvement"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeBaseMaximumCorrelation": _finite_median(
                [row["realtimeBaseMaximumCorrelation"] for row in realtime_rows]
            ),
            "medianRealtimeOrthogonalMaximumCorrelation": _finite_median(
                [
                    row["realtimeOrthogonalMaximumCorrelation"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeBaseConditionNumber": _finite_median(
                [row["realtimeBaseConditionNumber"] for row in realtime_rows]
            ),
            "medianRealtimeOrthogonalConditionNumber": _finite_median(
                [
                    row["realtimeOrthogonalConditionNumber"]
                    for row in realtime_rows
                ]
            ),
            "medianRealtimeOrthogonalizationUncertaintyShare": _finite_median(
                [
                    row["realtimeOrthogonalizationUncertaintyShare"]
                    for row in orthogonal_rows
                ]
            ),
            "medianRealtimeOrthogonalizationSpanUncertaintyShare": (
                _finite_median(
                    [
                        row[
                            "realtimeOrthogonalizationSpanUncertaintyShare"
                        ]
                        for row in orthogonal_rows
                    ]
                )
            ),
            "positiveTracks": sum(row["pointContribution"] > 0 for row in rows),
            "negativeTracks": sum(row["pointContribution"] < 0 for row in rows),
            "medianAbsoluteShare": float(np.median([row["absoluteShare"] for row in rows])),
            "medianVarianceShare120": float(np.median([row["varianceShare120"] for row in rows])),
            "medianReconstructionR2": float(np.median([row["reconstructionR2"] for row in rows])),
            "directionAgreementTracks": sum(
                row["filterDirectionAgreement"] is True for row in rows
            ),
            "medianFilterPathCorrelation": _finite_median(
                [row["filterPathCorrelation"] for row in rows]
            ),
            "topPositive": positive[:8],
            "topNegative": negative[:8],
            "topInfluence": influence[:16],
            "caveat": "横截面排名表示当前回溯频带影响，不代表该周期对指标的结构性因果效应。",
        }
    return {
        "status": "retrospective_frequency_contribution_study",
        "definition": "标准化指标变化 = 基线 + 可识别周期频带贡献 + 未解释残差",
        "method": "历史长度至少覆盖三轮周期；Gaussian FFT与Butterworth双边滤波分别重构；剔除滤波端点；时间分块选择Ridge强度；仅在方向、路径相关、点幅度和解释方差差异同时达标时标记稳定；显式保留残差并检查逐点守恒；近120期解释方差使用Shapley方法分配。",
        "notCausalAttribution": True,
        "notForecastWeight": True,
        "cycles": cycles,
    }
