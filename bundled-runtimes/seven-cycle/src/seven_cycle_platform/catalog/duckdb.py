"""Build and verify one-run DuckDB product catalogs."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ASSET_ATTRIBUTION_SCHEMA,
    CHANNEL_STATE_SCHEMA,
    CYCLE_PHASE_VINTAGE_SCHEMA,
    QUALITY_FINDING_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_SCHEMA,
)
from seven_cycle_platform.products.cycle_forecast import CYCLE_FORECAST_SCHEMA
from seven_cycle_platform.products.cycle_asset_surface import CYCLE_ASSET_SURFACE_SCHEMA
from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_FILENAME,
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME,
    DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME,
    PUBLICATION_GATE_SCHEMA,
)
from seven_cycle_platform.security import redact_secrets
from seven_cycle_platform.storage.manifest import (
    MANIFEST_FILENAME,
    ManifestVerificationError,
    RunManifest,
    sha256_file,
    verify_manifest,
)
from seven_cycle_platform.storage.run_context import canonical_json_bytes


CATALOG_SCHEMA_VERSION = 3
STABLE_VIEW_NAMES = (
    "runs",
    "cycle_current",
    "cycle_history",
    "cycle_forecast",
    "assets",
    "attribution",
    "asset_mapping_current",
    "asset_mapping_future",
    "cycle_asset_surface",
    "historical_analogs",
    "scenarios",
    "quality_findings",
    "cycle_evidence",
    "data_identity",
    "publication_gates",
    "calibration_log",
)

_HISTORICAL_ANALOG_SCHEMA = pa.schema(
    [
        pa.field("historical_date", pa.date32()),
        pa.field("historical_vintage", pa.date32()),
        pa.field("analog_rank", pa.int32()),
        pa.field("distance", pa.float64()),
        pa.field("effective_samples", pa.int32()),
        pa.field("cycle_difference_json", pa.string()),
        pa.field("channel_difference_json", pa.string()),
        pa.field("asset_outcome_json", pa.string()),
        pa.field("status", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


class CatalogError(ValueError):
    """Base class for catalog trust or build failures."""


class CatalogBuildError(CatalogError):
    """Raised when a verified run cannot produce a safe catalog."""


class CatalogVerificationError(CatalogError):
    """Raised when a catalog does not match its trusted run."""


class CatalogRepairRefusedError(CatalogError):
    """Raised when a catalog failure is not proven to be safe device drift."""


@dataclass(frozen=True, slots=True)
class VerifiedCatalogConnection:
    """Guarded read-only query surface bound to immutable product snapshots."""

    _connection: duckdb.DuckDBPyConnection
    _catalog_path: Path
    _catalog_identity: _FileIdentity
    _run_dir: Path
    _manifest: RunManifest
    _product_snapshots: tuple[_FileSnapshot, ...]

    def _verify(self) -> None:
        try:
            _verify_trusted_manifest(self._run_dir, expected=self._manifest)
            current_snapshots = _snapshot_products(self._run_dir, self._manifest)
            if tuple(current_snapshots.values()) != self._product_snapshots:
                raise CatalogVerificationError(
                    "catalog product snapshots changed during query lifecycle"
                )
            if _target_identity(self._catalog_path) != self._catalog_identity:
                raise CatalogVerificationError(
                    "catalog path changed during query lifecycle"
                )
        except CatalogVerificationError:
            self._connection.close()
            raise
        except BaseException as error:
            self._connection.close()
            raise CatalogVerificationError(
                "catalog trust binding changed during query lifecycle"
            ) from error

    def _guarded(self, operation: Callable[[], object]) -> object:
        self._verify()
        try:
            result = operation()
        except BaseException:
            self._verify()
            raise
        self._verify()
        return result

    def execute(
        self,
        query: str,
        parameters: object | None = None,
    ) -> "VerifiedCatalogConnection":
        if parameters is None:
            self._guarded(lambda: self._connection.execute(query))
        else:
            self._guarded(lambda: self._connection.execute(query, parameters))
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._guarded(self._connection.fetchone)

    def fetchmany(self, size: int = 1) -> list[tuple[object, ...]]:
        return self._guarded(lambda: self._connection.fetchmany(size))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._guarded(self._connection.fetchall)

    def fetchdf(self) -> object:
        return self._guarded(self._connection.fetchdf)

    def fetch_df(self) -> object:
        return self.fetchdf()

    def fetch_arrow_table(self) -> pa.Table:
        return self._guarded(self._connection.fetch_arrow_table)

    def fetchnumpy(self) -> dict[str, object]:
        return self._guarded(self._connection.fetchnumpy)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "VerifiedCatalogConnection":
        self._verify()
        return self

    def __exit__(
        self,
        exception_type: object,
        exception: object,
        traceback: object,
    ) -> None:
        self.close()


@dataclass(frozen=True)
class CatalogBuildResult:
    """Immutable audit result for one catalog build."""

    path: Path
    run_id: str
    view_names: tuple[str, ...]
    product_count: int
    manifest_checksum: str
    catalog_checksum: str


@dataclass(frozen=True, slots=True)
class CatalogDeviceIdentityDriftEvidence:
    """Strict evidence that one derived catalog differs only by device id."""

    catalog_path: Path
    catalog_device: int
    catalog_inode: int
    run_id: str
    previous_catalog_checksum: str
    replacement_catalog_checksum: str


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class _FileSnapshot:
    relative_path: str
    absolute_path: str
    checksum: str
    size_bytes: int
    mtime_ns: int
    device: int
    inode: int


@dataclass(frozen=True)
class _SourceSpec:
    product_name: str
    filename: str
    source_view: str
    schema: pa.Schema
    required_product: bool = False


@dataclass(frozen=True)
class _CatalogProduct:
    product_name: str
    expected_filename: str | None
    relative_path: str | None
    absolute_path: str | None
    checksum: str | None
    available: bool
    required_product: bool
    source_view: str | None
    schema_json: str | None
    size_bytes: int | None
    mtime_ns: int | None
    device: int | None
    inode: int | None


@dataclass(frozen=True)
class _QualityRecordAudit:
    count: int
    digest: str


_SOURCE_SPECS = (
    _SourceSpec(
        product_name="cycle_phase_vintage",
        filename="cycle_phase_vintage.parquet",
        source_view="_src_cycle_phase_vintage",
        schema=CYCLE_PHASE_VINTAGE_SCHEMA,
        required_product=True,
    ),
    _SourceSpec(
        product_name="channel_state",
        filename="channel_state.parquet",
        source_view="_src_channel_state",
        schema=CHANNEL_STATE_SCHEMA,
    ),
    _SourceSpec(
        product_name="asset_attribution",
        filename="asset_attribution.parquet",
        source_view="_src_asset_attribution",
        schema=ASSET_ATTRIBUTION_SCHEMA,
    ),
    _SourceSpec(
        product_name="asset_attribution_conservation",
        filename="asset_attribution_conservation.parquet",
        source_view="_src_asset_attribution_conservation",
        schema=ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ),
    _SourceSpec(
        product_name="asset_mapping_current",
        filename="asset_mapping_current.parquet",
        source_view="_src_asset_mapping_current",
        schema=ASSET_MAPPING_CURRENT_SCHEMA,
    ),
    _SourceSpec(
        product_name="cycle_forecast",
        filename="cycle_forecast.parquet",
        source_view="_src_cycle_forecast",
        schema=CYCLE_FORECAST_SCHEMA,
    ),
    _SourceSpec(
        product_name="asset_mapping_future",
        filename="asset_mapping_future.parquet",
        source_view="_src_asset_mapping_future",
        schema=ASSET_MAPPING_FUTURE_SCHEMA,
    ),
    _SourceSpec(
        product_name="cycle_asset_surface",
        filename="cycle_asset_surface.parquet",
        source_view="_src_cycle_asset_surface",
        schema=CYCLE_ASSET_SURFACE_SCHEMA,
    ),
    _SourceSpec(
        product_name="quality_findings_product",
        filename="quality_findings.parquet",
        source_view="_src_quality_findings",
        schema=QUALITY_FINDING_SCHEMA,
    ),
    _SourceSpec(
        product_name="historical_analogs",
        filename="historical_analogs.parquet",
        source_view="_src_historical_analogs",
        schema=_HISTORICAL_ANALOG_SCHEMA,
    ),
    _SourceSpec(
        product_name="cycle_evidence",
        filename=CYCLE_EVIDENCE_FILENAME,
        source_view="_src_cycle_evidence",
        schema=CYCLE_EVIDENCE_SCHEMA,
    ),
    _SourceSpec(
        product_name="data_identity",
        filename=DATA_IDENTITY_FILENAME,
        source_view="_src_data_identity",
        schema=DATA_IDENTITY_SCHEMA,
    ),
    _SourceSpec(
        product_name="publication_gate",
        filename=PUBLICATION_GATE_FILENAME,
        source_view="_src_publication_gate",
        schema=PUBLICATION_GATE_SCHEMA,
    ),
    _SourceSpec(
        product_name="calibration_log",
        filename=CALIBRATION_LOG_FILENAME,
        source_view="_src_calibration_log",
        schema=CALIBRATION_LOG_SCHEMA,
    ),
)
_SOURCE_SPEC_BY_NAME = {spec.product_name: spec for spec in _SOURCE_SPECS}
_SOURCE_SPEC_BY_FILENAME = {spec.filename: spec for spec in _SOURCE_SPECS}
_MANAGED_VIEW_NAMES = tuple(spec.source_view for spec in _SOURCE_SPECS) + (
    *STABLE_VIEW_NAMES,
)
_PLAN_ESTIMATE_PATTERN = re.compile(r"~[0-9,]+ Rows?")
_PARQUET_BATCH_SIZE = 4096
_QUALITY_INSERT_BATCH_SIZE = 1024
_DIGEST_MODULUS = 1 << 256
_UNSPECIFIED_TARGET_IDENTITY = object()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _verify_trusted_manifest(
    run_dir: Path,
    *,
    expected: RunManifest,
) -> RunManifest:
    try:
        return verify_manifest(run_dir, expected=expected)
    except ManifestVerificationError as error:
        raise ManifestVerificationError(redact_secrets(str(error))) from error


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _directory_identity(directory: Path, *, create: bool) -> _FileIdentity:
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    try:
        directory_stat = directory.lstat()
    except OSError as error:
        raise CatalogBuildError("catalog parent must be a real directory") from error
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise CatalogBuildError("catalog parent must be a real directory")
    return _FileIdentity(directory_stat.st_dev, directory_stat.st_ino)


def _assert_directory_identity(
    directory: Path,
    expected: _FileIdentity,
) -> None:
    if _directory_identity(directory, create=False) != expected:
        raise CatalogBuildError("catalog parent was replaced during build")


def _target_identity(path: Path) -> _FileIdentity | None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CatalogBuildError("catalog target is invalid") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise CatalogBuildError("catalog target must be a regular non-symlink file")
    return _FileIdentity(path_stat.st_dev, path_stat.st_ino)


def _assert_target_identity(
    path: Path,
    expected: _FileIdentity | None,
) -> None:
    actual = _target_identity(path)
    if actual != expected:
        raise CatalogBuildError("catalog target changed during build")


def _fsync_directory(directory: Path) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(
            os,
            "O_NOFOLLOW",
            0,
        )
    )
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_file(path: Path) -> None:
    with path.open("rb", buffering=0) as catalog_file:
        os.fsync(catalog_file.fileno())


def _normalize_catalog_path(
    catalog_path: Path,
    *,
    create_parent: bool,
) -> tuple[Path, _FileIdentity]:
    raw_path = Path(catalog_path).expanduser()
    parent = raw_path.parent.resolve(strict=False)
    parent_identity = _directory_identity(parent, create=create_parent)
    return parent / raw_path.name, parent_identity


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _require_safe_text(value: str) -> None:
    if "\x00" in value or redact_secrets(value) != value:
        raise CatalogBuildError("catalog input contains prohibited sensitive text")


def _require_catalog_outside_run(catalog_path: Path, run_dir: Path) -> None:
    if _is_within(catalog_path, run_dir):
        raise CatalogBuildError("catalog path must remain outside the immutable run")


def _relative_product_path(run_dir: Path, relative_name: str) -> Path:
    pure_path = PurePosixPath(relative_name)
    if pure_path.is_absolute() or ".." in pure_path.parts or not pure_path.parts:
        raise CatalogBuildError("manifest contains an invalid product path")
    path = run_dir.joinpath(*pure_path.parts)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CatalogBuildError("manifest product is missing or invalid") from error
    if not _is_within(resolved, run_dir):
        raise CatalogBuildError("manifest product escapes the immutable run")
    return resolved


def _snapshot_file(
    run_dir: Path,
    relative_name: str,
    expected_checksum: str,
) -> _FileSnapshot:
    path = _relative_product_path(run_dir, relative_name)
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise CatalogBuildError("manifest product is missing or invalid") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise CatalogBuildError("manifest product must be a regular file")
    checksum = sha256_file(path)
    if checksum != expected_checksum:
        raise CatalogBuildError("manifest product checksum changed during build")
    return _FileSnapshot(
        relative_path=relative_name,
        absolute_path=str(path),
        checksum=checksum,
        size_bytes=path_stat.st_size,
        mtime_ns=path_stat.st_mtime_ns,
        device=path_stat.st_dev,
        inode=path_stat.st_ino,
    )


def _snapshot_products(
    run_dir: Path,
    manifest: RunManifest,
) -> dict[str, _FileSnapshot]:
    snapshots: dict[str, _FileSnapshot] = {}
    for relative_name, checksum in manifest.product_checksums.items():
        _require_safe_text(relative_name)
        snapshots[relative_name] = _snapshot_file(
            run_dir,
            relative_name,
            checksum,
        )
    return snapshots


def _schema_json(schema: pa.Schema) -> str:
    payload = [
        {
            "name": field.name,
            "nullable": field.nullable,
            "type": str(field.type),
        }
        for field in schema
    ]
    return canonical_json_bytes(payload).decode("utf-8")


def _read_parquet_schema(path: str) -> pa.Schema:
    try:
        schema = pq.read_schema(path)
    except Exception as error:
        raise CatalogBuildError("manifest parquet product is unreadable") from error
    if len(schema.names) != len(set(schema.names)):
        raise CatalogBuildError("manifest parquet product has duplicate columns")
    return schema


def _governed_schema(schema: pa.Schema) -> pa.Schema:
    return pa.schema(
        [pa.field(field.name, field.type, nullable=field.nullable) for field in schema]
    )


def _require_exact_managed_schema(
    actual_schema: pa.Schema,
    expected_schema: pa.Schema,
    *,
    filename: str,
) -> None:
    if not _governed_schema(actual_schema).equals(
        _governed_schema(expected_schema),
        check_metadata=False,
    ):
        raise CatalogBuildError(
            f"managed parquet product {filename} schema does not match "
            "its governed schema"
        )


def _expected_provenance(
    manifest: RunManifest,
) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "as_of": manifest.as_of,
        "data_vintage": manifest.data_vintage,
        "model_version": manifest.model_version,
        "config_hash": manifest.config_hash,
        "created_at": manifest.created_at,
    }


def _validate_parquet_provenance(
    path: str,
    schema: pa.Schema,
    *,
    manifest: RunManifest,
) -> None:
    expected = _expected_provenance(manifest)
    provenance_columns = [
        field_name for field_name in expected if field_name in schema.names
    ]
    if not provenance_columns:
        return
    try:
        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(
            batch_size=_PARQUET_BATCH_SIZE,
            columns=provenance_columns,
        ):
            for field_name in provenance_columns:
                field = schema.field(field_name)
                values = batch.column(batch.schema.get_field_index(field_name))
                expected_value = pa.scalar(expected[field_name], type=field.type)
                matches = pc.fill_null(pc.equal(values, expected_value), False)
                if pc.any(pc.invert(matches)).as_py():
                    raise CatalogBuildError(
                        "managed parquet product provenance does not match "
                        "trusted manifest"
                    )
    except CatalogBuildError:
        raise
    except Exception as error:
        raise CatalogBuildError(
            "managed parquet product provenance is unreadable"
        ) from error


def _discover_products(
    manifest: RunManifest,
    snapshots: Mapping[str, _FileSnapshot],
) -> tuple[_CatalogProduct, ...]:
    by_filename: dict[str, list[str]] = {}
    for relative_name in manifest.product_checksums:
        filename = PurePosixPath(relative_name).name
        by_filename.setdefault(filename, []).append(relative_name)

    products: list[_CatalogProduct] = []
    matched_paths: set[str] = set()
    for spec in _SOURCE_SPECS:
        matches = by_filename.get(spec.filename, [])
        if len(matches) > 1:
            raise CatalogBuildError("manifest contains duplicate managed products")
        if not matches:
            if spec.required_product:
                raise CatalogBuildError("required catalog product is unavailable")
            products.append(
                _CatalogProduct(
                    product_name=spec.product_name,
                    expected_filename=spec.filename,
                    relative_path=None,
                    absolute_path=None,
                    checksum=None,
                    available=False,
                    required_product=False,
                    source_view=spec.source_view,
                    schema_json=_schema_json(spec.schema),
                    size_bytes=None,
                    mtime_ns=None,
                    device=None,
                    inode=None,
                )
            )
            continue
        relative_name = matches[0]
        matched_paths.add(relative_name)
        snapshot = snapshots[relative_name]
        actual_schema = _read_parquet_schema(snapshot.absolute_path)
        _require_exact_managed_schema(
            actual_schema,
            spec.schema,
            filename=spec.filename,
        )
        _validate_parquet_provenance(
            snapshot.absolute_path,
            actual_schema,
            manifest=manifest,
        )
        products.append(
            _CatalogProduct(
                product_name=spec.product_name,
                expected_filename=spec.filename,
                relative_path=relative_name,
                absolute_path=snapshot.absolute_path,
                checksum=snapshot.checksum,
                available=True,
                required_product=spec.required_product,
                source_view=spec.source_view,
                schema_json=_schema_json(actual_schema),
                size_bytes=snapshot.size_bytes,
                mtime_ns=snapshot.mtime_ns,
                device=snapshot.device,
                inode=snapshot.inode,
            )
        )

    for relative_name in sorted(
        set(manifest.product_checksums).difference(matched_paths)
    ):
        snapshot = snapshots[relative_name]
        schema_json = None
        if PurePosixPath(relative_name).suffix.casefold() == ".parquet":
            schema_json = _schema_json(_read_parquet_schema(snapshot.absolute_path))
        products.append(
            _CatalogProduct(
                product_name=f"file:{relative_name}",
                expected_filename=None,
                relative_path=relative_name,
                absolute_path=snapshot.absolute_path,
                checksum=snapshot.checksum,
                available=True,
                required_product=False,
                source_view=None,
                schema_json=schema_json,
                size_bytes=snapshot.size_bytes,
                mtime_ns=snapshot.mtime_ns,
                device=snapshot.device,
                inode=snapshot.inode,
            )
        )
    return tuple(sorted(products, key=lambda product: product.product_name))


def _flatten_json(
    value: object,
    *,
    path: str = "$",
) -> Iterator[tuple[str, str, str]]:
    if isinstance(value, Mapping):
        for key in sorted(value):
            yield from _flatten_json(value[key], path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten_json(item, path=f"{path}[{index}]")
        return
    if value is None:
        value_type = "null"
    elif isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    else:
        value_type = "string"
    value_json = canonical_json_bytes(value).decode("utf-8")
    safe_value = redact_secrets(value_json)
    yield path, value_type, safe_value


def _quality_rows(manifest: RunManifest) -> tuple[tuple[str, str, str, str], ...]:
    quality_summary = manifest.model_dump(mode="json")["quality_summary"]
    return tuple(
        (manifest.run_id, path, value_type, value_json)
        for path, value_type, value_json in _flatten_json(quality_summary)
    )


def _json_compatible(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_compatible(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _quality_record_payload(record: Mapping[str, object]) -> str:
    payload = canonical_json_bytes(_json_compatible(record)).decode("utf-8")
    return redact_secrets(payload)


def _iter_parquet_records(
    path: str,
    *,
    columns: tuple[str, ...],
) -> Iterator[dict[str, object]]:
    try:
        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(
            batch_size=_PARQUET_BATCH_SIZE,
            columns=list(columns),
        ):
            arrays = {
                field_name: batch.column(batch.schema.get_field_index(field_name))
                for field_name in columns
            }
            for row_index in range(batch.num_rows):
                yield {
                    field_name: arrays[field_name][row_index].as_py()
                    for field_name in columns
                }
    except Exception as error:
        raise CatalogBuildError("quality metadata source is unreadable") from error


def _iter_quality_record_rows(
    products: tuple[_CatalogProduct, ...],
    *,
    manifest: RunManifest,
) -> Iterator[tuple[str, str, str, str, str]]:
    by_name = {product.product_name: product for product in products}

    findings_product = by_name["quality_findings_product"]
    if findings_product.available:
        if findings_product.absolute_path is None:
            raise CatalogBuildError("quality metadata source path is unavailable")
        for finding in _iter_parquet_records(
            findings_product.absolute_path,
            columns=tuple(QUALITY_FINDING_SCHEMA.names),
        ):
            finding_key = finding.get("check") or finding.get("entity_id")
            safe_key = redact_secrets(str(finding_key or "quality_finding"))
            value_type = redact_secrets(str(finding.get("status") or "recorded"))
            yield (
                manifest.run_id,
                "quality_findings.parquet",
                safe_key,
                value_type,
                _quality_record_payload(finding),
            )

    conservation_product = by_name["asset_attribution_conservation"]
    if conservation_product.available:
        if conservation_product.absolute_path is None:
            raise CatalogBuildError("quality metadata source path is unavailable")
        conservation_fields = (
            "asset_id",
            "period_start",
            "period_end",
            "horizon_months",
            "return_basis",
            "point_conservation_error",
            "max_draw_conservation_error",
            "status",
        )
        for finding in _iter_parquet_records(
            conservation_product.absolute_path,
            columns=conservation_fields,
        ):
            finding_key = (
                "attribution_conservation:"
                f"{finding.get('asset_id') or ''}:"
                f"{finding.get('period_end') or ''}"
            )
            value_type = redact_secrets(str(finding.get("status") or "recorded"))
            yield (
                manifest.run_id,
                "asset_attribution_conservation.parquet",
                redact_secrets(finding_key),
                value_type,
                _quality_record_payload(finding),
            )


def _audit_quality_rows(
    rows: Iterator[tuple[str, str, str, str, str]],
) -> _QualityRecordAudit:
    row_count = 0
    digest_sum = 0
    digest_xor = 0
    for row in rows:
        row_digest = int.from_bytes(
            hashlib.sha256(canonical_json_bytes(row)).digest(),
            byteorder="big",
        )
        row_count += 1
        digest_sum = (digest_sum + row_digest) % _DIGEST_MODULUS
        digest_xor ^= row_digest
    digest_payload = {
        "count": row_count,
        "sum": f"{digest_sum:064x}",
        "xor": f"{digest_xor:064x}",
    }
    return _QualityRecordAudit(
        count=row_count,
        digest=_sha256_bytes(canonical_json_bytes(digest_payload)),
    )


def _quality_record_audit(
    products: tuple[_CatalogProduct, ...],
    *,
    manifest: RunManifest,
) -> _QualityRecordAudit:
    return _audit_quality_rows(_iter_quality_record_rows(products, manifest=manifest))


def _views_sql() -> tuple[str, str]:
    path = Path(__file__).with_name("views.sql")
    raw = path.read_bytes()
    return raw.decode("utf-8"), _sha256_bytes(raw)


def _product_audit_record(product: _CatalogProduct) -> dict[str, object]:
    return {
        "absolute_path": product.absolute_path,
        "available": product.available,
        "checksum": product.checksum,
        "device": product.device,
        "expected_filename": product.expected_filename,
        "inode": product.inode,
        "mtime_ns": product.mtime_ns,
        "product_name": product.product_name,
        "relative_path": product.relative_path,
        "required_product": product.required_product,
        "schema_json": product.schema_json,
        "size_bytes": product.size_bytes,
        "source_view": product.source_view,
    }


def _catalog_checksum(
    *,
    manifest: RunManifest,
    manifest_checksum: str,
    run_dir: Path,
    products: tuple[_CatalogProduct, ...],
    quality_rows: tuple[tuple[str, str, str, str], ...],
    quality_record_audit: _QualityRecordAudit,
    views_sql_checksum: str,
) -> str:
    payload = {
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "manifest": manifest.model_dump(mode="json"),
        "manifest_checksum": manifest_checksum,
        "products": [_product_audit_record(product) for product in products],
        "quality_record_audit": {
            "count": quality_record_audit.count,
            "digest": quality_record_audit.digest,
        },
        "quality_rows": quality_rows,
        "run_dir": str(run_dir),
        "stable_views": STABLE_VIEW_NAMES,
        "views_sql_checksum": views_sql_checksum,
    }
    return _sha256_bytes(canonical_json_bytes(payload))


def _duckdb_type(data_type: pa.DataType) -> str:
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return "VARCHAR"
    if pa.types.is_boolean(data_type):
        return "BOOLEAN"
    if pa.types.is_int8(data_type) or pa.types.is_int16(data_type):
        return "SMALLINT"
    if pa.types.is_int32(data_type) or pa.types.is_uint8(data_type):
        return "INTEGER"
    if pa.types.is_integer(data_type):
        return "BIGINT"
    if pa.types.is_float32(data_type):
        return "FLOAT"
    if pa.types.is_floating(data_type):
        return "DOUBLE"
    if pa.types.is_date(data_type):
        return "DATE"
    if pa.types.is_timestamp(data_type):
        if data_type.tz is not None:
            return "TIMESTAMP WITH TIME ZONE"
        return "TIMESTAMP"
    raise CatalogBuildError("catalog source schema contains an unsupported type")


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    _require_safe_text(value)
    return "'" + value.replace("'", "''") + "'"


def _empty_source_sql(spec: _SourceSpec) -> str:
    columns = ",\n    ".join(
        f"CAST(NULL AS {_duckdb_type(field.type)}) AS {_quote_identifier(field.name)}"
        for field in spec.schema
    )
    return (
        f"CREATE VIEW {_quote_identifier(spec.source_view)} AS\n"
        f"SELECT\n    {columns}\nWHERE FALSE"
    )


def _parquet_source_sql(
    spec: _SourceSpec,
    product: _CatalogProduct,
) -> str:
    if product.absolute_path is None:
        raise CatalogBuildError("available source product has no absolute path")
    return (
        f"CREATE VIEW {_quote_identifier(spec.source_view)} AS\n"
        "SELECT *\n"
        f"FROM read_parquet({_quote_literal(product.absolute_path)})"
    )


def _create_metadata_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE _catalog_metadata (
            catalog_schema_version INTEGER NOT NULL,
            run_id VARCHAR NOT NULL,
            run_dir VARCHAR NOT NULL,
            manifest_checksum VARCHAR NOT NULL,
            as_of DATE NOT NULL,
            data_vintage DATE NOT NULL,
            model_version VARCHAR NOT NULL,
            config_hash VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            product_count INTEGER NOT NULL,
            stable_view_count INTEGER NOT NULL,
            views_sql_checksum VARCHAR NOT NULL,
            catalog_checksum VARCHAR NOT NULL,
            quality_record_count BIGINT NOT NULL,
            quality_record_digest VARCHAR NOT NULL
        );
        CREATE TABLE _catalog_products (
            product_name VARCHAR NOT NULL,
            expected_filename VARCHAR,
            relative_path VARCHAR,
            absolute_path VARCHAR,
            checksum VARCHAR,
            available BOOLEAN NOT NULL,
            required_product BOOLEAN NOT NULL,
            source_view VARCHAR,
            schema_json VARCHAR,
            size_bytes BIGINT,
            mtime_ns BIGINT,
            device BIGINT,
            inode BIGINT
        );
        CREATE TABLE _catalog_quality_summary (
            run_id VARCHAR NOT NULL,
            metadata_path VARCHAR NOT NULL,
            value_type VARCHAR NOT NULL,
            value_json VARCHAR NOT NULL
        );
        CREATE TABLE _catalog_quality_records (
            run_id VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            finding_key VARCHAR NOT NULL,
            value_type VARCHAR NOT NULL,
            value_json VARCHAR NOT NULL
        );
        CREATE TABLE _catalog_views (
            view_name VARCHAR NOT NULL,
            available BOOLEAN NOT NULL,
            source_product VARCHAR,
            definition_checksum VARCHAR NOT NULL
        );
        """
    )


def _view_availability(products: tuple[_CatalogProduct, ...]) -> dict[str, bool]:
    available = {product.product_name: product.available for product in products}
    has_assets = any(
        available.get(name, False)
        for name in (
            "asset_attribution",
            "asset_mapping_current",
            "asset_mapping_future",
            "cycle_asset_surface",
        )
    )
    return {
        "runs": True,
        "cycle_current": available.get("cycle_phase_vintage", False),
        "cycle_history": available.get("cycle_phase_vintage", False),
        "cycle_forecast": available.get("cycle_forecast", False),
        "assets": has_assets,
        "attribution": available.get("asset_attribution", False),
        "asset_mapping_current": available.get("asset_mapping_current", False),
        "asset_mapping_future": available.get("asset_mapping_future", False),
        "cycle_asset_surface": available.get("cycle_asset_surface", False),
        "historical_analogs": available.get("historical_analogs", False),
        "scenarios": available.get("asset_mapping_future", False),
        "quality_findings": True,
        "cycle_evidence": available.get("cycle_evidence", False),
        "data_identity": available.get("data_identity", False),
        "publication_gates": available.get("publication_gate", False),
        "calibration_log": available.get("calibration_log", False),
    }


def _source_product_for_view(view_name: str) -> str | None:
    return {
        "cycle_current": "cycle_phase_vintage",
        "cycle_history": "cycle_phase_vintage",
        "cycle_forecast": "cycle_forecast",
        "attribution": "asset_attribution",
        "asset_mapping_current": "asset_mapping_current",
        "asset_mapping_future": "asset_mapping_future",
        "cycle_asset_surface": "cycle_asset_surface",
        "historical_analogs": "historical_analogs",
        "scenarios": "asset_mapping_future",
        "cycle_evidence": "cycle_evidence",
        "data_identity": "data_identity",
        "publication_gates": "publication_gate",
        "calibration_log": "calibration_log",
    }.get(view_name)


def _catalog_view_rows(
    products: tuple[_CatalogProduct, ...],
    *,
    views_sql_checksum: str,
) -> tuple[tuple[str, bool, str | None, str], ...]:
    availability = _view_availability(products)
    return tuple(
        (
            view_name,
            availability[view_name],
            _source_product_for_view(view_name),
            views_sql_checksum,
        )
        for view_name in STABLE_VIEW_NAMES
    )


def _insert_metadata(
    connection: duckdb.DuckDBPyConnection,
    *,
    manifest: RunManifest,
    run_dir: Path,
    manifest_checksum: str,
    catalog_checksum: str,
    views_sql_checksum: str,
    products: tuple[_CatalogProduct, ...],
    quality_rows: tuple[tuple[str, str, str, str], ...],
    quality_record_audit: _QualityRecordAudit,
) -> None:
    product_count = sum(product.available for product in products)
    connection.execute(
        "INSERT INTO _catalog_metadata VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            CATALOG_SCHEMA_VERSION,
            manifest.run_id,
            str(run_dir),
            manifest_checksum,
            manifest.as_of,
            manifest.data_vintage,
            manifest.model_version,
            manifest.config_hash,
            manifest.created_at,
            product_count,
            len(STABLE_VIEW_NAMES),
            views_sql_checksum,
            catalog_checksum,
            quality_record_audit.count,
            quality_record_audit.digest,
        ],
    )
    product_rows = [
        (
            product.product_name,
            product.expected_filename,
            product.relative_path,
            product.absolute_path,
            product.checksum,
            product.available,
            product.required_product,
            product.source_view,
            product.schema_json,
            product.size_bytes,
            product.mtime_ns,
            product.device,
            product.inode,
        )
        for product in products
    ]
    connection.executemany(
        "INSERT INTO _catalog_products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        product_rows,
    )
    if quality_rows:
        connection.executemany(
            "INSERT INTO _catalog_quality_summary VALUES (?, ?, ?, ?)",
            quality_rows,
        )
    connection.executemany(
        "INSERT INTO _catalog_views VALUES (?, ?, ?, ?)",
        _catalog_view_rows(
            products,
            views_sql_checksum=views_sql_checksum,
        ),
    )


def _insert_quality_records(
    connection: duckdb.DuckDBPyConnection,
    *,
    products: tuple[_CatalogProduct, ...],
    manifest: RunManifest,
) -> None:
    pending: list[tuple[str, str, str, str, str]] = []
    for row in _iter_quality_record_rows(products, manifest=manifest):
        pending.append(row)
        if len(pending) >= _QUALITY_INSERT_BATCH_SIZE:
            connection.executemany(
                "INSERT INTO _catalog_quality_records VALUES (?, ?, ?, ?, ?)",
                pending,
            )
            pending.clear()
    if pending:
        connection.executemany(
            "INSERT INTO _catalog_quality_records VALUES (?, ?, ?, ?, ?)",
            pending,
        )


def _create_source_views(
    connection: duckdb.DuckDBPyConnection,
    *,
    products: tuple[_CatalogProduct, ...],
) -> None:
    by_name = {product.product_name: product for product in products}
    for spec in _SOURCE_SPECS:
        product = by_name[spec.product_name]
        if product.available:
            source_sql = _parquet_source_sql(
                spec,
                product,
            )
        else:
            source_sql = _empty_source_sql(spec)
        connection.execute(source_sql)


def _validate_source_provenance(
    connection: duckdb.DuckDBPyConnection,
    *,
    manifest: RunManifest,
    products: tuple[_CatalogProduct, ...],
) -> None:
    by_name = {product.product_name: product for product in products}
    for spec in _SOURCE_SPECS:
        if (
            "run_id" not in spec.schema.names
            or not by_name[spec.product_name].available
        ):
            continue
        mismatch_count = connection.execute(
            f"SELECT count(*) FROM {_quote_identifier(spec.source_view)} "
            "WHERE run_id IS NULL OR run_id <> ?",
            [manifest.run_id],
        ).fetchone()[0]
        if mismatch_count:
            raise CatalogBuildError("catalog source contains mixed run provenance")


def _validate_catalog_contents(
    connection: duckdb.DuckDBPyConnection,
    *,
    manifest: RunManifest,
) -> None:
    rows = connection.execute(
        "SELECT run_id, catalog_schema_version, stable_view_count "
        "FROM _catalog_metadata"
    ).fetchall()
    if rows != [(manifest.run_id, CATALOG_SCHEMA_VERSION, len(STABLE_VIEW_NAMES))]:
        raise CatalogBuildError("catalog metadata is inconsistent")
    stable_views = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'VIEW'"
        ).fetchall()
    }
    if not set(STABLE_VIEW_NAMES).issubset(stable_views):
        raise CatalogBuildError("catalog stable view layer is incomplete")
    for view_name in STABLE_VIEW_NAMES:
        connection.execute(
            f"SELECT count(*) FROM {_quote_identifier(view_name)}"
        ).fetchone()
    invalid_tables = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
        "AND table_name NOT LIKE '_catalog_%'"
    ).fetchall()
    if invalid_tables:
        raise CatalogBuildError("catalog contains materialized product tables")


def _skip_sql_whitespace(sql: str, position: int) -> int:
    while position < len(sql) and sql[position].isspace():
        position += 1
    return position


def _consume_sql_keyword(sql: str, position: int, keyword: str) -> int:
    position = _skip_sql_whitespace(sql, position)
    end = position + len(keyword)
    if sql[position:end].casefold() != keyword.casefold():
        raise CatalogVerificationError("canonical view SQL is invalid")
    if end < len(sql) and (sql[end].isalnum() or sql[end] == "_"):
        raise CatalogVerificationError("canonical view SQL is invalid")
    return end


def _parse_sql_identifier(sql: str, position: int) -> tuple[str, int]:
    position = _skip_sql_whitespace(sql, position)
    if position >= len(sql):
        raise CatalogVerificationError("canonical view SQL is invalid")
    if sql[position] == '"':
        position += 1
        identifier: list[str] = []
        while position < len(sql):
            character = sql[position]
            if character != '"':
                identifier.append(character)
                position += 1
                continue
            if position + 1 < len(sql) and sql[position + 1] == '"':
                identifier.append('"')
                position += 2
                continue
            return "".join(identifier), position + 1
        raise CatalogVerificationError("canonical view SQL is invalid")
    start = position
    while position < len(sql) and (
        sql[position].isalnum() or sql[position] in {"_", "$"}
    ):
        position += 1
    if position == start:
        raise CatalogVerificationError("canonical view SQL is invalid")
    return sql[start:position], position


def _parse_create_view_query(sql: str) -> tuple[str, str]:
    position = _consume_sql_keyword(sql, 0, "CREATE")
    position = _consume_sql_keyword(sql, position, "VIEW")
    view_name, position = _parse_sql_identifier(sql, position)
    while True:
        qualified_position = _skip_sql_whitespace(sql, position)
        if qualified_position >= len(sql) or sql[qualified_position] != ".":
            break
        view_name, position = _parse_sql_identifier(
            sql,
            qualified_position + 1,
        )
    position = _consume_sql_keyword(sql, position, "AS")
    query = sql[position:].strip()
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if not query:
        raise CatalogVerificationError("canonical view SQL is invalid")
    return view_name, query


def _expected_view_queries(
    connection: duckdb.DuckDBPyConnection,
    *,
    products: tuple[_CatalogProduct, ...],
    views_sql: str,
) -> dict[str, str]:
    by_name = {product.product_name: product for product in products}
    sql_blocks = []
    for spec in _SOURCE_SPECS:
        product = by_name[spec.product_name]
        sql_blocks.append(
            _parquet_source_sql(spec, product)
            if product.available
            else _empty_source_sql(spec)
        )
    sql_blocks.append(views_sql)

    queries: dict[str, str] = {}
    for sql_block in sql_blocks:
        for statement in connection.extract_statements(sql_block):
            view_name, query = _parse_create_view_query(statement.query)
            if view_name in queries:
                raise CatalogVerificationError("canonical view SQL is duplicated")
            queries[view_name] = query
    if set(queries) != set(_MANAGED_VIEW_NAMES):
        raise CatalogVerificationError("canonical managed view set is invalid")
    return queries


def _actual_view_queries(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, str]:
    rows = connection.execute(
        "SELECT view_name, sql FROM duckdb_views() "
        "WHERE database_name = current_database() AND schema_name = 'main' "
        "AND NOT internal"
    ).fetchall()
    queries: dict[str, str] = {}
    for catalog_name, view_sql in rows:
        parsed_name, query = _parse_create_view_query(view_sql)
        if parsed_name != catalog_name or catalog_name in queries:
            raise CatalogVerificationError("catalog managed view SQL is invalid")
        queries[catalog_name] = query
    if set(queries) != set(_MANAGED_VIEW_NAMES):
        raise CatalogVerificationError("catalog managed view set is invalid")
    return queries


def _normalized_explain(
    connection: duckdb.DuckDBPyConnection,
    query: str,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            plan_kind,
            _PLAN_ESTIMATE_PATTERN.sub("~? Rows", plan),
        )
        for plan_kind, plan in connection.execute(f"EXPLAIN {query}").fetchall()
    )


def _described_query(
    connection: duckdb.DuckDBPyConnection,
    query: str,
) -> tuple[tuple[object, ...], ...]:
    return tuple(connection.execute(f"DESCRIBE {query}").fetchall())


def _verify_view_plans(
    connection: duckdb.DuckDBPyConnection,
    *,
    products: tuple[_CatalogProduct, ...],
    views_sql: str,
) -> None:
    actual_queries = _actual_view_queries(connection)
    expected_queries = _expected_view_queries(
        connection,
        products=products,
        views_sql=views_sql,
    )
    for view_name in sorted(_MANAGED_VIEW_NAMES):
        actual_query = actual_queries[view_name]
        expected_query = expected_queries[view_name]
        if _described_query(connection, actual_query) != _described_query(
            connection,
            expected_query,
        ):
            raise CatalogVerificationError("catalog view schema was replaced")
        if _normalized_explain(connection, actual_query) != _normalized_explain(
            connection,
            expected_query,
        ):
            raise CatalogVerificationError("catalog view plan was replaced")


def _create_catalog_database(
    temporary_path: Path,
    *,
    manifest: RunManifest,
    run_dir: Path,
    manifest_checksum: str,
    catalog_checksum: str,
    views_sql: str,
    views_sql_checksum: str,
    products: tuple[_CatalogProduct, ...],
    quality_rows: tuple[tuple[str, str, str, str], ...],
    quality_record_audit: _QualityRecordAudit,
) -> None:
    connection = duckdb.connect(str(temporary_path))
    try:
        connection.execute("BEGIN TRANSACTION")
        _create_metadata_tables(connection)
        _insert_metadata(
            connection,
            manifest=manifest,
            run_dir=run_dir,
            manifest_checksum=manifest_checksum,
            catalog_checksum=catalog_checksum,
            views_sql_checksum=views_sql_checksum,
            products=products,
            quality_rows=quality_rows,
            quality_record_audit=quality_record_audit,
        )
        _insert_quality_records(
            connection,
            products=products,
            manifest=manifest,
        )
        _create_source_views(connection, products=products)
        connection.execute(views_sql)
        _validate_source_provenance(
            connection,
            manifest=manifest,
            products=products,
        )
        _validate_catalog_contents(connection, manifest=manifest)
        connection.execute("COMMIT")
        connection.execute("CHECKPOINT")
    except BaseException:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()


def _assert_snapshots_unchanged(
    run_dir: Path,
    manifest: RunManifest,
    before: Mapping[str, _FileSnapshot],
) -> None:
    after = _snapshot_products(run_dir, manifest)
    if dict(before) != after:
        raise CatalogBuildError("immutable run products changed during catalog work")


def _create_lock(lock_path: Path) -> tuple[int, _FileIdentity]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError as error:
        raise CatalogBuildError("catalog target is being built concurrently") from error
    lock_stat = os.fstat(descriptor)
    identity = _FileIdentity(lock_stat.st_dev, lock_stat.st_ino)
    try:
        os.write(descriptor, b"catalog-build-lock\n")
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)
        raise
    return descriptor, identity


def _remove_lock(lock_path: Path, identity: _FileIdentity) -> None:
    try:
        lock_stat = lock_path.lstat()
    except FileNotFoundError:
        return
    if _FileIdentity(lock_stat.st_dev, lock_stat.st_ino) == identity:
        lock_path.unlink()


def _backup_existing_catalog(
    target: Path,
    backup_path: Path,
    expected_identity: _FileIdentity | None,
) -> None:
    if expected_identity is None:
        return
    try:
        os.link(target, backup_path, follow_symlinks=False)
    except OSError as error:
        raise CatalogBuildError(
            "existing catalog could not be backed up safely"
        ) from error
    backup_stat = backup_path.lstat()
    if _FileIdentity(backup_stat.st_dev, backup_stat.st_ino) != expected_identity:
        raise CatalogBuildError("existing catalog changed during backup")


def _rollback_catalog_replace(
    *,
    target: Path,
    replacement_identity: _FileIdentity,
    backup_path: Path | None,
) -> bool:
    if _target_identity(target) != replacement_identity:
        return False
    if backup_path is None:
        target.unlink()
    else:
        os.replace(backup_path, target)
    _fsync_directory(target.parent)
    return True


def _best_effort_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _best_effort_rmdir(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.rmdir()
    except Exception:
        pass


def build_catalog(
    run_dir: Path,
    catalog_path: Path,
    *,
    expected_manifest: RunManifest,
    _expected_target_identity: _FileIdentity | object = (
        _UNSPECIFIED_TARGET_IDENTITY
    ),
) -> CatalogBuildResult:
    """Build one verified catalog without changing its immutable run."""

    published_run = Path(run_dir)
    manifest = _verify_trusted_manifest(published_run, expected=expected_manifest)
    published_run = published_run.resolve(strict=True)
    target, parent_identity = _normalize_catalog_path(
        Path(catalog_path),
        create_parent=True,
    )
    _require_catalog_outside_run(target, published_run)
    for value in (str(published_run), str(target), manifest.model_version):
        _require_safe_text(value)

    initial_target_identity = _target_identity(target)
    if (
        _expected_target_identity is not _UNSPECIFIED_TARGET_IDENTITY
        and initial_target_identity != _expected_target_identity
    ):
        raise CatalogBuildError("catalog target changed before guarded rebuild")
    lock_path = target.with_name(f".{target.name}.lock")
    lock_descriptor, lock_identity = _create_lock(lock_path)
    temporary_path: Path | None = None
    temporary_directory: Path | None = None
    backup_path: Path | None = None
    replacement_identity: _FileIdentity | None = None
    committed = False
    preserve_rollback_evidence = False
    try:
        _assert_directory_identity(target.parent, parent_identity)
        _assert_target_identity(target, initial_target_identity)
        snapshots = _snapshot_products(published_run, manifest)
        products = _discover_products(manifest, snapshots)
        quality_rows = _quality_rows(manifest)
        quality_record_audit = _quality_record_audit(products, manifest=manifest)
        views_sql, views_sql_checksum = _views_sql()
        manifest_checksum = sha256_file(published_run / MANIFEST_FILENAME)
        audit_checksum = _catalog_checksum(
            manifest=manifest,
            manifest_checksum=manifest_checksum,
            run_dir=published_run,
            products=products,
            quality_rows=quality_rows,
            quality_record_audit=quality_record_audit,
            views_sql_checksum=views_sql_checksum,
        )

        temporary_directory = Path(
            tempfile.mkdtemp(
                dir=target.parent,
                prefix=f".{target.name}.",
            )
        )
        temporary_path = temporary_directory / "catalog.duckdb"
        _create_catalog_database(
            temporary_path,
            manifest=manifest,
            run_dir=published_run,
            manifest_checksum=manifest_checksum,
            catalog_checksum=audit_checksum,
            views_sql=views_sql,
            views_sql_checksum=views_sql_checksum,
            products=products,
            quality_rows=quality_rows,
            quality_record_audit=quality_record_audit,
        )
        _verify_trusted_manifest(published_run, expected=manifest)
        _assert_snapshots_unchanged(published_run, manifest, snapshots)
        _fsync_file(temporary_path)
        temporary_stat = temporary_path.lstat()
        replacement_identity = _FileIdentity(
            temporary_stat.st_dev,
            temporary_stat.st_ino,
        )
        _assert_directory_identity(target.parent, parent_identity)
        _assert_target_identity(target, initial_target_identity)
        if initial_target_identity is not None:
            backup_path = temporary_directory / "previous.duckdb"
            _backup_existing_catalog(
                target,
                backup_path,
                initial_target_identity,
            )
            _assert_target_identity(target, initial_target_identity)
        os.replace(temporary_path, target)
        if _target_identity(target) != replacement_identity:
            raise CatalogBuildError("catalog target identity changed after replace")
        _fsync_directory(target.parent)
        committed = True
        result = CatalogBuildResult(
            path=target,
            run_id=manifest.run_id,
            view_names=STABLE_VIEW_NAMES,
            product_count=sum(product.available for product in products),
            manifest_checksum=manifest_checksum,
            catalog_checksum=audit_checksum,
        )
        _best_effort_unlink(backup_path)
        _best_effort_rmdir(temporary_directory)
        return result
    except BaseException as error:
        if not committed and replacement_identity is not None:
            try:
                rolled_back = _rollback_catalog_replace(
                    target=target,
                    replacement_identity=replacement_identity,
                    backup_path=backup_path,
                )
                if not rolled_back and backup_path is not None:
                    raise CatalogBuildError("catalog target changed before rollback")
                if rolled_back:
                    backup_path = None
            except BaseException as rollback_error:
                preserve_rollback_evidence = True
                raise CatalogBuildError(
                    "catalog build failed and rollback was incomplete"
                ) from rollback_error
        if isinstance(error, CatalogError):
            raise
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise CatalogBuildError("DuckDB catalog build failed safely") from error
    finally:
        try:
            os.close(lock_descriptor)
        except OSError:
            pass
        try:
            _remove_lock(lock_path, lock_identity)
        except Exception:
            pass
        if not preserve_rollback_evidence:
            _best_effort_unlink(temporary_path)
            if temporary_path is not None:
                _best_effort_unlink(Path(f"{temporary_path}.wal"))
            _best_effort_unlink(backup_path)
            _best_effort_rmdir(temporary_directory)
        elif temporary_directory is not None:
            try:
                _fsync_directory(temporary_directory)
            except Exception:
                pass


def _stored_product_records(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        connection.execute(
            "SELECT product_name, expected_filename, relative_path, absolute_path, "
            "checksum, available, required_product, source_view, schema_json, "
            "size_bytes, mtime_ns, device, inode "
            "FROM _catalog_products ORDER BY product_name"
        ).fetchall()
    )


def _expected_product_records(
    products: tuple[_CatalogProduct, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            product.product_name,
            product.expected_filename,
            product.relative_path,
            product.absolute_path,
            product.checksum,
            product.available,
            product.required_product,
            product.source_view,
            product.schema_json,
            product.size_bytes,
            product.mtime_ns,
            product.device,
            product.inode,
        )
        for product in products
    )


def _stored_quality_rows(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        connection.execute(
            "SELECT run_id, metadata_path, value_type, value_json "
            "FROM _catalog_quality_summary "
            "ORDER BY run_id, metadata_path, value_type, value_json"
        ).fetchall()
    )


def _stored_quality_record_audit(
    connection: duckdb.DuckDBPyConnection,
) -> _QualityRecordAudit:
    connection.execute(
        "SELECT run_id, source, finding_key, value_type, value_json "
        "FROM _catalog_quality_records"
    )

    def rows() -> Iterator[tuple[str, str, str, str, str]]:
        while True:
            batch = connection.fetchmany(_PARQUET_BATCH_SIZE)
            if not batch:
                return
            for row in batch:
                yield row

    return _audit_quality_rows(rows())


def _stored_catalog_view_rows(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[tuple[str, bool, str | None, str], ...]:
    return tuple(
        connection.execute(
            "SELECT view_name, available, source_product, definition_checksum "
            "FROM _catalog_views ORDER BY view_name"
        ).fetchall()
    )


def _stored_products(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[_CatalogProduct, ...]:
    try:
        return tuple(
            _CatalogProduct(*record)
            for record in _stored_product_records(connection)
        )
    except (TypeError, ValueError) as error:
        raise CatalogRepairRefusedError(
            "catalog product metadata is not safely rebuildable"
        ) from error


def _without_device(product: _CatalogProduct) -> _CatalogProduct:
    return replace(product, device=None)


def _verify_device_drift_rebuild_evidence(
    catalog_path: Path,
    *,
    run_dir: Path,
    manifest: RunManifest,
) -> CatalogDeviceIdentityDriftEvidence:
    """Prove that a trusted derived catalog differs only by filesystem device."""

    target, _ = _normalize_catalog_path(catalog_path, create_parent=False)
    target_identity = _target_identity(target)
    if target_identity is None:
        raise CatalogRepairRefusedError(
            "catalog is missing; device-drift repair is not applicable"
        )

    snapshots = _snapshot_products(run_dir, manifest)
    current_products = _discover_products(manifest, snapshots)
    quality_rows = _quality_rows(manifest)
    quality_record_audit = _quality_record_audit(
        current_products,
        manifest=manifest,
    )
    views_sql, views_sql_checksum = _views_sql()
    manifest_checksum = sha256_file(run_dir / MANIFEST_FILENAME)

    try:
        connection = duckdb.connect(str(target), read_only=True)
    except Exception as error:
        raise CatalogRepairRefusedError(
            "catalog is unreadable; device-drift repair was refused"
        ) from error
    try:
        metadata_rows = connection.execute(
            "SELECT catalog_schema_version, run_id, run_dir, manifest_checksum, "
            "as_of, data_vintage, model_version, config_hash, created_at, "
            "product_count, stable_view_count, views_sql_checksum, "
            "catalog_checksum, quality_record_count, quality_record_digest "
            "FROM _catalog_metadata"
        ).fetchall()
        if len(metadata_rows) != 1:
            raise CatalogRepairRefusedError(
                "catalog metadata is not safely rebuildable"
            )
        metadata = metadata_rows[0]
        expected_prefix = (
            CATALOG_SCHEMA_VERSION,
            manifest.run_id,
            str(run_dir),
            manifest_checksum,
            manifest.as_of,
            manifest.data_vintage,
            manifest.model_version,
            manifest.config_hash,
            manifest.created_at,
            sum(product.available for product in current_products),
            len(STABLE_VIEW_NAMES),
            views_sql_checksum,
        )
        expected_suffix = (
            quality_record_audit.count,
            quality_record_audit.digest,
        )
        if metadata[:12] != expected_prefix or metadata[13:] != expected_suffix:
            raise CatalogRepairRefusedError(
                "catalog metadata changed beyond filesystem device identity"
            )

        stored_products = _stored_products(connection)
        if tuple(map(_without_device, stored_products)) != tuple(
            map(_without_device, current_products)
        ):
            raise CatalogRepairRefusedError(
                "catalog products changed beyond filesystem device identity"
            )

        available_pairs = [
            (stored, current)
            for stored, current in zip(
                stored_products,
                current_products,
                strict=True,
            )
            if current.available
        ]
        old_devices = {stored.device for stored, _ in available_pairs}
        current_devices = {current.device for _, current in available_pairs}
        run_device = run_dir.lstat().st_dev
        manifest_device = (run_dir / MANIFEST_FILENAME).lstat().st_dev
        if (
            not available_pairs
            or len(old_devices) != 1
            or len(current_devices) != 1
            or None in old_devices
            or None in current_devices
            or old_devices == current_devices
            or current_devices != {run_device}
            or manifest_device != run_device
            or any(stored.inode != current.inode for stored, current in available_pairs)
        ):
            raise CatalogRepairRefusedError(
                "catalog failure is not a uniform filesystem device drift"
            )

        stored_catalog_checksum = _catalog_checksum(
            manifest=manifest,
            manifest_checksum=manifest_checksum,
            run_dir=run_dir,
            products=stored_products,
            quality_rows=quality_rows,
            quality_record_audit=quality_record_audit,
            views_sql_checksum=views_sql_checksum,
        )
        if metadata[12] != stored_catalog_checksum:
            raise CatalogRepairRefusedError(
                "catalog audit checksum is not valid for its stored identity"
            )
        replacement_catalog_checksum = _catalog_checksum(
            manifest=manifest,
            manifest_checksum=manifest_checksum,
            run_dir=run_dir,
            products=current_products,
            quality_rows=quality_rows,
            quality_record_audit=quality_record_audit,
            views_sql_checksum=views_sql_checksum,
        )
        if _stored_quality_rows(connection) != tuple(sorted(quality_rows)):
            raise CatalogRepairRefusedError(
                "catalog quality metadata changed beyond device identity"
            )
        if _stored_quality_record_audit(connection) != quality_record_audit:
            raise CatalogRepairRefusedError(
                "catalog quality records changed beyond device identity"
            )
        if _stored_catalog_view_rows(connection) != tuple(
            sorted(
                _catalog_view_rows(
                    current_products,
                    views_sql_checksum=views_sql_checksum,
                )
            )
        ):
            raise CatalogRepairRefusedError(
                "catalog view metadata changed beyond device identity"
            )
        _verify_view_plans(
            connection,
            products=current_products,
            views_sql=views_sql,
        )
        _validate_catalog_contents(connection, manifest=manifest)
    except CatalogRepairRefusedError:
        raise
    except Exception as error:
        raise CatalogRepairRefusedError(
            "catalog could not be proven safe for device-drift repair"
        ) from error
    finally:
        connection.close()

    _verify_trusted_manifest(run_dir, expected=manifest)
    _assert_snapshots_unchanged(run_dir, manifest, snapshots)
    if _target_identity(target) != target_identity:
        raise CatalogRepairRefusedError(
            "catalog path changed during device-drift inspection"
        )
    return CatalogDeviceIdentityDriftEvidence(
        catalog_path=target,
        catalog_device=target_identity.device,
        catalog_inode=target_identity.inode,
        run_id=manifest.run_id,
        previous_catalog_checksum=stored_catalog_checksum,
        replacement_catalog_checksum=replacement_catalog_checksum,
    )


def inspect_catalog_device_identity_drift(
    run_dir: Path,
    catalog_path: Path,
    *,
    expected_manifest: RunManifest,
) -> CatalogDeviceIdentityDriftEvidence | None:
    """Return strict rebuild evidence, or ``None`` for a healthy catalog."""

    published_run = Path(run_dir)
    manifest = _verify_trusted_manifest(
        published_run,
        expected=expected_manifest,
    )
    published_run = published_run.resolve(strict=True)
    target, _ = _normalize_catalog_path(Path(catalog_path), create_parent=False)
    _require_catalog_outside_run(target, published_run)
    try:
        connection = open_catalog(
            target,
            run_dir=published_run,
            expected_manifest=manifest,
        )
    except CatalogVerificationError:
        pass
    else:
        connection.close()
        return None
    return _verify_device_drift_rebuild_evidence(
        target,
        run_dir=published_run,
        manifest=manifest,
    )


def repair_catalog_device_identity_drift(
    run_dir: Path,
    catalog_path: Path,
    *,
    expected_manifest: RunManifest,
) -> CatalogBuildResult | None:
    """Rebuild a derived catalog only when device drift is strictly proven.

    A healthy catalog is left untouched. Missing, corrupt, replaced, or product-
    inconsistent catalogs are never repaired by this path.
    """

    evidence = inspect_catalog_device_identity_drift(
        run_dir,
        catalog_path,
        expected_manifest=expected_manifest,
    )
    if evidence is None:
        return None
    target_identity = _FileIdentity(
        evidence.catalog_device,
        evidence.catalog_inode,
    )
    result = build_catalog(
        run_dir,
        evidence.catalog_path,
        expected_manifest=expected_manifest,
        _expected_target_identity=target_identity,
    )
    if result.catalog_checksum != evidence.replacement_catalog_checksum:
        raise CatalogBuildError(
            "guarded rebuild checksum changed after device-drift inspection"
        )
    with open_catalog(
        evidence.catalog_path,
        run_dir=run_dir,
        expected_manifest=expected_manifest,
    ):
        pass
    return result


def open_catalog(
    catalog_path: Path,
    *,
    run_dir: Path,
    expected_manifest: RunManifest,
) -> VerifiedCatalogConnection:
    """Open a catalog read-only after revalidating its run and product paths."""

    published_run = Path(run_dir)
    manifest = _verify_trusted_manifest(published_run, expected=expected_manifest)
    published_run = published_run.resolve(strict=True)
    target, _ = _normalize_catalog_path(Path(catalog_path), create_parent=False)
    _require_catalog_outside_run(target, published_run)
    for value in (str(published_run), str(target), manifest.model_version):
        _require_safe_text(value)
    target_identity = _target_identity(target)
    if target_identity is None:
        raise CatalogVerificationError("catalog file is missing")

    snapshots = _snapshot_products(published_run, manifest)
    products = _discover_products(manifest, snapshots)
    quality_rows = _quality_rows(manifest)
    quality_record_audit = _quality_record_audit(products, manifest=manifest)
    views_sql, views_sql_checksum = _views_sql()
    manifest_checksum = sha256_file(published_run / MANIFEST_FILENAME)
    audit_checksum = _catalog_checksum(
        manifest=manifest,
        manifest_checksum=manifest_checksum,
        run_dir=published_run,
        products=products,
        quality_rows=quality_rows,
        quality_record_audit=quality_record_audit,
        views_sql_checksum=views_sql_checksum,
    )
    try:
        connection = duckdb.connect(str(target), read_only=True)
    except Exception as error:
        raise CatalogVerificationError("catalog file is unreadable") from error
    try:
        metadata = connection.execute(
            "SELECT catalog_schema_version, run_id, run_dir, manifest_checksum, "
            "product_count, stable_view_count, views_sql_checksum, catalog_checksum, "
            "quality_record_count, quality_record_digest "
            "FROM _catalog_metadata"
        ).fetchall()
        if len(metadata) != 1:
            raise CatalogVerificationError("catalog metadata is corrupt")
        stored_schema_version = metadata[0][0]
        if stored_schema_version != CATALOG_SCHEMA_VERSION:
            raise CatalogVerificationError(
                "catalog schema version mismatch: "
                f"expected {CATALOG_SCHEMA_VERSION}, found {stored_schema_version}"
            )
        expected_metadata = [
            (
                CATALOG_SCHEMA_VERSION,
                manifest.run_id,
                str(published_run),
                manifest_checksum,
                sum(product.available for product in products),
                len(STABLE_VIEW_NAMES),
                views_sql_checksum,
                audit_checksum,
                quality_record_audit.count,
                quality_record_audit.digest,
            )
        ]
        if metadata != expected_metadata:
            raise CatalogVerificationError(
                "catalog metadata is corrupt or bound to a different run"
            )
        if _stored_product_records(connection) != _expected_product_records(products):
            raise CatalogVerificationError("catalog product paths were replaced")
        if _stored_quality_rows(connection) != tuple(sorted(quality_rows)):
            raise CatalogVerificationError("catalog quality metadata was replaced")
        if _stored_quality_record_audit(connection) != quality_record_audit:
            raise CatalogVerificationError("catalog quality records were replaced")
        if _stored_catalog_view_rows(connection) != tuple(
            sorted(
                _catalog_view_rows(
                    products,
                    views_sql_checksum=views_sql_checksum,
                )
            )
        ):
            raise CatalogVerificationError("catalog view metadata was replaced")
        _verify_view_plans(
            connection,
            products=products,
            views_sql=views_sql,
        )
        _validate_catalog_contents(connection, manifest=manifest)
        _verify_trusted_manifest(published_run, expected=manifest)
        _assert_snapshots_unchanged(published_run, manifest, snapshots)
        if _target_identity(target) != target_identity:
            raise CatalogVerificationError("catalog path was replaced during open")
        return VerifiedCatalogConnection(
            _connection=connection,
            _catalog_path=target,
            _catalog_identity=target_identity,
            _run_dir=published_run,
            _manifest=manifest,
            _product_snapshots=tuple(snapshots.values()),
        )
    except CatalogError:
        connection.close()
        raise
    except Exception as error:
        connection.close()
        raise CatalogVerificationError("catalog verification failed safely") from error
