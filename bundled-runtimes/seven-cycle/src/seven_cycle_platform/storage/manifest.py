"""Strict run manifests and staged-product checksum verification."""

import hashlib
from pathlib import Path
import stat
from typing import Literal, Self

from pydantic import ValidationError

from seven_cycle_platform.storage.run_context import RunContext


MANIFEST_FILENAME = "manifest.json"


class ManifestVerificationError(ValueError):
    """Raised when a staged or published run does not match its manifest."""


class RunManifest(RunContext):
    """Versioned immutable manifest stored with each published run."""

    schema_version: Literal[1] = 1

    @classmethod
    def from_context(cls, context: RunContext) -> Self:
        return cls.model_validate(context.model_dump(mode="python"))


def _require_real_run_directory(run_dir: Path) -> tuple[int, int]:
    try:
        run_stat = run_dir.lstat()
    except OSError as error:
        raise ManifestVerificationError(
            "run directory must be a real directory"
        ) from error
    if not stat.S_ISDIR(run_stat.st_mode):
        raise ManifestVerificationError(
            "run directory must be a real directory"
        )
    return run_stat.st_dev, run_stat.st_ino


def _require_regular_manifest(manifest_path: Path) -> None:
    try:
        manifest_stat = manifest_path.lstat()
    except OSError as error:
        raise ManifestVerificationError("manifest is missing or invalid") from error
    if not stat.S_ISREG(manifest_stat.st_mode):
        raise ManifestVerificationError("manifest is missing or invalid")


def sha256_file(path: Path) -> str:
    """Hash one regular file without loading it fully into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as product_file:
        for chunk in iter(lambda: product_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_product_checksums(run_dir: Path) -> dict[str, str]:
    """Collect deterministic checksums for all non-manifest regular files."""

    run_identity = _require_real_run_directory(run_dir)
    checksums: dict[str, str] = {}
    paths = sorted(
        run_dir.rglob("*"),
        key=lambda path: path.relative_to(run_dir).as_posix(),
    )
    for path in paths:
        relative_path = path.relative_to(run_dir)
        relative_name = relative_path.as_posix()
        if relative_name == MANIFEST_FILENAME:
            continue
        path_mode = path.lstat().st_mode
        if stat.S_ISLNK(path_mode):
            raise ManifestVerificationError(
                f"staged products cannot contain symlinks: {relative_name}"
            )
        if stat.S_ISDIR(path_mode):
            continue
        if not stat.S_ISREG(path_mode):
            raise ManifestVerificationError(
                f"staged product is not a regular file: {relative_name}"
            )
        checksums[relative_name] = sha256_file(path)
    if _require_real_run_directory(run_dir) != run_identity:
        raise ManifestVerificationError(
            "run directory changed during checksum collection"
        )
    return checksums


def write_manifest(run_dir: Path, manifest: RunManifest) -> Path:
    """Write a canonical manifest without replacing caller-created files."""

    _require_real_run_directory(run_dir)
    manifest_path = run_dir / MANIFEST_FILENAME
    with manifest_path.open("xb") as manifest_file:
        manifest_file.write(manifest.to_json_bytes())
    return manifest_path


def load_manifest(run_dir: Path) -> RunManifest:
    """Parse one strict manifest without asserting external authenticity."""

    _require_real_run_directory(run_dir)
    manifest_path = run_dir / MANIFEST_FILENAME
    _require_regular_manifest(manifest_path)
    try:
        return RunManifest.model_validate_json(manifest_path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise ManifestVerificationError("manifest is missing or invalid") from error


def verify_manifest(
    run_dir: Path,
    *,
    expected: RunManifest,
) -> RunManifest:
    """Verify self-consistency against a trusted expected manifest."""

    run_identity = _require_real_run_directory(run_dir)
    manifest_path = run_dir / MANIFEST_FILENAME
    manifest = load_manifest(run_dir)
    if manifest.run_id != run_dir.name:
        raise ManifestVerificationError(
            "manifest run_id does not match its run directory"
        )
    if manifest_path.read_bytes() != manifest.to_json_bytes():
        raise ManifestVerificationError("manifest JSON is not canonical")
    if manifest != expected:
        raise ManifestVerificationError(
            "manifest does not match the trusted expected manifest"
        )
    actual_checksums = collect_product_checksums(run_dir)
    if actual_checksums != manifest.product_checksums:
        raise ManifestVerificationError(
            "manifest product checksums do not match staged files"
        )
    if _require_real_run_directory(run_dir) != run_identity:
        raise ManifestVerificationError(
            "run directory changed during manifest verification"
        )
    return manifest
