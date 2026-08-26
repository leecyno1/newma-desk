"""Exact point-in-time reconstruction from immutable observations."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from seven_cycle_platform.cycles.engine import SevenCycleEngine
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.types import VintageKind


_PANEL_FIELD_NAMES = ("annual_panel", "monthly_panel")
_SUPPORTED_CYCLE_VINTAGES = frozenset(
    {
        VintageKind.REALTIME,
        VintageKind.LATEST_HISTORICAL,
        VintageKind.PSEUDO_VINTAGE,
    }
)
CYCLE_VINTAGE_COLUMNS = (
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    "frequency",
    "angle",
    "phase",
    "level",
    "slope",
    "acceleration",
    "amplitude",
    "innovation",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
    "evidence_level",
    "usage_status",
    "effective_cycles",
    "observed_observations",
    "member_breadth",
    "category_breadth",
    "total_members",
    "total_categories",
)


def _readonly_frame(values: pd.DataFrame) -> pd.DataFrame:
    copied = values.copy(deep=True)
    for block in copied._mgr.blocks:
        block.values.setflags(write=False)
    return copied


@dataclass(frozen=True)
class VintageSelection:
    """One deterministic visible revision per entity and observation date."""

    as_of: date
    vintage: VintageKind
    observations: tuple[Observation, ...]
    caveats: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a date")
        if not isinstance(self.vintage, VintageKind):
            raise TypeError("vintage must be a VintageKind")
        if self.vintage not in _SUPPORTED_CYCLE_VINTAGES:
            raise ValueError(
                "cycle vintage selection does not support data-identity vintage: "
                f"{self.vintage.value}"
            )

        try:
            observations = tuple(self.observations)
        except TypeError as error:
            raise TypeError(
                "observations must be an iterable of Observation records"
            ) from error
        if any(not isinstance(observation, Observation) for observation in observations):
            raise TypeError("observations must contain Observation records")

        if isinstance(self.caveats, str):
            raise TypeError("caveats must be an iterable of strings")
        try:
            raw_caveats = tuple(self.caveats)
        except TypeError as error:
            raise TypeError("caveats must be an iterable of strings") from error
        if any(not isinstance(caveat, str) or not caveat.strip() for caveat in raw_caveats):
            raise ValueError("caveats must contain non-empty strings")
        caveats = tuple(sorted(caveat.strip() for caveat in raw_caveats))

        ordered = tuple(
            sorted(
                observations,
                key=lambda observation: (
                    observation.entity_id,
                    observation.observation_date,
                ),
            )
        )
        keys = [
            (observation.entity_id, observation.observation_date)
            for observation in ordered
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "selection must contain one observation per entity_id × date"
            )
        for observation in ordered:
            if observation.release_date > self.as_of:
                raise ValueError(
                    "selected observation is not visible because release_date "
                    f"{observation.release_date} exceeds as_of {self.as_of}"
                )
            if observation.vintage_date > self.as_of:
                raise ValueError(
                    "selected observation is not visible because vintage_date "
                    f"{observation.vintage_date} exceeds as_of {self.as_of}"
                )

        kinds = {observation.vintage_kind for observation in ordered}
        unsupported_kinds = kinds.difference(_SUPPORTED_CYCLE_VINTAGES)
        if unsupported_kinds:
            values = ", ".join(
                sorted(vintage.value for vintage in unsupported_kinds)
            )
            raise ValueError(
                "cycle vintage selection observations do not support "
                f"data-identity vintages: {values}"
            )
        if not ordered:
            if caveats:
                raise ValueError("empty selections must have empty caveats")
        elif self.vintage is VintageKind.REALTIME:
            if kinds != {VintageKind.REALTIME}:
                raise ValueError(
                    "REALTIME selections may contain only REALTIME rows"
                )
            if caveats:
                raise ValueError("REALTIME selections cannot contain pseudo caveats")
        elif self.vintage is VintageKind.LATEST_HISTORICAL:
            if kinds != {VintageKind.LATEST_HISTORICAL}:
                raise ValueError(
                    "LATEST_HISTORICAL selections may contain only "
                    "LATEST_HISTORICAL rows"
                )
            if caveats:
                raise ValueError(
                    "LATEST_HISTORICAL selections cannot contain caveats"
                )
        else:
            if VintageKind.LATEST_HISTORICAL in kinds:
                raise ValueError(
                    "PSEUDO_VINTAGE selections cannot contain "
                    "LATEST_HISTORICAL rows"
                )
            if VintageKind.PSEUDO_VINTAGE not in kinds:
                raise ValueError(
                    "PSEUDO_VINTAGE selections require at least one PSEUDO row"
                )
            if not caveats:
                raise ValueError(
                    "PSEUDO_VINTAGE selections require non-empty caveats"
                )

        object.__setattr__(self, "observations", ordered)
        object.__setattr__(self, "caveats", caveats)


@dataclass(frozen=True)
class VintagePanels:
    """Detached annual and monthly panels selected for one cutoff."""

    annual_panel: pd.DataFrame
    monthly_panel: pd.DataFrame

    def __post_init__(self) -> None:
        for field_name in _PANEL_FIELD_NAMES:
            values = object.__getattribute__(self, field_name)
            if not isinstance(values, pd.DataFrame):
                raise TypeError(f"{field_name} must be a pandas DataFrame")
            object.__setattr__(self, field_name, _readonly_frame(values))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _PANEL_FIELD_NAMES and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def _normalize_date(value: object, *, name: str) -> date:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a date, not a boolean")
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise ValueError(f"{name} cannot be missing")
        timestamp = value
    elif isinstance(value, datetime):
        timestamp = pd.Timestamp(value)
    elif isinstance(value, date):
        return value
    elif isinstance(value, np.datetime64):
        if np.isnat(value):
            raise ValueError(f"{name} cannot be missing")
        timestamp = pd.Timestamp(value)
    elif isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{name} cannot be blank")
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must be a valid date") from error
    else:
        raise TypeError(f"{name} must be a date")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone.utc).tz_localize(None)
    return timestamp.date()


def _normalize_as_of_dates(as_of: object) -> tuple[date, ...]:
    scalar_types = (str, date, datetime, np.datetime64, pd.Timestamp)
    if isinstance(as_of, (bool, np.bool_)):
        raise TypeError("as_of must be a date, not a boolean")
    if isinstance(as_of, scalar_types):
        raw_dates = [as_of]
    elif isinstance(as_of, Iterable) and not isinstance(as_of, Mapping):
        raw_dates = list(as_of)
    else:
        raise TypeError("as_of must be a date or an iterable of dates")
    if not raw_dates:
        raise ValueError("as_of must contain at least one date")
    normalized = tuple(
        _normalize_date(raw_date, name="as_of") for raw_date in raw_dates
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate as_of dates are not supported")
    return tuple(sorted(normalized))


def _normalize_interpretation(value: object) -> VintageKind:
    if isinstance(value, VintageKind):
        interpretation = value
    elif isinstance(value, str):
        try:
            interpretation = VintageKind(value)
        except ValueError as error:
            raise ValueError(f"unknown vintage interpretation: {value}") from error
    else:
        raise TypeError("interpretation must be a VintageKind or string")
    if interpretation not in _SUPPORTED_CYCLE_VINTAGES:
        raise ValueError(
            "cycle vintage interpretation does not support data-identity "
            f"vintage: {interpretation.value}"
        )
    return interpretation


def _observation_key(observation: Observation) -> tuple[object, ...]:
    return (
        observation.entity_id,
        observation.observation_date,
        observation.release_date,
        observation.vintage_date,
        observation.value,
        observation.unit,
        observation.source,
        observation.retrieval_time,
        observation.revision_number,
        observation.quality_status,
        observation.vintage_kind,
    )


def _revision_signature(observation: Observation) -> tuple[object, ...]:
    return (
        observation.entity_id,
        observation.observation_date,
        observation.release_date,
        observation.vintage_date,
        observation.value,
        observation.unit,
        observation.source,
        observation.revision_number,
        observation.quality_status,
        observation.vintage_kind,
    )


def _observation_records(records: object) -> tuple[Observation, ...]:
    if isinstance(records, (str, bytes, bytearray, Mapping)) or isinstance(
        records,
        (bool, np.bool_),
    ):
        raise TypeError("records must be an iterable of Observation records")
    try:
        observations = tuple(records)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "records must be an iterable of Observation records"
        ) from error
    if any(not isinstance(record, Observation) for record in observations):
        raise TypeError("records must contain only Observation records")
    unsupported_kinds = {
        record.vintage_kind
        for record in observations
        if record.vintage_kind not in _SUPPORTED_CYCLE_VINTAGES
    }
    if unsupported_kinds:
        values = ", ".join(
            sorted(vintage.value for vintage in unsupported_kinds)
        )
        raise ValueError(
            "cycle vintage records do not support data-identity vintages: "
            f"{values}"
        )
    exact_keys = [_observation_key(record) for record in observations]
    if len(exact_keys) != len(set(exact_keys)):
        raise ValueError("duplicate observation records are not supported")
    return observations


def _candidate_kinds(interpretation: VintageKind) -> frozenset[VintageKind]:
    if interpretation is VintageKind.REALTIME:
        return frozenset(
            {VintageKind.REALTIME, VintageKind.PSEUDO_VINTAGE}
        )
    return frozenset({interpretation})


def _latest_revision(
    records: list[Observation],
    *,
    entity_id: str,
    observation_date: date,
) -> Observation:
    by_revision: dict[int, list[Observation]] = {}
    for record in records:
        by_revision.setdefault(record.revision_number, []).append(record)

    collapsed: list[Observation] = []
    for revision_number in sorted(by_revision):
        revision_records = by_revision[revision_number]
        signatures = {
            _revision_signature(record) for record in revision_records
        }
        if len(signatures) != 1:
            raise ValueError(
                "ambiguous duplicate revision for "
                f"{entity_id} at {observation_date} revision {revision_number}"
            )
        collapsed.append(
            max(revision_records, key=lambda record: record.retrieval_time)
        )

    for earlier, later in zip(collapsed, collapsed[1:], strict=False):
        if later.vintage_date < earlier.vintage_date:
            raise ValueError(
                "revision vintage dates must be monotonic for "
                f"{entity_id} at {observation_date}"
            )
    return collapsed[-1]


def read_vintage(
    records: object,
    *,
    as_of: object,
    strict: bool = True,
    interpretation: VintageKind | str = VintageKind.REALTIME,
) -> VintageSelection:
    """Select the latest revision visible at ``as_of`` without retrieval leakage.

    Historical visibility is determined by ``release_date`` and ``vintage_date``.
    ``retrieval_time`` records archive ingestion and is used only to choose the
    latest equivalent reingestion of the same unambiguous revision.
    """

    if not isinstance(strict, bool):
        raise TypeError("strict must be a boolean")
    cutoff = _normalize_date(as_of, name="as_of")
    requested = _normalize_interpretation(interpretation)
    observations = _observation_records(records)
    visible = [
        record
        for record in observations
        if record.vintage_kind in _candidate_kinds(requested)
        and record.release_date <= cutoff
        and record.vintage_date <= cutoff
    ]

    grouped: dict[tuple[str, date], list[Observation]] = {}
    for record in visible:
        grouped.setdefault(
            (record.entity_id, record.observation_date),
            [],
        ).append(record)

    selected: list[Observation] = []
    for (entity_id, observation_date), candidates in sorted(grouped.items()):
        if requested is VintageKind.REALTIME:
            true_realtime = [
                record
                for record in candidates
                if record.vintage_kind is VintageKind.REALTIME
            ]
            if true_realtime:
                candidates = true_realtime
        selected.append(
            _latest_revision(
                candidates,
                entity_id=entity_id,
                observation_date=observation_date,
            )
        )

    pseudo_entities = tuple(
        sorted(
            {
                record.entity_id
                for record in selected
                if record.vintage_kind is VintageKind.PSEUDO_VINTAGE
            }
        )
    )
    if strict and pseudo_entities:
        entities = ", ".join(pseudo_entities)
        raise ValueError(
            "strict vintage mode rejects selected pseudo_vintage data for "
            f"{entities}"
        )

    if pseudo_entities:
        vintage = VintageKind.PSEUDO_VINTAGE
        caveats = tuple(
            f"{entity_id} is pseudo-vintage evidence and is not true realtime "
            "history."
            for entity_id in pseudo_entities
        )
    else:
        vintage = requested
        caveats = ()
    return VintageSelection(
        as_of=cutoff,
        vintage=vintage,
        observations=tuple(selected),
        caveats=caveats,
    )


def _category_mapping(
    categories: Mapping[object, str] | pd.Series,
    *,
    name: str,
) -> dict[str, str]:
    if isinstance(categories, pd.Series):
        if categories.index.has_duplicates:
            raise ValueError(f"{name} keys must be unique")
        raw = categories.to_dict()
    elif isinstance(categories, Mapping):
        raw = dict(categories)
    else:
        raise TypeError(f"{name} must be a mapping or pandas Series")
    normalized: dict[str, str] = {}
    for entity_id, category in raw.items():
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError(f"{name} keys must be non-empty strings")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"{name} values must be non-empty strings")
        normalized[entity_id] = category.strip()
    return {entity_id: normalized[entity_id] for entity_id in sorted(normalized)}


def _validate_selected_metadata(records: tuple[Observation, ...]) -> None:
    metadata: dict[str, tuple[str, str]] = {}
    for record in records:
        current = (record.unit, record.source)
        previous = metadata.setdefault(record.entity_id, current)
        if current != previous:
            raise ValueError(
                f"{record.entity_id} has inconsistent unit or source metadata"
            )


def _annual_panel(
    records: list[Observation],
    columns: list[str],
) -> pd.DataFrame:
    if records:
        years = [record.observation_date.year for record in records]
        index = pd.Index(
            range(min(years), max(years) + 1),
            name="year",
            dtype="int64",
        )
    else:
        index = pd.Index([], name="year", dtype="int64")
    panel = pd.DataFrame(np.nan, index=index, columns=columns, dtype="float64")
    for record in records:
        if record.observation_date != date(record.observation_date.year, 12, 31):
            raise ValueError(
                "annual observations must be aligned to December 31: "
                f"{record.entity_id} at {record.observation_date}"
            )
        year = record.observation_date.year
        if pd.notna(panel.loc[year, record.entity_id]):
            raise ValueError(
                "annual observations must be unique by entity and year"
            )
        panel.loc[year, record.entity_id] = float(record.value)
    return panel


def _monthly_panel(
    records: list[Observation],
    columns: list[str],
) -> pd.DataFrame:
    if records:
        dates = [pd.Timestamp(record.observation_date) for record in records]
        index = pd.date_range(
            min(dates),
            max(dates),
            freq="ME",
            name="month",
        )
    else:
        index = pd.DatetimeIndex([], name="month")
    panel = pd.DataFrame(np.nan, index=index, columns=columns, dtype="float64")
    for record in records:
        timestamp = pd.Timestamp(record.observation_date)
        if not timestamp.is_month_end:
            raise ValueError(
                "monthly observations must be aligned to month end: "
                f"{record.entity_id} at {record.observation_date}"
            )
        if pd.notna(panel.loc[timestamp, record.entity_id]):
            raise ValueError(
                "monthly observations must be unique by entity and month"
            )
        panel.loc[timestamp, record.entity_id] = float(record.value)
    return panel


def build_vintage_panels(
    selection: VintageSelection,
    *,
    annual_categories: Mapping[object, str] | pd.Series,
    monthly_categories: Mapping[object, str] | pd.Series,
) -> VintagePanels:
    """Pivot one vintage selection into stable regular annual/monthly panels."""

    if not isinstance(selection, VintageSelection):
        raise TypeError("selection must be a VintageSelection")
    annual_map = _category_mapping(
        annual_categories,
        name="annual_categories",
    )
    monthly_map = _category_mapping(
        monthly_categories,
        name="monthly_categories",
    )
    overlap = sorted(set(annual_map).intersection(monthly_map))
    if overlap:
        raise ValueError(
            "entities cannot be both annual and monthly: " + ", ".join(overlap)
        )

    annual_records: list[Observation] = []
    monthly_records: list[Observation] = []
    known_entities = set(annual_map).union(monthly_map)
    for record in selection.observations:
        if record.entity_id not in known_entities:
            raise ValueError(
                f"selected observation has no frequency/category mapping: "
                f"{record.entity_id}"
            )
        if record.entity_id in annual_map:
            annual_records.append(record)
        else:
            monthly_records.append(record)
    _validate_selected_metadata(selection.observations)
    return VintagePanels(
        annual_panel=_annual_panel(annual_records, list(annual_map)),
        monthly_panel=_monthly_panel(monthly_records, list(monthly_map)),
    )


def reconstruct_cycle_vintage(
    records: object,
    *,
    engine: SevenCycleEngine,
    annual_categories: Mapping[object, str] | pd.Series,
    monthly_categories: Mapping[object, str] | pd.Series,
    as_of: object,
    strict: bool = True,
    interpretation: VintageKind | str = VintageKind.REALTIME,
) -> pd.DataFrame:
    """Rebuild governed cycle states independently at every requested cutoff."""

    if not isinstance(engine, SevenCycleEngine):
        raise TypeError("engine must be a SevenCycleEngine")
    observations = _observation_records(records)
    annual_map = _category_mapping(
        annual_categories,
        name="annual_categories",
    )
    monthly_map = _category_mapping(
        monthly_categories,
        name="monthly_categories",
    )
    if not annual_map or not monthly_map:
        raise ValueError(
            "annual_categories and monthly_categories must both be non-empty"
        )
    cutoffs = _normalize_as_of_dates(as_of)
    requested = _normalize_interpretation(interpretation)

    histories: list[pd.DataFrame] = []
    for cutoff in cutoffs:
        selection = read_vintage(
            observations,
            as_of=cutoff,
            strict=strict,
            interpretation=requested,
        )
        panels = build_vintage_panels(
            selection,
            annual_categories=annual_map,
            monthly_categories=monthly_map,
        )
        states = engine.compute(
            annual_panel=panels.annual_panel,
            monthly_panel=panels.monthly_panel,
            annual_categories=annual_map,
            monthly_categories=monthly_map,
            as_of=cutoff,
        ).copy(deep=True)
        states = states.rename(columns={"as_of": "date"})
        states.insert(2, "vintage", selection.vintage.value)
        caveat = "; ".join(selection.caveats) if selection.caveats else None
        states.insert(3, "vintage_caveat", caveat)
        histories.append(states)

    output = pd.concat(histories, ignore_index=True)
    output["date"] = pd.to_datetime(output["date"]).dt.normalize()
    cycle_order = output["cycle_id"].str.removeprefix("C").astype("int64")
    ordered = (
        output.assign(_cycle_order=cycle_order)
        .sort_values(["date", "_cycle_order", "vintage"], kind="stable")
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )
    return ordered.loc[:, CYCLE_VINTAGE_COLUMNS]


select_vintage_observations = read_vintage
reconstruct_cycle_phase_vintage = reconstruct_cycle_vintage


__all__ = [
    "CYCLE_VINTAGE_COLUMNS",
    "VintagePanels",
    "VintageSelection",
    "build_vintage_panels",
    "read_vintage",
    "reconstruct_cycle_phase_vintage",
    "reconstruct_cycle_vintage",
    "select_vintage_observations",
]
