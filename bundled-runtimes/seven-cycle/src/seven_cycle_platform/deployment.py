"""Canonical and rollback-safe Circle deployment metadata publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Mapping

from seven_cycle_platform.storage.manifest import sha256_file
from seven_cycle_platform.storage.run_context import (
    RUN_ID_PATTERN,
    canonical_json_bytes,
)


DEPLOYMENT_FILENAME = "deployment.json"
REPAIR_JOURNAL_FILENAME = ".catalog-repair-transaction.json"
_DEPLOYMENT_KEYS = {
    "api_run_id",
    "catalog_checksum",
    "deployment_as_of",
    "deployment_id",
    "schema_version",
    "web_bundle_hash",
    "web_files",
}
_SHA256_LENGTH = 64


class DeploymentError(ValueError):
    """Raised when paired deployment metadata cannot be trusted or committed."""


@dataclass(frozen=True, slots=True)
class DeploymentRepairSnapshot:
    """Anchored deployment state validated against the pre-repair catalog."""

    product_path: Path
    product_identity: tuple[int, int]
    web_path: Path
    web_identity: tuple[int, int]
    web_root: Path
    payload: Mapping[str, object]
    content: bytes
    web_files: Mapping[str, str]


@dataclass(slots=True)
class _Replacement:
    target: Path
    staged: Path
    expected_identity: tuple[int, int] | None
    staged_identity: tuple[int, int]
    backup: Path | None = None
    committed: bool = False


@dataclass(frozen=True, slots=True)
class _LatestGuard:
    path: Path
    identity: tuple[int, int]
    content: bytes
    run_id: str


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DeploymentError("deployment path is invalid") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise DeploymentError("deployment path must be a regular file")
    return path_stat.st_dev, path_stat.st_ino


def _require_real_directory(path: Path) -> tuple[Path, tuple[int, int]]:
    normalized = path.resolve(strict=True)
    path_stat = normalized.lstat()
    if not stat.S_ISDIR(path_stat.st_mode):
        raise DeploymentError("deployment root must be a real directory")
    return normalized, (path_stat.st_dev, path_stat.st_ino)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _web_file_checksums(web_root: Path) -> dict[str, str]:
    normalized_root, root_identity = _require_real_directory(web_root)
    checksums: dict[str, str] = {}
    snapshots: dict[str, tuple[int, int, int, int]] = {}
    for path in sorted(normalized_root.rglob("*")):
        relative_path = path.relative_to(normalized_root).as_posix()
        path_stat = path.lstat()
        if stat.S_ISDIR(path_stat.st_mode):
            continue
        if not stat.S_ISREG(path_stat.st_mode):
            raise DeploymentError("web distribution may contain only regular files")
        if relative_path == f"data/{DEPLOYMENT_FILENAME}":
            continue
        checksums[relative_path] = sha256_file(path)
        snapshots[relative_path] = (
            path_stat.st_dev,
            path_stat.st_ino,
            path_stat.st_size,
            path_stat.st_mtime_ns,
        )
    if _require_real_directory(normalized_root)[1] != root_identity:
        raise DeploymentError("web distribution changed during verification")
    for relative_path, expected in snapshots.items():
        path_stat = (normalized_root / relative_path).lstat()
        actual = (
            path_stat.st_dev,
            path_stat.st_ino,
            path_stat.st_size,
            path_stat.st_mtime_ns,
        )
        if not stat.S_ISREG(path_stat.st_mode) or actual != expected:
            raise DeploymentError("web distribution changed during verification")
    return checksums


def _deployment_payload(
    *,
    catalog_checksum: str,
    deployment_as_of: date,
    run_id: str,
    web_files: Mapping[str, str],
) -> dict[str, object]:
    web_bundle_hash = hashlib.sha256(canonical_json_bytes(web_files)).hexdigest()
    core: dict[str, object] = {
        "api_run_id": run_id,
        "catalog_checksum": catalog_checksum,
        "deployment_as_of": deployment_as_of.isoformat(),
        "schema_version": 1,
        "web_bundle_hash": web_bundle_hash,
        "web_files": dict(web_files),
    }
    deployment_id = hashlib.sha256(canonical_json_bytes(core)).hexdigest()[:16]
    return {**core, "deployment_id": deployment_id}


def _stage_content(target: Path, content: bytes) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _remove_stale_lock(lock_path: Path) -> bool:
    identity = _identity(lock_path)
    if identity is None:
        return True
    try:
        content = lock_path.read_bytes()
        payload = json.loads(content)
    except (OSError, TypeError, ValueError):
        return False
    if (
        not isinstance(payload, dict)
        or set(payload) != {"pid"}
        or not isinstance(payload.get("pid"), int)
        or content != canonical_json_bytes(payload) + b"\n"
        or _process_alive(payload["pid"])
        or _identity(lock_path) != identity
    ):
        return False
    lock_path.unlink()
    _fsync_directory(lock_path.parent)
    return True


def _create_lock(
    lock_path: Path,
    *,
    allow_stale: bool = False,
) -> tuple[int, tuple[int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError as error:
        if not allow_stale or not _remove_stale_lock(lock_path):
            raise DeploymentError(
                "deployment metadata is being updated concurrently"
            ) from error
        descriptor = os.open(lock_path, flags, 0o600)
    lock_stat = os.fstat(descriptor)
    identity = lock_stat.st_dev, lock_stat.st_ino
    try:
        os.write(
            descriptor,
            canonical_json_bytes({"pid": os.getpid()}) + b"\n",
        )
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        if _identity(lock_path) == identity:
            lock_path.unlink()
        raise
    return descriptor, identity


def _remove_lock(lock_path: Path, identity: tuple[int, int]) -> None:
    if _identity(lock_path) == identity:
        lock_path.unlink()


def _replace_transaction(
    replacements: list[_Replacement],
    *,
    lock_path: Path,
) -> None:
    lock_descriptor, lock_identity = _create_lock(lock_path)
    rollback_incomplete = False
    try:
        for replacement in replacements:
            if _identity(replacement.target) != replacement.expected_identity:
                raise DeploymentError("deployment target changed before update")
            if _identity(replacement.staged) != replacement.staged_identity:
                raise DeploymentError("staged deployment replacement changed")
            if replacement.expected_identity is not None:
                replacement.backup = replacement.staged.with_name(
                    f"{replacement.staged.name}.backup"
                )
                os.link(
                    replacement.target,
                    replacement.backup,
                    follow_symlinks=False,
                )
                if _identity(replacement.backup) != replacement.expected_identity:
                    raise DeploymentError("deployment backup identity changed")

        for replacement in replacements:
            if _identity(replacement.target) != replacement.expected_identity:
                raise DeploymentError("deployment target changed during update")
            os.replace(replacement.staged, replacement.target)
            replacement.committed = True
            if _identity(replacement.target) != replacement.staged_identity:
                raise DeploymentError("deployment replacement identity changed")
        for directory in {item.target.parent for item in replacements}:
            _fsync_directory(directory)
    except BaseException as error:
        for replacement in reversed(replacements):
            if not replacement.committed:
                continue
            try:
                if _identity(replacement.target) != replacement.staged_identity:
                    rollback_incomplete = True
                    continue
                if replacement.backup is None:
                    replacement.target.unlink()
                else:
                    os.replace(replacement.backup, replacement.target)
                    replacement.backup = None
                _fsync_directory(replacement.target.parent)
            except BaseException:
                rollback_incomplete = True
        if rollback_incomplete:
            raise DeploymentError(
                "deployment update failed and rollback was incomplete"
            ) from error
        raise
    finally:
        try:
            os.close(lock_descriptor)
        except OSError:
            pass
        try:
            _remove_lock(lock_path, lock_identity)
        except Exception:
            pass
        if not rollback_incomplete:
            for replacement in replacements:
                replacement.staged.unlink(missing_ok=True)
                if replacement.backup is not None:
                    replacement.backup.unlink(missing_ok=True)


def _deployment_targets(
    product_root: Path,
    web_root: Path,
    *,
    create_web_data: bool,
) -> tuple[Path, Path, Path]:
    normalized_product_root, _ = _require_real_directory(product_root)
    normalized_web_root, _ = _require_real_directory(web_root)
    data_dir = normalized_web_root / "data"
    if create_web_data:
        data_dir.mkdir(parents=True, exist_ok=True)
    try:
        data_mode = data_dir.lstat().st_mode
    except OSError as error:
        raise DeploymentError("web deployment parent is missing") from error
    if not stat.S_ISDIR(data_mode):
        raise DeploymentError("web deployment parent must be a real directory")
    return (
        normalized_product_root / DEPLOYMENT_FILENAME,
        data_dir / DEPLOYMENT_FILENAME,
        normalized_product_root / ".deployment-update.lock",
    )


def _checksum(path: Path) -> str | None:
    if _identity(path) is None:
        return None
    try:
        return sha256_file(path)
    except OSError as error:
        raise DeploymentError("transaction file is unreadable") from error


def _latest_matches(guard: _LatestGuard) -> bool:
    try:
        before = _identity(guard.path)
        content = guard.path.read_bytes()
        after = _identity(guard.path)
    except OSError:
        return False
    return (
        before == guard.identity
        and after == guard.identity
        and content == guard.content
        and content
        == canonical_json_bytes({"run_id": guard.run_id}) + b"\n"
    )


def _repair_record(replacement: _Replacement) -> dict[str, object]:
    if replacement.expected_identity is None:
        raise DeploymentError("catalog repair targets must already exist")
    backup = replacement.staged.with_name(f"{replacement.staged.name}.backup")
    os.link(replacement.target, backup, follow_symlinks=False)
    if _identity(backup) != replacement.expected_identity:
        backup.unlink(missing_ok=True)
        raise DeploymentError("catalog repair backup identity changed")
    replacement.backup = backup
    old_checksum = _checksum(replacement.target)
    new_checksum = _checksum(replacement.staged)
    if old_checksum is None or new_checksum is None:
        raise DeploymentError("catalog repair artifacts are invalid")
    return {
        "backup": str(backup),
        "new_checksum": new_checksum,
        "new_identity": list(replacement.staged_identity),
        "old_checksum": old_checksum,
        "old_identity": list(replacement.expected_identity),
        "staged": str(replacement.staged),
        "target": str(replacement.target),
    }


def _write_repair_journal(path: Path, payload: dict[str, object]) -> None:
    content = canonical_json_bytes(payload) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _read_repair_journal(path: Path) -> dict[str, object] | None:
    journal_identity = _identity(path)
    if journal_identity is None:
        return None
    try:
        content = path.read_bytes()
        payload = json.loads(content)
    except (OSError, TypeError, ValueError) as error:
        raise DeploymentError("catalog repair journal is invalid") from error
    if (
        _identity(path) != journal_identity
        or not isinstance(payload, dict)
        or set(payload)
        != {
            "latest_checksum",
            "latest_identity",
            "replacement_catalog_checksum",
            "run_id",
            "schema_version",
            "targets",
        }
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("run_id"), str)
        or not RUN_ID_PATTERN.fullmatch(payload["run_id"])
        or not isinstance(payload.get("latest_checksum"), str)
        or not isinstance(payload.get("latest_identity"), list)
        or len(payload["latest_identity"]) != 2
        or not all(isinstance(value, int) for value in payload["latest_identity"])
        or not isinstance(payload.get("replacement_catalog_checksum"), str)
        or not isinstance(payload.get("targets"), list)
        or len(payload["targets"]) != 3
        or content != canonical_json_bytes(payload) + b"\n"
    ):
        raise DeploymentError("catalog repair journal is not canonical")
    return payload


def _record_identity(record: Mapping[str, object], key: str) -> tuple[int, int]:
    value = record.get(key)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) for item in value)
    ):
        raise DeploymentError("catalog repair journal identity is invalid")
    return value[0], value[1]


def _record_path(record: Mapping[str, object], key: str) -> Path:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise DeploymentError("catalog repair journal path is invalid")
    return Path(value)


def _record_checksum(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        raise DeploymentError("catalog repair journal checksum is invalid")
    return value


def _target_state(record: Mapping[str, object]) -> str:
    target = _record_path(record, "target")
    actual_identity = _identity(target)
    actual_checksum = _checksum(target)
    if (
        actual_identity == _record_identity(record, "old_identity")
        and actual_checksum == _record_checksum(record, "old_checksum")
    ):
        return "old"
    if (
        actual_identity == _record_identity(record, "new_identity")
        and actual_checksum == _record_checksum(record, "new_checksum")
    ):
        return "new"
    return "unknown"


def _artifact_matches(
    record: Mapping[str, object],
    *,
    path_key: str,
    identity_key: str,
    checksum_key: str,
) -> bool:
    path = _record_path(record, path_key)
    return (
        _identity(path) == _record_identity(record, identity_key)
        and _checksum(path) == _record_checksum(record, checksum_key)
    )


def _forward_repair(
    records: list[Mapping[str, object]],
    *,
    latest_guard: _LatestGuard,
) -> None:
    for record in records:
        if not _latest_matches(latest_guard):
            raise DeploymentError("latest run changed before catalog repair commit")
        state = _target_state(record)
        if state == "new":
            continue
        if state != "old" or not _artifact_matches(
            record,
            path_key="staged",
            identity_key="new_identity",
            checksum_key="new_checksum",
        ):
            raise DeploymentError("pending catalog repair cannot move forward safely")
        os.replace(_record_path(record, "staged"), _record_path(record, "target"))
        if _target_state(record) != "new":
            raise DeploymentError("catalog repair replacement identity changed")
        _fsync_directory(_record_path(record, "target").parent)
    if not _latest_matches(latest_guard):
        raise DeploymentError("latest run changed before catalog repair completion")
    if any(_target_state(record) != "new" for record in records):
        raise DeploymentError("catalog repair did not reach a consistent new state")


def _rollback_repair(records: list[Mapping[str, object]]) -> bool:
    for record in reversed(records):
        state = _target_state(record)
        if state == "old":
            continue
        if state != "new" or not _artifact_matches(
            record,
            path_key="backup",
            identity_key="old_identity",
            checksum_key="old_checksum",
        ):
            return False
        os.replace(_record_path(record, "backup"), _record_path(record, "target"))
        if _target_state(record) != "old":
            return False
        _fsync_directory(_record_path(record, "target").parent)
    return all(_target_state(record) == "old" for record in records)


def _cleanup_repair_artifacts(
    records: list[Mapping[str, object]],
    journal_path: Path,
) -> None:
    for record in records:
        for path_key, identity_key, checksum_key in (
            ("staged", "new_identity", "new_checksum"),
            ("backup", "old_identity", "old_checksum"),
        ):
            try:
                if _artifact_matches(
                    record,
                    path_key=path_key,
                    identity_key=identity_key,
                    checksum_key=checksum_key,
                ):
                    _record_path(record, path_key).unlink()
            except (DeploymentError, OSError):
                pass
    journal_path.unlink(missing_ok=True)
    _fsync_directory(journal_path.parent)


def _journal_records(
    payload: Mapping[str, object],
    *,
    product_root: Path,
    catalog_root: Path,
    web_root: Path,
) -> tuple[list[Mapping[str, object]], _LatestGuard]:
    run_id = str(payload["run_id"])
    product_path, web_path, _ = _deployment_targets(
        product_root,
        web_root,
        create_web_data=False,
    )
    expected_targets = (
        Path(catalog_root).resolve(strict=True) / f"{run_id}.duckdb",
        product_path,
        web_path,
    )
    raw_records = payload["targets"]
    if not isinstance(raw_records, list):
        raise DeploymentError("catalog repair journal targets are invalid")
    records: list[Mapping[str, object]] = []
    for raw, expected_target in zip(raw_records, expected_targets, strict=True):
        if not isinstance(raw, dict) or set(raw) != {
            "backup",
            "new_checksum",
            "new_identity",
            "old_checksum",
            "old_identity",
            "staged",
            "target",
        }:
            raise DeploymentError("catalog repair journal target is invalid")
        if _record_path(raw, "target") != expected_target:
            raise DeploymentError("catalog repair journal target escaped its root")
        allowed_root = expected_target.parent
        if expected_target == expected_targets[0]:
            allowed_root = Path(catalog_root).resolve(strict=True)
        for key in ("staged", "backup"):
            candidate = _record_path(raw, key)
            try:
                candidate.relative_to(allowed_root)
            except ValueError as error:
                raise DeploymentError(
                    "catalog repair artifact escaped its approved root"
                ) from error
        _record_identity(raw, "old_identity")
        _record_identity(raw, "new_identity")
        _record_checksum(raw, "old_checksum")
        _record_checksum(raw, "new_checksum")
        records.append(raw)
    latest_path = Path(product_root).resolve(strict=True) / "latest.json"
    latest_guard = _LatestGuard(
        path=latest_path,
        identity=(
            int(payload["latest_identity"][0]),
            int(payload["latest_identity"][1]),
        ),
        content=canonical_json_bytes({"run_id": run_id}) + b"\n",
        run_id=run_id,
    )
    if hashlib.sha256(latest_guard.content).hexdigest() != payload["latest_checksum"]:
        raise DeploymentError("catalog repair journal latest checksum is invalid")
    return records, latest_guard


def write_deployment_manifest(
    *,
    product_root: Path,
    catalog_checksum: str,
    run_id: str,
    deployment_as_of: date,
    web_root: Path,
) -> tuple[Path, str]:
    """Publish canonical product and web deployment manifests as one transaction."""

    product_path, web_path, lock_path = _deployment_targets(
        product_root,
        web_root,
        create_web_data=True,
    )
    web_files = _web_file_checksums(web_root)
    payload = _deployment_payload(
        catalog_checksum=catalog_checksum,
        deployment_as_of=deployment_as_of,
        run_id=run_id,
        web_files=web_files,
    )
    content = canonical_json_bytes(payload) + b"\n"
    replacements: list[_Replacement] = []
    try:
        for target in (product_path, web_path):
            staged = _stage_content(target, content)
            staged_identity = _identity(staged)
            if staged_identity is None:
                raise DeploymentError("staged deployment replacement is invalid")
            replacements.append(
                _Replacement(
                    target=target,
                    staged=staged,
                    expected_identity=_identity(target),
                    staged_identity=staged_identity,
                )
            )
        _replace_transaction(replacements, lock_path=lock_path)
    finally:
        for replacement in replacements:
            replacement.staged.unlink(missing_ok=True)
            if replacement.backup is not None:
                replacement.backup.unlink(missing_ok=True)
    return product_path, str(payload["deployment_id"])


def verify_deployment_for_catalog_repair(
    *,
    product_root: Path,
    web_root: Path,
    run_id: str,
    catalog_checksum: str,
) -> DeploymentRepairSnapshot:
    """Verify both deployment copies and every referenced web artifact."""

    product_path, web_path, _ = _deployment_targets(
        product_root,
        web_root,
        create_web_data=False,
    )
    product_identity = _identity(product_path)
    web_identity = _identity(web_path)
    if product_identity is None or web_identity is None:
        raise DeploymentError("deployment metadata is missing")
    try:
        product_content = product_path.read_bytes()
        web_content = web_path.read_bytes()
        payload = json.loads(product_content)
    except (OSError, TypeError, ValueError) as error:
        raise DeploymentError("deployment metadata is invalid") from error
    if product_content != web_content:
        raise DeploymentError("deployment metadata copies do not match")
    if (
        not isinstance(payload, dict)
        or set(payload) != _DEPLOYMENT_KEYS
        or payload.get("schema_version") != 1
        or payload.get("api_run_id") != run_id
        or payload.get("catalog_checksum") != catalog_checksum
        or not isinstance(payload.get("deployment_id"), str)
        or not isinstance(payload.get("deployment_as_of"), str)
        or not isinstance(payload.get("web_bundle_hash"), str)
        or not isinstance(payload.get("web_files"), dict)
        or product_content != canonical_json_bytes(payload) + b"\n"
    ):
        raise DeploymentError("deployment metadata is not safely repairable")
    try:
        deployment_as_of = date.fromisoformat(payload["deployment_as_of"])
    except ValueError as error:
        raise DeploymentError("deployment date is invalid") from error
    web_files = _web_file_checksums(web_root)
    expected_payload = _deployment_payload(
        catalog_checksum=catalog_checksum,
        deployment_as_of=deployment_as_of,
        run_id=run_id,
        web_files=web_files,
    )
    if payload != expected_payload:
        raise DeploymentError("deployment audit metadata is invalid")
    if (
        _identity(product_path) != product_identity
        or _identity(web_path) != web_identity
        or product_path.read_bytes() != product_content
        or web_path.read_bytes() != web_content
        or _web_file_checksums(web_root) != web_files
    ):
        raise DeploymentError("deployment metadata changed during verification")
    return DeploymentRepairSnapshot(
        product_path=product_path,
        product_identity=product_identity,
        web_path=web_path,
        web_identity=web_identity,
        web_root=Path(web_root).resolve(strict=True),
        payload=payload,
        content=product_content,
        web_files=web_files,
    )


def recover_pending_catalog_repair(
    *,
    product_root: Path,
    catalog_root: Path,
    web_root: Path,
) -> dict[str, str] | None:
    """Finish or roll back a durable repair journal before normal startup."""

    normalized_product_root, _ = _require_real_directory(product_root)
    journal_path = normalized_product_root / REPAIR_JOURNAL_FILENAME
    payload = _read_repair_journal(journal_path)
    if payload is None:
        return None
    records, latest_guard = _journal_records(
        payload,
        product_root=product_root,
        catalog_root=catalog_root,
        web_root=web_root,
    )
    catalog_target = _record_path(records[0], "target")
    catalog_lock_path = catalog_target.with_name(f".{catalog_target.name}.lock")
    catalog_lock_descriptor, catalog_lock_identity = _create_lock(
        catalog_lock_path,
        allow_stale=True,
    )
    deployment_lock_path = normalized_product_root / ".deployment-update.lock"
    deployment_lock_descriptor: int | None = None
    deployment_lock_identity: tuple[int, int] | None = None
    try:
        deployment_lock_descriptor, deployment_lock_identity = _create_lock(
            deployment_lock_path,
            allow_stale=True,
        )
        if _latest_matches(latest_guard):
            try:
                _forward_repair(records, latest_guard=latest_guard)
            except BaseException as error:
                if not _rollback_repair(records):
                    raise DeploymentError(
                        "pending catalog repair requires manual recovery"
                    ) from error
                _cleanup_repair_artifacts(records, journal_path)
                return {
                    "action": "rolled_back_pending_repair",
                    "run_id": latest_guard.run_id,
                }
            _cleanup_repair_artifacts(records, journal_path)
            return {
                "action": "completed_pending_repair",
                "catalog_checksum": str(payload["replacement_catalog_checksum"]),
                "run_id": latest_guard.run_id,
            }
        if not _rollback_repair(records):
            raise DeploymentError(
                "latest changed and pending catalog repair could not roll back"
            )
        _cleanup_repair_artifacts(records, journal_path)
        return {
            "action": "rolled_back_pending_repair_after_latest_change",
            "run_id": latest_guard.run_id,
        }
    finally:
        if deployment_lock_descriptor is not None:
            os.close(deployment_lock_descriptor)
        if deployment_lock_identity is not None:
            try:
                _remove_lock(deployment_lock_path, deployment_lock_identity)
            except Exception:
                pass
        os.close(catalog_lock_descriptor)
        try:
            _remove_lock(catalog_lock_path, catalog_lock_identity)
        except Exception:
            pass


def install_catalog_repair_transaction(
    *,
    snapshot: DeploymentRepairSnapshot,
    catalog_path: Path,
    catalog_identity: tuple[int, int],
    candidate_catalog_path: Path,
    latest_content: bytes,
    latest_identity: tuple[int, int],
    latest_path: Path,
    replacement_catalog_checksum: str,
) -> str:
    """Install one candidate Catalog and both deployment references together."""

    if not RUN_ID_PATTERN.fullmatch(str(snapshot.payload["api_run_id"])):
        raise DeploymentError("deployment run id is invalid")
    if len(replacement_catalog_checksum) != _SHA256_LENGTH:
        raise DeploymentError("replacement catalog checksum is invalid")
    if (
        _identity(snapshot.product_path) != snapshot.product_identity
        or _identity(snapshot.web_path) != snapshot.web_identity
        or snapshot.product_path.read_bytes() != snapshot.content
        or snapshot.web_path.read_bytes() != snapshot.content
    ):
        raise DeploymentError("deployment metadata changed before catalog repair")
    deployment_as_of = date.fromisoformat(str(snapshot.payload["deployment_as_of"]))
    if _web_file_checksums(snapshot.web_root) != dict(snapshot.web_files):
        raise DeploymentError("web distribution changed before catalog repair")
    payload = _deployment_payload(
        catalog_checksum=replacement_catalog_checksum,
        deployment_as_of=deployment_as_of,
        run_id=str(snapshot.payload["api_run_id"]),
        web_files=snapshot.web_files,
    )
    content = canonical_json_bytes(payload) + b"\n"
    latest_guard = _LatestGuard(
        path=Path(latest_path),
        identity=latest_identity,
        content=latest_content,
        run_id=str(snapshot.payload["api_run_id"]),
    )
    if not _latest_matches(latest_guard):
        raise DeploymentError("latest run changed before catalog repair staging")
    product_staged: Path | None = None
    web_staged: Path | None = None
    replacements: list[_Replacement] = []
    records: list[Mapping[str, object]] = []
    candidate = Path(candidate_catalog_path)
    candidate_identity = _identity(candidate)
    if candidate_identity is None:
        raise DeploymentError("candidate catalog is invalid")
    catalog_lock_path = Path(catalog_path).with_name(
        f".{Path(catalog_path).name}.lock"
    )
    catalog_lock_descriptor: int | None = None
    catalog_lock_identity: tuple[int, int] | None = None
    deployment_lock_descriptor: int | None = None
    deployment_lock_identity: tuple[int, int] | None = None
    journal_path = snapshot.product_path.parent / REPAIR_JOURNAL_FILENAME
    preserve_journal = False
    try:
        product_staged = _stage_content(snapshot.product_path, content)
        web_staged = _stage_content(snapshot.web_path, content)
        product_staged_identity = _identity(product_staged)
        web_staged_identity = _identity(web_staged)
        if product_staged_identity is None or web_staged_identity is None:
            raise DeploymentError("staged catalog repair replacement is invalid")
        replacements = [
            _Replacement(
                target=Path(catalog_path),
                staged=candidate,
                expected_identity=catalog_identity,
                staged_identity=candidate_identity,
            ),
            _Replacement(
                target=snapshot.product_path,
                staged=product_staged,
                expected_identity=snapshot.product_identity,
                staged_identity=product_staged_identity,
            ),
            _Replacement(
                target=snapshot.web_path,
                staged=web_staged,
                expected_identity=snapshot.web_identity,
                staged_identity=web_staged_identity,
            ),
        ]
        catalog_lock_descriptor, catalog_lock_identity = _create_lock(
            catalog_lock_path
        )
        deployment_lock_path = snapshot.product_path.parent / ".deployment-update.lock"
        deployment_lock_descriptor, deployment_lock_identity = _create_lock(
            deployment_lock_path
        )
        if _read_repair_journal(journal_path) is not None:
            raise DeploymentError("a catalog repair journal is already pending")
        for replacement in replacements:
            if _identity(replacement.target) != replacement.expected_identity:
                raise DeploymentError("catalog repair target changed before journal")
            records.append(_repair_record(replacement))
        journal_payload: dict[str, object] = {
            "latest_checksum": hashlib.sha256(latest_content).hexdigest(),
            "latest_identity": list(latest_identity),
            "replacement_catalog_checksum": replacement_catalog_checksum,
            "run_id": latest_guard.run_id,
            "schema_version": 1,
            "targets": records,
        }
        _write_repair_journal(journal_path, journal_payload)
        try:
            _forward_repair(records, latest_guard=latest_guard)
        except BaseException as error:
            if not _rollback_repair(records):
                preserve_journal = True
                raise DeploymentError(
                    "catalog repair was interrupted; durable recovery is pending"
                ) from error
            _cleanup_repair_artifacts(records, journal_path)
            raise
        _cleanup_repair_artifacts(records, journal_path)
    finally:
        if deployment_lock_descriptor is not None:
            os.close(deployment_lock_descriptor)
        if deployment_lock_identity is not None:
            try:
                _remove_lock(
                    snapshot.product_path.parent / ".deployment-update.lock",
                    deployment_lock_identity,
                )
            except Exception:
                pass
        if catalog_lock_descriptor is not None:
            os.close(catalog_lock_descriptor)
        if catalog_lock_identity is not None:
            try:
                _remove_lock(catalog_lock_path, catalog_lock_identity)
            except Exception:
                pass
        if not preserve_journal:
            for path in (product_staged, web_staged):
                if path is not None:
                    path.unlink(missing_ok=True)
            for replacement in replacements:
                if replacement.backup is not None:
                    replacement.backup.unlink(missing_ok=True)
    return str(payload["deployment_id"])
