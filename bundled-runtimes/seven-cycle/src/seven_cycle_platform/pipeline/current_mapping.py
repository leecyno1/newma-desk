"""Governed M4 current-mapping pipeline entrypoint."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from seven_cycle_platform.mapping.distribution import CurrentDistributionResult
from seven_cycle_platform.mapping.features import CurrentFeatureSnapshot
from seven_cycle_platform.mapping.transferability import TransferabilityResult
from seven_cycle_platform.mapping.weights import WeightRangeResult
from seven_cycle_platform.products.asset_mapping_current import M3_INFLUENCE_COLUMNS
from seven_cycle_platform.verification.current_mapping import (
    CurrentMappingPublicationResult,
    publish_current_mapping,
)


@dataclass(frozen=True)
class CurrentMappingPipelineInput:
    """Frozen governed M3→M4 dependency surface."""

    snapshot: CurrentFeatureSnapshot
    distribution: CurrentDistributionResult
    transferability: TransferabilityResult
    weight_ranges: WeightRangeResult
    m3_influence: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, CurrentFeatureSnapshot):
            raise TypeError("snapshot must be a CurrentFeatureSnapshot")
        if not isinstance(self.distribution, CurrentDistributionResult):
            raise TypeError("distribution must be a CurrentDistributionResult")
        if not isinstance(self.transferability, TransferabilityResult):
            raise TypeError("transferability must be a TransferabilityResult")
        if not isinstance(self.weight_ranges, WeightRangeResult):
            raise TypeError("weight_ranges must be a WeightRangeResult")
        if not isinstance(self.m3_influence, pd.DataFrame):
            raise TypeError("m3_influence must be a pandas DataFrame")
        if tuple(self.m3_influence.columns) != M3_INFLUENCE_COLUMNS:
            raise ValueError(
                "m3_influence columns do not match the M3 attribution contract"
            )
        if self.m3_influence.empty:
            raise ValueError("m3_influence cannot be empty")
        if set(self.m3_influence["source_stage"]) != {"m3_asset_attribution"}:
            raise ValueError(
                "m3_influence source_stage must identify M3 asset attribution"
            )
        object.__setattr__(self, "m3_influence", self.m3_influence.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == "m3_influence" and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def build_current_mapping(
    pipeline_input: CurrentMappingPipelineInput,
    *,
    run_dir: Path,
) -> CurrentMappingPublicationResult:
    """Run the governed M3-dependent M4 build→verify→publish sequence."""

    if not isinstance(pipeline_input, CurrentMappingPipelineInput):
        raise TypeError("pipeline_input must be a CurrentMappingPipelineInput")
    return publish_current_mapping(
        run_dir,
        snapshot=pipeline_input.snapshot,
        distribution=pipeline_input.distribution,
        transferability=pipeline_input.transferability,
        weight_ranges=pipeline_input.weight_ranges,
        influence=pipeline_input.m3_influence,
    )


run_current_mapping_pipeline = build_current_mapping


__all__ = [
    "CurrentMappingPipelineInput",
    "build_current_mapping",
    "run_current_mapping_pipeline",
]
