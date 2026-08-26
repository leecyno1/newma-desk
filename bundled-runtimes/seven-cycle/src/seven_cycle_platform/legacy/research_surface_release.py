"""Publish real cycle states and evidence-gated asset surfaces together."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from seven_cycle_platform.assets.sources import LEGACY_CORE_ASSET_MAP
from seven_cycle_platform.products.cycle_phase import (
    build_and_write_cycle_phase_vintage,
)
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import (
    RunManifest,
    load_manifest,
    sha256_file,
)
from seven_cycle_platform.storage.run_context import canonical_json_bytes
from seven_cycle_platform.surfaces.materialize import (
    SurfaceRequest,
    build_and_write_cycle_asset_surfaces,
)
from seven_cycle_platform.surfaces.history import (
    select_current_cycle_snapshot,
    select_preferred_cycle_vintage,
)
from seven_cycle_platform.surfaces.response import ESTIMATOR_VERSION


DEFAULT_ASSET_LABELS = {
    "cn_equity_hs300": "沪深300",
    "cn_equity_csi500": "中证500",
    "cn_equity_csi1000": "中证1000",
    "cn_bond_government_index": "中国国债",
    "us_equity_sp500": "标普500",
}
_STATE_COLUMNS = (
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    "angle",
    "phase",
    "level",
    "slope",
    "amplitude",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
)


@dataclass(frozen=True, slots=True)
class ResearchSurfaceReleaseResult:
    manifest: RunManifest
    run_dir: Path
    surface_count: int


def _horizons(values: tuple[int, ...]) -> tuple[int, ...]:
    if not values or any(isinstance(value, bool) or value < 1 for value in values):
        raise ValueError("horizons must contain positive integers")
    normalized = tuple(sorted(set(values)))
    if normalized != values:
        raise ValueError("horizons must be unique and sorted")
    return normalized


def _windows(value: int | tuple[int, ...]) -> tuple[int, ...]:
    values = (value,) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(values, tuple) or not values:
        raise ValueError("window_months must be an integer or non-empty tuple")
    if any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or not 36 <= item <= 120
        for item in values
    ):
        raise ValueError("window_months must contain integers between 36 and 120")
    normalized = tuple(sorted(set(values)))
    if normalized != values:
        raise ValueError("window_months must be unique and sorted")
    return normalized


def build_forward_return_history(
    panel: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = (3, 6, 12),
) -> pd.DataFrame:
    """Build date-aligned forward compounded returns for governed legacy assets."""

    normalized_horizons = _horizons(horizons)
    if not isinstance(panel, pd.DataFrame) or panel.empty:
        raise ValueError("panel must be a non-empty DataFrame")
    if not isinstance(panel.index, pd.DatetimeIndex):
        raise TypeError("panel must use a DatetimeIndex")
    records: list[pd.DataFrame] = []
    for column, mapping in LEGACY_CORE_ASSET_MAP.items():
        if column not in panel.columns:
            continue
        monthly = pd.to_numeric(panel[column], errors="coerce").astype(float)
        for horizon in normalized_horizons:
            forward = (
                monthly.add(1.0)
                .rolling(horizon)
                .apply(np.prod, raw=True)
                .shift(-(horizon - 1))
                .sub(1.0)
                .dropna()
            )
            if forward.empty:
                continue
            frame = forward.rename("observed_return").reset_index()
            frame.columns = ["period_end", "observed_return"]
            frame.insert(0, "asset_id", mapping.asset_id)
            frame["period_end"] = pd.to_datetime(frame["period_end"]).dt.date
            frame["horizon_months"] = horizon
            frame["return_basis"] = "absolute"
            frame["component_type"] = "observed"
            frame["component_id"] = "forward_total_return"
            records.append(frame)
    if not records:
        raise ValueError("panel contains no governed asset return history")
    return (
        pd.concat(records, ignore_index=True)
        .sort_values(
            ["asset_id", "horizon_months", "period_end"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )


def build_surface_requests(
    *,
    asset_labels: dict[str, str],
    horizons: tuple[int, ...] = (3, 6, 12),
    window_months: int | tuple[int, ...] = 60,
    grid_size: int = 27,
) -> tuple[SurfaceRequest, ...]:
    normalized_horizons = _horizons(horizons)
    normalized_windows = _windows(window_months)
    pairs = tuple(combinations(("C1", "C2", "C3", "C4", "C5", "C6", "C7"), 2))
    return tuple(
        SurfaceRequest(
            asset_id=asset_id,
            asset_label=asset_labels[asset_id],
            cycle_x=cycle_x,
            cycle_y=cycle_y,
            horizon_months=horizon,
            scenario_id="baseline",
            window_months=window,
            grid_size=grid_size,
        )
        for asset_id in sorted(asset_labels)
        for horizon in normalized_horizons
        for window in normalized_windows
        for cycle_x, cycle_y in pairs
    )


def _copy_source_audit(source_run: Path, staging_dir: Path) -> None:
    for relative in (
        "cycle_model_versions.json",
        "quality_findings.parquet",
        "verification_plan.json",
    ):
        source = source_run / relative
        if source.exists():
            shutil.copy2(source, staging_dir / relative)
    registries = source_run / "registries"
    if registries.exists():
        shutil.copytree(registries, staging_dir / "registries")


def publish_research_surface_release(
    *,
    source_cycle_run: Path,
    returns_path: Path,
    product_root: Path,
    horizons: tuple[int, ...] = (3, 6, 12),
    window_months: int | tuple[int, ...] = 60,
    grid_size: int = 27,
) -> ResearchSurfaceReleaseResult:
    """Publish an immutable retrospective release without fabricating forecasts."""

    source_run = Path(source_cycle_run).resolve(strict=True)
    source_manifest = load_manifest(source_run)
    cycle_source_path = source_run / "cycle_phase_vintage.parquet"
    returns_source_path = Path(returns_path).resolve(strict=True)
    cycle_source = pd.read_parquet(cycle_source_path)
    missing_state = set(_STATE_COLUMNS).difference(cycle_source.columns)
    if missing_state:
        raise ValueError(f"source cycle product is missing columns: {sorted(missing_state)}")
    states = cycle_source.loc[:, _STATE_COLUMNS].copy()
    return_panel = pd.read_parquet(returns_source_path)
    return_history = build_forward_return_history(return_panel, horizons=horizons)
    available_asset_ids = tuple(sorted(return_history["asset_id"].unique()))
    asset_labels = {
        asset_id: DEFAULT_ASSET_LABELS[asset_id]
        for asset_id in available_asset_ids
        if asset_id in DEFAULT_ASSET_LABELS
    }
    requests = build_surface_requests(
        asset_labels=asset_labels,
        horizons=horizons,
        window_months=window_months,
        grid_size=grid_size,
    )
    config = {
        "asset_ids": list(asset_labels),
        "grid_size": grid_size,
        "horizons": list(horizons),
        "source_cycle_run": source_manifest.run_id,
        "surface_estimator": ESTIMATOR_VERSION,
        "window_months": list(_windows(window_months)),
    }
    context = RunContext.create(
        as_of=source_manifest.as_of,
        data_vintage=source_manifest.data_vintage,
        model_version=f"{source_manifest.model_version}+surface-v2",
        config=config,
        input_checksums={
            "cycle_phase_vintage.parquet": sha256_file(cycle_source_path),
            "monthly_returns_20y.parquet": sha256_file(returns_source_path),
            "source_manifest.json": sha256_file(source_run / "manifest.json"),
        },
        quality_summary={
            "asset_count": len(asset_labels),
            "forecast_status": "not_published",
            "surface_request_count": len(requests),
            "vintage_status": "retrospective_only",
        },
        created_at=datetime.now(timezone.utc),
    )
    cycles_for_surface = select_preferred_cycle_vintage(
        states.loc[:, ["date", "cycle_id", "angle", "vintage"]]
    )
    current_cycles = select_current_cycle_snapshot(cycles_for_surface).loc[
        :, ["cycle_id", "angle"]
    ]
    empty_forecasts = pd.DataFrame(
        columns=["cycle_id", "horizon_months", "status", "angle_q50"]
    )
    empty_current_mapping = pd.DataFrame(
        columns=["asset_id", "horizon_months", "absolute_expected_return"]
    )
    empty_future_mapping = pd.DataFrame(
        columns=[
            "asset_id",
            "horizon_months",
            "scenario_id",
            "status",
            "absolute_expected_return",
        ]
    )

    def write_staging(staging_dir: Path) -> None:
        build_and_write_cycle_phase_vintage(staging_dir, states, context=context)
        build_and_write_cycle_asset_surfaces(
            staging_dir,
            cycles=cycles_for_surface,
            returns=return_history,
            current_cycles=current_cycles,
            forecasts=empty_forecasts,
            current_mapping=empty_current_mapping,
            future_mapping=empty_future_mapping,
            requests=requests,
            context=context,
        )
        _copy_source_audit(source_run, staging_dir)
        (staging_dir / "source_cycle_run.json").write_bytes(
            canonical_json_bytes(
                {
                    "run_id": source_manifest.run_id,
                    "manifest_checksum": sha256_file(source_run / "manifest.json"),
                }
            )
            + b"\n"
        )

    manifest = publish_run(Path(product_root), context, write_staging=write_staging)
    run_dir = Path(product_root) / "runs" / manifest.run_id
    surface_count = len(pd.read_parquet(run_dir / "cycle_asset_surface.parquet"))
    return ResearchSurfaceReleaseResult(
        manifest=manifest,
        run_dir=run_dir,
        surface_count=surface_count,
    )


__all__ = [
    "DEFAULT_ASSET_LABELS",
    "ResearchSurfaceReleaseResult",
    "build_forward_return_history",
    "build_surface_requests",
    "publish_research_surface_release",
]
