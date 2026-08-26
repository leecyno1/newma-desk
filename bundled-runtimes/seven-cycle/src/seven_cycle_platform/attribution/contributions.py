"""Conserved two-stage cycle-to-asset contribution composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.identifiability import (
    IDENTIFIABILITY_COLUMNS,
    IdentifiabilityConfig,
    identify_cycle_groups,
)
from seven_cycle_platform.attribution.stage1 import CYCLE_IDS


ATTRIBUTION_PATH_COLUMNS = (
    "date",
    "asset_id",
    "channel_id",
    "cycle_id",
    "cycle_innovation",
    "cycle_to_channel_coefficient",
    "channel_to_asset_coefficient",
    "raw_path_contribution",
    "allocation_group_id",
    "allocation_status",
    "stage1_status",
    "stage2_status",
)

ATTRIBUTION_COMPONENT_COLUMNS = (
    "date",
    "asset_id",
    "component_type",
    "component_id",
    "contribution",
    "contribution_share",
    "observed_return",
    "reconstructed_return",
    "is_explained",
    "is_residual",
    "source",
    "status",
    "allocation_method",
)

_RESULT_FIELDS = frozenset({"paths", "components", "identifiability"})
_VALID_STAGE1_STATUSES = frozenset(
    {
        "estimated",
        "insufficient_history",
        "not_identifiable",
        "unavailable",
    }
)
_VALID_STAGE2_COMPONENT_TYPES = frozenset(
    {
        "intercept",
        "benchmark",
        "channel",
        "interaction",
        "control",
        "event",
        "residual",
    }
)
_USABLE_STAGE2_STATUSES = frozenset({"estimated", "parent_informed", "parent_only"})
_FAILED_STAGE2_STATUSES = frozenset(
    {"insufficient_history", "not_identifiable", "unavailable"}
)
_VALID_STAGE2_STATUSES = _USABLE_STAGE2_STATUSES | _FAILED_STAGE2_STATUSES
_VALID_ALLOCATION_STATUSES = frozenset(
    {
        "independent",
        "merged_cycles",
        "insufficient_history",
        "not_identifiable",
        "unavailable",
    }
)
_VALID_COMPONENT_STATUSES = (
    _VALID_STAGE1_STATUSES
    | _VALID_STAGE2_STATUSES
    | _VALID_ALLOCATION_STATUSES
    | frozenset({"validated"})
)
_VALID_IDENTIFIABILITY_METHODS = frozenset(
    {"correlation_union_find", "unallocated_total"}
)
_VALID_COMPONENT_SOURCES = frozenset(
    {
        "stage2",
        "stage1_cycle_x_stage2_beta",
        "stage1_intercept_x_stage2_beta",
        "stage1_residual_x_stage2_beta",
        "stage2_channel",
        "validated_direct_evidence",
        "stage2_residual",
        "stage2_unavailable_balance",
        "unavailable_placeholder",
    }
)
_VALID_ALLOCATION_METHODS = frozenset(
    {
        "direct_passthrough",
        "correlation_union_find",
        "unallocated_total",
        "path_expansion",
        "unresolved_channel",
        "validated_direct_evidence",
        "residual",
        "unavailable_placeholder",
    }
)
_COMPONENT_ORDER = {
    "asset_intercept": 0,
    "benchmark": 1,
    "cycle": 2,
    "cycle_group": 3,
    "channel_baseline_path": 4,
    "channel_residual_path": 5,
    "unresolved_channel": 6,
    "interaction": 7,
    "control": 8,
    "event": 9,
    "unobserved_channel_residual": 10,
    "asset_residual": 11,
}


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


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return numeric


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


@dataclass(frozen=True)
class ContributionConfig:
    """Configuration for conservation and validated direct residual evidence."""

    identifiability: IdentifiabilityConfig = field(
        default_factory=IdentifiabilityConfig
    )
    conservation_tolerance: float = 1e-10
    direct_min_oos_gain: float = 1e-6
    direct_min_stability_score: float = 0.80
    direct_min_validation_count: int = 12

    def __post_init__(self) -> None:
        if not isinstance(self.identifiability, IdentifiabilityConfig):
            raise TypeError("identifiability must be an IdentifiabilityConfig")
        tolerance = _finite_real(
            self.conservation_tolerance,
            "conservation_tolerance",
        )
        if tolerance <= 0.0:
            raise ValueError("conservation_tolerance must be positive")
        minimum_gain = _finite_real(self.direct_min_oos_gain, "direct_min_oos_gain")
        if minimum_gain < 0.0:
            raise ValueError("direct_min_oos_gain must be nonnegative")
        minimum_stability = _finite_real(
            self.direct_min_stability_score,
            "direct_min_stability_score",
        )
        if not 0.0 <= minimum_stability <= 1.0:
            raise ValueError("direct_min_stability_score must be in [0, 1]")
        minimum_validations = _nonnegative_integer(
            self.direct_min_validation_count,
            "direct_min_validation_count",
        )
        object.__setattr__(self, "conservation_tolerance", tolerance)
        object.__setattr__(self, "direct_min_oos_gain", minimum_gain)
        object.__setattr__(self, "direct_min_stability_score", minimum_stability)
        object.__setattr__(
            self,
            "direct_min_validation_count",
            minimum_validations,
        )


def _is_close(left: float, right: float, tolerance: float) -> bool:
    return bool(np.isclose(left, right, atol=tolerance, rtol=0.0))


def _validate_result_groups(
    paths: pd.DataFrame,
    components: pd.DataFrame,
    identifiability: pd.DataFrame,
    tolerance: float,
) -> None:
    if paths.duplicated(["date", "asset_id", "channel_id", "cycle_id"]).any():
        raise ValueError("attribution path rows must be unique")
    if components.duplicated(
        ["date", "asset_id", "component_type", "component_id"]
    ).any():
        raise ValueError("attribution component rows must be unique")
    if identifiability.duplicated(["date", "asset_id", "cycle_id"]).any():
        raise ValueError("identifiability rows must be unique")
    if not set(components["component_type"]).issubset(_COMPONENT_ORDER):
        raise ValueError("components contain an unknown component_type")
    if not set(paths["allocation_status"]).issubset(_VALID_ALLOCATION_STATUSES):
        raise ValueError("paths contain an unknown allocation_status")
    if not set(paths["stage1_status"]).issubset(_VALID_STAGE1_STATUSES):
        raise ValueError("paths contain an unknown stage1_status")
    if not set(paths["stage2_status"]).issubset(_VALID_STAGE2_STATUSES):
        raise ValueError("paths contain an unknown stage2_status")
    if not set(components["status"]).issubset(_VALID_COMPONENT_STATUSES):
        raise ValueError("components contain an unknown status")
    if not set(components["source"]).issubset(_VALID_COMPONENT_SOURCES):
        raise ValueError("components contain an unknown source")
    if not set(components["allocation_method"]).issubset(_VALID_ALLOCATION_METHODS):
        raise ValueError("components contain an unknown allocation_method")
    for column in ("is_explained", "is_residual"):
        if any(
            not isinstance(value, (bool, np.bool_))
            for value in components[column].tolist()
        ):
            raise TypeError(f"{column} values must be boolean")
    if not set(identifiability["status"]).issubset(_VALID_ALLOCATION_STATUSES):
        raise ValueError("identifiability contains an unknown status")
    if not set(identifiability["method"]).issubset(_VALID_IDENTIFIABILITY_METHODS):
        raise ValueError("identifiability contains an unknown method")
    identification_lookup: dict[tuple[object, str, str], tuple[str, str]] = {}
    group_lookup: dict[tuple[object, str], dict[str, tuple[int, str, str]]] = {}
    for key, group in identifiability.groupby(["date", "asset_id"], sort=False):
        if len(group) != len(CYCLE_IDS) or set(group["cycle_id"]) != set(CYCLE_IDS):
            raise ValueError(
                "each identifiability group must contain C1 through C7 exactly once"
            )
        asset_groups: dict[str, tuple[int, str, str]] = {}
        for group_id, allocation_group in group.groupby("group_id", sort=False):
            if not isinstance(group_id, str) or not group_id:
                raise TypeError("identifiability group_id values must be strings")
            group_sizes = allocation_group["group_size"].drop_duplicates().tolist()
            statuses = allocation_group["status"].drop_duplicates().tolist()
            methods = allocation_group["method"].drop_duplicates().tolist()
            if len(group_sizes) != 1 or len(statuses) != 1 or len(methods) != 1:
                raise ValueError("identifiability group metadata must be consistent")
            group_size = group_sizes[0]
            if isinstance(group_size, (bool, np.bool_)) or not isinstance(
                group_size,
                (Integral, np.integer),
            ):
                raise TypeError("identifiability group_size values must be integers")
            numeric_size = int(group_size)
            if numeric_size != len(allocation_group):
                raise ValueError("identifiability group_size is inconsistent")
            cycle_positions = {
                cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)
            }
            ordered_cycles = sorted(
                allocation_group["cycle_id"].tolist(),
                key=cycle_positions.__getitem__,
            )
            if group_id != "+".join(ordered_cycles):
                raise ValueError("identifiability group_id is inconsistent")
            status = str(statuses[0])
            method = str(methods[0])
            if status == "independent" and numeric_size != 1:
                raise ValueError(
                    "independent identifiability groups must be singletons"
                )
            if status == "merged_cycles" and numeric_size < 2:
                raise ValueError("merged identifiability groups must contain cycles")
            if status in _FAILED_STAGE2_STATUSES and numeric_size != len(CYCLE_IDS):
                raise ValueError("failed identifiability must retain all C1 through C7")
            expected_method = (
                "correlation_union_find"
                if status in {"independent", "merged_cycles"}
                else "unallocated_total"
            )
            if method != expected_method:
                raise ValueError("identifiability method is inconsistent with status")
            asset_groups[group_id] = (numeric_size, status, method)
            for cycle_id in ordered_cycles:
                identification_lookup[(key[0], key[1], cycle_id)] = (
                    group_id,
                    status,
                )
        group_lookup[key] = asset_groups
    component_keys = set(
        components.loc[:, ["date", "asset_id"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    identifiability_keys = set(group_lookup)
    if component_keys != identifiability_keys:
        raise ValueError("component and identifiability date × asset keys must align")
    for row in paths.itertuples(index=False):
        identification = identification_lookup.get(
            (row.date, row.asset_id, row.cycle_id)
        )
        if identification is None:
            raise ValueError("path rows must align with identifiability")
        if (
            row.allocation_group_id != identification[0]
            or row.allocation_status != identification[1]
        ):
            raise ValueError("path allocation must match identifiability")
    cycle_components = components.loc[
        components["component_type"].isin(["cycle", "cycle_group"])
    ]
    if cycle_components.duplicated(["date", "asset_id", "component_id"]).any():
        raise ValueError("cycle components cannot duplicate identifiability groups")
    for row in cycle_components.itertuples(index=False):
        allocation = group_lookup[(row.date, row.asset_id)].get(row.component_id)
        if allocation is None:
            raise ValueError("cycle component must match identifiability group")
        group_size, allocation_status, allocation_method = allocation
        if (
            row.status != allocation_status
            or row.allocation_method != allocation_method
        ):
            raise ValueError("cycle component must match identifiability metadata")
        if row.component_type == "cycle" and not (
            group_size == 1 and allocation_status == "independent"
        ):
            raise ValueError("cycle component must match a singleton group")
        if row.component_type == "cycle_group" and (
            group_size == 1 and allocation_status == "independent"
        ):
            raise ValueError("cycle_group component must match a grouped allocation")
    for _, group in components.groupby(["date", "asset_id"], sort=False):
        observed_values = group["observed_return"].to_numpy(dtype="float64")
        reconstructed_values = group["reconstructed_return"].to_numpy(dtype="float64")
        if (
            not np.isfinite(observed_values).all()
            or not np.isfinite(reconstructed_values).all()
        ):
            raise ValueError("composed asset groups require finite observed returns")
        observed = float(observed_values[0])
        reconstructed = float(reconstructed_values[0])
        if not np.allclose(
            observed_values,
            observed,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("observed_return must be constant within an asset group")
        if not np.allclose(
            reconstructed_values,
            reconstructed,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError(
                "reconstructed_return must be constant within an asset group"
            )
        contributions = group["contribution"].to_numpy(dtype="float64")
        if not np.isfinite(contributions).all():
            raise ValueError("composed contributions must be finite")
        contribution_sum = float(group["contribution"].sum())
        if not _is_close(contribution_sum, observed, tolerance):
            raise ValueError("component contributions do not conserve observed_return")
        if not _is_close(reconstructed, observed, tolerance):
            raise ValueError("reconstructed_return does not equal observed_return")
        if abs(observed) <= tolerance:
            if group["contribution_share"].notna().any():
                raise ValueError("zero-like observed returns require missing shares")
        else:
            expected = group["contribution"] / observed
            if not np.allclose(
                group["contribution_share"],
                expected,
                atol=tolerance,
                rtol=0.0,
            ):
                raise ValueError("contribution_share must equal contribution/return")
    finite_paths = paths.loc[paths["raw_path_contribution"].notna()]
    if not finite_paths.empty:
        expected = (
            finite_paths["cycle_innovation"]
            * finite_paths["cycle_to_channel_coefficient"]
            * finite_paths["channel_to_asset_coefficient"]
        )
        if not np.allclose(
            finite_paths["raw_path_contribution"],
            expected,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("raw paths do not equal the exact coefficient product")


@dataclass(frozen=True)
class AttributionContributionResult:
    """Detached raw paths, conserved components, and identifiability evidence."""

    paths: pd.DataFrame
    components: pd.DataFrame
    identifiability: pd.DataFrame
    conservation_tolerance: float = 1e-10

    def __post_init__(self) -> None:
        paths = object.__getattribute__(self, "paths")
        components = object.__getattribute__(self, "components")
        identifiability = object.__getattribute__(self, "identifiability")
        tolerance = _finite_real(
            object.__getattribute__(self, "conservation_tolerance"),
            "conservation_tolerance",
        )
        if tolerance <= 0.0:
            raise ValueError("conservation_tolerance must be positive")
        for frame, name in (
            (paths, "paths"),
            (components, "components"),
            (identifiability, "identifiability"),
        ):
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"{name} must be a pandas DataFrame")
        if tuple(paths.columns) != ATTRIBUTION_PATH_COLUMNS:
            raise ValueError("paths columns do not match the contribution contract")
        if tuple(components.columns) != ATTRIBUTION_COMPONENT_COLUMNS:
            raise ValueError(
                "components columns do not match the contribution contract"
            )
        if tuple(identifiability.columns) != IDENTIFIABILITY_COLUMNS:
            raise ValueError(
                "identifiability columns do not match the contribution contract"
            )
        _validate_result_groups(paths, components, identifiability, tolerance)
        object.__setattr__(self, "paths", _copy_frame(paths))
        object.__setattr__(self, "components", _copy_frame(components))
        object.__setattr__(self, "identifiability", _copy_frame(identifiability))
        object.__setattr__(self, "conservation_tolerance", tolerance)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.components


def _source_frame(values: object, attribute: str, name: str) -> pd.DataFrame:
    if isinstance(values, pd.DataFrame):
        return values.copy(deep=True)
    frame = getattr(values, attribute, None)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame or expose .{attribute}")
    return frame.copy(deep=True)


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


def _validate_identifiers(values: pd.Series, name: str) -> None:
    if any(not isinstance(value, str) or not value for value in values.tolist()):
        raise TypeError(f"{name} values must be non-empty strings")


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


def _constant_numeric(
    group: pd.DataFrame,
    column: str,
    message: str,
    tolerance: float,
) -> float:
    values = group[column]
    if values.isna().all():
        return np.nan
    if values.isna().any():
        raise ValueError(message)
    numeric = values.to_numpy(dtype="float64")
    if not np.allclose(numeric, numeric[0], atol=tolerance, rtol=0.0):
        raise ValueError(message)
    return float(numeric[0])


def _normalize_stage1(values: object, tolerance: float) -> pd.DataFrame:
    frame = _source_frame(values, "paths", "stage1_paths")
    required = (
        "date",
        "channel_id",
        "cycle_id",
        "cycle_innovation",
        "coefficient_mean",
        "contribution",
        "intercept",
        "observed_channel_innovation",
        "channel_residual",
        "status",
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"stage1_paths is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError("stage1_paths must contain at least one row")
    frame = frame.loc[:, list(required)].copy(deep=True)
    frame["date"] = _normalize_dates(frame["date"], "stage1 path")
    for column in ("channel_id", "cycle_id", "status"):
        _validate_identifiers(frame[column], column)
    if not set(frame["cycle_id"]).issubset(CYCLE_IDS):
        raise ValueError("stage1 cycle_id values must be C1 through C7")
    if not set(frame["status"]).issubset(_VALID_STAGE1_STATUSES):
        raise ValueError("stage1 paths contain an unknown status")
    if frame.duplicated(["date", "channel_id", "cycle_id"]).any():
        raise ValueError("stage1 path rows must be unique")
    for column in (
        "cycle_innovation",
        "coefficient_mean",
        "contribution",
        "intercept",
        "observed_channel_innovation",
        "channel_residual",
    ):
        frame[column] = _normalize_numeric(
            frame[column],
            column.replace("_", " "),
            allow_missing=True,
        )
    for _, group in frame.groupby(["date", "cycle_id"], sort=False):
        innovations = group["cycle_innovation"]
        if innovations.isna().all():
            continue
        if innovations.isna().any() or not np.allclose(
            innovations,
            innovations.iloc[0],
            atol=1e-12,
            rtol=0.0,
        ):
            raise ValueError("cycle innovation must agree across channels")
    for _, group in frame.groupby(["date", "channel_id"], sort=False):
        if len(group) != len(CYCLE_IDS) or set(group["cycle_id"]) != set(CYCLE_IDS):
            raise ValueError(
                "each present stage1 channel group must contain C1 through C7"
            )
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("stage1 status must be constant within a channel group")
        intercept = _constant_numeric(
            group,
            "intercept",
            "stage1 intercept must be constant within a channel group",
            tolerance,
        )
        observed = _constant_numeric(
            group,
            "observed_channel_innovation",
            "stage1 observed innovation must be constant within a channel group",
            tolerance,
        )
        residual = _constant_numeric(
            group,
            "channel_residual",
            "stage1 residual must be constant within a channel group",
            tolerance,
        )
        if group["status"].iloc[0] == "estimated":
            required_values = group[
                ["cycle_innovation", "coefficient_mean", "contribution"]
            ]
            if required_values.isna().any().any() or not all(
                np.isfinite(value) for value in (intercept, observed, residual)
            ):
                raise ValueError("estimated stage1 paths require finite values")
            expected = group["cycle_innovation"] * group["coefficient_mean"]
            if not np.allclose(
                group["contribution"],
                expected,
                atol=tolerance,
                rtol=0.0,
            ):
                raise ValueError("stage1 contribution does not conserve path products")
            reconstructed = intercept + float(group["contribution"].sum()) + residual
            if not _is_close(reconstructed, observed, tolerance):
                raise ValueError("stage1 channel contributions do not conserve")
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    frame["_cycle_order"] = frame["cycle_id"].map(cycle_order)
    return (
        frame.sort_values(
            ["date", "channel_id", "_cycle_order"],
            kind="stable",
        )
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )


def _normalize_stage2(values: object, tolerance: float) -> pd.DataFrame:
    frame = _source_frame(values, "components", "stage2_components")
    required = (
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
        "status",
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"stage2_components is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError("stage2_components must contain at least one row")
    frame = frame.loc[:, list(required)].copy(deep=True)
    frame["date"] = _normalize_dates(frame["date"], "stage2 component")
    for column in ("asset_id", "component_type", "component_id", "status"):
        _validate_identifiers(frame[column], column)
    if not set(frame["component_type"]).issubset(_VALID_STAGE2_COMPONENT_TYPES):
        raise ValueError("stage2 components contain an unknown component type")
    if not set(frame["status"]).issubset(_VALID_STAGE2_STATUSES):
        raise ValueError("stage2 components contain an unknown status")
    if frame.duplicated(["date", "asset_id", "component_type", "component_id"]).any():
        raise ValueError("stage2 component rows must be unique")
    for column in (
        "component_value",
        "coefficient_mean",
        "contribution",
        "observed_return",
        "predicted_return",
        "asset_residual",
    ):
        frame[column] = _normalize_numeric(
            frame[column],
            column.replace("_", " "),
            allow_missing=True,
        )
    for _, group in frame.groupby(["date", "asset_id"], sort=False):
        if len(group.loc[group["component_type"].eq("intercept")]) != 1:
            raise ValueError("each stage2 asset group must contain one intercept")
        if len(group.loc[group["component_type"].eq("residual")]) != 1:
            raise ValueError("each stage2 asset group must contain one residual")
        if group["status"].nunique(dropna=False) != 1:
            raise ValueError("stage2 status must be constant within an asset group")
        observed = _constant_numeric(
            group,
            "observed_return",
            "stage2 observed_return must be constant within an asset group",
            tolerance,
        )
        predicted = _constant_numeric(
            group,
            "predicted_return",
            "stage2 predicted_return must be constant within an asset group",
            tolerance,
        )
        residual = _constant_numeric(
            group,
            "asset_residual",
            "stage2 asset_residual must be constant within an asset group",
            tolerance,
        )
        contributions = group["contribution"]
        status = str(group["status"].iloc[0])
        if status in _FAILED_STAGE2_STATUSES:
            if contributions.notna().any():
                raise ValueError("failed stage2 status requires all-NaN contributions")
            continue
        if contributions.isna().any():
            raise ValueError("usable stage2 status requires finite contributions")
        if not all(np.isfinite(value) for value in (observed, predicted, residual)):
            raise ValueError(
                "finite stage2 contributions require finite grouped returns"
            )
        non_residual = group.loc[group["component_type"].ne("residual")]
        residual_contribution = float(
            group.loc[group["component_type"].eq("residual"), "contribution"].iloc[0]
        )
        if not _is_close(
            float(non_residual["contribution"].sum()), predicted, tolerance
        ):
            raise ValueError("stage2 contributions do not conserve predicted_return")
        if not _is_close(residual_contribution, residual, tolerance):
            raise ValueError("stage2 residual contribution does not conserve")
        if not _is_close(predicted + residual, observed, tolerance):
            raise ValueError("stage2 components do not conserve observed_return")
        finite_products = group.loc[
            group["component_type"].ne("residual")
            & group["component_value"].notna()
            & group["coefficient_mean"].notna()
        ]
        expected = (
            finite_products["component_value"] * finite_products["coefficient_mean"]
        )
        if not np.allclose(
            finite_products["contribution"],
            expected,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("stage2 component products do not conserve")
    return frame.sort_values(
        ["date", "asset_id", "component_type", "component_id"],
        kind="stable",
    ).reset_index(drop=True)


def _normalize_direct_evidence(values: object | None) -> pd.DataFrame:
    columns = (
        "date",
        "asset_id",
        "contribution",
        "oos_gain",
        "stability_score",
        "validation_count",
        "validated",
        "validation_end_date",
    )
    if values is None:
        return pd.DataFrame(columns=columns)
    if not isinstance(values, pd.DataFrame):
        raise TypeError("direct_evidence must be a pandas DataFrame")
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"direct_evidence is missing columns: {', '.join(missing)}")
    frame = values.loc[:, list(columns)].copy(deep=True)
    if frame.empty:
        return frame
    frame["date"] = _normalize_dates(frame["date"], "direct evidence")
    frame["validation_end_date"] = _normalize_dates(
        frame["validation_end_date"],
        "direct evidence validation end",
    )
    _validate_identifiers(frame["asset_id"], "asset_id")
    if frame.duplicated(["date", "asset_id"]).any():
        raise ValueError("direct evidence rows must be unique")
    for column in ("contribution", "oos_gain", "stability_score"):
        frame[column] = _normalize_numeric(
            frame[column],
            column.replace("_", " "),
            allow_missing=False,
        )
    if bool(
        ((frame["stability_score"] < 0.0) | (frame["stability_score"] > 1.0)).any()
    ):
        raise ValueError("stability_score must be in [0, 1]")
    normalized_counts: list[int] = []
    for value in frame["validation_count"].tolist():
        normalized_counts.append(_nonnegative_integer(value, "validation_count"))
    frame["validation_count"] = normalized_counts
    if any(not isinstance(value, (bool, np.bool_)) for value in frame["validated"]):
        raise TypeError("validated values must be boolean")
    frame["validated"] = frame["validated"].astype(bool)
    return frame.sort_values(["date", "asset_id"], kind="stable").reset_index(drop=True)


def _component_record(
    *,
    current_date: pd.Timestamp,
    asset_id: str,
    component_type: str,
    component_id: str,
    contribution: float,
    is_explained: bool,
    is_residual: bool,
    source: str,
    status: str,
    allocation_method: str,
) -> dict[str, object]:
    return {
        "date": current_date,
        "asset_id": asset_id,
        "component_type": component_type,
        "component_id": component_id,
        "contribution": float(contribution),
        "contribution_share": np.nan,
        "observed_return": np.nan,
        "reconstructed_return": np.nan,
        "is_explained": is_explained,
        "is_residual": is_residual,
        "source": source,
        "status": status,
        "allocation_method": allocation_method,
    }


def _accepted_direct_evidence(
    evidence: pd.Series | None,
    current_date: pd.Timestamp,
    config: ContributionConfig,
) -> bool:
    if evidence is None:
        return False
    return bool(
        evidence["validated"]
        and evidence["oos_gain"] > config.direct_min_oos_gain
        and evidence["stability_score"] >= config.direct_min_stability_score
        and evidence["validation_count"] >= config.direct_min_validation_count
        and evidence["validation_end_date"] < current_date
    )


def _current_innovation_lookup(stage1: pd.DataFrame) -> dict[tuple[object, str], float]:
    unique = stage1.drop_duplicates(["date", "cycle_id"])
    return {
        (row.date, row.cycle_id): float(row.cycle_innovation)
        for row in unique.itertuples(index=False)
    }


def _identifiability_lookup(
    identifiability: pd.DataFrame,
) -> dict[tuple[object, str, str], pd.Series]:
    return {
        (row.date, row.asset_id, row.cycle_id): pd.Series(row._asdict())
        for row in identifiability.itertuples(index=False)
    }


def _path_record(
    *,
    current_date: pd.Timestamp,
    asset_id: str,
    channel_id: str,
    cycle_id: str,
    cycle_innovation: float,
    cycle_coefficient: float,
    asset_coefficient: float,
    raw_contribution: float,
    allocation: pd.Series,
    stage1_status: str,
    stage2_status: str,
) -> dict[str, object]:
    return {
        "date": current_date,
        "asset_id": asset_id,
        "channel_id": channel_id,
        "cycle_id": cycle_id,
        "cycle_innovation": cycle_innovation,
        "cycle_to_channel_coefficient": cycle_coefficient,
        "channel_to_asset_coefficient": asset_coefficient,
        "raw_path_contribution": raw_contribution,
        "allocation_group_id": allocation["group_id"],
        "allocation_status": allocation["status"],
        "stage1_status": stage1_status,
        "stage2_status": stage2_status,
    }


def _finalize_component_group(
    records: list[dict[str, object]],
    observed_return: float,
    tolerance: float,
) -> None:
    reconstructed = float(sum(float(record["contribution"]) for record in records))
    if not _is_close(reconstructed, observed_return, tolerance):
        raise ValueError("composed contributions do not conserve observed_return")
    reconstructed = observed_return
    for record in records:
        contribution = float(record["contribution"])
        record["contribution_share"] = (
            np.nan
            if abs(observed_return) <= tolerance
            else contribution / observed_return
        )
        record["observed_return"] = observed_return
        record["reconstructed_return"] = reconstructed


def compose_attribution_paths(
    stage1_paths: object,
    stage2_components: object,
    *,
    direct_evidence: pd.DataFrame | None = None,
    config: ContributionConfig | None = None,
) -> AttributionContributionResult:
    """Expand channel contributions into conserved cycle-to-asset paths."""

    normalized_config = config or ContributionConfig()
    if not isinstance(normalized_config, ContributionConfig):
        raise TypeError("config must be a ContributionConfig")
    stage1 = _normalize_stage1(
        stage1_paths,
        normalized_config.conservation_tolerance,
    )
    stage2 = _normalize_stage2(
        stage2_components,
        normalized_config.conservation_tolerance,
    )
    evidence = _normalize_direct_evidence(direct_evidence)
    attribution_index = stage2.loc[
        stage2["observed_return"].notna(), ["date", "asset_id"]
    ]
    attribution_index = attribution_index.drop_duplicates()
    if attribution_index.empty:
        raise ValueError("stage2_components must contain a finite observed return")
    identifiability = identify_cycle_groups(
        stage1,
        attribution_index,
        config=normalized_config.identifiability,
    )
    identification = _identifiability_lookup(identifiability)
    innovation_lookup = _current_innovation_lookup(stage1)
    stage1_groups = {
        (date, channel_id): group.reset_index(drop=True)
        for (date, channel_id), group in stage1.groupby(
            ["date", "channel_id"],
            sort=False,
        )
    }
    evidence_lookup = {
        (row.date, row.asset_id): pd.Series(row._asdict())
        for row in evidence.itertuples(index=False)
    }
    path_records: list[dict[str, object]] = []
    component_records: list[dict[str, object]] = []
    for (current_date, asset_id), asset_group in stage2.groupby(
        ["date", "asset_id"],
        sort=False,
    ):
        observed_return = float(asset_group["observed_return"].iloc[0])
        if not np.isfinite(observed_return):
            continue
        stage2_status = str(asset_group["status"].iloc[0])
        current_components: list[dict[str, object]] = []
        residual_row = asset_group.loc[
            asset_group["component_type"].eq("residual")
        ].iloc[0]
        if stage2_status in _FAILED_STAGE2_STATUSES:
            asset_residual = observed_return
            residual_source = "stage2_unavailable_balance"
            for row in asset_group.loc[
                asset_group["component_type"].ne("residual")
            ].itertuples(index=False):
                if row.component_type == "intercept":
                    output_type = "asset_intercept"
                    output_id = "asset_intercept"
                elif row.component_type == "channel":
                    output_type = "unresolved_channel"
                    output_id = row.component_id
                else:
                    output_type = row.component_type
                    output_id = row.component_id
                current_components.append(
                    _component_record(
                        current_date=current_date,
                        asset_id=asset_id,
                        component_type=output_type,
                        component_id=output_id,
                        contribution=0.0,
                        is_explained=False,
                        is_residual=row.component_type == "channel",
                        source="unavailable_placeholder",
                        status=stage2_status,
                        allocation_method="unavailable_placeholder",
                    )
                )
        else:
            asset_residual = float(residual_row["contribution"])
            residual_source = "stage2_residual"
            passthrough = asset_group.loc[
                ~asset_group["component_type"].isin(["channel", "residual"])
            ]
            for row in passthrough.itertuples(index=False):
                output_type = (
                    "asset_intercept"
                    if row.component_type == "intercept"
                    else row.component_type
                )
                output_id = (
                    "asset_intercept"
                    if row.component_type == "intercept"
                    else row.component_id
                )
                current_components.append(
                    _component_record(
                        current_date=current_date,
                        asset_id=asset_id,
                        component_type=output_type,
                        component_id=output_id,
                        contribution=float(row.contribution),
                        is_explained=True,
                        is_residual=False,
                        source="stage2",
                        status=stage2_status,
                        allocation_method="direct_passthrough",
                    )
                )
            allocated_paths: dict[str, list[float]] = {}
            allocation_rows: dict[str, pd.Series] = {}
            channel_rows = asset_group.loc[asset_group["component_type"].eq("channel")]
            for channel_row in channel_rows.itertuples(index=False):
                channel_id = str(channel_row.component_id)
                channel_coefficient = float(channel_row.coefficient_mean)
                channel_contribution = float(channel_row.contribution)
                stage1_group = stage1_groups.get((current_date, channel_id))
                stage1_status = (
                    "unavailable"
                    if stage1_group is None
                    else str(stage1_group["status"].iloc[0])
                )
                usable = stage1_group is not None and stage1_status == "estimated"
                if usable:
                    required_values = stage1_group[
                        [
                            "cycle_innovation",
                            "coefficient_mean",
                            "contribution",
                            "intercept",
                            "channel_residual",
                        ]
                    ]
                    usable = not required_values.isna().any().any()
                path_source = (
                    stage1_group.itertuples(index=False)
                    if stage1_group is not None
                    else (
                        SimplePathRow(
                            cycle_id=cycle_id,
                            cycle_innovation=innovation_lookup.get(
                                (current_date, cycle_id),
                                np.nan,
                            ),
                            coefficient_mean=np.nan,
                            contribution=np.nan,
                        )
                        for cycle_id in CYCLE_IDS
                    )
                )
                raw_total = 0.0
                for stage1_row in path_source:
                    cycle_id = str(stage1_row.cycle_id)
                    allocation = identification[(current_date, asset_id, cycle_id)]
                    raw_contribution = np.nan
                    if usable:
                        raw_contribution = float(
                            stage1_row.contribution * channel_coefficient
                        )
                        exact_product = float(
                            stage1_row.cycle_innovation
                            * stage1_row.coefficient_mean
                            * channel_coefficient
                        )
                        if not _is_close(
                            raw_contribution,
                            exact_product,
                            normalized_config.conservation_tolerance,
                        ):
                            raise ValueError("raw path multiplication is inconsistent")
                        raw_total += raw_contribution
                        group_id = str(allocation["group_id"])
                        allocated_paths.setdefault(group_id, []).append(
                            raw_contribution
                        )
                        allocation_rows[group_id] = allocation
                    path_records.append(
                        _path_record(
                            current_date=current_date,
                            asset_id=asset_id,
                            channel_id=channel_id,
                            cycle_id=cycle_id,
                            cycle_innovation=float(stage1_row.cycle_innovation),
                            cycle_coefficient=float(stage1_row.coefficient_mean),
                            asset_coefficient=channel_coefficient,
                            raw_contribution=raw_contribution,
                            allocation=allocation,
                            stage1_status=stage1_status,
                            stage2_status=stage2_status,
                        )
                    )
                if not usable:
                    current_components.append(
                        _component_record(
                            current_date=current_date,
                            asset_id=asset_id,
                            component_type="unresolved_channel",
                            component_id=channel_id,
                            contribution=channel_contribution,
                            is_explained=False,
                            is_residual=True,
                            source="stage2_channel",
                            status=stage1_status,
                            allocation_method="unresolved_channel",
                        )
                    )
                    continue
                intercept = float(stage1_group["intercept"].iloc[0])
                channel_residual = float(stage1_group["channel_residual"].iloc[0])
                baseline_contribution = intercept * channel_coefficient
                residual_contribution = channel_residual * channel_coefficient
                expanded = baseline_contribution + raw_total + residual_contribution
                if not _is_close(
                    expanded,
                    channel_contribution,
                    normalized_config.conservation_tolerance,
                ):
                    raise ValueError(
                        "expanded stage1 paths do not conserve stage2 channel"
                    )
                current_components.extend(
                    [
                        _component_record(
                            current_date=current_date,
                            asset_id=asset_id,
                            component_type="channel_baseline_path",
                            component_id=channel_id,
                            contribution=baseline_contribution,
                            is_explained=True,
                            is_residual=False,
                            source="stage1_intercept_x_stage2_beta",
                            status=stage1_status,
                            allocation_method="path_expansion",
                        ),
                        _component_record(
                            current_date=current_date,
                            asset_id=asset_id,
                            component_type="channel_residual_path",
                            component_id=channel_id,
                            contribution=residual_contribution,
                            is_explained=False,
                            is_residual=True,
                            source="stage1_residual_x_stage2_beta",
                            status=stage1_status,
                            allocation_method="path_expansion",
                        ),
                    ]
                )
            for group_id, contributions in allocated_paths.items():
                allocation = allocation_rows[group_id]
                group_status = str(allocation["status"])
                component_type = (
                    "cycle"
                    if int(allocation["group_size"]) == 1
                    and group_status == "independent"
                    else "cycle_group"
                )
                current_components.append(
                    _component_record(
                        current_date=current_date,
                        asset_id=asset_id,
                        component_type=component_type,
                        component_id=group_id,
                        contribution=float(sum(contributions)),
                        is_explained=True,
                        is_residual=False,
                        source="stage1_cycle_x_stage2_beta",
                        status=group_status,
                        allocation_method=str(allocation["method"]),
                    )
                )
        direct_row = evidence_lookup.get((current_date, asset_id))
        if _accepted_direct_evidence(
            direct_row,
            current_date,
            normalized_config,
        ):
            direct_contribution = float(direct_row["contribution"])
            current_components.append(
                _component_record(
                    current_date=current_date,
                    asset_id=asset_id,
                    component_type="unobserved_channel_residual",
                    component_id="direct_cycle_residual",
                    contribution=direct_contribution,
                    is_explained=True,
                    is_residual=False,
                    source="validated_direct_evidence",
                    status="validated",
                    allocation_method="validated_direct_evidence",
                )
            )
            asset_residual -= direct_contribution
        current_components.append(
            _component_record(
                current_date=current_date,
                asset_id=asset_id,
                component_type="asset_residual",
                component_id="asset_residual",
                contribution=asset_residual,
                is_explained=False,
                is_residual=True,
                source=residual_source,
                status=stage2_status,
                allocation_method="residual",
            )
        )
        _finalize_component_group(
            current_components,
            observed_return,
            normalized_config.conservation_tolerance,
        )
        component_records.extend(current_components)
    paths = pd.DataFrame.from_records(path_records, columns=ATTRIBUTION_PATH_COLUMNS)
    components = pd.DataFrame.from_records(
        component_records,
        columns=ATTRIBUTION_COMPONENT_COLUMNS,
    )
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    if not paths.empty:
        paths["_cycle_order"] = paths["cycle_id"].map(cycle_order)
        paths = (
            paths.sort_values(
                ["date", "asset_id", "channel_id", "_cycle_order"],
                kind="stable",
            )
            .drop(columns="_cycle_order")
            .reset_index(drop=True)
        )
    if not components.empty:
        components["_component_order"] = components["component_type"].map(
            _COMPONENT_ORDER
        )
        components = (
            components.sort_values(
                ["date", "asset_id", "_component_order", "component_id"],
                kind="stable",
            )
            .drop(columns="_component_order")
            .reset_index(drop=True)
        )
    return AttributionContributionResult(
        paths=paths,
        components=components,
        identifiability=identifiability,
        conservation_tolerance=normalized_config.conservation_tolerance,
    )


@dataclass(frozen=True)
class SimplePathRow:
    cycle_id: str
    cycle_innovation: float
    coefficient_mean: float
    contribution: float
