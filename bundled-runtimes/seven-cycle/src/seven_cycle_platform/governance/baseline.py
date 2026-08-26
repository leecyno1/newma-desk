"""Strict loader for the approved seven-cycle evidence baseline."""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.resolver import BaseResolver

from seven_cycle_platform.registry.models import CycleId


EvidenceStatus = Literal[
    "supported",
    "scenario_supported",
    "explanatory_only",
    "calendar_defined",
    "unidentified",
]
NonEmptyString = Annotated[str, Field(min_length=1)]
_EXPECTED_CYCLE_IDS: tuple[CycleId, ...] = (
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "C7",
)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class EvidenceRecord(BaseModel):
    """One immutable, strictly validated cycle evidence decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    cycle_id: CycleId
    evidence_status: EvidenceStatus
    center_prior_months: float = Field(gt=0)
    empirical_band_months: tuple[float, float] | None
    family_centers_months: tuple[float, ...]
    reason_codes: tuple[NonEmptyString, ...] = Field(min_length=1)
    summary: str = Field(min_length=1)

    @field_validator(
        "empirical_band_months",
        "family_centers_months",
        "reason_codes",
        mode="before",
    )
    @classmethod
    def convert_yaml_sequences(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_band(self) -> Self:
        if self.empirical_band_months is not None:
            lower, upper = self.empirical_band_months
            if lower <= 0 or lower > upper:
                raise ValueError(
                    "empirical_band_months must be positive and ordered"
                )
        if self.evidence_status == "supported" and self.empirical_band_months is None:
            raise ValueError("supported evidence requires empirical_band_months")
        if self.evidence_status == "unidentified" and self.empirical_band_months:
            raise ValueError("unidentified evidence cannot publish an empirical band")
        return self


class EvidenceBaseline(BaseModel):
    """Immutable approved evidence baseline for exactly seven cycles."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    generated: date
    source_document: str = Field(min_length=1)
    cycles: tuple[EvidenceRecord, ...]

    @model_validator(mode="before")
    @classmethod
    def validate_cycle_structure(cls, payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        cycles = payload.get("cycles")
        if not isinstance(cycles, (list, tuple)):
            return payload
        if len(cycles) != len(_EXPECTED_CYCLE_IDS):
            raise ValueError("evidence baseline must contain exactly seven cycles")
        cycle_ids: list[object] = []
        for index, record in enumerate(cycles):
            if not isinstance(record, dict):
                raise ValueError(f"cycles[{index}] must be a mapping")
            cycle_ids.append(record.get("cycle_id"))
        if tuple(cycle_ids) != _EXPECTED_CYCLE_IDS:
            raise ValueError("evidence baseline must contain C1 through C7 in order")
        return payload

    @field_validator("cycles", mode="before")
    @classmethod
    def convert_yaml_cycles(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def load_evidence_baseline(path: str | Path) -> EvidenceBaseline:
    """Load the approved baseline with strict schema and YAML validation."""

    baseline_path = Path(path)
    with baseline_path.open(encoding="utf-8") as baseline_file:
        try:
            payload = yaml.load(baseline_file, Loader=_UniqueKeySafeLoader)
        except yaml.YAMLError as error:
            raise ValueError(
                f"invalid evidence baseline YAML in {baseline_path}: {error}"
            ) from error
    return EvidenceBaseline.model_validate(payload)
