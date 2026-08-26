"""2019 Baijiu attribution report from verified published products only."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from numbers import Integral, Real
import os
from pathlib import Path
import secrets
import stat
from typing import Mapping

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ASSET_ATTRIBUTION_SCHEMA,
)
from seven_cycle_platform.products.asset_attribution import (
    ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
    ASSET_ATTRIBUTION_FILENAME,
    validate_asset_attribution,
)
from seven_cycle_platform.storage.manifest import (
    MANIFEST_FILENAME,
    RunManifest,
)
from seven_cycle_platform.storage.run_context import (
    RUN_ID_PATTERN,
    canonical_json_bytes,
)


REPORT_ID = "baijiu_2019"
BAIJIU_2019_MARKDOWN_FILENAME = f"{REPORT_ID}.md"
BAIJIU_2019_JSON_FILENAME = f"{REPORT_ID}.json"

REALTIME = "realtime"
LATEST_HISTORICAL = "latest_historical"
INTERPRETATIONS = (REALTIME, LATEST_HISTORICAL)

PERIOD_START = pd.Timestamp("2019-01-31")
PERIOD_END = pd.Timestamp("2019-12-31")
HORIZON_MONTHS = 12

PRIMARY_ASSET_ID = "cn_equity_baijiu"
PRIMARY_SYMBOL = "399997.SZ"
PROXY_ASSET_ID = "cn_equity_baijiu_citic_food_beverage"
PROXY_SYMBOL = "CI005019.CI"
BENCHMARK_ASSET_ID = "cn_equity_hs300"
BENCHMARK_SYMBOL = "000300.SH"

REQUIRED_CYCLE_IDS = tuple(f"C{cycle}" for cycle in range(1, 8))
REQUIRED_CHANNEL_IDS = (
    "growth_demand",
    "real_rate_discount",
    "liquidity_credit",
    "earnings_margin",
    "risk_premium_crowding",
)
REQUIRED_CONTROL_IDS = ("foreign_flow_funding", "valuation_repricing")
REQUIRED_EVENT_IDS = ("industry_event",)
REQUIRED_RETURN_BASES = ("absolute", "excess")
_CHANNEL_COMPONENT_TYPES = frozenset(
    {
        "channel_baseline_path",
        "channel_residual_path",
        "unresolved_channel",
    }
)


@dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class Baijiu2019ReportResult:
    """Paths and provenance for one generated or reused report pair."""

    requested_run_id: str
    markdown_path: Path
    json_path: Path
    interpretation_runs: tuple[tuple[str, str], ...]
    reused: bool

    @property
    def source_runs(self) -> dict[str, str]:
        return dict(self.interpretation_runs)


@dataclass(frozen=True)
class _VerifiedView:
    interpretation: str
    run_dir: Path
    manifest: RunManifest
    metadata: dict[str, object]
    attribution: pd.DataFrame
    conservation: pd.DataFrame


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError(f"{name} keys must be non-empty strings")
    return {str(key): nested for key, nested in value.items()}


def _nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _run_id(value: object, name: str) -> str:
    normalized = _nonblank(value, name)
    if not RUN_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{name} does not match the RunContext contract")
    return normalized


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Integral, np.integer)
    ):
        raise ValueError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _directory_identity(path: Path, *, label: str) -> _DirectoryIdentity:
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} must be a real directory") from error
    if stat.S_ISLNK(path_stat.st_mode):
        raise ValueError(f"{label} cannot be a symlink")
    if not stat.S_ISDIR(path_stat.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return _DirectoryIdentity(path_stat.st_dev, path_stat.st_ino)


def _fd_identity(descriptor: int, *, label: str) -> _DirectoryIdentity:
    descriptor_stat = os.fstat(descriptor)
    if not stat.S_ISDIR(descriptor_stat.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return _DirectoryIdentity(descriptor_stat.st_dev, descriptor_stat.st_ino)


def _open_directory_fd(
    path: Path,
    *,
    label: str,
    expected: _DirectoryIdentity | None = None,
) -> tuple[int, _DirectoryIdentity]:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"{label} must be a real non-symlink directory") from error
    try:
        identity = _fd_identity(descriptor, label=label)
        if expected is not None and identity != expected:
            raise ValueError(f"{label} changed before it could be opened")
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _open_child_directory_fd(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[int, _DirectoryIdentity]:
    if not name or "/" in name:
        raise ValueError(f"{label} name must be one path component")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise ValueError(f"{label} must be a real non-symlink directory") from error
    try:
        return descriptor, _fd_identity(descriptor, label=label)
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_bytes_at(
    directory_descriptor: int,
    name: str,
    *,
    label: str,
) -> bytes:
    if not name or "/" in name:
        raise ValueError(f"{label} name must be one path component")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise ValueError(f"{label} is missing, invalid, or a symlink") from error
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError(f"{label} must be a regular file")
        return source.read()


def _hash_regular_file_at(
    directory_descriptor: int,
    name: str,
    *,
    label: str,
) -> str:
    if not name or "/" in name:
        raise ValueError(f"{label} name must be one path component")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as error:
        raise ValueError(f"{label} is missing, invalid, or a symlink") from error
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError(f"{label} must be a regular file")
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_metadata(manifest: RunManifest) -> dict[str, object]:
    payload = manifest.model_dump(mode="json")
    quality_summary = _mapping(payload.get("quality_summary"), "quality_summary")
    metadata = _mapping(
        quality_summary.get(REPORT_ID),
        f"quality_summary.{REPORT_ID}",
    )
    interpretation = _nonblank(
        metadata.get("interpretation"),
        f"{REPORT_ID}.interpretation",
    )
    vintage_kind = _nonblank(
        metadata.get("vintage_kind"),
        f"{REPORT_ID}.vintage_kind",
    )
    if interpretation not in INTERPRETATIONS:
        raise ValueError(f"unknown {REPORT_ID} interpretation: {interpretation}")
    if vintage_kind != interpretation:
        raise ValueError(
            f"{REPORT_ID} vintage_kind must match interpretation {interpretation}"
        )

    raw_runs = _mapping(
        metadata.get("interpretation_runs"),
        f"{REPORT_ID}.interpretation_runs",
    )
    missing_interpretations = [
        value for value in INTERPRETATIONS if value not in raw_runs
    ]
    if missing_interpretations:
        raise ValueError(
            f"{REPORT_ID} interpretation_runs is missing "
            + ", ".join(missing_interpretations)
        )
    unexpected_interpretations = sorted(set(raw_runs).difference(INTERPRETATIONS))
    if unexpected_interpretations:
        raise ValueError(
            f"{REPORT_ID} interpretation_runs contains unsupported views: "
            + ", ".join(unexpected_interpretations)
        )
    interpretation_runs = {
        value: _run_id(
            raw_runs[value],
            f"{REPORT_ID}.interpretation_runs.{value}",
        )
        for value in INTERPRETATIONS
    }
    if len(set(interpretation_runs.values())) != len(INTERPRETATIONS):
        raise ValueError("realtime and latest_historical must use distinct runs")
    if interpretation_runs[interpretation] != manifest.run_id:
        raise ValueError(
            f"{REPORT_ID} interpretation mapping does not identify its own run"
        )

    period = _mapping(metadata.get("period"), f"{REPORT_ID}.period")
    expected_period = {
        "period_start": PERIOD_START.date().isoformat(),
        "period_end": PERIOD_END.date().isoformat(),
        "horizon_months": HORIZON_MONTHS,
    }
    actual_period = {
        "period_start": _nonblank(
            period.get("period_start"), f"{REPORT_ID}.period.period_start"
        ),
        "period_end": _nonblank(
            period.get("period_end"), f"{REPORT_ID}.period.period_end"
        ),
        "horizon_months": _positive_integer(
            period.get("horizon_months"),
            f"{REPORT_ID}.period.horizon_months",
        ),
    }
    if actual_period != expected_period:
        raise ValueError(f"{REPORT_ID} period must be calendar-year 2019")

    benchmark = _mapping(metadata.get("benchmark"), f"{REPORT_ID}.benchmark")
    actual_benchmark = {
        "asset_id": _nonblank(
            benchmark.get("asset_id"), f"{REPORT_ID}.benchmark.asset_id"
        ),
        "symbol": _nonblank(benchmark.get("symbol"), f"{REPORT_ID}.benchmark.symbol"),
    }
    expected_benchmark = {
        "asset_id": BENCHMARK_ASSET_ID,
        "symbol": BENCHMARK_SYMBOL,
    }
    if actual_benchmark != expected_benchmark:
        raise ValueError(f"{REPORT_ID} benchmark must be HS300 / 000300.SH")

    raw_assets = _mapping(metadata.get("assets"), f"{REPORT_ID}.assets")
    assets: dict[str, dict[str, object]] = {}
    for asset_id in (PRIMARY_ASSET_ID, PROXY_ASSET_ID):
        if asset_id not in raw_assets:
            role = "primary" if asset_id == PRIMARY_ASSET_ID else "proxy"
            raise ValueError(
                f"{REPORT_ID} {role} asset metadata is missing: {asset_id}"
            )
        asset = _mapping(raw_assets[asset_id], f"{REPORT_ID}.assets.{asset_id}")
        assets[asset_id] = {
            "symbol": _nonblank(
                asset.get("symbol"), f"{REPORT_ID}.assets.{asset_id}.symbol"
            ),
            "proxy_status": _nonblank(
                asset.get("proxy_status"),
                f"{REPORT_ID}.assets.{asset_id}.proxy_status",
            ),
            "proxy_for": asset.get("proxy_for"),
            "history_status": _nonblank(
                asset.get("history_status"),
                f"{REPORT_ID}.assets.{asset_id}.history_status",
            ),
            "shrinkage_status": _nonblank(
                asset.get("shrinkage_status"),
                f"{REPORT_ID}.assets.{asset_id}.shrinkage_status",
            ),
            "confidence": _nonblank(
                asset.get("confidence"),
                f"{REPORT_ID}.assets.{asset_id}.confidence",
            ),
        }
    expected_asset_identity = {
        PRIMARY_ASSET_ID: (PRIMARY_SYMBOL, "primary", None),
        PROXY_ASSET_ID: (PROXY_SYMBOL, "proxy", PRIMARY_ASSET_ID),
    }
    for asset_id, expected in expected_asset_identity.items():
        asset = assets[asset_id]
        actual = (asset["symbol"], asset["proxy_status"], asset["proxy_for"])
        if actual != expected:
            raise ValueError(
                f"{REPORT_ID} asset proxy identity is invalid for {asset_id}"
            )
    primary = assets[PRIMARY_ASSET_ID]
    if (
        primary["history_status"] != "short_history"
        or primary["shrinkage_status"] != "strong"
        or primary["confidence"] != "low"
    ):
        raise ValueError(
            f"{REPORT_ID} primary must disclose short history, strong shrinkage, "
            "and low confidence"
        )

    raw_reasons = _mapping(
        metadata.get("unavailable_reasons"),
        f"{REPORT_ID}.unavailable_reasons",
    )
    unavailable_reasons = {
        key: _nonblank(
            reason,
            f"{REPORT_ID}.unavailable_reasons.{key}",
        )
        for key, reason in raw_reasons.items()
    }
    return {
        "interpretation": interpretation,
        "vintage_kind": vintage_kind,
        "interpretation_runs": interpretation_runs,
        "period": actual_period,
        "benchmark": actual_benchmark,
        "assets": assets,
        "unavailable_reasons": unavailable_reasons,
    }


def _read_verified_parquet_at(
    run_descriptor: int,
    filename: str,
    *,
    expected_checksum: str,
    expected_schema: object,
    label: str,
) -> pd.DataFrame:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(filename, flags, dir_fd=run_descriptor)
    except OSError as error:
        raise ValueError(f"{label} is missing, invalid, or a symlink") from error
    descriptor_open = True
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ValueError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor_open = False
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != expected_checksum:
                raise ValueError(
                    f"{label} checksum does not match the verified manifest"
                )
            source.seek(0)
            table = pq.read_table(source)
        if table.schema != expected_schema:
            raise ValueError(f"{label} schema does not match the contract")
        return table.to_pandas()
    finally:
        if descriptor_open:
            os.close(descriptor)


def _collect_product_checksums_at(run_descriptor: int) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for directory_path, directory_names, filenames, directory_descriptor in os.fwalk(
        ".",
        topdown=True,
        follow_symlinks=False,
        dir_fd=run_descriptor,
    ):
        for directory_name in directory_names:
            directory_stat = os.stat(
                directory_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(directory_stat.st_mode):
                raise ValueError("source run cannot contain symlink directories")
            if not stat.S_ISDIR(directory_stat.st_mode):
                raise ValueError("source run contains a non-directory tree entry")
        for filename in filenames:
            relative_path = (Path(directory_path) / filename).as_posix()
            if relative_path.startswith("./"):
                relative_path = relative_path[2:]
            file_stat = os.stat(
                filename,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(file_stat.st_mode):
                raise ValueError(f"source run cannot contain symlink: {relative_path}")
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError(
                    f"source run contains a non-regular file: {relative_path}"
                )
            if relative_path == MANIFEST_FILENAME:
                continue
            checksums[relative_path] = _hash_regular_file_at(
                directory_descriptor,
                filename,
                label=relative_path,
            )
    return dict(sorted(checksums.items()))


def _load_verified_manifest_at(
    runs_descriptor: int,
    run_id: str,
) -> tuple[int, _DirectoryIdentity, RunManifest]:
    normalized_run_id = _run_id(run_id, "run_id")
    run_descriptor, run_identity = _open_child_directory_fd(
        runs_descriptor,
        normalized_run_id,
        label="source run directory",
    )
    try:
        raw_manifest = _read_regular_bytes_at(
            run_descriptor,
            MANIFEST_FILENAME,
            label="manifest",
        )
        manifest = RunManifest.model_validate_json(raw_manifest)
        if manifest.run_id != normalized_run_id:
            raise ValueError("manifest run_id does not match its run directory")
        if raw_manifest != manifest.to_json_bytes():
            raise ValueError("manifest JSON is not canonical")
        actual_checksums = _collect_product_checksums_at(run_descriptor)
        if actual_checksums != dict(manifest.product_checksums):
            raise ValueError(
                "manifest product checksums do not match anchored source files"
            )
        return run_descriptor, run_identity, manifest
    except BaseException:
        os.close(run_descriptor)
        raise


def _read_verified_products_at(
    run_descriptor: int,
    run_identity: _DirectoryIdentity,
    manifest: RunManifest,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if _fd_identity(run_descriptor, label="source run directory") != run_identity:
        raise ValueError("source run directory descriptor identity changed")
    required_files = (
        ASSET_ATTRIBUTION_FILENAME,
        ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
    )
    missing = [
        filename
        for filename in required_files
        if filename not in manifest.product_checksums
    ]
    if missing:
        raise ValueError(
            f"{REPORT_ID} source manifest is missing products: " + ", ".join(missing)
        )
    attribution = _read_verified_parquet_at(
        run_descriptor,
        ASSET_ATTRIBUTION_FILENAME,
        expected_checksum=manifest.product_checksums[ASSET_ATTRIBUTION_FILENAME],
        expected_schema=ASSET_ATTRIBUTION_SCHEMA,
        label=ASSET_ATTRIBUTION_FILENAME,
    )
    conservation = _read_verified_parquet_at(
        run_descriptor,
        ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
        expected_checksum=manifest.product_checksums[
            ASSET_ATTRIBUTION_CONSERVATION_FILENAME
        ],
        expected_schema=ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
        label=ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
    )
    if _fd_identity(run_descriptor, label="source run directory") != run_identity:
        raise ValueError("source run directory descriptor identity changed")
    validate_asset_attribution(attribution, conservation, context=manifest)
    return attribution, conservation


def _period_filter(values: pd.DataFrame) -> pd.Series:
    return (
        pd.to_datetime(values["period_start"]).eq(PERIOD_START)
        & pd.to_datetime(values["period_end"]).eq(PERIOD_END)
        & values["horizon_months"].eq(HORIZON_MONTHS)
    )


def _reason_key(row: Mapping[str, object]) -> str:
    return "|".join(
        (
            str(row["asset_id"]),
            str(row["return_basis"]),
            str(row["component_type"]),
            str(row["component_id"]),
        )
    )


def _require_components(group: pd.DataFrame, *, label: str) -> None:
    keys = set(
        group.loc[:, ["component_type", "component_id"]].itertuples(
            index=False,
            name=None,
        )
    )
    missing_cycles = [
        cycle_id for cycle_id in REQUIRED_CYCLE_IDS if ("cycle", cycle_id) not in keys
    ]
    if missing_cycles:
        raise ValueError(f"{label} is missing C1-C7 rows: {', '.join(missing_cycles)}")
    missing_channels = [
        channel_id
        for channel_id in REQUIRED_CHANNEL_IDS
        if not any(
            component_type in _CHANNEL_COMPONENT_TYPES and component_id == channel_id
            for component_type, component_id in keys
        )
    ]
    if missing_channels:
        raise ValueError(
            f"{label} is missing required channel rows: " + ", ".join(missing_channels)
        )
    required_exact = (
        *(("control", component_id) for component_id in REQUIRED_CONTROL_IDS),
        *(("event", component_id) for component_id in REQUIRED_EVENT_IDS),
        ("asset_residual", "asset_residual"),
        ("benchmark", BENCHMARK_ASSET_ID),
    )
    missing_exact = [
        f"{component_type}:{component_id}"
        for component_type, component_id in required_exact
        if (component_type, component_id) not in keys
    ]
    if missing_exact:
        raise ValueError(
            f"{label} is missing required attribution rows: " + ", ".join(missing_exact)
        )


def _validate_case_rows(
    interpretation: str,
    attribution: pd.DataFrame,
    conservation: pd.DataFrame,
    metadata: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected_assets = (PRIMARY_ASSET_ID, PROXY_ASSET_ID)
    attribution = attribution.loc[
        _period_filter(attribution)
        & attribution["asset_id"].isin(expected_assets)
        & attribution["return_basis"].isin(REQUIRED_RETURN_BASES)
    ].copy(deep=True)
    conservation = conservation.loc[
        _period_filter(conservation)
        & conservation["asset_id"].isin(expected_assets)
        & conservation["return_basis"].isin(REQUIRED_RETURN_BASES)
    ].copy(deep=True)

    actual_assets = set(attribution["asset_id"])
    if PRIMARY_ASSET_ID not in actual_assets:
        raise ValueError(
            f"{interpretation} primary {PRIMARY_ASSET_ID} is missing; "
            f"proxy {PROXY_ASSET_ID} cannot replace it"
        )
    if PROXY_ASSET_ID not in actual_assets:
        raise ValueError(
            f"{interpretation} explicit proxy result is missing: {PROXY_ASSET_ID}"
        )

    expected_groups = {
        (asset_id, return_basis)
        for asset_id in expected_assets
        for return_basis in REQUIRED_RETURN_BASES
    }
    attribution_groups = set(
        attribution.loc[:, ["asset_id", "return_basis"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    conservation_groups = set(
        conservation.loc[:, ["asset_id", "return_basis"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if attribution_groups != expected_groups:
        raise ValueError(
            f"{interpretation} attribution must contain primary/proxy absolute/excess"
        )
    if conservation_groups != expected_groups:
        raise ValueError(
            f"{interpretation} conservation must contain primary/proxy absolute/excess"
        )

    unavailable_reasons = _mapping(
        metadata.get("unavailable_reasons"),
        f"{interpretation}.unavailable_reasons",
    )
    for (asset_id, return_basis), group in attribution.groupby(
        ["asset_id", "return_basis"], sort=False
    ):
        label = f"{interpretation} {asset_id} {return_basis}"
        _require_components(group, label=label)
        for row in group.to_dict(orient="records"):
            if row["interval_status"] != "unavailable":
                continue
            key = _reason_key(row)
            reason = unavailable_reasons.get(key)
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(
                    f"unavailable reason is missing for {asset_id} "
                    f"{return_basis} {row['component_id']}"
                )

        benchmark_rows = group.loc[
            group["component_type"].eq("benchmark")
            & group["component_id"].eq(BENCHMARK_ASSET_ID)
        ]
        if len(benchmark_rows) != 1:
            raise ValueError(f"{label} must contain exactly one HS300 benchmark row")

    attribution = attribution.sort_values(
        ["asset_id", "return_basis", "component_type", "component_id"],
        kind="stable",
    ).reset_index(drop=True)
    conservation = conservation.sort_values(
        ["asset_id", "return_basis"], kind="stable"
    ).reset_index(drop=True)
    return attribution, conservation


def _load_view_at(
    runs_descriptor: int,
    runs_root: Path,
    run_id: str,
) -> _VerifiedView:
    run_descriptor, run_identity, manifest = _load_verified_manifest_at(
        runs_descriptor,
        run_id,
    )
    try:
        metadata = _manifest_metadata(manifest)
        interpretation = str(metadata["interpretation"])
        attribution, conservation = _read_verified_products_at(
            run_descriptor,
            run_identity,
            manifest,
        )
        attribution, conservation = _validate_case_rows(
            interpretation,
            attribution,
            conservation,
            metadata,
        )
        return _VerifiedView(
            interpretation=interpretation,
            run_dir=runs_root / manifest.run_id,
            manifest=manifest,
            metadata=metadata,
            attribution=attribution,
            conservation=conservation,
        )
    finally:
        os.close(run_descriptor)


def _load_views(product_root: Path, requested_run_id: str) -> dict[str, _VerifiedView]:
    root = Path(product_root)
    root_identity = _directory_identity(root, label="product root")
    root_descriptor, opened_root_identity = _open_directory_fd(
        root,
        label="product root",
        expected=root_identity,
    )
    runs_descriptor: int | None = None
    try:
        runs_descriptor, runs_identity = _open_child_directory_fd(
            root_descriptor,
            "runs",
            label="runs root",
        )
        runs_root = root / "runs"
        requested_view = _load_view_at(
            runs_descriptor,
            runs_root,
            requested_run_id,
        )
        requested_metadata = requested_view.metadata
        interpretation_runs = _mapping(
            requested_metadata["interpretation_runs"],
            f"{REPORT_ID}.interpretation_runs",
        )
        views = {requested_view.interpretation: requested_view}
        for interpretation in INTERPRETATIONS:
            related_run_id = _run_id(
                interpretation_runs[interpretation],
                f"{REPORT_ID}.interpretation_runs.{interpretation}",
            )
            if related_run_id == requested_view.manifest.run_id:
                view = requested_view
            else:
                view = _load_view_at(
                    runs_descriptor,
                    runs_root,
                    related_run_id,
                )
            if view.interpretation != interpretation:
                raise ValueError(
                    f"related run {related_run_id} does not contain {interpretation}"
                )
            if (
                view.metadata["interpretation_runs"]
                != requested_metadata["interpretation_runs"]
            ):
                raise ValueError(
                    "paired interpretation manifests disagree on run mapping"
                )
            for field_name in ("period", "benchmark", "assets"):
                if view.metadata[field_name] != requested_metadata[field_name]:
                    raise ValueError(
                        f"paired interpretation manifests disagree on {field_name}"
                    )
            views[interpretation] = view
        if _fd_identity(root_descriptor, label="product root") != opened_root_identity:
            raise ValueError("product root descriptor identity changed")
        if _fd_identity(runs_descriptor, label="runs root") != runs_identity:
            raise ValueError("runs root descriptor identity changed")
        runs_entry = os.stat(
            "runs",
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            stat.S_ISLNK(runs_entry.st_mode)
            or _DirectoryIdentity(
                runs_entry.st_dev,
                runs_entry.st_ino,
            )
            != runs_identity
        ):
            raise ValueError("runs root entry changed during report generation")
        if _directory_identity(root, label="product root") != opened_root_identity:
            raise ValueError("product root path changed during report generation")
        return views
    finally:
        if runs_descriptor is not None:
            os.close(runs_descriptor)
        os.close(root_descriptor)


def _date_text(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _timestamp_text(value: object) -> str:
    return pd.Timestamp(value).isoformat()


def _number(value: object) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Real, np.integer, np.floating)
    ):
        raise TypeError("report numeric fields must contain real numbers")
    normalized = float(value)
    if not np.isfinite(normalized):
        raise ValueError("report numeric fields must be finite or missing")
    return normalized


def _integer(value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Integral, np.integer)
    ):
        raise TypeError("report count fields must contain integers")
    return int(value)


def _asset_metadata(view: _VerifiedView, asset_id: str) -> dict[str, object]:
    assets = _mapping(view.metadata["assets"], f"{view.interpretation}.assets")
    return _mapping(assets[asset_id], f"{view.interpretation}.assets.{asset_id}")


def _attribution_payload(view: _VerifiedView) -> list[dict[str, object]]:
    reasons = _mapping(
        view.metadata["unavailable_reasons"],
        f"{view.interpretation}.unavailable_reasons",
    )
    records: list[dict[str, object]] = []
    for row in view.attribution.to_dict(orient="records"):
        asset = _asset_metadata(view, str(row["asset_id"]))
        unavailable_reason = (
            reasons[_reason_key(row)]
            if row["interval_status"] == "unavailable"
            else None
        )
        records.append(
            {
                "interpretation": view.interpretation,
                "asset_id": str(row["asset_id"]),
                "symbol": str(asset["symbol"]),
                "proxy_status": str(asset["proxy_status"]),
                "proxy_for": asset["proxy_for"],
                "period_start": _date_text(row["period_start"]),
                "period_end": _date_text(row["period_end"]),
                "horizon_months": _integer(row["horizon_months"]),
                "return_basis": str(row["return_basis"]),
                "component_type": str(row["component_type"]),
                "component_id": str(row["component_id"]),
                "point_contribution": _number(row["point_contribution"]),
                "lower_50": _number(row["lower_50"]),
                "upper_50": _number(row["upper_50"]),
                "lower_80": _number(row["lower_80"]),
                "upper_80": _number(row["upper_80"]),
                "significance": str(row["significance"]),
                "is_explained": bool(row["is_explained"]),
                "is_residual": bool(row["is_residual"]),
                "observed_return": _number(row["observed_return"]),
                "reconstructed_return": _number(row["reconstructed_return"]),
                "interval_status": str(row["interval_status"]),
                "status": str(row["status"]),
                "evidence_level": str(row["evidence_level"]),
                "effective_samples": _integer(row["effective_samples"]),
                "draw_count": _integer(row["draw_count"]),
                "run_id": str(row["run_id"]),
                "as_of": _date_text(row["as_of"]),
                "data_vintage": _date_text(row["data_vintage"]),
                "model_version": str(row["model_version"]),
                "config_hash": str(row["config_hash"]),
                "created_at": _timestamp_text(row["created_at"]),
                "unavailable_reason": unavailable_reason,
            }
        )
    return records


def _conservation_payload(view: _VerifiedView) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in view.conservation.to_dict(orient="records"):
        asset = _asset_metadata(view, str(row["asset_id"]))
        records.append(
            {
                "interpretation": view.interpretation,
                "asset_id": str(row["asset_id"]),
                "symbol": str(asset["symbol"]),
                "proxy_status": str(asset["proxy_status"]),
                "proxy_for": asset["proxy_for"],
                "period_start": _date_text(row["period_start"]),
                "period_end": _date_text(row["period_end"]),
                "horizon_months": _integer(row["horizon_months"]),
                "return_basis": str(row["return_basis"]),
                "point_component_sum": _number(row["point_component_sum"]),
                "observed_return": _number(row["observed_return"]),
                "point_conservation_error": _number(row["point_conservation_error"]),
                "max_draw_conservation_error": _number(
                    row["max_draw_conservation_error"]
                ),
                "available_component_count": _integer(row["available_component_count"]),
                "unavailable_component_count": _integer(
                    row["unavailable_component_count"]
                ),
                "status": str(row["status"]),
                "run_id": str(row["run_id"]),
                "as_of": _date_text(row["as_of"]),
                "data_vintage": _date_text(row["data_vintage"]),
                "model_version": str(row["model_version"]),
                "config_hash": str(row["config_hash"]),
                "created_at": _timestamp_text(row["created_at"]),
            }
        )
    return records


def _comparison_payload(views: Mapping[str, _VerifiedView]) -> list[dict[str, object]]:
    dimensions = [
        "asset_id",
        "return_basis",
        "component_type",
        "component_id",
    ]
    realtime = views[REALTIME].attribution.set_index(dimensions)
    latest = views[LATEST_HISTORICAL].attribution.set_index(dimensions)
    if set(realtime.index) != set(latest.index):
        raise ValueError(
            "realtime and latest_historical attribution component keys must match"
        )
    records: list[dict[str, object]] = []
    for key in sorted(realtime.index):
        realtime_row = realtime.loc[key]
        latest_row = latest.loc[key]
        asset_id, return_basis, component_type, component_id = key
        asset = _asset_metadata(views[REALTIME], str(asset_id))
        realtime_point = float(realtime_row["point_contribution"])
        latest_point = float(latest_row["point_contribution"])
        realtime_observed = float(realtime_row["observed_return"])
        latest_observed = float(latest_row["observed_return"])
        records.append(
            {
                "asset_id": str(asset_id),
                "symbol": str(asset["symbol"]),
                "proxy_status": str(asset["proxy_status"]),
                "proxy_for": asset["proxy_for"],
                "return_basis": str(return_basis),
                "component_type": str(component_type),
                "component_id": str(component_id),
                "realtime_point_contribution": realtime_point,
                "latest_historical_point_contribution": latest_point,
                "point_contribution_change": latest_point - realtime_point,
                "realtime_observed_return": realtime_observed,
                "latest_historical_observed_return": latest_observed,
                "observed_return_change": latest_observed - realtime_observed,
            }
        )
    return records


def _report_payload(
    requested_run_id: str,
    views: Mapping[str, _VerifiedView],
) -> dict[str, object]:
    requested_metadata = views[
        next(
            interpretation
            for interpretation in INTERPRETATIONS
            if views[interpretation].manifest.run_id == requested_run_id
        )
    ].metadata
    return {
        "report_id": REPORT_ID,
        "requested_run_id": requested_run_id,
        "interpretation_runs": {
            interpretation: views[interpretation].manifest.run_id
            for interpretation in INTERPRETATIONS
        },
        "period": requested_metadata["period"],
        "benchmark": requested_metadata["benchmark"],
        "source_manifests": {
            interpretation: {
                "run_id": view.manifest.run_id,
                "as_of": view.manifest.as_of.isoformat(),
                "data_vintage": view.manifest.data_vintage.isoformat(),
                "model_version": view.manifest.model_version,
                "config_hash": view.manifest.config_hash,
            }
            for interpretation, view in views.items()
        },
        "asset_metadata": requested_metadata["assets"],
        "attribution": [
            row
            for interpretation in INTERPRETATIONS
            for row in _attribution_payload(views[interpretation])
        ],
        "conservation": [
            row
            for interpretation in INTERPRETATIONS
            for row in _conservation_payload(views[interpretation])
        ],
        "vintage_comparison": _comparison_payload(views),
    }


def _percent(value: object) -> str:
    if value is None:
        return "不可用"
    return f"{float(value):.2%}"


def _markdown(payload: Mapping[str, object]) -> str:
    attribution = payload["attribution"]
    conservation = payload["conservation"]
    comparison = payload["vintage_comparison"]
    if not isinstance(attribution, list) or not isinstance(conservation, list):
        raise TypeError("report payload tables must be lists")
    if not isinstance(comparison, list):
        raise TypeError("vintage comparison must be a list")
    source_manifests = _mapping(payload["source_manifests"], "source_manifests")
    benchmark = _mapping(payload["benchmark"], "benchmark")
    period = _mapping(payload["period"], "period")
    asset_metadata = _mapping(payload["asset_metadata"], "asset_metadata")

    lines = [
        f"# 2019 白酒归因验收（{REPORT_ID}）",
        "",
        "本报告仅消费已校验的 `asset_attribution.parquet`、"
        "`asset_attribution_conservation.parquet` 与对应 manifest；"
        "白酒主指数与食品饮料代理独立披露，不拼接、不替换。",
        "",
        "## 报告口径",
        "",
        f"- 期间：{period['period_start']} 至 {period['period_end']}，"
        f"horizon={period['horizon_months']}。",
        f"- 基准：{benchmark['asset_id']} / {benchmark['symbol']}。",
        f"- 请求运行：{payload['requested_run_id']}。",
        "",
        "## Vintage 版本对比",
        "",
        "| interpretation | run_id | data_vintage | model_version | config_hash |",
        "|---|---|---|---|---|",
    ]
    for interpretation in INTERPRETATIONS:
        source = _mapping(source_manifests[interpretation], interpretation)
        lines.append(
            "| "
            + " | ".join(
                (
                    interpretation,
                    str(source["run_id"]),
                    str(source["data_vintage"]),
                    str(source["model_version"]),
                    str(source["config_hash"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "| asset_id | symbol | proxy_status | history | shrinkage | confidence |",
            "|---|---|---|---|---|---|",
        ]
    )
    for asset_id in (PRIMARY_ASSET_ID, PROXY_ASSET_ID):
        asset = _mapping(asset_metadata[asset_id], asset_id)
        lines.append(
            "| "
            + " | ".join(
                (
                    asset_id,
                    str(asset["symbol"]),
                    str(asset["proxy_status"]),
                    str(asset["history_status"]),
                    str(asset["shrinkage_status"]),
                    str(asset["confidence"]),
                )
            )
            + " |"
        )

    for interpretation in INTERPRETATIONS:
        manifest = _mapping(source_manifests[interpretation], interpretation)
        lines.extend(
            [
                "",
                f"## {interpretation}",
                "",
                f"run_id={manifest['run_id']}；data_vintage={manifest['data_vintage']}；"
                f"model_version={manifest['model_version']}。",
            ]
        )
        for asset_id in (PRIMARY_ASSET_ID, PROXY_ASSET_ID):
            asset = _mapping(asset_metadata[asset_id], asset_id)
            lines.extend(
                [
                    "",
                    f"### {asset_id} / {asset['symbol']} ({asset['proxy_status']})",
                ]
            )
            for return_basis in REQUIRED_RETURN_BASES:
                rows = [
                    row
                    for row in attribution
                    if isinstance(row, Mapping)
                    and row["interpretation"] == interpretation
                    and row["asset_id"] == asset_id
                    and row["return_basis"] == return_basis
                ]
                observed = rows[0]["observed_return"]
                lines.extend(
                    [
                        "",
                        f"#### {return_basis}",
                        "",
                        f"观测收益：{_percent(observed)}。",
                        "",
                        "| component_type | component_id | point | 50% interval | "
                        "80% interval | evidence | significance | interval_status | "
                        "status | unavailable reason |",
                        "|---|---|---:|---:|---:|---|---|---|---|---|",
                    ]
                )
                for row in rows:
                    reason = row["unavailable_reason"] or "—"
                    lines.append(
                        "| "
                        + " | ".join(
                            (
                                str(row["component_type"]),
                                str(row["component_id"]),
                                _percent(row["point_contribution"]),
                                f"{_percent(row['lower_50'])} / "
                                f"{_percent(row['upper_50'])}",
                                f"{_percent(row['lower_80'])} / "
                                f"{_percent(row['upper_80'])}",
                                str(row["evidence_level"]),
                                str(row["significance"]),
                                str(row["interval_status"]),
                                str(row["status"]),
                                str(reason),
                            )
                        )
                        + " |"
                    )

    lines.extend(
        [
            "",
            "## 守恒诊断",
            "",
            "| interpretation | asset_id | return_basis | observed | component sum | "
            "point error | status |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in conservation:
        if not isinstance(row, Mapping):
            raise TypeError("conservation rows must be mappings")
        lines.append(
            "| "
            + " | ".join(
                (
                    str(row["interpretation"]),
                    str(row["asset_id"]),
                    str(row["return_basis"]),
                    _percent(row["observed_return"]),
                    _percent(row["point_component_sum"]),
                    _percent(row["point_conservation_error"]),
                    str(row["status"]),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 时点对比明细",
            "",
            "| asset_id | proxy_status | return_basis | component_type | component_id | "
            "realtime | latest_historical | change |",
            "|---|---|---|---|---|---:|---:|---:|",
        ]
    )
    for row in comparison:
        if not isinstance(row, Mapping):
            raise TypeError("comparison rows must be mappings")
        lines.append(
            "| "
            + " | ".join(
                (
                    str(row["asset_id"]),
                    str(row["proxy_status"]),
                    str(row["return_basis"]),
                    str(row["component_type"]),
                    str(row["component_id"]),
                    _percent(row["realtime_point_contribution"]),
                    _percent(row["latest_historical_point_contribution"]),
                    _percent(row["point_contribution_change"]),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _open_existing_child_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[int, _DirectoryIdentity] | None:
    try:
        child_stat = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(child_stat.st_mode):
        raise ValueError(f"{label} cannot be a symlink")
    if not stat.S_ISDIR(child_stat.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return _open_child_directory_fd(parent_descriptor, name, label=label)


def _ensure_child_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[int, _DirectoryIdentity]:
    opened = _open_existing_child_directory_at(
        parent_descriptor,
        name,
        label=label,
    )
    if opened is not None:
        return opened
    try:
        os.mkdir(name, mode=0o755, dir_fd=parent_descriptor)
    except FileExistsError:
        pass
    return _open_child_directory_fd(parent_descriptor, name, label=label)


def _existing_report_pair_at(
    reports_descriptor: int,
    requested_run_id: str,
    markdown_bytes: bytes,
    json_bytes: bytes,
) -> bool:
    opened = _open_existing_child_directory_at(
        reports_descriptor,
        requested_run_id,
        label="report destination",
    )
    if opened is None:
        return False
    report_descriptor, report_identity = opened
    try:
        expected_names = {
            BAIJIU_2019_MARKDOWN_FILENAME,
            BAIJIU_2019_JSON_FILENAME,
        }
        actual_names = set(os.listdir(report_descriptor))
        if actual_names != expected_names:
            raise FileExistsError(
                "incomplete or unexpected existing Baijiu report pair"
            )
        actual_markdown = _read_regular_bytes_at(
            report_descriptor,
            BAIJIU_2019_MARKDOWN_FILENAME,
            label="existing Baijiu Markdown report",
        )
        actual_json = _read_regular_bytes_at(
            report_descriptor,
            BAIJIU_2019_JSON_FILENAME,
            label="existing Baijiu JSON report",
        )
        if (
            _fd_identity(report_descriptor, label="report destination")
            != report_identity
        ):
            raise ValueError("report destination descriptor identity changed")
        if actual_markdown == markdown_bytes and actual_json == json_bytes:
            return True
        raise FileExistsError("refuse overwrite of an existing Baijiu report")
    finally:
        os.close(report_descriptor)


def _write_staged_report_at(
    staging_descriptor: int,
    filename: str,
    content: bytes,
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(filename, flags, 0o644, dir_fd=staging_descriptor)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor_open = False
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
            if not stat.S_ISREG(os.fstat(output.fileno()).st_mode):
                raise ValueError("staged report must be a regular file")
    finally:
        if descriptor_open:
            os.close(descriptor)


def _cleanup_staging_at(
    reports_descriptor: int,
    staging_descriptor: int,
    staging_name: str,
    *,
    expected: _DirectoryIdentity,
    promoted: bool,
) -> None:
    try:
        if not promoted:
            for filename in (
                BAIJIU_2019_MARKDOWN_FILENAME,
                BAIJIU_2019_JSON_FILENAME,
            ):
                try:
                    os.unlink(filename, dir_fd=staging_descriptor)
                except FileNotFoundError:
                    pass
    finally:
        os.close(staging_descriptor)
    if promoted:
        return
    try:
        staging_stat = os.stat(
            staging_name,
            dir_fd=reports_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if stat.S_ISDIR(staging_stat.st_mode) and (
        staging_stat.st_dev,
        staging_stat.st_ino,
    ) == (expected.device, expected.inode):
        os.rmdir(staging_name, dir_fd=reports_descriptor)


def _write_report_pair_at(
    reports_descriptor: int,
    reports_identity: _DirectoryIdentity,
    reports_root: Path,
    requested_run_id: str,
    markdown_bytes: bytes,
    json_bytes: bytes,
) -> tuple[Path, Path, bool]:
    report_dir = reports_root / requested_run_id
    markdown_path = report_dir / BAIJIU_2019_MARKDOWN_FILENAME
    json_path = report_dir / BAIJIU_2019_JSON_FILENAME
    if _existing_report_pair_at(
        reports_descriptor,
        requested_run_id,
        markdown_bytes,
        json_bytes,
    ):
        return markdown_path, json_path, True

    staging_name = f".{requested_run_id}.{secrets.token_hex(8)}.tmp"
    os.mkdir(staging_name, mode=0o755, dir_fd=reports_descriptor)
    staging_descriptor, staging_identity = _open_child_directory_fd(
        reports_descriptor,
        staging_name,
        label="report staging directory",
    )
    promoted = False
    try:
        _write_staged_report_at(
            staging_descriptor,
            BAIJIU_2019_MARKDOWN_FILENAME,
            markdown_bytes,
        )
        _write_staged_report_at(
            staging_descriptor,
            BAIJIU_2019_JSON_FILENAME,
            json_bytes,
        )
        os.fsync(staging_descriptor)
        if _fd_identity(reports_descriptor, label="reports root") != reports_identity:
            raise ValueError("reports root descriptor identity changed")
        if _existing_report_pair_at(
            reports_descriptor,
            requested_run_id,
            markdown_bytes,
            json_bytes,
        ):
            return markdown_path, json_path, True
        try:
            os.rename(
                staging_name,
                requested_run_id,
                src_dir_fd=reports_descriptor,
                dst_dir_fd=reports_descriptor,
            )
        except OSError:
            if _existing_report_pair_at(
                reports_descriptor,
                requested_run_id,
                markdown_bytes,
                json_bytes,
            ):
                return markdown_path, json_path, True
            raise
        promoted = True
        destination_stat = os.stat(
            requested_run_id,
            dir_fd=reports_descriptor,
            follow_symlinks=False,
        )
        if (
            _DirectoryIdentity(
                destination_stat.st_dev,
                destination_stat.st_ino,
            )
            != staging_identity
        ):
            raise ValueError("published report directory identity changed")
        os.fsync(reports_descriptor)
        return markdown_path, json_path, False
    finally:
        _cleanup_staging_at(
            reports_descriptor,
            staging_descriptor,
            staging_name,
            expected=staging_identity,
            promoted=promoted,
        )


def generate_baijiu_2019_report(
    product_root: Path,
    run_id: str,
) -> Baijiu2019ReportResult:
    """Generate a deterministic two-vintage report without mutating source runs."""

    normalized_run_id = _run_id(run_id, "run_id")
    root = Path(product_root)
    views = _load_views(root, normalized_run_id)
    payload = _report_payload(normalized_run_id, views)
    json_bytes = canonical_json_bytes(payload) + b"\n"
    markdown_bytes = _markdown(payload).encode("utf-8")
    root_identity = _directory_identity(root, label="product root")
    root_descriptor, opened_root_identity = _open_directory_fd(
        root,
        label="product root",
        expected=root_identity,
    )
    reports_descriptor: int | None = None
    try:
        reports_descriptor, reports_identity = _ensure_child_directory_at(
            root_descriptor,
            "reports",
            label="reports root",
        )
        reports_root = root / "reports"
        markdown_path, json_path, reused = _write_report_pair_at(
            reports_descriptor,
            reports_identity,
            reports_root,
            normalized_run_id,
            markdown_bytes,
            json_bytes,
        )
        if _fd_identity(root_descriptor, label="product root") != opened_root_identity:
            raise ValueError("product root descriptor identity changed")
        reports_entry = os.stat(
            "reports",
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            stat.S_ISLNK(reports_entry.st_mode)
            or _DirectoryIdentity(
                reports_entry.st_dev,
                reports_entry.st_ino,
            )
            != reports_identity
        ):
            raise ValueError("reports root entry changed during report generation")
        if _directory_identity(root, label="product root") != opened_root_identity:
            raise ValueError("product root path changed during report generation")
    finally:
        if reports_descriptor is not None:
            os.close(reports_descriptor)
        os.close(root_descriptor)
    return Baijiu2019ReportResult(
        requested_run_id=normalized_run_id,
        markdown_path=markdown_path,
        json_path=json_path,
        interpretation_runs=tuple(
            (interpretation, views[interpretation].manifest.run_id)
            for interpretation in INTERPRETATIONS
        ),
        reused=reused,
    )


__all__ = [
    "BAIJIU_2019_JSON_FILENAME",
    "BAIJIU_2019_MARKDOWN_FILENAME",
    "Baijiu2019ReportResult",
    "generate_baijiu_2019_report",
]
