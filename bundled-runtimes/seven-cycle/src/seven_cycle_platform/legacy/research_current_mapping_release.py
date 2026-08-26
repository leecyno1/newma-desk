"""Retrospective pseudo-vintage current mapping from cycle-state analogs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.mapping.distribution import (
    CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    HORIZONS,
    RETURN_BASES,
    CurrentDistributionConfig,
    CurrentDistributionResult,
    direction_probabilities,
)
from seven_cycle_platform.mapping.features import CurrentFeatureSnapshot
from seven_cycle_platform.mapping.features import (
    FeatureInput,
    FeatureKind,
    FeaturePayload,
    FeatureProvenance,
    FreshnessPolicy,
    StructuralDriftFlag,
)
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.mapping.transferability import (
    TRANSFERABILITY_EVIDENCE_COLUMNS,
    TransferabilityConfig,
    TransferabilityResult,
    score_transferability,
)
from seven_cycle_platform.mapping.weights import (
    WEIGHT_POLICY_COLUMNS,
    WeightRangeResult,
    suggest_weight_ranges,
)
from seven_cycle_platform.products.asset_mapping_current import (
    AssetMappingCurrentProduct,
    build_asset_mapping_current,
)
from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.types import VintageKind


METHOD_ID = "retrospective_cycle_analog_knn_v1"
CALIBRATION_VERSION = "retrospective-cycle-analog-knn-v1"
EXPECTED_CYCLE_IDS = tuple(f"C{position}" for position in range(1, 8))
RETROSPECTIVE_ANALOG_COLUMNS = (
    "draw_id",
    "analog_origin",
    "analog_end",
    "distance",
    "current_state_date",
    "method",
)
RETROSPECTIVE_ANALOG_FILENAME = "retrospective_analogs.parquet"


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _finite_nonnegative(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite nonnegative number")
    normalized = float(value)
    if not np.isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return normalized


@dataclass(frozen=True, slots=True)
class RetrospectiveAnalogConfig:
    """Immutable historical-neighbor selection policy."""

    draw_count: int = 24
    max_horizon_months: int = 12
    min_effective_samples: int = 24
    angle_period_degrees: float = 360.0

    def __post_init__(self) -> None:
        draw_count = _positive_integer(self.draw_count, name="draw_count")
        horizon = _positive_integer(
            self.max_horizon_months,
            name="max_horizon_months",
        )
        minimum = _positive_integer(
            self.min_effective_samples,
            name="min_effective_samples",
        )
        period = _finite_nonnegative(
            self.angle_period_degrees,
            name="angle_period_degrees",
        )
        if horizon != max(HORIZONS):
            raise ValueError("max_horizon_months must remain 12")
        if minimum > draw_count:
            raise ValueError("min_effective_samples cannot exceed draw_count")
        if period <= 0.0:
            raise ValueError("angle_period_degrees must be strictly positive")
        object.__setattr__(self, "draw_count", draw_count)
        object.__setattr__(self, "max_horizon_months", horizon)
        object.__setattr__(self, "min_effective_samples", minimum)
        object.__setattr__(self, "angle_period_degrees", period)


@dataclass(frozen=True, slots=True)
class RetrospectiveDistributionResult:
    """Governed distribution plus the retained shared analog origins."""

    distribution: CurrentDistributionResult
    analogs: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.distribution, CurrentDistributionResult):
            raise TypeError("distribution must be a CurrentDistributionResult")
        if not isinstance(self.analogs, pd.DataFrame):
            raise TypeError("analogs must be a pandas DataFrame")
        if tuple(self.analogs.columns) != RETROSPECTIVE_ANALOG_COLUMNS:
            raise ValueError("analogs do not match the retrospective contract")
        object.__setattr__(self, "analogs", self.analogs.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == "analogs" and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


@dataclass(frozen=True, slots=True)
class ResearchCurrentMappingArtifacts:
    """Complete retrospective M4 objects retained before atomic publication."""

    snapshot: CurrentFeatureSnapshot
    distribution: CurrentDistributionResult
    transferability: TransferabilityResult
    weight_ranges: WeightRangeResult
    product: AssetMappingCurrentProduct
    analogs: pd.DataFrame

    def __post_init__(self) -> None:
        if tuple(self.analogs.columns) != RETROSPECTIVE_ANALOG_COLUMNS:
            raise ValueError("analogs do not match the retrospective contract")
        object.__setattr__(self, "analogs", self.analogs.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == "analogs" and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def _month_end(values: pd.Series, *, name: str) -> pd.Series:
    try:
        normalized = pd.to_datetime(values, errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain valid dates") from error
    if normalized.isna().any():
        raise ValueError(f"{name} cannot contain missing dates")
    if getattr(normalized.dt, "tz", None) is not None:
        normalized = normalized.dt.tz_convert("UTC").dt.tz_localize(None)
    return normalized.dt.to_period("M").dt.to_timestamp("M")


def _cycle_matrix(cycle_phase: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "cycle_id", "angle"}
    if not isinstance(cycle_phase, pd.DataFrame) or cycle_phase.empty:
        raise ValueError("cycle_phase must be a non-empty DataFrame")
    if not required.issubset(cycle_phase.columns):
        raise ValueError("cycle_phase is missing date, cycle_id, or angle")
    frame = cycle_phase.loc[:, ["date", "cycle_id", "angle"]].copy(deep=True)
    frame["date"] = _month_end(frame["date"], name="cycle date")
    frame["cycle_id"] = frame["cycle_id"].astype(str)
    frame["angle"] = pd.to_numeric(frame["angle"], errors="coerce")
    if frame.duplicated(["date", "cycle_id"]).any():
        raise ValueError("cycle_phase date × cycle_id rows must be unique")
    if set(frame["cycle_id"]) != set(EXPECTED_CYCLE_IDS):
        raise ValueError("cycle_phase must contain exactly C1-C7")
    if not np.isfinite(frame["angle"].to_numpy(dtype="float64")).all():
        raise ValueError("cycle angles must be finite")
    matrix = frame.pivot(index="date", columns="cycle_id", values="angle")
    matrix = matrix.reindex(columns=list(EXPECTED_CYCLE_IDS)).sort_index()
    if matrix.isna().any().any():
        raise ValueError("every cycle date must contain exactly C1-C7")
    return matrix


def _return_panel(asset_returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"date", "asset_id", "return", "benchmark_return"}
    if not isinstance(asset_returns, pd.DataFrame) or asset_returns.empty:
        raise ValueError("asset_returns must be a non-empty DataFrame")
    if not required.issubset(asset_returns.columns):
        raise ValueError("asset_returns is missing required columns")
    frame = asset_returns.loc[:, list(required)].copy(deep=True)
    frame["date"] = _month_end(frame["date"], name="asset return date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ("return", "benchmark_return"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.duplicated(["date", "asset_id"]).any():
        raise ValueError("asset_returns date × asset_id rows must be unique")
    numeric = frame[["return", "benchmark_return"]].to_numpy(dtype="float64")
    if not np.isfinite(numeric).all() or bool((numeric <= -1.0).any()):
        raise ValueError("asset and benchmark returns must be finite and above -100%")
    asset_panel = frame.pivot(index="date", columns="asset_id", values="return")
    benchmark_panel = frame.pivot(
        index="date",
        columns="asset_id",
        values="benchmark_return",
    )
    assets = sorted(asset_panel.columns)
    asset_panel = asset_panel.reindex(columns=assets).sort_index()
    benchmark_panel = benchmark_panel.reindex(columns=assets).sort_index()
    if asset_panel.isna().any().any() or benchmark_panel.isna().any().any():
        raise ValueError("asset_returns must have complete asset coverage by month")
    return asset_panel, benchmark_panel


def _circular_distance(
    candidates: np.ndarray,
    current: np.ndarray,
    *,
    period: float,
) -> np.ndarray:
    difference = np.abs(candidates - current)
    wrapped = np.minimum(difference, period - np.mod(difference, period))
    return np.sqrt(np.mean(np.square(wrapped), axis=1))


def select_retrospective_analogs(
    cycle_phase: pd.DataFrame,
    asset_returns: pd.DataFrame,
    config: RetrospectiveAnalogConfig | None = None,
) -> pd.DataFrame:
    """Select nearest historical C1-C7 states with complete forward paths."""

    normalized_config = config or RetrospectiveAnalogConfig()
    if not isinstance(normalized_config, RetrospectiveAnalogConfig):
        raise TypeError("config must be a RetrospectiveAnalogConfig or None")
    cycle_matrix = _cycle_matrix(cycle_phase)
    asset_panel, benchmark_panel = _return_panel(asset_returns)
    common_return_dates = asset_panel.index.intersection(benchmark_panel.index)
    current_state_date = pd.Timestamp(cycle_matrix.index.max())
    current = cycle_matrix.loc[current_state_date].to_numpy(dtype="float64")
    eligible: list[pd.Timestamp] = []
    for candidate in cycle_matrix.index[cycle_matrix.index < current_state_date]:
        forward_dates = pd.date_range(
            pd.Timestamp(candidate) + pd.offsets.MonthEnd(1),
            periods=normalized_config.max_horizon_months,
            freq="ME",
        )
        if (
            forward_dates[-1] < current_state_date
            and forward_dates.isin(common_return_dates).all()
        ):
            eligible.append(pd.Timestamp(candidate))
    if len(eligible) < normalized_config.draw_count:
        raise ValueError(
            "insufficient complete historical analog paths for requested draw_count"
        )
    candidate_values = cycle_matrix.loc[eligible].to_numpy(dtype="float64")
    distances = _circular_distance(
        candidate_values,
        current,
        period=normalized_config.angle_period_degrees,
    )
    ranked = pd.DataFrame(
        {
            "analog_origin": eligible,
            "distance": distances,
        }
    ).sort_values(["distance", "analog_origin"], kind="stable")
    ranked = ranked.head(normalized_config.draw_count).reset_index(drop=True)
    ranked.insert(0, "draw_id", np.arange(len(ranked), dtype="int64"))
    ranked["analog_end"] = ranked["analog_origin"] + pd.offsets.MonthEnd(
        normalized_config.max_horizon_months
    )
    ranked["current_state_date"] = current_state_date
    ranked["method"] = METHOD_ID
    for column in ("analog_origin", "analog_end", "current_state_date"):
        ranked[column] = ranked[column].dt.date
    return ranked.loc[:, list(RETROSPECTIVE_ANALOG_COLUMNS)]


def _future_dates(as_of: date) -> pd.DatetimeIndex:
    return pd.date_range(
        pd.Timestamp(as_of) + pd.offsets.MonthEnd(1),
        periods=max(HORIZONS),
        freq="ME",
    )


def _summary_rows(
    draws: pd.DataFrame,
    *,
    snapshot: CurrentFeatureSnapshot,
    support: int,
    posterior_date: date,
    config: CurrentDistributionConfig,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for asset_id in sorted(draws["asset_id"].unique()):
        asset_draws = draws.loc[draws["asset_id"].eq(asset_id)]
        for horizon_months in HORIZONS:
            horizon = asset_draws.loc[asset_draws["horizon_months"].eq(horizon_months)]
            for return_basis in RETURN_BASES:
                return_column = (
                    "absolute_return" if return_basis == "absolute" else "excess_return"
                )
                drawdown_column = (
                    "absolute_max_drawdown"
                    if return_basis == "absolute"
                    else "excess_max_drawdown"
                )
                returns = horizon[return_column].to_numpy(dtype="float64")
                drawdowns = horizon[drawdown_column].to_numpy(dtype="float64")
                probabilities = direction_probabilities(
                    returns,
                    neutral_band=config.neutral_bands[(return_basis, horizon_months)],
                )
                q10, q25, q50, q75, q90 = np.quantile(
                    returns,
                    [0.10, 0.25, 0.50, 0.75, 0.90],
                )
                risk = summarize_risk(returns, drawdowns)
                rows.append(
                    {
                        "asset_id": asset_id,
                        "horizon_months": horizon_months,
                        "return_basis": return_basis,
                        "raw_up_probability": probabilities["up"],
                        "raw_neutral_probability": probabilities["neutral"],
                        "raw_down_probability": probabilities["down"],
                        "up_probability": probabilities["up"],
                        "neutral_probability": probabilities["neutral"],
                        "down_probability": probabilities["down"],
                        "q10": float(q10),
                        "q25": float(q25),
                        "q50": float(q50),
                        "q75": float(q75),
                        "q90": float(q90),
                        "expected_return": float(np.mean(returns)),
                        "volatility": risk.volatility,
                        "var95": risk.var95,
                        "cvar95": risk.cvar95,
                        "drawdown_q50": risk.drawdown_q50,
                        "drawdown_q80": risk.drawdown_q80,
                        "drawdown_q95": risk.drawdown_q95,
                        "effective_samples": support,
                        "stage1_training_count": support,
                        "stage2_effective_training_count": support,
                        "residual_history_count": support,
                        "status": "available",
                        "calibration_version": CALIBRATION_VERSION,
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                        "snapshot_data_vintage": snapshot.provenance.data_vintage,
                        "snapshot_model_version": snapshot.provenance.model_version,
                        "snapshot_config_hash": snapshot.provenance.config_hash,
                        "stage1_posterior_date": posterior_date,
                        "stage2_posterior_date": posterior_date,
                        "forecast_origin": snapshot.as_of,
                    }
                )
    return rows


def build_retrospective_current_distribution(
    *,
    snapshot: CurrentFeatureSnapshot,
    cycle_phase: pd.DataFrame,
    asset_returns: pd.DataFrame,
    config: RetrospectiveAnalogConfig | None = None,
) -> RetrospectiveDistributionResult:
    """Build shared-path 3/6/12-month distributions from historical analogs."""

    if not isinstance(snapshot, CurrentFeatureSnapshot):
        raise TypeError("snapshot must be a CurrentFeatureSnapshot")
    normalized_config = config or RetrospectiveAnalogConfig()
    analogs = select_retrospective_analogs(
        cycle_phase,
        asset_returns,
        normalized_config,
    )
    asset_panel, benchmark_panel = _return_panel(asset_returns)
    future_dates = _future_dates(snapshot.as_of)
    monthly_rows: list[dict[str, object]] = []
    draw_rows: list[dict[str, object]] = []
    assets = tuple(sorted(asset_panel.columns))
    for analog in analogs.itertuples(index=False):
        source_dates = pd.date_range(
            pd.Timestamp(analog.analog_origin) + pd.offsets.MonthEnd(1),
            periods=max(HORIZONS),
            freq="ME",
        )
        for asset_id in assets:
            asset_path = asset_panel.loc[source_dates, asset_id].to_numpy(
                dtype="float64"
            )
            benchmark_path = benchmark_panel.loc[source_dates, asset_id].to_numpy(
                dtype="float64"
            )
            relative_path = (1.0 + asset_path) / (1.0 + benchmark_path) - 1.0
            for month_number, (
                forecast_date,
                asset_return,
                benchmark_return,
                relative_return,
            ) in enumerate(
                zip(
                    future_dates,
                    asset_path,
                    benchmark_path,
                    relative_path,
                    strict=True,
                ),
                start=1,
            ):
                monthly_rows.append(
                    {
                        "asset_id": asset_id,
                        "draw_id": int(analog.draw_id),
                        "month_number": month_number,
                        "date": forecast_date,
                        "forecast_origin": snapshot.as_of,
                        "asset_monthly_return": float(asset_return),
                        "benchmark_monthly_return": float(benchmark_return),
                        "relative_monthly_return": float(relative_return),
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                    }
                )
            for horizon_months in HORIZONS:
                absolute_prefix = asset_path[:horizon_months]
                benchmark_prefix = benchmark_path[:horizon_months]
                relative_prefix = relative_path[:horizon_months]
                absolute_return = float(np.prod(1.0 + absolute_prefix) - 1.0)
                benchmark_return = float(np.prod(1.0 + benchmark_prefix) - 1.0)
                excess_return = float(
                    (1.0 + absolute_return) / (1.0 + benchmark_return) - 1.0
                )
                draw_rows.append(
                    {
                        "asset_id": asset_id,
                        "draw_id": int(analog.draw_id),
                        "horizon_months": horizon_months,
                        "absolute_return": absolute_return,
                        "benchmark_return": benchmark_return,
                        "excess_return": excess_return,
                        "absolute_max_drawdown": float(
                            compute_max_drawdown(absolute_prefix)
                        ),
                        "excess_max_drawdown": float(
                            compute_max_drawdown(relative_prefix)
                        ),
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                    }
                )
    distribution_config = CurrentDistributionConfig(
        draw_count=normalized_config.draw_count,
        seed=0,
        residual_block_length=1,
        min_effective_samples=normalized_config.min_effective_samples,
    )
    draws = pd.DataFrame(draw_rows, columns=CURRENT_DISTRIBUTION_DRAW_COLUMNS)
    posterior_date = max(analogs["current_state_date"])
    summary = pd.DataFrame(
        _summary_rows(
            draws,
            snapshot=snapshot,
            support=len(analogs),
            posterior_date=posterior_date,
            config=distribution_config,
        ),
        columns=CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    )
    distribution = CurrentDistributionResult(
        summary=summary,
        monthly_draws=pd.DataFrame(
            monthly_rows,
            columns=CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
        ),
        draws=draws,
        config=distribution_config,
    )
    return RetrospectiveDistributionResult(
        distribution=distribution,
        analogs=analogs,
    )


def _research_feature(
    *,
    context: RunContext,
    kind: FeatureKind,
    feature_id: str,
    values: dict[str, object],
    observation_date: date,
    unit: str,
    entity_id: str | None = None,
) -> FeatureInput:
    payload = FeaturePayload(
        kind=kind,
        feature_id=feature_id,
        entity_id=entity_id,
        values=values,
    )
    provenance = FeatureProvenance.from_payload(
        payload,
        observation_date=observation_date,
        release_date=observation_date,
        vintage_date=context.data_vintage,
        source="retrospective_research_release",
        unit=unit,
        retrieval_time=context.created_at,
        revision_number=0,
        quality_status="accepted_for_retrospective_research",
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
        methodology=METHOD_ID,
        vintage_caveat=(
            "Pseudo-vintage retrospective research evidence; not realtime history."
        ),
    )
    return FeatureInput(
        payload=payload,
        provenance=provenance,
        freshness_policy=FreshnessPolicy(
            max_observation_age_days=120,
            max_visible_age_days=31,
        ),
        structural_drift=StructuralDriftFlag(
            detected=False,
            score=0.0,
            threshold=1.0,
            method="retrospective_release_gate",
            baseline_id="retrospective-cycle-analog-v1",
            evaluated_at=context.data_vintage,
            reason="formal structural validation is not published",
        ),
    )


def build_research_current_snapshot(
    *,
    context: RunContext,
    cycle_phase: pd.DataFrame,
    channel_states: pd.DataFrame,
    asset_ids: tuple[str, ...],
) -> CurrentFeatureSnapshot:
    """Build explicit pseudo-vintage current features without invented controls."""

    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    cycle_matrix = _cycle_matrix(cycle_phase)
    current_state_date = pd.Timestamp(cycle_matrix.index.max())
    latest_cycles = cycle_phase.copy(deep=True)
    latest_cycles["date"] = _month_end(latest_cycles["date"], name="cycle date")
    latest_cycles = latest_cycles.loc[latest_cycles["date"].eq(current_state_date)]
    latest_cycles = latest_cycles.set_index("cycle_id")
    cycles = tuple(
        _research_feature(
            context=context,
            kind=FeatureKind.CYCLE,
            feature_id=cycle_id,
            values={
                "angle": float(latest_cycles.loc[cycle_id, "angle"]),
                "phase": str(latest_cycles.loc[cycle_id, "phase"]),
                "level": float(latest_cycles.loc[cycle_id, "level"]),
                "slope": float(latest_cycles.loc[cycle_id, "slope"]),
                "confidence": float(latest_cycles.loc[cycle_id, "confidence"]),
                "status": "available",
            },
            observation_date=current_state_date.date(),
            unit="cycle_state",
        )
        for cycle_id in EXPECTED_CYCLE_IDS
    )
    channel_frame = channel_states.copy(deep=True)
    channel_frame["date"] = _month_end(channel_frame["date"], name="channel date")
    latest_channels = channel_frame.loc[
        channel_frame["date"].eq(current_state_date)
    ].set_index("channel_id")
    channel_features: list[FeatureInput] = []
    for channel_id in sorted(latest_channels.index):
        row = latest_channels.loc[channel_id]
        available = str(row["status"]) == "available"
        values: dict[str, object] = {
            "status": "available" if available else "unavailable",
            "status_reason": str(row["status_reason"]),
            "member_count": int(row["member_count"]),
        }
        if available:
            values.update(
                {
                    "state": float(row["state"]),
                    "innovation": float(row["innovation"]),
                    "uncertainty": float(row["uncertainty"]),
                }
            )
        channel_features.append(
            _research_feature(
                context=context,
                kind=FeatureKind.CHANNEL,
                feature_id=channel_id,
                values=values,
                observation_date=current_state_date.date(),
                unit="research_channel_state",
            )
        )
    if not channel_features:
        raise ValueError("channel_states must retain current channel coverage")

    def unavailable_controls(
        kind: FeatureKind, feature_id: str
    ) -> tuple[FeatureInput, ...]:
        return tuple(
            _research_feature(
                context=context,
                kind=kind,
                feature_id=feature_id,
                entity_id=asset_id,
                values={
                    "status": "unavailable",
                    "reason": "no governed point-in-time input in retrospective release",
                },
                observation_date=current_state_date.date(),
                unit="availability_status",
            )
            for asset_id in asset_ids
        )

    return CurrentFeatureSnapshot(
        as_of=context.as_of,
        cycle_states=cycles,
        channel_states=tuple(channel_features),
        valuation_controls=unavailable_controls(
            FeatureKind.VALUATION,
            "valuation_unavailable",
        ),
        earnings_controls=unavailable_controls(
            FeatureKind.EARNINGS,
            "earnings_unavailable",
        ),
        positioning_controls=unavailable_controls(
            FeatureKind.POSITIONING,
            "positioning_unavailable",
        ),
        liquidity_controls=unavailable_controls(
            FeatureKind.LIQUIDITY,
            "liquidity_unavailable",
        ),
        event_scenarios=unavailable_controls(
            FeatureKind.EVENT,
            "event_unavailable",
        ),
        historical_posterior=tuple(
            _research_feature(
                context=context,
                kind=FeatureKind.HISTORICAL_POSTERIOR,
                feature_id="cycle_analog_history",
                entity_id=asset_id,
                values={"status": "available", "method": METHOD_ID},
                observation_date=current_state_date.date(),
                unit="historical_analog_model",
            )
            for asset_id in asset_ids
        ),
        run_context=context,
    )


def _stability_score(values: np.ndarray) -> float:
    q25, q50, q75 = np.quantile(values, [0.25, 0.50, 0.75])
    spread = float(q75 - q25)
    scale = abs(float(q50)) + spread + 1e-12
    return float(np.clip(1.0 - spread / scale, 0.0, 1.0))


def _structural_score(values: np.ndarray, origins: np.ndarray) -> float:
    order = np.argsort(origins, kind="stable")
    ordered = values[order]
    midpoint = len(ordered) // 2
    left = ordered[:midpoint]
    right = ordered[midpoint:]
    if len(left) == 0 or len(right) == 0:
        return 0.0
    difference = abs(float(np.median(left)) - float(np.median(right)))
    scale = float(np.std(ordered, ddof=0)) + difference + 1e-12
    return float(np.clip(1.0 - difference / scale, 0.0, 1.0))


def _transferability_evidence(
    *,
    distribution: CurrentDistributionResult,
    analogs: pd.DataFrame,
    snapshot: CurrentFeatureSnapshot,
) -> pd.DataFrame:
    draws = distribution.draws
    origins = (
        pd.to_datetime(analogs.sort_values("draw_id")["analog_origin"])
        .astype("int64")
        .to_numpy()
    )
    neighbor_similarity = float(np.exp(-float(analogs["distance"].mean()) / 90.0))
    cycle_confidence = float(
        np.mean(
            [
                float(feature.payload.values["confidence"])
                for feature in snapshot.cycle_states
            ]
        )
    )
    channel_confidence = float(
        np.mean(
            [
                1.0 if feature.payload.values["status"] == "available" else 0.0
                for feature in snapshot.channel_states
            ]
        )
    )
    rows: list[dict[str, object]] = []
    for (asset_id, horizon_months), group in draws.groupby(
        ["asset_id", "horizon_months"],
        sort=True,
    ):
        returns = group.sort_values("draw_id")["absolute_return"].to_numpy(
            dtype="float64"
        )
        positive_share = float(np.mean(returns > 0.0))
        negative_share = float(np.mean(returns < 0.0))
        sign_stability = max(positive_share, negative_share)
        model_loss = max(float(np.mean(np.square(returns - np.median(returns)))), 1e-12)
        baseline_loss = max(float(np.mean(np.square(returns))), 1e-12)
        rows.append(
            {
                "asset_id": asset_id,
                "horizon_months": int(horizon_months),
                "sign_stability": sign_stability,
                "magnitude_stability": _stability_score(returns),
                "historical_neighbor_similarity": neighbor_similarity,
                "constituent_business_model_stability": 1.0,
                "valuation_positioning_similarity": 0.0,
                "structural_stability": _structural_score(returns, origins),
                "cycle_confidence": cycle_confidence,
                "channel_confidence": channel_confidence,
                "proxy_discount": 0.0,
                "model_oos_loss": model_loss,
                "baseline_oos_loss": baseline_loss,
                "oos_validation_count": len(returns),
                "evidence_date": snapshot.provenance.data_vintage,
                "validation_end": max(analogs["analog_end"]),
            }
        )
    return pd.DataFrame(rows, columns=TRANSFERABILITY_EVIDENCE_COLUMNS)


def _weight_policy(
    distribution: CurrentDistributionResult, *, as_of: date
) -> pd.DataFrame:
    dimensions = (
        distribution.summary.loc[:, ["asset_id", "horizon_months"]]
        .drop_duplicates()
        .sort_values(["asset_id", "horizon_months"], kind="stable")
    )
    return pd.DataFrame(
        [
            {
                "asset_id": row.asset_id,
                "horizon_months": int(row.horizon_months),
                "neutral_min_weight": 0.0,
                "neutral_max_weight": 0.1,
                "max_active_tilt": 0.0,
                "active_risk_budget_cap": 0.0,
                "model_disagreement": 1.0,
                "leveraged": False,
                "liquidity_constrained": False,
                "currency_exposed": False,
                "policy_date": as_of,
                "policy_version": "retrospective-only-no-weight-publication-v1",
            }
            for row in dimensions.itertuples(index=False)
        ],
        columns=WEIGHT_POLICY_COLUMNS,
    )


def build_research_current_mapping(
    *,
    context: RunContext,
    cycle_phase: pd.DataFrame,
    channel_states: pd.DataFrame,
    asset_returns: pd.DataFrame,
    m3_influence: pd.DataFrame,
    analog_config: RetrospectiveAnalogConfig | None = None,
) -> ResearchCurrentMappingArtifacts:
    """Build retrospective-only M4 Mapping with formal usage and weights disabled."""

    asset_ids = tuple(sorted(asset_returns["asset_id"].unique()))
    snapshot = build_research_current_snapshot(
        context=context,
        cycle_phase=cycle_phase,
        channel_states=channel_states,
        asset_ids=asset_ids,
    )
    retrospective = build_retrospective_current_distribution(
        snapshot=snapshot,
        cycle_phase=cycle_phase,
        asset_returns=asset_returns,
        config=analog_config,
    )
    evidence = _transferability_evidence(
        distribution=retrospective.distribution,
        analogs=retrospective.analogs,
        snapshot=snapshot,
    )
    transferability = score_transferability(
        retrospective.distribution,
        evidence,
        TransferabilityConfig(
            min_oos_validation_count=1,
            min_oos_increment=1.0,
            full_score_oos_increment=1.0,
        ),
    )
    if not transferability.summary["status"].eq("retrospective_only").all():
        raise ValueError("retrospective release cannot promote transferability")
    weight_ranges = suggest_weight_ranges(
        retrospective.distribution,
        transferability,
        _weight_policy(retrospective.distribution, as_of=context.as_of),
    )
    if not weight_ranges.summary["range_status"].eq("unavailable").all():
        raise ValueError("retrospective release cannot publish weight ranges")
    product = build_asset_mapping_current(
        snapshot,
        retrospective.distribution,
        transferability,
        weight_ranges,
        m3_influence,
    )
    return ResearchCurrentMappingArtifacts(
        snapshot=snapshot,
        distribution=retrospective.distribution,
        transferability=transferability,
        weight_ranges=weight_ranges,
        product=product,
        analogs=retrospective.analogs,
    )


__all__ = [
    "CALIBRATION_VERSION",
    "METHOD_ID",
    "RETROSPECTIVE_ANALOG_COLUMNS",
    "RETROSPECTIVE_ANALOG_FILENAME",
    "ResearchCurrentMappingArtifacts",
    "RetrospectiveAnalogConfig",
    "RetrospectiveDistributionResult",
    "build_research_current_mapping",
    "build_research_current_snapshot",
    "build_retrospective_current_distribution",
    "select_retrospective_analogs",
]
