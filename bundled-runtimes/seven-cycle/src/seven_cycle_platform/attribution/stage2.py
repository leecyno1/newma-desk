"""Hierarchical channel-to-asset attribution with past-only estimation."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.hierarchy import (
    HierarchicalPosterior,
    fit_hierarchical_tvp_ridge,
)


CHANNEL_TO_ASSET_COMPONENT_COLUMNS = (
    "date",
    "asset_id",
    "component_type",
    "component_id",
    "component_value",
    "coefficient_mean",
    "contribution",
    "observed_return",
    "predicted_return",
    "asset_residual",
    "training_start",
    "training_end",
    "training_count",
    "effective_training_count",
    "parent_node_id",
    "parent_coefficient_mean",
    "own_weight",
    "parent_weight",
    "confidence",
    "proxy_discount",
    "condition_number",
    "status",
    "window",
    "rolling_window",
    "forgetting_factor",
    "estimation_method",
)

CHANNEL_TO_ASSET_POSTERIOR_COLUMNS = (
    "date",
    "node_level",
    "node_id",
    "parent_node_id",
    "component_type",
    "component_id",
    "coefficient_mean",
    "parent_coefficient_mean",
    "prior_precision",
    "own_weight",
    "parent_weight",
    "confidence",
    "proxy_discount",
    "training_start",
    "training_end",
    "training_count",
    "effective_training_count",
    "condition_number",
    "status",
    "window",
    "rolling_window",
    "forgetting_factor",
    "estimation_method",
)

CHANNEL_TO_ASSET_COVARIANCE_COLUMNS = (
    "date",
    "node_level",
    "node_id",
    "parent_node_id",
    "component_i_type",
    "component_i_id",
    "component_j_type",
    "component_j_id",
    "coefficient_covariance",
    "training_start",
    "training_end",
    "training_count",
    "effective_training_count",
    "prior_precision",
    "own_weight",
    "parent_weight",
    "confidence",
    "proxy_discount",
    "condition_number",
    "status",
    "window",
    "rolling_window",
    "forgetting_factor",
    "estimation_method",
)

_RESULT_FIELDS = frozenset({"components", "posteriors", "covariance"})
_COMPONENT_ORDER = {
    "intercept": 0,
    "benchmark": 1,
    "channel": 2,
    "interaction": 3,
    "control": 4,
    "event": 5,
    "residual": 6,
}
_NODE_LEVEL_ORDER = {"asset_class": 0, "industry": 1, "asset": 2}
_VALID_COMPONENT_TYPES = frozenset(_COMPONENT_ORDER)
_VALID_STATUSES = frozenset(
    {
        "estimated",
        "parent_informed",
        "parent_only",
        "insufficient_history",
        "not_identifiable",
        "unavailable",
    }
)
_ESTIMATION_METHOD = "hierarchical_tvp_ridge"
_INTERCEPT_KEY = ("intercept", "intercept")
_BENCHMARK_KEY = ("benchmark", "benchmark_return")


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


@dataclass(frozen=True)
class HierarchicalTVPConfig:
    """Configuration for past-only hierarchical TVP ridge estimation."""

    window: str = "expanding"
    rolling_window: int | None = None
    min_asset_training_count: int = 18
    min_parent_training_count: int = 24
    root_ridge: float = 1.0
    industry_prior_strength: float = 12.0
    asset_prior_strength: float = 18.0
    condition_number_threshold: float = 1_000_000.0
    forgetting_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.window not in {"expanding", "rolling"}:
            raise ValueError("window must be 'expanding' or 'rolling'")
        min_asset = _positive_integer(
            self.min_asset_training_count,
            "min_asset_training_count",
        )
        min_parent = _positive_integer(
            self.min_parent_training_count,
            "min_parent_training_count",
        )
        normalized_rolling: int | None = None
        if self.window == "rolling":
            normalized_rolling = _positive_integer(
                self.rolling_window,
                "rolling_window",
            )
            if normalized_rolling < max(min_asset, min_parent):
                raise ValueError(
                    "rolling_window cannot be smaller than minimum training counts"
                )
        elif self.rolling_window is not None:
            raise ValueError("rolling_window is only valid for a rolling window")
        root_ridge = _positive_real(self.root_ridge, "root_ridge")
        industry_strength = _positive_real(
            self.industry_prior_strength,
            "industry_prior_strength",
        )
        asset_strength = _positive_real(
            self.asset_prior_strength,
            "asset_prior_strength",
        )
        threshold = _positive_real(
            self.condition_number_threshold,
            "condition_number_threshold",
        )
        forgetting_factor = _positive_real(
            self.forgetting_factor,
            "forgetting_factor",
        )
        if forgetting_factor > 1.0:
            raise ValueError("forgetting_factor must be in (0, 1]")
        object.__setattr__(self, "rolling_window", normalized_rolling)
        object.__setattr__(self, "min_asset_training_count", min_asset)
        object.__setattr__(self, "min_parent_training_count", min_parent)
        object.__setattr__(self, "root_ridge", root_ridge)
        object.__setattr__(self, "industry_prior_strength", industry_strength)
        object.__setattr__(self, "asset_prior_strength", asset_strength)
        object.__setattr__(self, "condition_number_threshold", threshold)
        object.__setattr__(self, "forgetting_factor", forgetting_factor)


def _validate_component_groups(components: pd.DataFrame) -> None:
    for _, group in components.groupby(["date", "asset_id"], sort=False):
        if len(group.loc[group["component_type"].eq("intercept")]) != 1:
            raise ValueError("each asset group must contain one intercept")
        if len(group.loc[group["component_type"].eq("residual")]) != 1:
            raise ValueError("each asset group must contain one residual")
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("component status must be constant within an asset group")
        predicted = group["predicted_return"].iloc[0]
        if np.isfinite(predicted):
            if not group["predicted_return"].eq(predicted).all():
                raise ValueError("predicted_return must be grouped")
            non_residual = group.loc[group["component_type"].ne("residual")]
            expected = float(non_residual["contribution"].sum())
            if not np.isclose(predicted, expected, atol=1e-10, rtol=1e-10):
                raise ValueError("predicted_return does not conserve contributions")
            observed = group["observed_return"].iloc[0]
            residual = group["asset_residual"].iloc[0]
            residual_contribution = group.loc[
                group["component_type"].eq("residual"), "contribution"
            ].iloc[0]
            if np.isfinite(observed):
                if not np.isfinite(residual) or not np.isclose(
                    observed,
                    predicted + residual,
                    atol=1e-10,
                    rtol=1e-10,
                ):
                    raise ValueError("observed_return does not conserve residual")
                if not np.isclose(
                    residual,
                    residual_contribution,
                    atol=1e-10,
                    rtol=1e-10,
                ):
                    raise ValueError("residual contribution is inconsistent")
        training_rows = group.loc[group["training_end"].notna()]
        if bool((training_rows["training_end"] >= training_rows["date"]).any()):
            raise ValueError("training_end must be earlier than attribution date")


def _validate_posterior_covariance(
    posteriors: pd.DataFrame,
    covariance: pd.DataFrame,
) -> None:
    posterior_keys: set[tuple[object, object, object]] = set()
    for key, group in posteriors.groupby(["date", "node_level", "node_id"], sort=False):
        posterior_keys.add(key)
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("posterior status must be constant within a node")
        training_rows = group.loc[group["training_end"].notna()]
        if bool((training_rows["training_end"] >= training_rows["date"]).any()):
            raise ValueError("training_end must be earlier than attribution date")
    covariance_keys: set[tuple[object, object, object]] = set()
    for key, group in covariance.groupby(["date", "node_level", "node_id"], sort=False):
        covariance_keys.add(key)
        posterior_group = posteriors.loc[
            posteriors["date"].eq(key[0])
            & posteriors["node_level"].eq(key[1])
            & posteriors["node_id"].eq(key[2])
        ]
        labels = list(
            dict.fromkeys(
                zip(
                    posterior_group["component_type"],
                    posterior_group["component_id"],
                    strict=True,
                )
            )
        )
        label_set = set(labels)
        pairs = set(
            zip(
                zip(
                    group["component_i_type"],
                    group["component_i_id"],
                    strict=True,
                ),
                zip(
                    group["component_j_type"],
                    group["component_j_id"],
                    strict=True,
                ),
                strict=True,
            )
        )
        expected_pairs = {
            (label_i, label_j) for label_i in label_set for label_j in label_set
        }
        if pairs != expected_pairs:
            raise ValueError("covariance must contain every node component pair")
        values = group["coefficient_covariance"]
        status = posterior_group["status"].iloc[0]
        coefficient_means = posterior_group["coefficient_mean"]
        if status in {"insufficient_history", "not_identifiable"}:
            if coefficient_means.notna().any() or values.notna().any():
                raise ValueError("failed posteriors must have missing estimates")
            continue
        if coefficient_means.isna().any():
            raise ValueError("usable posteriors must have finite estimates")
        if values.notna().any():
            if values.isna().any():
                raise ValueError("covariance matrices cannot be partially missing")
            lookup = {
                (
                    (row.component_i_type, row.component_i_id),
                    (row.component_j_type, row.component_j_id),
                ): row.coefficient_covariance
                for row in group.itertuples(index=False)
            }
            for label_i in label_set:
                for label_j in labels:
                    if not np.isclose(
                        lookup[(label_i, label_j)],
                        lookup[(label_j, label_i)],
                        atol=1e-10,
                        rtol=1e-10,
                    ):
                        raise ValueError("covariance must be symmetric")
            matrix = np.asarray(
                [
                    [lookup[(label_i, label_j)] for label_j in labels]
                    for label_i in labels
                ],
                dtype="float64",
            )
            eigenvalues = np.linalg.eigvalsh((matrix + matrix.T) / 2.0)
            scale = max(1.0, float(np.max(np.abs(eigenvalues))))
            if eigenvalues.min() < -1e-10 * scale:
                raise ValueError("covariance must be positive semidefinite")
        else:
            raise ValueError("usable posteriors require finite covariance")
    if posterior_keys != covariance_keys:
        raise ValueError("posterior and covariance node groups must align")


@dataclass(frozen=True)
class ChannelToAssetResult:
    """Detached asset components, hierarchical posteriors, and covariance."""

    components: pd.DataFrame
    posteriors: pd.DataFrame
    covariance: pd.DataFrame

    def __post_init__(self) -> None:
        components = object.__getattribute__(self, "components")
        posteriors = object.__getattribute__(self, "posteriors")
        covariance = object.__getattribute__(self, "covariance")
        if not isinstance(components, pd.DataFrame):
            raise TypeError("components must be a pandas DataFrame")
        if not isinstance(posteriors, pd.DataFrame):
            raise TypeError("posteriors must be a pandas DataFrame")
        if not isinstance(covariance, pd.DataFrame):
            raise TypeError("covariance must be a pandas DataFrame")
        if tuple(components.columns) != CHANNEL_TO_ASSET_COMPONENT_COLUMNS:
            raise ValueError("components columns do not match the attribution contract")
        if tuple(posteriors.columns) != CHANNEL_TO_ASSET_POSTERIOR_COLUMNS:
            raise ValueError("posteriors columns do not match the attribution contract")
        if tuple(covariance.columns) != CHANNEL_TO_ASSET_COVARIANCE_COLUMNS:
            raise ValueError("covariance columns do not match the attribution contract")
        if components.duplicated(
            ["date", "asset_id", "component_type", "component_id"]
        ).any():
            raise ValueError("asset component rows must be unique")
        if posteriors.duplicated(
            ["date", "node_level", "node_id", "component_type", "component_id"]
        ).any():
            raise ValueError("node posterior rows must be unique")
        if covariance.duplicated(
            [
                "date",
                "node_level",
                "node_id",
                "component_i_type",
                "component_i_id",
                "component_j_type",
                "component_j_id",
            ]
        ).any():
            raise ValueError("node covariance rows must be unique")
        if not set(components["component_type"]).issubset(_VALID_COMPONENT_TYPES):
            raise ValueError("components contain an unknown component type")
        for frame in (components, posteriors, covariance):
            if not set(frame["status"]).issubset(_VALID_STATUSES):
                raise ValueError("result contains an unknown attribution status")
        _validate_component_groups(components)
        _validate_posterior_covariance(posteriors, covariance)
        object.__setattr__(self, "components", _copy_frame(components))
        object.__setattr__(self, "posteriors", _copy_frame(posteriors))
        object.__setattr__(self, "covariance", _copy_frame(covariance))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.components

    @property
    def coefficients(self) -> pd.DataFrame:
        return self.posteriors

    @property
    def coefficient_covariance(self) -> pd.DataFrame:
        return self.covariance


def _normalize_dates(values: pd.Series, name: str) -> pd.Series:
    normalized: list[pd.Timestamp] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            raise ValueError(f"{name} dates cannot be missing")
        if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
            raise TypeError(f"{name} dates must be date-like values")
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{name} dates must be valid date-like values") from error
        if timestamp.tzinfo is not None:
            raise ValueError(f"{name} dates must be timezone-naive")
        normalized.append(timestamp.normalize())
    return pd.Series(normalized, index=values.index, dtype="datetime64[ns]")


def _normalize_numeric(
    values: pd.Series,
    name: str,
    *,
    allow_missing: bool,
) -> pd.Series:
    normalized: list[float] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            if allow_missing:
                normalized.append(np.nan)
                continue
            raise ValueError(f"{name} values cannot be missing")
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (Real, np.integer, np.floating),
        ):
            raise TypeError(f"{name} values must be numeric")
        numeric = float(value)
        if not np.isfinite(numeric):
            suffix = " or missing" if allow_missing else ""
            raise ValueError(f"{name} values must be finite{suffix}")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _validate_identifiers(values: pd.Series, name: str) -> None:
    if any(not isinstance(value, str) or not value for value in values):
        raise TypeError(f"{name} values must be non-empty strings")


def _required_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
    allow_empty: bool = False,
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")
    if values.empty and not allow_empty:
        raise ValueError(f"{name} must contain at least one row")
    return values.loc[:, list(columns)].copy(deep=True)


def _normalize_asset_returns(values: object) -> pd.DataFrame:
    returns = _required_frame(
        values,
        name="asset_returns",
        columns=("date", "asset_id", "return", "benchmark_return"),
    )
    returns["date"] = _normalize_dates(returns["date"], "asset return")
    _validate_identifiers(returns["asset_id"], "asset_id")
    if returns.duplicated(["date", "asset_id"]).any():
        raise ValueError("date × asset_id asset returns must be unique")
    returns["return"] = _normalize_numeric(
        returns["return"],
        "asset return",
        allow_missing=True,
    )
    returns["benchmark_return"] = _normalize_numeric(
        returns["benchmark_return"],
        "benchmark return",
        allow_missing=True,
    )
    return returns.sort_values(["date", "asset_id"], kind="stable").reset_index(
        drop=True
    )


def _normalize_channels(values: object) -> pd.DataFrame:
    channels = _required_frame(
        values,
        name="channel_innovations",
        columns=("date", "channel_id", "innovation"),
    )
    channels["date"] = _normalize_dates(channels["date"], "channel innovation")
    _validate_identifiers(channels["channel_id"], "channel_id")
    if channels.duplicated(["date", "channel_id"]).any():
        raise ValueError("date × channel_id channel innovations must be unique")
    channels["innovation"] = _normalize_numeric(
        channels["innovation"],
        "channel innovation",
        allow_missing=True,
    )
    return channels.sort_values(["date", "channel_id"], kind="stable").reset_index(
        drop=True
    )


def _normalize_hierarchy(values: object) -> pd.DataFrame:
    hierarchy = _required_frame(
        values,
        name="hierarchy",
        columns=(
            "asset_id",
            "asset_class_id",
            "industry_id",
            "is_proxy",
            "confidence_discount",
        ),
    )
    for column in ("asset_id", "asset_class_id", "industry_id"):
        _validate_identifiers(hierarchy[column], column)
    if hierarchy.duplicated(["asset_id"]).any():
        raise ValueError("asset_id hierarchy rows must be unique")
    asset_ids = set(hierarchy["asset_id"])
    class_ids = set(hierarchy["asset_class_id"])
    industry_ids = set(hierarchy["industry_id"])
    if asset_ids & class_ids or asset_ids & industry_ids or class_ids & industry_ids:
        raise ValueError("hierarchy identifiers cannot overlap across levels")
    class_counts = hierarchy.groupby("industry_id")["asset_class_id"].nunique()
    if bool(class_counts.gt(1).any()):
        raise ValueError("each industry_id must map to one asset_class_id")
    if any(not isinstance(value, (bool, np.bool_)) for value in hierarchy["is_proxy"]):
        raise TypeError("is_proxy values must be boolean")
    hierarchy["is_proxy"] = hierarchy["is_proxy"].astype(bool)
    hierarchy["confidence_discount"] = _normalize_numeric(
        hierarchy["confidence_discount"],
        "confidence_discount",
        allow_missing=False,
    )
    if bool(
        (
            (hierarchy["confidence_discount"] < 0.0)
            | (hierarchy["confidence_discount"] >= 1.0)
        ).any()
    ):
        raise ValueError("confidence_discount must be in [0, 1)")
    invalid_non_proxy = ~hierarchy["is_proxy"] & hierarchy["confidence_discount"].ne(
        0.0
    )
    if bool(invalid_non_proxy.any()):
        raise ValueError("non-proxy assets cannot define a confidence discount")
    return hierarchy.sort_values(
        ["asset_class_id", "industry_id", "asset_id"], kind="stable"
    ).reset_index(drop=True)


def _normalize_interactions(values: object | None) -> pd.DataFrame:
    columns = ("date", "interaction_id", "value", "validated")
    if values is None:
        return pd.DataFrame(columns=columns)
    interactions = _required_frame(
        values,
        name="interactions",
        columns=columns,
        allow_empty=True,
    )
    if interactions.empty:
        return interactions
    interactions["date"] = _normalize_dates(interactions["date"], "interaction")
    _validate_identifiers(interactions["interaction_id"], "interaction_id")
    if interactions.duplicated(["date", "interaction_id"]).any():
        raise ValueError("date × interaction_id interactions must be unique")
    interactions["value"] = _normalize_numeric(
        interactions["value"],
        "interaction",
        allow_missing=False,
    )
    if any(
        not isinstance(value, (bool, np.bool_)) for value in interactions["validated"]
    ):
        raise TypeError("validated values must be boolean")
    interactions["validated"] = interactions["validated"].astype(bool)
    return interactions.sort_values(
        ["date", "interaction_id"], kind="stable"
    ).reset_index(drop=True)


def _normalize_asset_features(
    values: object | None,
    *,
    name: str,
    id_column: str,
) -> pd.DataFrame:
    columns = ("date", "asset_id", id_column, "value")
    if values is None:
        return pd.DataFrame(columns=columns)
    features = _required_frame(
        values,
        name=name,
        columns=columns,
        allow_empty=True,
    )
    if features.empty:
        return features
    features["date"] = _normalize_dates(features["date"], name[:-1])
    _validate_identifiers(features["asset_id"], "asset_id")
    _validate_identifiers(features[id_column], id_column)
    if features.duplicated(["date", "asset_id", id_column]).any():
        raise ValueError(f"date × asset_id × {id_column} {name} must be unique")
    features["value"] = _normalize_numeric(
        features["value"],
        name[:-1],
        allow_missing=False,
    )
    return features.sort_values(
        ["date", "asset_id", id_column], kind="stable"
    ).reset_index(drop=True)


@dataclass(frozen=True)
class _NodeFit:
    posterior: HierarchicalPosterior
    training_start: pd.Timestamp | pd.NaT
    training_end: pd.Timestamp | pd.NaT
    parameter_keys: tuple[tuple[str, str], ...]


def _lookup(
    values: pd.DataFrame, key_columns: list[str]
) -> dict[tuple[object, ...], float]:
    if values.empty:
        return {}
    return {
        tuple(getattr(row, column) for column in key_columns): float(row.value)
        for row in values.itertuples(index=False)
    }


def _channel_lookup(values: pd.DataFrame) -> dict[tuple[pd.Timestamp, str], float]:
    return {
        (row.date, row.channel_id): float(row.innovation)
        for row in values.itertuples(index=False)
    }


def _training_arrays(
    asset_returns: pd.DataFrame,
    *,
    descendant_assets: set[str],
    current_date: pd.Timestamp,
    feature_keys: tuple[tuple[str, str], ...],
    channel_values: dict[tuple[pd.Timestamp, str], float],
    interaction_values: dict[tuple[pd.Timestamp, str], float],
    control_values: dict[tuple[pd.Timestamp, str, str], float],
    event_values: dict[tuple[pd.Timestamp, str, str], float],
    hierarchy_rows: dict[str, dict[str, object]],
    config: HierarchicalTVPConfig,
) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT
]:
    candidates = asset_returns.loc[
        asset_returns["date"].lt(current_date)
        & asset_returns["asset_id"].isin(descendant_assets)
    ]
    records: list[tuple[pd.Timestamp, str, float, list[float]]] = []
    for date, asset_id, observed_value, benchmark_value in candidates.itertuples(
        index=False,
        name=None,
    ):
        observed = float(observed_value)
        benchmark_return = float(benchmark_value)
        if not np.isfinite(observed) or not np.isfinite(benchmark_return):
            continue
        feature_values: list[float] = []
        complete = True
        for component_type, component_id in feature_keys:
            if component_type == "benchmark":
                value = benchmark_return
            elif component_type == "channel":
                value = channel_values.get((date, component_id), np.nan)
            elif component_type == "interaction":
                value = interaction_values.get((date, component_id), np.nan)
            elif component_type == "control":
                value = control_values.get((date, asset_id, component_id), 0.0)
            else:
                value = event_values.get((date, asset_id, component_id), 0.0)
            if not np.isfinite(value):
                complete = False
                break
            feature_values.append(float(value))
        if complete:
            records.append((date, asset_id, observed, feature_values))
    if config.window == "rolling" and records:
        eligible_dates = sorted({record[0] for record in records})
        selected_dates = set(eligible_dates[-config.rolling_window :])
        records = [record for record in records if record[0] in selected_dates]
    if not records:
        return (
            np.empty((0, len(feature_keys)), dtype="float64"),
            np.empty(0, dtype="float64"),
            np.empty(0, dtype="float64"),
            pd.NaT,
            pd.NaT,
        )
    records.sort(key=lambda record: (record[0], record[1]))
    training_dates = sorted({record[0] for record in records})
    date_positions = {date: position for position, date in enumerate(training_dates)}
    features = np.asarray([record[3] for record in records], dtype="float64")
    target = np.asarray([record[2] for record in records], dtype="float64")
    weights = np.asarray(
        [
            config.forgetting_factor
            ** (len(training_dates) - 1 - date_positions[record[0]])
            * float(hierarchy_rows[record[1]]["effective_confidence"])
            for record in records
        ],
        dtype="float64",
    )
    return features, target, weights, training_dates[0], training_dates[-1]


def _fit_node(
    asset_returns: pd.DataFrame,
    *,
    descendant_assets: set[str],
    current_date: pd.Timestamp,
    feature_keys: tuple[tuple[str, str], ...],
    channel_values: dict[tuple[pd.Timestamp, str], float],
    interaction_values: dict[tuple[pd.Timestamp, str], float],
    control_values: dict[tuple[pd.Timestamp, str, str], float],
    event_values: dict[tuple[pd.Timestamp, str, str], float],
    hierarchy_rows: dict[str, dict[str, object]],
    config: HierarchicalTVPConfig,
    parent: HierarchicalPosterior | None,
    prior_strength: float,
    min_training_count: int,
    confidence_discount: float,
) -> _NodeFit:
    features, target, weights, training_start, training_end = _training_arrays(
        asset_returns,
        descendant_assets=descendant_assets,
        current_date=current_date,
        feature_keys=feature_keys,
        channel_values=channel_values,
        interaction_values=interaction_values,
        control_values=control_values,
        event_values=event_values,
        hierarchy_rows=hierarchy_rows,
        config=config,
    )
    posterior = fit_hierarchical_tvp_ridge(
        features,
        target,
        weights,
        min_training_count=min_training_count,
        prior_strength=prior_strength,
        condition_number_threshold=config.condition_number_threshold,
        parent=parent,
        confidence_discount=confidence_discount,
    )
    return _NodeFit(
        posterior=posterior,
        training_start=training_start,
        training_end=training_end,
        parameter_keys=(_INTERCEPT_KEY, *feature_keys),
    )


def _sorted_feature_keys(
    values: object,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            set(values),  # type: ignore[arg-type]
            key=lambda key: (_COMPONENT_ORDER[key[0]], key[1]),
        )
    )


def _aligned_parent(
    parent_fit: _NodeFit,
    child_feature_keys: tuple[tuple[str, str], ...],
) -> HierarchicalPosterior:
    child_parameter_keys = (_INTERCEPT_KEY, *child_feature_keys)
    parent_positions = {
        key: position for position, key in enumerate(parent_fit.parameter_keys)
    }
    if any(key not in parent_positions for key in child_parameter_keys):
        raise ValueError("child feature universe must be a subset of its parent")
    positions = [parent_positions[key] for key in child_parameter_keys]
    posterior = parent_fit.posterior
    covariance = posterior.covariance[np.ix_(positions, positions)]
    return HierarchicalPosterior(
        mean=posterior.mean[positions],
        covariance=covariance,
        parent_mean=posterior.parent_mean[positions],
        training_count=posterior.training_count,
        effective_training_count=posterior.effective_training_count,
        condition_number=posterior.condition_number,
        prior_precision=posterior.prior_precision,
        own_weight=posterior.own_weight,
        parent_weight=posterior.parent_weight,
        confidence=posterior.confidence,
        status=posterior.status,
    )


def _posterior_records(
    *,
    current_date: pd.Timestamp,
    node_level: str,
    node_id: str,
    parent_node_id: str | None,
    parameter_keys: tuple[tuple[str, str], ...],
    node_fit: _NodeFit,
    proxy_discount: float,
    config: HierarchicalTVPConfig,
) -> list[dict[str, object]]:
    posterior = node_fit.posterior
    return [
        {
            "date": current_date,
            "node_level": node_level,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "component_type": component_type,
            "component_id": component_id,
            "coefficient_mean": float(posterior.mean[position]),
            "parent_coefficient_mean": (
                np.nan if position == 0 else float(posterior.parent_mean[position])
            ),
            "prior_precision": (0.0 if position == 0 else posterior.prior_precision),
            "own_weight": posterior.own_weight,
            "parent_weight": posterior.parent_weight,
            "confidence": posterior.confidence,
            "proxy_discount": proxy_discount,
            "training_start": node_fit.training_start,
            "training_end": node_fit.training_end,
            "training_count": posterior.training_count,
            "effective_training_count": posterior.effective_training_count,
            "condition_number": posterior.condition_number,
            "status": posterior.status,
            "window": config.window,
            "rolling_window": config.rolling_window,
            "forgetting_factor": config.forgetting_factor,
            "estimation_method": _ESTIMATION_METHOD,
        }
        for position, (component_type, component_id) in enumerate(parameter_keys)
    ]


def _covariance_records(
    *,
    current_date: pd.Timestamp,
    node_level: str,
    node_id: str,
    parent_node_id: str | None,
    parameter_keys: tuple[tuple[str, str], ...],
    node_fit: _NodeFit,
    proxy_discount: float,
    config: HierarchicalTVPConfig,
) -> list[dict[str, object]]:
    posterior = node_fit.posterior
    return [
        {
            "date": current_date,
            "node_level": node_level,
            "node_id": node_id,
            "parent_node_id": parent_node_id,
            "component_i_type": component_i_type,
            "component_i_id": component_i_id,
            "component_j_type": component_j_type,
            "component_j_id": component_j_id,
            "coefficient_covariance": float(posterior.covariance[row, column]),
            "training_start": node_fit.training_start,
            "training_end": node_fit.training_end,
            "training_count": posterior.training_count,
            "effective_training_count": posterior.effective_training_count,
            "prior_precision": posterior.prior_precision,
            "own_weight": posterior.own_weight,
            "parent_weight": posterior.parent_weight,
            "confidence": posterior.confidence,
            "proxy_discount": proxy_discount,
            "condition_number": posterior.condition_number,
            "status": posterior.status,
            "window": config.window,
            "rolling_window": config.rolling_window,
            "forgetting_factor": config.forgetting_factor,
            "estimation_method": _ESTIMATION_METHOD,
        }
        for row, (component_i_type, component_i_id) in enumerate(parameter_keys)
        for column, (component_j_type, component_j_id) in enumerate(parameter_keys)
    ]


def _component_records(
    *,
    observed: float,
    benchmark_return: float,
    current_date: pd.Timestamp,
    asset_id: str,
    current_keys: tuple[tuple[str, str], ...],
    parameter_keys: tuple[tuple[str, str], ...],
    node_fit: _NodeFit,
    parent_node_id: str,
    proxy_discount: float,
    channel_values: dict[tuple[pd.Timestamp, str], float],
    interaction_values: dict[tuple[pd.Timestamp, str], float],
    control_values: dict[tuple[pd.Timestamp, str, str], float],
    event_values: dict[tuple[pd.Timestamp, str, str], float],
    config: HierarchicalTVPConfig,
) -> list[dict[str, object]]:
    posterior = node_fit.posterior
    parameter_positions = {key: position for position, key in enumerate(parameter_keys)}
    values: dict[tuple[str, str], float] = {_INTERCEPT_KEY: 1.0}
    for component_type, component_id in current_keys:
        if component_type == "benchmark":
            value = benchmark_return
        elif component_type == "channel":
            value = channel_values.get((current_date, component_id), np.nan)
        elif component_type == "interaction":
            value = interaction_values.get((current_date, component_id), np.nan)
        elif component_type == "control":
            value = control_values.get((current_date, asset_id, component_id), np.nan)
        else:
            value = event_values.get((current_date, asset_id, component_id), np.nan)
        values[(component_type, component_id)] = float(value)
    has_current_channel = any(
        component_type == "channel" for component_type, _ in current_keys
    )
    values_available = has_current_channel and all(
        np.isfinite(value) for value in values.values()
    )
    parameters_available = all(key in parameter_positions for key in values)
    posterior_available = np.isfinite(posterior.mean).all()
    status = (
        posterior.status if values_available and parameters_available else "unavailable"
    )
    contributions: dict[tuple[str, str], float] = {}
    if values_available and parameters_available and posterior_available:
        for key, value in values.items():
            position = parameter_positions[key]
            contributions[key] = float(value * posterior.mean[position])
        predicted = float(sum(contributions.values()))
    else:
        contributions = {key: np.nan for key in values}
        predicted = np.nan
    residual = (
        float(observed - predicted)
        if np.isfinite(observed) and np.isfinite(predicted)
        else np.nan
    )
    records: list[dict[str, object]] = []
    for component_type, component_id in (_INTERCEPT_KEY, *current_keys):
        position = parameter_positions.get((component_type, component_id))
        coefficient_mean = (
            np.nan if position is None else float(posterior.mean[position])
        )
        parent_coefficient_mean = (
            np.nan
            if position is None or position == 0
            else float(posterior.parent_mean[position])
        )
        records.append(
            {
                "date": current_date,
                "asset_id": asset_id,
                "component_type": component_type,
                "component_id": component_id,
                "component_value": values[(component_type, component_id)],
                "coefficient_mean": coefficient_mean,
                "contribution": contributions[(component_type, component_id)],
                "observed_return": observed,
                "predicted_return": predicted,
                "asset_residual": residual,
                "training_start": node_fit.training_start,
                "training_end": node_fit.training_end,
                "training_count": posterior.training_count,
                "effective_training_count": posterior.effective_training_count,
                "parent_node_id": parent_node_id,
                "parent_coefficient_mean": parent_coefficient_mean,
                "own_weight": posterior.own_weight,
                "parent_weight": posterior.parent_weight,
                "confidence": posterior.confidence,
                "proxy_discount": proxy_discount,
                "condition_number": posterior.condition_number,
                "status": status,
                "window": config.window,
                "rolling_window": config.rolling_window,
                "forgetting_factor": config.forgetting_factor,
                "estimation_method": _ESTIMATION_METHOD,
            }
        )
    records.append(
        {
            "date": current_date,
            "asset_id": asset_id,
            "component_type": "residual",
            "component_id": "asset_residual",
            "component_value": residual,
            "coefficient_mean": 1.0,
            "contribution": residual,
            "observed_return": observed,
            "predicted_return": predicted,
            "asset_residual": residual,
            "training_start": node_fit.training_start,
            "training_end": node_fit.training_end,
            "training_count": posterior.training_count,
            "effective_training_count": posterior.effective_training_count,
            "parent_node_id": parent_node_id,
            "parent_coefficient_mean": np.nan,
            "own_weight": posterior.own_weight,
            "parent_weight": posterior.parent_weight,
            "confidence": posterior.confidence,
            "proxy_discount": proxy_discount,
            "condition_number": posterior.condition_number,
            "status": status,
            "window": config.window,
            "rolling_window": config.rolling_window,
            "forgetting_factor": config.forgetting_factor,
            "estimation_method": _ESTIMATION_METHOD,
        }
    )
    return records


def _sort_outputs(
    components: pd.DataFrame,
    posteriors: pd.DataFrame,
    covariance: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    components["_component_order"] = components["component_type"].map(_COMPONENT_ORDER)
    components = (
        components.sort_values(
            ["date", "asset_id", "_component_order", "component_id"],
            kind="stable",
        )
        .drop(columns="_component_order")
        .reset_index(drop=True)
    )
    posteriors["_node_order"] = posteriors["node_level"].map(_NODE_LEVEL_ORDER)
    posteriors["_component_order"] = posteriors["component_type"].map(_COMPONENT_ORDER)
    posteriors = (
        posteriors.sort_values(
            [
                "date",
                "_node_order",
                "node_id",
                "_component_order",
                "component_id",
            ],
            kind="stable",
        )
        .drop(columns=["_node_order", "_component_order"])
        .reset_index(drop=True)
    )
    covariance["_node_order"] = covariance["node_level"].map(_NODE_LEVEL_ORDER)
    covariance["_component_i_order"] = covariance["component_i_type"].map(
        _COMPONENT_ORDER
    )
    covariance["_component_j_order"] = covariance["component_j_type"].map(
        _COMPONENT_ORDER
    )
    covariance = (
        covariance.sort_values(
            [
                "date",
                "_node_order",
                "node_id",
                "_component_i_order",
                "component_i_id",
                "_component_j_order",
                "component_j_id",
            ],
            kind="stable",
        )
        .drop(columns=["_node_order", "_component_i_order", "_component_j_order"])
        .reset_index(drop=True)
    )
    return components, posteriors, covariance


def estimate_channel_to_asset(
    asset_returns: pd.DataFrame,
    channel_innovations: pd.DataFrame,
    hierarchy: pd.DataFrame,
    *,
    interactions: pd.DataFrame | None = None,
    controls: pd.DataFrame | None = None,
    event_shocks: pd.DataFrame | None = None,
    config: HierarchicalTVPConfig | None = None,
) -> ChannelToAssetResult:
    """Estimate hierarchical date-specific channel sensitivities for assets."""

    if config is None:
        normalized_config = HierarchicalTVPConfig()
    elif isinstance(config, HierarchicalTVPConfig):
        normalized_config = config
    else:
        raise TypeError("config must be a HierarchicalTVPConfig")
    normalized_returns = _normalize_asset_returns(asset_returns)
    normalized_channels = _normalize_channels(channel_innovations)
    normalized_hierarchy = _normalize_hierarchy(hierarchy)
    normalized_interactions = _normalize_interactions(interactions)
    normalized_controls = _normalize_asset_features(
        controls,
        name="controls",
        id_column="control_id",
    )
    normalized_events = _normalize_asset_features(
        event_shocks,
        name="event_shocks",
        id_column="event_id",
    )
    hierarchy_assets = set(normalized_hierarchy["asset_id"])
    input_assets = set(normalized_returns["asset_id"])
    if not input_assets.issubset(hierarchy_assets):
        missing = ", ".join(sorted(input_assets - hierarchy_assets))
        raise ValueError(f"asset_returns assets are missing from hierarchy: {missing}")
    for name, values in (
        ("controls", normalized_controls),
        ("event_shocks", normalized_events),
    ):
        feature_assets = set(values["asset_id"])
        if not feature_assets.issubset(hierarchy_assets):
            missing = ", ".join(sorted(feature_assets - hierarchy_assets))
            raise ValueError(f"{name} assets are missing from hierarchy: {missing}")
    hierarchy_rows = {
        row.asset_id: {
            "asset_class_id": row.asset_class_id,
            "industry_id": row.industry_id,
            "is_proxy": row.is_proxy,
            "confidence_discount": float(row.confidence_discount),
            "effective_confidence": 1.0 - float(row.confidence_discount),
        }
        for row in normalized_hierarchy.itertuples(index=False)
    }
    channel_values = _channel_lookup(normalized_channels)
    channel_first_dates = normalized_channels.groupby("channel_id")["date"].min()
    validated_interactions = normalized_interactions.loc[
        normalized_interactions["validated"]
    ]
    interaction_first_dates = validated_interactions.groupby("interaction_id")[
        "date"
    ].min()
    control_first_dates = normalized_controls.groupby(["asset_id", "control_id"])[
        "date"
    ].min()
    event_first_dates = normalized_events.groupby(["asset_id", "event_id"])[
        "date"
    ].min()
    interaction_values = _lookup(
        validated_interactions.rename(columns={"interaction_id": "feature_id"}),
        ["date", "feature_id"],
    )
    control_values = _lookup(
        normalized_controls.rename(columns={"control_id": "feature_id"}),
        ["date", "asset_id", "feature_id"],
    )
    event_values = _lookup(
        normalized_events.rename(columns={"event_id": "feature_id"}),
        ["date", "asset_id", "feature_id"],
    )
    component_rows: list[dict[str, object]] = []
    posterior_rows: list[dict[str, object]] = []
    covariance_rows: list[dict[str, object]] = []
    for current_date, current_returns in normalized_returns.groupby("date", sort=True):
        current_assets = set(current_returns["asset_id"])
        current_channel_ids = sorted(
            channel_id
            for channel_id, first_date in channel_first_dates.items()
            if first_date <= current_date
        )
        eligible_channel_ids = [
            channel_id
            for channel_id in current_channel_ids
            if channel_first_dates[channel_id] < current_date
        ]
        current_interaction_ids = sorted(
            validated_interactions.loc[
                validated_interactions["date"].eq(current_date),
                "interaction_id",
            ].unique()
        )
        eligible_interaction_ids = [
            interaction_id
            for interaction_id in current_interaction_ids
            if interaction_first_dates[interaction_id] < current_date
        ]
        current_controls = normalized_controls.loc[
            normalized_controls["date"].eq(current_date)
            & normalized_controls["asset_id"].isin(current_assets)
        ]
        current_events = normalized_events.loc[
            normalized_events["date"].eq(current_date)
            & normalized_events["asset_id"].isin(current_assets)
        ]
        control_ids_by_asset = {
            asset_id: sorted(group["control_id"].unique())
            for asset_id, group in current_controls.groupby("asset_id", sort=False)
        }
        event_ids_by_asset = {
            asset_id: sorted(group["event_id"].unique())
            for asset_id, group in current_events.groupby("asset_id", sort=False)
        }
        common_feature_keys = (
            (_BENCHMARK_KEY,)
            + tuple(("channel", channel_id) for channel_id in eligible_channel_ids)
            + tuple(
                ("interaction", interaction_id)
                for interaction_id in eligible_interaction_ids
            )
        )
        asset_feature_keys: dict[str, tuple[tuple[str, str], ...]] = {}
        asset_current_keys: dict[str, tuple[tuple[str, str], ...]] = {}
        for asset_id in sorted(current_assets):
            current_control_ids = control_ids_by_asset.get(asset_id, [])
            current_event_ids = event_ids_by_asset.get(asset_id, [])
            eligible_control_ids = [
                control_id
                for control_id in current_control_ids
                if control_first_dates[(asset_id, control_id)] < current_date
            ]
            eligible_event_ids = [
                event_id
                for event_id in current_event_ids
                if event_first_dates[(asset_id, event_id)] < current_date
            ]
            asset_feature_keys[asset_id] = (
                common_feature_keys
                + tuple(("control", control_id) for control_id in eligible_control_ids)
                + tuple(("event", event_id) for event_id in eligible_event_ids)
            )
            asset_current_keys[asset_id] = (
                (_BENCHMARK_KEY,)
                + tuple(("channel", channel_id) for channel_id in current_channel_ids)
                + tuple(
                    ("interaction", interaction_id)
                    for interaction_id in current_interaction_ids
                )
                + tuple(("control", control_id) for control_id in current_control_ids)
                + tuple(("event", event_id) for event_id in current_event_ids)
            )
        current_hierarchy = normalized_hierarchy.loc[
            normalized_hierarchy["asset_id"].isin(current_assets)
        ]
        class_fits: dict[str, _NodeFit] = {}
        for asset_class_id in sorted(current_hierarchy["asset_class_id"].unique()):
            current_class_assets = set(
                current_hierarchy.loc[
                    current_hierarchy["asset_class_id"].eq(asset_class_id),
                    "asset_id",
                ]
            )
            class_feature_keys = _sorted_feature_keys(
                key
                for asset_id in current_class_assets
                for key in asset_feature_keys[asset_id]
            )
            descendants = set(
                normalized_hierarchy.loc[
                    normalized_hierarchy["asset_class_id"].eq(asset_class_id),
                    "asset_id",
                ]
            )
            node_fit = _fit_node(
                normalized_returns,
                descendant_assets=descendants,
                current_date=current_date,
                feature_keys=class_feature_keys,
                channel_values=channel_values,
                interaction_values=interaction_values,
                control_values=control_values,
                event_values=event_values,
                hierarchy_rows=hierarchy_rows,
                config=normalized_config,
                parent=None,
                prior_strength=normalized_config.root_ridge,
                min_training_count=normalized_config.min_parent_training_count,
                confidence_discount=0.0,
            )
            class_fits[asset_class_id] = node_fit
            posterior_rows.extend(
                _posterior_records(
                    current_date=current_date,
                    node_level="asset_class",
                    node_id=asset_class_id,
                    parent_node_id=None,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=0.0,
                    config=normalized_config,
                )
            )
            covariance_rows.extend(
                _covariance_records(
                    current_date=current_date,
                    node_level="asset_class",
                    node_id=asset_class_id,
                    parent_node_id=None,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=0.0,
                    config=normalized_config,
                )
            )
        industry_fits: dict[str, _NodeFit] = {}
        current_industries = current_hierarchy.loc[
            :, ["industry_id", "asset_class_id"]
        ].drop_duplicates()
        for industry_row in current_industries.sort_values("industry_id").itertuples(
            index=False
        ):
            current_industry_assets = set(
                current_hierarchy.loc[
                    current_hierarchy["industry_id"].eq(industry_row.industry_id),
                    "asset_id",
                ]
            )
            industry_feature_keys = _sorted_feature_keys(
                key
                for asset_id in current_industry_assets
                for key in asset_feature_keys[asset_id]
            )
            descendants = set(
                normalized_hierarchy.loc[
                    normalized_hierarchy["industry_id"].eq(industry_row.industry_id),
                    "asset_id",
                ]
            )
            node_fit = _fit_node(
                normalized_returns,
                descendant_assets=descendants,
                current_date=current_date,
                feature_keys=industry_feature_keys,
                channel_values=channel_values,
                interaction_values=interaction_values,
                control_values=control_values,
                event_values=event_values,
                hierarchy_rows=hierarchy_rows,
                config=normalized_config,
                parent=_aligned_parent(
                    class_fits[industry_row.asset_class_id],
                    industry_feature_keys,
                ),
                prior_strength=normalized_config.industry_prior_strength,
                min_training_count=normalized_config.min_parent_training_count,
                confidence_discount=0.0,
            )
            industry_fits[industry_row.industry_id] = node_fit
            posterior_rows.extend(
                _posterior_records(
                    current_date=current_date,
                    node_level="industry",
                    node_id=industry_row.industry_id,
                    parent_node_id=industry_row.asset_class_id,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=0.0,
                    config=normalized_config,
                )
            )
            covariance_rows.extend(
                _covariance_records(
                    current_date=current_date,
                    node_level="industry",
                    node_id=industry_row.industry_id,
                    parent_node_id=industry_row.asset_class_id,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=0.0,
                    config=normalized_config,
                )
            )
        for (
            current_date_value,
            asset_id,
            observed_value,
            benchmark_value,
        ) in current_returns.sort_values("asset_id").itertuples(
            index=False,
            name=None,
        ):
            if current_date_value != current_date:
                raise ValueError("current asset return date is inconsistent")
            hierarchy_row = hierarchy_rows[asset_id]
            industry_id = str(hierarchy_row["industry_id"])
            proxy_discount = float(hierarchy_row["confidence_discount"])
            feature_keys = asset_feature_keys[asset_id]
            node_fit = _fit_node(
                normalized_returns,
                descendant_assets={asset_id},
                current_date=current_date,
                feature_keys=feature_keys,
                channel_values=channel_values,
                interaction_values=interaction_values,
                control_values=control_values,
                event_values=event_values,
                hierarchy_rows=hierarchy_rows,
                config=normalized_config,
                parent=_aligned_parent(industry_fits[industry_id], feature_keys),
                prior_strength=normalized_config.asset_prior_strength,
                min_training_count=normalized_config.min_asset_training_count,
                confidence_discount=proxy_discount,
            )
            posterior_rows.extend(
                _posterior_records(
                    current_date=current_date,
                    node_level="asset",
                    node_id=asset_id,
                    parent_node_id=industry_id,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=proxy_discount,
                    config=normalized_config,
                )
            )
            covariance_rows.extend(
                _covariance_records(
                    current_date=current_date,
                    node_level="asset",
                    node_id=asset_id,
                    parent_node_id=industry_id,
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    proxy_discount=proxy_discount,
                    config=normalized_config,
                )
            )
            component_rows.extend(
                _component_records(
                    observed=float(observed_value),
                    benchmark_return=float(benchmark_value),
                    current_date=current_date,
                    asset_id=asset_id,
                    current_keys=asset_current_keys[asset_id],
                    parameter_keys=node_fit.parameter_keys,
                    node_fit=node_fit,
                    parent_node_id=industry_id,
                    proxy_discount=proxy_discount,
                    channel_values=channel_values,
                    interaction_values=interaction_values,
                    control_values=control_values,
                    event_values=event_values,
                    config=normalized_config,
                )
            )
    components_frame = pd.DataFrame(
        component_rows,
        columns=CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    )
    posterior_frame = pd.DataFrame(
        posterior_rows,
        columns=CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    )
    covariance_frame = pd.DataFrame(
        covariance_rows,
        columns=CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    )
    components_frame, posterior_frame, covariance_frame = _sort_outputs(
        components_frame,
        posterior_frame,
        covariance_frame,
    )
    return ChannelToAssetResult(
        components=components_frame,
        posteriors=posterior_frame,
        covariance=covariance_frame,
    )


__all__ = [
    "CHANNEL_TO_ASSET_COMPONENT_COLUMNS",
    "CHANNEL_TO_ASSET_COVARIANCE_COLUMNS",
    "CHANNEL_TO_ASSET_POSTERIOR_COLUMNS",
    "ChannelToAssetResult",
    "HierarchicalTVPConfig",
    "estimate_channel_to_asset",
]
