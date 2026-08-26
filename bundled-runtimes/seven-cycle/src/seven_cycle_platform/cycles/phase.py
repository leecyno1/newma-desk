"""Stable UI phase labels derived from continuous cycle states."""

from enum import StrEnum
from numbers import Real

import numpy as np


class CyclePhase(StrEnum):
    """Four serialized level/slope quadrants used by presentation layers."""

    EXPANSION = "expansion"
    DOWNTURN = "downturn"
    CONTRACTION = "contraction"
    RECOVERY = "recovery"


def phase_from_level_slope(level: object, slope: object) -> CyclePhase | None:
    """Map finite continuous level and slope values to a UI quadrant."""

    for value, name in ((level, "level"), (slope, "slope")):
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (Real, np.integer, np.floating),
        ):
            raise TypeError(f"{name} must be a real number")
    numeric_level = float(level)
    numeric_slope = float(slope)
    if not np.isfinite(numeric_level) or not np.isfinite(numeric_slope):
        return None
    if numeric_level >= 0.0 and numeric_slope >= 0.0:
        return CyclePhase.EXPANSION
    if numeric_level >= 0.0 and numeric_slope < 0.0:
        return CyclePhase.DOWNTURN
    if numeric_level < 0.0 and numeric_slope < 0.0:
        return CyclePhase.CONTRACTION
    return CyclePhase.RECOVERY
