"""Build a retrospective C1-C7 input bundle from legacy research panels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from seven_cycle_platform.cycles.model_version import (
    CycleModelVersion,
    RecalibrationReason,
    RecalibrationStatus,
)
from seven_cycle_platform.data.observations import Observation
from seven_cycle_platform.pipeline.cycles import CyclePipelineInput
from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.types import VintageKind


_MONTHLY_CATEGORY_MAP = {
    "利率与债券类（Rates & Bonds）": "rates",
    "宏观增长类（Macro Growth）": "growth",
    "汇率与外部部门（FX & External）": "external",
    "股票市场与估值（Equity Market & Valuation）": "market",
    "货币与信用类（Money & Credit）": "credit",
    "通胀与价格类（Inflation & Prices）": "prices",
}


@dataclass(frozen=True, slots=True)
class ResearchCycleInputRequest:
    annual_panel_path: Path
    annual_selection_path: Path
    monthly_panel_path: Path
    monthly_selection_path: Path
    as_of: date
    state_start: date
    state_end: date
    verification_cutoffs: tuple[date, ...]
    config_dir: Path = Path("config/seven_cycle")
    max_members_per_category: int = 5
    minimum_coverage_pct: float = 0.0
    annual_release_lag_days: int = 90
    monthly_release_lag_days: int = 15

    def __post_init__(self) -> None:
        if self.state_start > self.state_end:
            raise ValueError("state_start cannot follow state_end")
        if self.state_end > self.as_of:
            raise ValueError("state_end cannot follow as_of")
        if not self.verification_cutoffs:
            raise ValueError("verification_cutoffs must not be empty")
        if tuple(sorted(set(self.verification_cutoffs))) != self.verification_cutoffs:
            raise ValueError("verification_cutoffs must be unique and sorted")
        if self.verification_cutoffs[-1] > self.as_of:
            raise ValueError("verification_cutoffs cannot follow as_of")
        if self.max_members_per_category < 1:
            raise ValueError("max_members_per_category must be positive")
        if not 0.0 <= float(self.minimum_coverage_pct) <= 100.0:
            raise ValueError("minimum_coverage_pct must be between 0 and 100")


def _annual_category(column: str) -> str:
    normalized = column.lower()
    rules = (
        (("rate", "yield"), "rates"),
        (("debt", "bank", "lending", "borrow", "balance_sheet", "m1", "money", "credit"), "credit"),
        (("cpi", "price", "deflator", "wage", "earning", "oil"), "prices"),
        (("exchange", "export", "import", "trade", "current_account", "terms_of_trade"), "external"),
        (("share", "house_price"), "market"),
        (("government", "public", "receipts", "expenditure", "tax"), "fiscal"),
    )
    for keywords, category in rules:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "growth"


def _month_end_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("monthly research panel must use a DatetimeIndex")
    normalized = frame.copy(deep=True)
    normalized.index = normalized.index.to_period("M").to_timestamp("M")
    normalized = normalized.groupby(level=0, sort=True).last()
    normalized.index.name = frame.index.name
    return normalized


def _selected_members(
    selection: pd.DataFrame,
    *,
    column_field: str,
    category_field: str,
    available_columns: pd.Index,
    max_members_per_category: int,
    minimum_coverage_pct: float,
) -> pd.DataFrame:
    required = {column_field, "coverage_pct", "status", category_field}
    missing = required.difference(selection.columns)
    if missing:
        raise ValueError(f"selection metadata is missing columns: {sorted(missing)}")
    chosen = selection.loc[
        selection["status"].eq("selected")
        & pd.to_numeric(selection["coverage_pct"], errors="coerce").ge(
            minimum_coverage_pct
        )
        & selection[column_field].isin(available_columns)
        & selection[category_field].notna()
    ].copy()
    if chosen.empty:
        raise ValueError("selection metadata has no eligible research members")
    chosen["coverage_pct"] = pd.to_numeric(chosen["coverage_pct"])
    return (
        chosen.sort_values(
            [category_field, "coverage_pct", column_field],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .groupby(category_field, sort=True, group_keys=False)
        .head(max_members_per_category)
        .reset_index(drop=True)
    )


def _observations(
    frame: pd.DataFrame,
    *,
    categories: dict[str, str],
    metadata: pd.DataFrame,
    column_field: str,
    source_field: str,
    release_lag_days: int,
    annual: bool,
    retrieval_time: datetime,
) -> list[Observation]:
    metadata_by_column = metadata.set_index(column_field)
    records: list[Observation] = []
    for entity_id in sorted(categories):
        series = pd.to_numeric(frame[entity_id], errors="coerce").dropna()
        source = str(metadata_by_column.loc[entity_id, source_field])
        unit = str(metadata_by_column.loc[entity_id, "value_type"])
        for index_value, value in series.items():
            observation_date = (
                date(int(index_value), 12, 31)
                if annual
                else pd.Timestamp(index_value).date()
            )
            release_date = observation_date + timedelta(days=release_lag_days)
            records.append(
                Observation(
                    entity_id=entity_id,
                    observation_date=observation_date,
                    release_date=release_date,
                    vintage_date=release_date,
                    value=float(value),
                    unit=unit,
                    source=source,
                    retrieval_time=retrieval_time,
                    revision_number=0,
                    quality_status="retrospective_research_input",
                    vintage_kind=VintageKind.PSEUDO_VINTAGE,
                )
            )
    return records


def _quarter_end_on_or_before(value: date) -> date:
    candidates = (
        date(value.year, 3, 31),
        date(value.year, 6, 30),
        date(value.year, 9, 30),
        date(value.year, 12, 31),
    )
    return max(candidate for candidate in candidates if candidate <= value)


def _prior_versions(request: ResearchCycleInputRequest) -> tuple[CycleModelVersion, ...]:
    effective_date = _quarter_end_on_or_before(request.as_of)
    bundle = load_registry_bundle(request.config_dir)
    versions: list[CycleModelVersion] = []
    for cycle in bundle.cycles:
        center = float(
            cycle.initial_center
            if cycle.initial_center is not None
            else (cycle.search_min + cycle.search_max) / 2.0
        )
        versions.append(
            CycleModelVersion(
                cycle_id=cycle.cycle_id,
                effective_date=effective_date,
                old_center=center,
                new_center=center,
                old_band=(float(cycle.search_min), float(cycle.search_max)),
                new_band=(float(cycle.search_min), float(cycle.search_max)),
                old_confidence=0.60,
                new_confidence=0.60,
                candidate_center=center,
                status=RecalibrationStatus.ACCEPTED,
                reason_code=RecalibrationReason.ACCEPTED,
                rejection_reason=None,
                reason_codes=(RecalibrationReason.ACCEPTED,),
                evidence_metrics={"retrospective_research_bridge": 1},
            )
        )
    return tuple(versions)


def build_research_cycle_pipeline_input(
    request: ResearchCycleInputRequest,
) -> CyclePipelineInput:
    """Convert real legacy panels into an explicitly pseudo-vintage M2 input."""

    if not isinstance(request, ResearchCycleInputRequest):
        raise TypeError("request must be a ResearchCycleInputRequest")
    annual = pd.read_parquet(request.annual_panel_path)
    monthly = _month_end_frame(pd.read_parquet(request.monthly_panel_path))
    annual_selection = pd.read_csv(request.annual_selection_path)
    monthly_selection = pd.read_csv(request.monthly_selection_path)
    annual_selection = annual_selection.copy()
    annual_selection["research_category"] = annual_selection["column"].map(
        _annual_category
    )
    monthly_selection = monthly_selection.copy()
    monthly_selection["research_category"] = monthly_selection[
        "universe_category"
    ].map(_MONTHLY_CATEGORY_MAP)
    annual_members = _selected_members(
        annual_selection,
        column_field="column",
        category_field="research_category",
        available_columns=annual.columns,
        max_members_per_category=request.max_members_per_category,
        minimum_coverage_pct=request.minimum_coverage_pct,
    )
    monthly_members = _selected_members(
        monthly_selection,
        column_field="panel_main_column",
        category_field="research_category",
        available_columns=monthly.columns,
        max_members_per_category=request.max_members_per_category,
        minimum_coverage_pct=request.minimum_coverage_pct,
    )
    annual_categories = dict(
        sorted(
            zip(
                annual_members["column"],
                annual_members["research_category"],
                strict=True,
            )
        )
    )
    monthly_categories = dict(
        sorted(
            zip(
                monthly_members["panel_main_column"],
                monthly_members["research_category"],
                strict=True,
            )
        )
    )
    retrieval_time = datetime.combine(
        request.as_of + timedelta(days=366),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    observations = _observations(
        annual,
        categories=annual_categories,
        metadata=annual_members,
        column_field="column",
        source_field="source",
        release_lag_days=request.annual_release_lag_days,
        annual=True,
        retrieval_time=retrieval_time,
    )
    observations.extend(
        _observations(
            monthly,
            categories=monthly_categories,
            metadata=monthly_members,
            column_field="panel_main_column",
            source_field="primary_source",
            release_lag_days=request.monthly_release_lag_days,
            annual=False,
            retrieval_time=retrieval_time,
        )
    )
    state_dates = tuple(
        timestamp.date()
        for timestamp in pd.date_range(
            request.state_start,
            request.state_end,
            freq="ME",
        )
    )
    if not state_dates:
        raise ValueError("requested state range contains no month ends")
    return CyclePipelineInput(
        observations=tuple(observations),
        annual_categories=annual_categories,
        monthly_categories=monthly_categories,
        prior_model_versions=_prior_versions(request),
        discovery_evidence=(),
        state_dates=state_dates,
        verification_cutoffs=request.verification_cutoffs,
    )


__all__ = [
    "ResearchCycleInputRequest",
    "build_research_cycle_pipeline_input",
]
