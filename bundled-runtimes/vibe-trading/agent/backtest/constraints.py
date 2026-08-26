"""Composable, fail-closed constraints for optimizer target weights."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


_EPS = 1e-9
_TOL = 1e-9
_MAX_PASSES = 50


def _fraction(value: Any, label: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be numeric, not boolean")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or not 0 < parsed <= 1:
        raise ValueError(f"{label} must be finite and in (0, 1]")
    return parsed


class MaxWeight:
    def __init__(self, cap: float) -> None:
        self.cap = cap

    def apply(self, weights: np.ndarray, codes: Sequence[str]) -> np.ndarray:
        del codes
        result = weights.astype(float).copy()
        gross = float(result.sum())
        if len(result) * self.cap + _TOL < gross:
            raise ValueError(
                f"max_weight cap {self.cap} is infeasible for {len(result)} active symbols "
                f"and gross exposure {gross:.8f}"
            )
        for _ in range(_MAX_PASSES):
            over = result > self.cap + _TOL
            if not over.any():
                return result
            excess = float((result[over] - self.cap).sum())
            result[over] = self.cap
            room = np.maximum(self.cap - result, 0.0)
            capacity = float(room.sum())
            if capacity + _TOL < excess:
                raise ValueError("max_weight redistribution is infeasible")
            result += room / capacity * excess
        raise ValueError("max_weight constraint did not converge")

    def violations(self, weights: np.ndarray, codes: Sequence[str]) -> list[str]:
        return [
            f"{code}={weight:.8f} exceeds max_weight {self.cap:.8f}"
            for code, weight in zip(codes, weights)
            if weight > self.cap + _TOL
        ]


class MinWeight:
    def __init__(self, floor: float) -> None:
        self.floor = floor

    def apply(self, weights: np.ndarray, codes: Sequence[str]) -> np.ndarray:
        del codes
        result = weights.astype(float).copy()
        gross = float(result.sum())
        if len(result) * self.floor > gross + _TOL:
            raise ValueError(
                f"min_weight floor {self.floor} is infeasible for {len(result)} active symbols "
                f"and gross exposure {gross:.8f}"
            )
        below = result < self.floor - _TOL
        if not below.any():
            return result
        need = float((self.floor - result[below]).sum())
        result[below] = self.floor
        donors = result > self.floor + _TOL
        available = float((result[donors] - self.floor).sum())
        if available + _TOL < need:
            raise ValueError("min_weight redistribution is infeasible")
        result[donors] -= (result[donors] - self.floor) / available * need
        return result

    def violations(self, weights: np.ndarray, codes: Sequence[str]) -> list[str]:
        return [
            f"{code}={weight:.8f} is below min_weight {self.floor:.8f}"
            for code, weight in zip(codes, weights)
            if weight > _EPS and weight < self.floor - _TOL
        ]


class GroupExposure:
    def __init__(self, groups: Mapping[str, str], caps: Mapping[str, float]) -> None:
        self.groups = dict(groups)
        self.caps = dict(caps)

    def apply(self, weights: np.ndarray, codes: Sequence[str]) -> np.ndarray:
        result = weights.astype(float).copy()
        for group, cap in self.caps.items():
            indices = [index for index, code in enumerate(codes) if self.groups.get(code) == group]
            total = float(result[indices].sum()) if indices else 0.0
            if total > cap + _TOL:
                result[indices] *= cap / total
        return result

    def violations(self, weights: np.ndarray, codes: Sequence[str]) -> list[str]:
        violations: list[str] = []
        for group, cap in self.caps.items():
            total = sum(
                float(weight)
                for code, weight in zip(codes, weights)
                if self.groups.get(code) == group
            )
            if total > cap + _TOL:
                violations.append(
                    f"group {group!r} exposure {total:.8f} exceeds cap {cap:.8f}"
                )
        return violations


def _build_constraint(spec: Mapping[str, Any]) -> Any:
    if not isinstance(spec, Mapping):
        raise ValueError(f"constraint spec must be a mapping, got {type(spec).__name__}")
    kind = spec.get("type")
    if kind == "max_weight":
        if "cap" not in spec:
            raise ValueError("max_weight constraint requires 'cap'")
        return MaxWeight(_fraction(spec["cap"], "max_weight cap"))
    if kind == "min_weight":
        if "floor" not in spec:
            raise ValueError("min_weight constraint requires 'floor'")
        return MinWeight(_fraction(spec["floor"], "min_weight floor"))
    if kind == "group_exposure":
        groups = spec.get("groups")
        caps = spec.get("caps")
        if not isinstance(groups, Mapping) or not groups:
            raise ValueError("group_exposure constraint requires a non-empty 'groups' mapping")
        if any(not isinstance(code, str) or not isinstance(group, str) for code, group in groups.items()):
            raise ValueError("groups must map string asset codes to string group names")
        if not isinstance(caps, Mapping) or not caps:
            raise ValueError("group_exposure constraint requires a non-empty 'caps' mapping")
        unknown = set(caps) - set(groups.values())
        if unknown:
            raise ValueError(
                "caps reference groups with no mapped assets: " + ", ".join(sorted(unknown))
            )
        return GroupExposure(
            groups,
            {
                str(group): _fraction(cap, f"cap for group {group!r}")
                for group, cap in caps.items()
            },
        )
    raise ValueError(
        f"unknown constraint type {kind!r}; expected max_weight, min_weight, or group_exposure"
    )


def load_constraints(config: Mapping[str, Any]) -> list[Any]:
    raw = config.get("constraints")
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("constraints must be a list of constraint specs")
    return [_build_constraint(spec) for spec in raw]


def apply_constraints_frame(
    frame: pd.DataFrame,
    constraints: Sequence[Any],
) -> pd.DataFrame:
    """Apply constraints per decision date while preserving signs and inactive names."""
    if not constraints:
        return frame
    if not np.isfinite(frame.fillna(0.0).to_numpy(dtype=float)).all():
        raise ValueError("optimizer output contains non-finite weights")

    output = frame.copy()
    for date in frame.index:
        row = frame.loc[date].fillna(0.0)
        codes = [str(code) for code in row.index if abs(float(row[code])) > _EPS]
        if not codes:
            continue
        signs = np.sign(row[codes].to_numpy(dtype=float))
        magnitudes = np.abs(row[codes].to_numpy(dtype=float))
        for constraint in constraints:
            try:
                magnitudes = constraint.apply(magnitudes, codes)
            except ValueError as exc:
                raise ValueError(f"constraint composition is infeasible at {date}: {exc}") from exc
        violations = [
            violation
            for constraint in constraints
            for violation in constraint.violations(magnitudes, codes)
        ]
        if violations:
            raise ValueError(
                f"constraint composition is infeasible at {date}: " + "; ".join(violations)
            )
        output.loc[date, codes] = signs * magnitudes
    return output
