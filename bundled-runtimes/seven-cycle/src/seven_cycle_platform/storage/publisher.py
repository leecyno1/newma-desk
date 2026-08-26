"""Atomic publication for immutable seven-cycle product runs."""

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

from seven_cycle_platform.storage.manifest import (
    RunManifest,
    collect_product_checksums,
    verify_manifest,
    write_manifest,
)
from seven_cycle_platform.storage.run_context import (
    RunContext,
    canonical_json_bytes,
)


StagingWriter = Callable[[Path], None]
StagingValidator = Callable[[Path, RunManifest], None]
PublishedValidator = Callable[[Path, RunManifest], None]


@dataclass(frozen=True)
class _DirectoryIdentity:
    device: int
    inode: int


def _directory_identity(directory: Path, *, label: str) -> _DirectoryIdentity:
    try:
        directory_stat = directory.lstat()
    except OSError as error:
        raise ValueError(f"{label} must be a real directory") from error
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError(f"{label} must be a real directory")
    return _DirectoryIdentity(
        device=directory_stat.st_dev,
        inode=directory_stat.st_ino,
    )


def _ensure_real_directory(
    directory: Path,
    *,
    label: str,
    parents: bool = False,
) -> _DirectoryIdentity:
    try:
        directory_stat = directory.lstat()
    except FileNotFoundError:
        try:
            directory.mkdir(parents=parents)
        except FileExistsError:
            pass
    except OSError as error:
        raise ValueError(f"{label} must be a real directory") from error
    else:
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise ValueError(f"{label} must be a real directory")
    return _directory_identity(directory, label=label)


def _assert_directory_identity(
    directory: Path,
    *,
    label: str,
    expected: _DirectoryIdentity,
) -> None:
    actual = _directory_identity(directory, label=label)
    if actual != expected:
        raise ValueError(f"{label} was replaced during publication")


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _fsync_directory(directory: Path) -> None:
    _directory_identity(directory, label="directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(directory, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _fsync_staged_tree(
    staging_dir: Path,
    *,
    expected_identity: _DirectoryIdentity,
) -> None:
    _assert_directory_identity(
        staging_dir,
        label="staging directory",
        expected=expected_identity,
    )
    staged_paths = sorted(
        staging_dir.rglob("*"),
        key=lambda path: path.relative_to(staging_dir).as_posix(),
    )
    directories = [staging_dir]
    for path in staged_paths:
        path_mode = path.lstat().st_mode
        if stat.S_ISLNK(path_mode):
            raise ValueError("staged runs cannot contain symlinks")
        if stat.S_ISDIR(path_mode):
            directories.append(path)
            continue
        if not stat.S_ISREG(path_mode):
            raise ValueError("staged runs may contain only regular files")
        with path.open("rb", buffering=0) as staged_file:
            os.fsync(staged_file.fileno())
    for directory in sorted(
        directories,
        key=lambda path: len(path.relative_to(staging_dir).parts),
        reverse=True,
    ):
        _fsync_directory(directory)


def _assert_publication_layout(
    *,
    product_root: Path,
    product_identity: _DirectoryIdentity,
    staging_root: Path,
    staging_root_identity: _DirectoryIdentity,
    runs_root: Path,
    runs_root_identity: _DirectoryIdentity,
    staging_dir: Path,
    staging_identity: _DirectoryIdentity,
) -> None:
    _assert_directory_identity(
        product_root,
        label="product root",
        expected=product_identity,
    )
    _assert_directory_identity(
        staging_root,
        label="staging root",
        expected=staging_root_identity,
    )
    _assert_directory_identity(
        runs_root,
        label="runs root",
        expected=runs_root_identity,
    )
    _assert_directory_identity(
        staging_dir,
        label="staging directory",
        expected=staging_identity,
    )


def _cleanup_staging(
    staging_root: Path,
    staging_dir: Path,
    *,
    expected_staging_root: _DirectoryIdentity,
) -> None:
    try:
        _assert_directory_identity(
            staging_root,
            label="staging root",
            expected=expected_staging_root,
        )
        staging_stat = staging_dir.lstat()
    except (FileNotFoundError, ValueError):
        return
    if stat.S_ISDIR(staging_stat.st_mode):
        shutil.rmtree(staging_dir)
    else:
        staging_dir.unlink(missing_ok=True)


def _assert_published_layout(
    *,
    product_root: Path,
    product_identity: _DirectoryIdentity,
    staging_root: Path,
    staging_root_identity: _DirectoryIdentity,
    runs_root: Path,
    runs_root_identity: _DirectoryIdentity,
    destination: Path,
    destination_identity: _DirectoryIdentity,
) -> None:
    _assert_directory_identity(
        product_root,
        label="product root",
        expected=product_identity,
    )
    _assert_directory_identity(
        staging_root,
        label="staging root",
        expected=staging_root_identity,
    )
    _assert_directory_identity(
        runs_root,
        label="runs root",
        expected=runs_root_identity,
    )
    _assert_directory_identity(
        destination,
        label="published run directory",
        expected=destination_identity,
    )


def _isolate_failed_destination(
    runs_root: Path,
    destination: Path,
    *,
    expected_runs_root: _DirectoryIdentity,
    expected_destination: _DirectoryIdentity,
) -> Path | None:
    """Move only the known failed inode away from its canonical live run id."""

    try:
        _assert_directory_identity(
            runs_root,
            label="runs root",
            expected=expected_runs_root,
        )
        actual_destination = _directory_identity(
            destination,
            label="published run directory",
        )
    except (FileNotFoundError, ValueError):
        return None
    if actual_destination != expected_destination:
        return None

    quarantine = runs_root / (f".failed.{destination.name}.{uuid.uuid4().hex}")
    try:
        os.rename(destination, quarantine)
    except OSError:
        return None
    try:
        quarantined_identity = _directory_identity(
            quarantine,
            label="isolated failed run directory",
        )
    except ValueError:
        return quarantine
    if quarantined_identity != expected_destination:
        if not _path_entry_exists(destination):
            try:
                os.rename(quarantine, destination)
            except OSError:
                pass
        return None
    _fsync_directory(runs_root)
    return quarantine


def _atomic_replace_latest(
    product_root: Path,
    run_id: str,
    *,
    expected_product_root: _DirectoryIdentity,
) -> None:
    _assert_directory_identity(
        product_root,
        label="product root",
        expected=expected_product_root,
    )
    latest_path = product_root / "latest.json"
    pointer_bytes = canonical_json_bytes({"run_id": run_id}) + b"\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=product_root,
        prefix=".latest.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            descriptor_open = False
            temporary_file.write(pointer_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, latest_path)
        _fsync_directory(product_root)
    finally:
        if descriptor_open:
            os.close(file_descriptor)
        temporary_path.unlink(missing_ok=True)


def publish_run(
    product_root: Path,
    context: RunContext,
    *,
    write_staging: StagingWriter,
    validate_staging: StagingValidator | None = None,
    validate_published: PublishedValidator | None = None,
) -> RunManifest:
    """Build, verify, promote, post-validate, and point to one immutable run."""

    product_root = Path(product_root)
    staging_root = product_root / "staging"
    runs_root = product_root / "runs"
    staging_dir = staging_root / context.run_id
    destination = runs_root / context.run_id

    product_identity = _ensure_real_directory(
        product_root,
        label="product root",
        parents=True,
    )
    staging_root_identity = _ensure_real_directory(
        staging_root,
        label="staging root",
    )
    runs_root_identity = _ensure_real_directory(
        runs_root,
        label="runs root",
    )
    if staging_root_identity.device != runs_root_identity.device:
        raise ValueError("staging root and runs root must share a filesystem")

    if _path_entry_exists(destination):
        raise FileExistsError(
            f"published run destinations are immutable: {destination}"
        )
    if _path_entry_exists(staging_dir):
        raise FileExistsError(f"staging directory already exists: {staging_dir}")

    staging_dir.mkdir()
    staging_identity = _directory_identity(
        staging_dir,
        label="staging directory",
    )
    destination_promoted = False
    pre_latest_gate_complete = False
    try:
        write_staging(staging_dir)
        _assert_publication_layout(
            product_root=product_root,
            product_identity=product_identity,
            staging_root=staging_root,
            staging_root_identity=staging_root_identity,
            runs_root=runs_root,
            runs_root_identity=runs_root_identity,
            staging_dir=staging_dir,
            staging_identity=staging_identity,
        )
        product_checksums = collect_product_checksums(staging_dir)
        finalized_context = context.with_product_checksums(product_checksums)
        manifest = RunManifest.from_context(finalized_context)
        write_manifest(staging_dir, manifest)
        _fsync_staged_tree(
            staging_dir,
            expected_identity=staging_identity,
        )
        verify_manifest(staging_dir, expected=manifest)

        if validate_staging is not None:
            validate_staging(staging_dir, manifest)

        _assert_publication_layout(
            product_root=product_root,
            product_identity=product_identity,
            staging_root=staging_root,
            staging_root_identity=staging_root_identity,
            runs_root=runs_root,
            runs_root_identity=runs_root_identity,
            staging_dir=staging_dir,
            staging_identity=staging_identity,
        )
        verify_manifest(staging_dir, expected=manifest)
        if _path_entry_exists(destination):
            raise FileExistsError(
                f"published run destinations are immutable: {destination}"
            )
        try:
            os.rename(staging_dir, destination)
        except OSError as error:
            if destination.exists():
                raise FileExistsError(
                    f"published run destinations are immutable: {destination}"
                ) from error
            raise
        destination_promoted = True
        if (
            _directory_identity(
                destination,
                label="published run directory",
            )
            != staging_identity
        ):
            raise ValueError("published run directory identity changed")
        _fsync_directory(staging_root)
        _fsync_directory(runs_root)
        verify_manifest(destination, expected=manifest)

        if validate_published is not None:
            validate_published(destination, manifest)

        _assert_published_layout(
            product_root=product_root,
            product_identity=product_identity,
            staging_root=staging_root,
            staging_root_identity=staging_root_identity,
            runs_root=runs_root,
            runs_root_identity=runs_root_identity,
            destination=destination,
            destination_identity=staging_identity,
        )
        verify_manifest(destination, expected=manifest)
        pre_latest_gate_complete = True
        _atomic_replace_latest(
            product_root,
            manifest.run_id,
            expected_product_root=product_identity,
        )
        return manifest
    except BaseException:
        if destination_promoted and not pre_latest_gate_complete:
            _isolate_failed_destination(
                runs_root,
                destination,
                expected_runs_root=runs_root_identity,
                expected_destination=staging_identity,
            )
        _cleanup_staging(
            staging_root,
            staging_dir,
            expected_staging_root=staging_root_identity,
        )
        raise
