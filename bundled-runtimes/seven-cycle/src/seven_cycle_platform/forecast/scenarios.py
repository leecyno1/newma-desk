"""Governed future channel-shock scenarios with exact date resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from numbers import Integral, Real
from pathlib import Path
import re
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import yaml


STANDARD_SCENARIO_IDS = (
    "baseline",
    "easing",
    "tightening",
    "growth",
    "inflation",
    "geopolitical_supply",
)
SCENARIO_SHOCK_COLUMNS = (
    "scenario_id",
    "scenario_version",
    "shock_id",
    "shock_version",
    "channel_id",
    "date",
    "effective_date",
    "end_date",
    "scenario_shock",
    "unit",
    "direction",
    "path",
)

_DATE_RULE = re.compile(r"^forecast_month:([1-9][0-9]*)$")
_VALID_DIRECTIONS = frozenset({"increase", "decrease", "flat"})
_VALID_PATHS = frozenset({"step", "linear", "pulse"})
_SCENARIO_KEYS = frozenset({"scenario_id", "name", "version", "shocks"})
_SHOCK_KEYS = frozenset(
    {
        "shock_id",
        "channel_id",
        "effective_date",
        "effective_date_rule",
        "duration_months",
        "end_date",
        "end_date_rule",
        "value",
        "unit",
        "direction",
        "path",
        "version",
    }
)


class ScenarioConfigError(ValueError):
    """A scenario catalog is malformed or cannot resolve to the forecast surface."""


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name=name)


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _normalize_date(value: object, *, name: str) -> date:
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    if not isinstance(value, (str, date, datetime, np.datetime64, pd.Timestamp)):
        raise TypeError(f"{name} must be date-like")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be missing")
    if timestamp.tzinfo is not None:
        raise ValueError(f"{name} must be timezone-naive")
    return timestamp.normalize().date()


def _stable_hash(payload: object) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=lambda value: value.isoformat() if isinstance(value, date) else value,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class ScenarioShock:
    """One explicit additive shock in governed channel-state units."""

    shock_id: str
    channel_id: str
    value: float
    unit: str
    direction: str
    path: str
    version: str
    effective_date: date | None = None
    effective_date_rule: str | None = None
    duration_months: int | None = None
    end_date: date | None = None
    end_date_rule: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "shock_id", _text(self.shock_id, name="shock_id"))
        object.__setattr__(
            self,
            "channel_id",
            _text(self.channel_id, name="channel_id"),
        )
        effective_date = (
            None
            if self.effective_date is None
            else _normalize_date(self.effective_date, name="effective_date")
        )
        effective_rule = _optional_text(
            self.effective_date_rule,
            name="effective_date_rule",
        )
        if (effective_date is None) == (effective_rule is None):
            raise ValueError(
                "shock must define exactly one of effective_date or effective_date_rule"
            )
        if effective_rule is not None and _DATE_RULE.fullmatch(effective_rule) is None:
            raise ValueError(
                "effective_date_rule must be forecast_month:<positive integer>"
            )
        duration = (
            None
            if self.duration_months is None
            else _positive_integer(self.duration_months, name="duration_months")
        )
        end_date = (
            None
            if self.end_date is None
            else _normalize_date(self.end_date, name="end_date")
        )
        end_rule = _optional_text(self.end_date_rule, name="end_date_rule")
        if duration is None and end_date is None:
            raise ValueError("shock must define duration_months or end_date")
        if end_rule is not None and end_rule != "inclusive_duration":
            raise ValueError("end_date_rule must be inclusive_duration")
        if end_rule is not None and duration is None:
            raise ValueError("inclusive_duration requires duration_months")
        numeric = _finite_real(self.value, name="value")
        unit = _text(self.unit, name="unit")
        direction = _text(self.direction, name="direction")
        path = _text(self.path, name="path")
        version = _text(self.version, name="version")
        if direction not in _VALID_DIRECTIONS:
            raise ValueError("direction must be increase, decrease, or flat")
        if path not in _VALID_PATHS:
            raise ValueError("path must be step, linear, or pulse")
        expected_direction = (
            "increase" if numeric > 0.0 else "decrease" if numeric < 0.0 else "flat"
        )
        if direction != expected_direction:
            raise ValueError("shock direction must explicitly match the value sign")
        if path == "pulse" and duration not in {None, 1}:
            raise ValueError("pulse shocks must have a one-month duration")
        object.__setattr__(self, "effective_date", effective_date)
        object.__setattr__(self, "effective_date_rule", effective_rule)
        object.__setattr__(self, "duration_months", duration)
        object.__setattr__(self, "end_date", end_date)
        object.__setattr__(self, "end_date_rule", end_rule)
        object.__setattr__(self, "value", numeric)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "version", version)


@dataclass(frozen=True)
class ScenarioDefinition:
    """A named, versioned collection of explicit channel shocks."""

    scenario_id: str
    name: str
    version: str
    shocks: Sequence[ScenarioShock]

    def __post_init__(self) -> None:
        scenario_id = _text(self.scenario_id, name="scenario_id")
        name = _text(self.name, name="name")
        version = _text(self.version, name="version")
        if isinstance(self.shocks, (str, bytes, bytearray)):
            raise TypeError("shocks must be a sequence of ScenarioShock")
        shocks = tuple(self.shocks)
        if not all(isinstance(shock, ScenarioShock) for shock in shocks):
            raise TypeError("shocks must contain only ScenarioShock values")
        shock_ids = [shock.shock_id for shock in shocks]
        if len(shock_ids) != len(set(shock_ids)):
            raise ValueError("scenario contains duplicate shock_id values")
        if scenario_id == "baseline" and any(shock.value != 0.0 for shock in shocks):
            raise ValueError("baseline scenario shocks must be strictly zero")
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "shocks", shocks)


@dataclass(frozen=True)
class ScenarioCatalog:
    """Immutable scenario catalog with deterministic provenance hash."""

    catalog_version: str
    scenarios: Sequence[ScenarioDefinition]

    def __post_init__(self) -> None:
        version = _text(self.catalog_version, name="catalog_version")
        if isinstance(self.scenarios, (str, bytes, bytearray)):
            raise TypeError("scenarios must be a sequence of ScenarioDefinition")
        scenarios = tuple(self.scenarios)
        if not scenarios or not all(
            isinstance(scenario, ScenarioDefinition) for scenario in scenarios
        ):
            raise TypeError("scenarios must contain ScenarioDefinition values")
        scenario_ids = [scenario.scenario_id for scenario in scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario catalog contains duplicate scenario_id values")
        object.__setattr__(self, "catalog_version", version)
        object.__setattr__(self, "scenarios", scenarios)

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        return tuple(scenario.scenario_id for scenario in self.scenarios)

    @property
    def config_hash(self) -> str:
        return _stable_hash(
            {
                "catalog_version": self.catalog_version,
                "scenarios": [asdict(scenario) for scenario in self.scenarios],
            }
        )

    def get(self, scenario_id: str) -> ScenarioDefinition:
        normalized = _text(scenario_id, name="scenario_id")
        for scenario in self.scenarios:
            if scenario.scenario_id == normalized:
                return scenario
        raise KeyError(f"unknown scenario_id: {normalized}")


def validate_standard_scenario_catalog(catalog: ScenarioCatalog) -> ScenarioCatalog:
    """Validate the exact governed catalog and explicit non-baseline shocks."""

    if not isinstance(catalog, ScenarioCatalog):
        raise TypeError("catalog must be a ScenarioCatalog")
    if catalog.scenario_ids != STANDARD_SCENARIO_IDS:
        raise ValueError(
            "scenario_catalog.scenario_ids must exactly equal "
            "baseline/easing/tightening/growth/inflation/geopolitical_supply "
            "in standard order"
        )
    baseline = catalog.get("baseline")
    if any(shock.value != 0.0 for shock in baseline.shocks):
        raise ValueError("baseline scenario may contain only zero shocks")
    for scenario_id in STANDARD_SCENARIO_IDS[1:]:
        scenario = catalog.get(scenario_id)
        if not any(shock.value != 0.0 for shock in scenario.shocks):
            raise ValueError(
                f"non-baseline scenario {scenario_id} requires at least one "
                "nonzero explicit shock"
            )
    return catalog


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _strict_keys(
    value: Mapping[str, object],
    *,
    expected: frozenset[str],
    required: frozenset[str],
    name: str,
) -> None:
    supplied = set(value)
    unknown = supplied - expected
    missing = required - supplied
    if unknown:
        raise ValueError(
            f"{name} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise ValueError(f"{name} is missing fields: {', '.join(sorted(missing))}")


def _shock_from_mapping(value: object) -> ScenarioShock:
    payload = _mapping(value, name="shock")
    _strict_keys(
        payload,
        expected=_SHOCK_KEYS,
        required=frozenset(
            {
                "shock_id",
                "channel_id",
                "value",
                "unit",
                "direction",
                "path",
                "version",
            }
        ),
        name="shock",
    )
    return ScenarioShock(**dict(payload))


def _scenario_from_mapping(value: object) -> ScenarioDefinition:
    payload = _mapping(value, name="scenario")
    _strict_keys(
        payload,
        expected=_SCENARIO_KEYS,
        required=_SCENARIO_KEYS,
        name="scenario",
    )
    shocks = payload["shocks"]
    if not isinstance(shocks, list):
        raise TypeError("scenario shocks must be a list")
    return ScenarioDefinition(
        scenario_id=payload["scenario_id"],
        name=payload["name"],
        version=payload["version"],
        shocks=tuple(_shock_from_mapping(shock) for shock in shocks),
    )


def load_scenario_catalog(path: str | Path) -> ScenarioCatalog:
    """Load and strictly validate the governed six-scenario YAML catalog."""

    scenario_path = Path(path)
    if not scenario_path.is_file():
        raise FileNotFoundError(f"scenario file does not exist: {scenario_path}")
    try:
        with scenario_path.open(encoding="utf-8") as scenario_file:
            raw = yaml.safe_load(scenario_file)
    except yaml.YAMLError as error:
        raise ScenarioConfigError(
            f"failed to parse scenario file: {scenario_path}"
        ) from error
    try:
        payload = _mapping(raw, name="scenario catalog")
        _strict_keys(
            payload,
            expected=frozenset({"catalog_version", "scenarios"}),
            required=frozenset({"catalog_version", "scenarios"}),
            name="scenario catalog",
        )
        raw_scenarios = payload["scenarios"]
        if not isinstance(raw_scenarios, list):
            raise TypeError("scenarios must be a list")
        catalog = ScenarioCatalog(
            catalog_version=payload["catalog_version"],
            scenarios=tuple(
                _scenario_from_mapping(scenario) for scenario in raw_scenarios
            ),
        )
        return validate_standard_scenario_catalog(catalog)
    except (TypeError, ValueError, KeyError) as error:
        raise ScenarioConfigError(
            f"failed to validate scenario file: {scenario_path}"
        ) from error


def _forecast_dates(values: Sequence[object]) -> pd.DatetimeIndex:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("forecast_dates must be a sequence of dates")
    normalized = pd.DatetimeIndex(
        [_normalize_date(value, name="forecast date") for value in values]
    )
    if normalized.empty or normalized.has_duplicates:
        raise ValueError("forecast_dates must be non-empty and unique")
    normalized = normalized.sort_values()
    expected = pd.date_range(normalized[0], periods=len(normalized), freq="ME")
    if not normalized.equals(expected):
        raise ValueError("forecast_dates must be continuous month-end dates")
    return normalized


def _resolve_start(
    shock: ScenarioShock,
    *,
    forecast_dates: pd.DatetimeIndex,
) -> pd.Timestamp:
    if shock.effective_date is not None:
        start = pd.Timestamp(shock.effective_date)
    else:
        match = _DATE_RULE.fullmatch(str(shock.effective_date_rule))
        if match is None:
            raise ValueError("effective_date_rule cannot be resolved")
        month_number = int(match.group(1))
        if month_number > len(forecast_dates):
            raise ValueError("scenario effective month is outside forecast horizon")
        start = forecast_dates[month_number - 1]
    if start not in forecast_dates:
        raise ValueError("scenario effective date is outside forecast horizon")
    return pd.Timestamp(start)


def _resolve_end(
    shock: ScenarioShock,
    *,
    start: pd.Timestamp,
    forecast_dates: pd.DatetimeIndex,
) -> pd.Timestamp:
    positions = {
        pd.Timestamp(value): position for position, value in enumerate(forecast_dates)
    }
    start_position = positions[start]
    duration_end: pd.Timestamp | None = None
    if shock.duration_months is not None:
        end_position = start_position + shock.duration_months - 1
        if end_position >= len(forecast_dates):
            raise ValueError("scenario shock duration extends beyond forecast horizon")
        duration_end = forecast_dates[end_position]
    explicit_end = None if shock.end_date is None else pd.Timestamp(shock.end_date)
    if explicit_end is not None:
        if explicit_end not in forecast_dates or explicit_end < start:
            raise ValueError(
                "scenario end date is outside or precedes forecast horizon"
            )
        if duration_end is not None and explicit_end != duration_end:
            raise ValueError("scenario end date conflicts with duration_months")
    end = explicit_end if explicit_end is not None else duration_end
    if end is None:
        raise ValueError("scenario shock end cannot be resolved")
    return pd.Timestamp(end)


def resolve_scenario_shocks(
    catalog: ScenarioCatalog,
    *,
    scenario_id: str,
    forecast_dates: Sequence[object],
    channel_ids: Sequence[str],
) -> pd.DataFrame:
    """Resolve one scenario to a complete zero-filled channel/date shock surface."""

    if not isinstance(catalog, ScenarioCatalog):
        raise TypeError("catalog must be a ScenarioCatalog")
    validate_standard_scenario_catalog(catalog)
    scenario = catalog.get(scenario_id)
    dates = _forecast_dates(forecast_dates)
    if isinstance(channel_ids, (str, bytes, bytearray)):
        raise TypeError("channel_ids must be a sequence of strings")
    channels = tuple(sorted(_text(value, name="channel_id") for value in channel_ids))
    if not channels or len(channels) != len(set(channels)):
        raise ValueError("channel_ids must be non-empty and unique")
    channel_set = set(channels)
    rows: dict[tuple[str, pd.Timestamp], dict[str, object]] = {}
    for channel_id in channels:
        for forecast_date in dates:
            rows[(channel_id, pd.Timestamp(forecast_date))] = {
                "scenario_id": scenario.scenario_id,
                "scenario_version": scenario.version,
                "shock_id": None,
                "shock_version": None,
                "channel_id": channel_id,
                "date": pd.Timestamp(forecast_date),
                "effective_date": pd.NaT,
                "end_date": pd.NaT,
                "scenario_shock": 0.0,
                "unit": "channel_innovation",
                "direction": "flat",
                "path": "step",
            }
    occupied: set[tuple[str, pd.Timestamp]] = set()
    for shock in scenario.shocks:
        if shock.channel_id not in channel_set:
            raise ValueError(
                f"scenario shock channel is not covered by the channel forecast: "
                f"{shock.channel_id}"
            )
        if shock.unit != "channel_innovation":
            raise ValueError("scenario shock unit must be channel_innovation")
        if scenario.scenario_id == "baseline" and shock.value != 0.0:
            raise ValueError("baseline scenario shocks must be strictly zero")
        start = _resolve_start(shock, forecast_dates=dates)
        end = _resolve_end(shock, start=start, forecast_dates=dates)
        active_dates = dates[(dates >= start) & (dates <= end)]
        if shock.path == "pulse" and len(active_dates) != 1:
            raise ValueError("pulse shocks must resolve to exactly one forecast date")
        if shock.path == "linear":
            values = np.linspace(
                shock.value / len(active_dates),
                shock.value,
                len(active_dates),
                dtype="float64",
            )
        elif shock.path == "pulse":
            values = np.asarray([shock.value], dtype="float64")
        else:
            values = np.full(len(active_dates), shock.value, dtype="float64")
        for forecast_date, value in zip(active_dates, values, strict=True):
            key = (shock.channel_id, pd.Timestamp(forecast_date))
            if key in occupied:
                raise ValueError("scenario contains duplicate or overlapping shocks")
            occupied.add(key)
            rows[key] = {
                "scenario_id": scenario.scenario_id,
                "scenario_version": scenario.version,
                "shock_id": shock.shock_id,
                "shock_version": shock.version,
                "channel_id": shock.channel_id,
                "date": pd.Timestamp(forecast_date),
                "effective_date": start,
                "end_date": end,
                "scenario_shock": float(value),
                "unit": shock.unit,
                "direction": shock.direction,
                "path": shock.path,
            }
    frame = pd.DataFrame(rows.values(), columns=SCENARIO_SHOCK_COLUMNS)
    frame = frame.sort_values(["channel_id", "date"], kind="stable").reset_index(
        drop=True
    )
    if scenario.scenario_id == "baseline" and not frame["scenario_shock"].eq(0.0).all():
        raise ValueError("baseline scenario shock surface must be strictly zero")
    return frame


load_scenarios = load_scenario_catalog


__all__ = [
    "SCENARIO_SHOCK_COLUMNS",
    "STANDARD_SCENARIO_IDS",
    "ScenarioCatalog",
    "ScenarioConfigError",
    "ScenarioDefinition",
    "ScenarioShock",
    "load_scenario_catalog",
    "load_scenarios",
    "resolve_scenario_shocks",
    "validate_standard_scenario_catalog",
]
