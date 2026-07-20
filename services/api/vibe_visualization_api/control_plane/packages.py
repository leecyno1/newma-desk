import io
import json
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from vibe_visualization_api.control_plane.schemas import (
    ModuleManifest,
    manifest_repository_dict,
)


MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_FILES = 2_000
ALLOWED_ROOT_FILES = {"module.json"}
READ_CHUNK_BYTES = 1024 * 1024
DETERMINISTIC_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ModulePackageError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def safe_member_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and "\x00" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
    )


def _remove_directory(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def _ensure_package_root(package_root: Path) -> None:
    if package_root.is_symlink():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )
    try:
        package_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ModulePackageError(
            "module package storage is unavailable",
            status_code=500,
        ) from error
    if not package_root.is_dir() or package_root.is_symlink():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )


def _validate_existing_package_root(package_root: Path) -> None:
    if package_root.is_symlink() or (
        package_root.exists() and not package_root.is_dir()
    ):
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )


def _member_is_link(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)


def _member_has_unsupported_type(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    return file_type not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}


def _validated_members(
    archive: zipfile.ZipFile,
) -> tuple[list[zipfile.ZipInfo], dict[str, zipfile.ZipInfo]]:
    members = archive.infolist()
    if len(members) > MAX_FILES:
        raise ModulePackageError("module package contains too many files")
    file_members: dict[str, zipfile.ZipInfo] = {}
    seen_paths: set[str] = set()
    total_uncompressed = 0

    for member in members:
        name = member.filename
        if not safe_member_path(name):
            raise ModulePackageError("module package contains an unsafe path")
        if member.flag_bits & 0x1:
            raise ModulePackageError("module package contains an encrypted file")
        if _member_is_link(member):
            raise ModulePackageError("module package contains a link")
        if _member_has_unsupported_type(member):
            raise ModulePackageError("module package contains an unsupported file type")

        is_directory = member.is_dir()
        unix_file_type = stat.S_IFMT(member.external_attr >> 16)
        if (is_directory and unix_file_type == stat.S_IFREG) or (
            not is_directory and unix_file_type == stat.S_IFDIR
        ):
            raise ModulePackageError("module package contains an unsafe path")
        raw_path = name[:-1] if is_directory and name.endswith("/") else name
        path = PurePosixPath(raw_path)
        normalized_name = path.as_posix()
        raw_parts = raw_path.split("/")
        if (
            not raw_path
            or any(part in {"", ".", ".."} for part in raw_parts)
            or normalized_name != raw_path
        ):
            raise ModulePackageError("module package contains an unsafe path")

        path_key = normalized_name.casefold()
        if path_key in seen_paths:
            raise ModulePackageError("module package contains an unsafe path")
        seen_paths.add(path_key)

        if normalized_name in ALLOWED_ROOT_FILES:
            if is_directory:
                raise ModulePackageError("module package contains an unsafe path")
        elif path.parts[0] == "dist":
            if len(path.parts) == 1 and not is_directory:
                raise ModulePackageError("module package contains an unsafe path")
        else:
            raise ModulePackageError("module package contains an unsafe path")

        if not is_directory:
            file_members[normalized_name] = member
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_PACKAGE_BYTES:
                raise ModulePackageError("module package is too large")

    file_path_keys = {name.casefold() for name in file_members}
    for name in file_members:
        path = PurePosixPath(name)
        for parent in path.parents:
            if parent == PurePosixPath("."):
                break
            if parent.as_posix().casefold() in file_path_keys:
                raise ModulePackageError("module package contains an unsafe path")

    return members, file_members


async def _read_upload(package: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await package.read(READ_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_PACKAGE_BYTES:
            raise ModulePackageError("module package is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_members(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    staging_path: Path,
) -> None:
    total_written = 0
    for member in members:
        name = member.filename[:-1] if member.is_dir() else member.filename
        target = staging_path.joinpath(*PurePosixPath(name).parts)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        member_written = 0
        with archive.open(member, "r") as source, target.open("xb") as destination:
            while chunk := source.read(READ_CHUNK_BYTES):
                member_written += len(chunk)
                total_written += len(chunk)
                if total_written > MAX_PACKAGE_BYTES:
                    raise ModulePackageError("module package is too large")
                destination.write(chunk)
        if member_written != member.file_size:
            raise ModulePackageError("module package is not a valid zip archive")


@dataclass
class PreparedModulePackage:
    manifest: dict[str, object]
    module_id: str
    package_root: Path
    staging_path: Path

    def install(self, revision: int) -> Callable[[], None]:
        _ensure_package_root(self.package_root)
        module_root = self.package_root / self.module_id
        target = module_root / str(revision)
        if module_root.is_symlink():
            raise ModulePackageError(
                "module package storage is unsafe",
                status_code=500,
            )
        try:
            module_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ModulePackageError(
                "module package storage is unavailable",
                status_code=500,
            ) from error
        if not module_root.is_dir() or module_root.is_symlink():
            raise ModulePackageError(
                "module package storage is unsafe",
                status_code=500,
            )
        if target.exists() or target.is_symlink():
            raise ModulePackageError(
                "module package revision already exists",
                status_code=409,
            )
        try:
            self.staging_path.rename(target)
        except OSError as error:
            raise ModulePackageError(
                "module package could not be installed",
                status_code=500,
            ) from error

        def undo() -> None:
            _remove_directory(target)
            try:
                module_root.rmdir()
            except OSError:
                pass

        return undo

    def discard(self) -> None:
        _remove_directory(self.staging_path)


async def prepare_module_package(
    package: UploadFile,
    package_root: Path,
) -> PreparedModulePackage:
    package_bytes = await _read_upload(package)
    if not package_bytes:
        raise ModulePackageError("module package is not a valid zip archive")
    return await run_in_threadpool(
        _prepare_module_package_bytes,
        package_bytes,
        package_root,
    )


def _prepare_module_package_bytes(
    package_bytes: bytes,
    package_root: Path,
) -> PreparedModulePackage:
    staging_path: Path | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as archive:
            members, file_members = _validated_members(archive)
            manifest_member = file_members.get("module.json")
            if manifest_member is None:
                raise ModulePackageError("module package is missing module.json")
            try:
                manifest_model = ModuleManifest.model_validate_json(
                    archive.read(manifest_member)
                )
            except (ValidationError, ValueError, UnicodeDecodeError) as error:
                raise ModulePackageError(
                    "module package contains an invalid manifest"
                ) from error

            if (
                manifest_model.entry.type != "external"
                and "dist/index.html" not in file_members
            ):
                raise ModulePackageError("module package is missing dist/index.html")

            try:
                _ensure_package_root(package_root)
                staging_path = Path(
                    tempfile.mkdtemp(prefix=".import-", dir=package_root)
                )
            except OSError as error:
                raise ModulePackageError(
                    "module package storage is unavailable",
                    status_code=500,
                ) from error
            _extract_members(archive, members, staging_path)
    except ModulePackageError:
        if staging_path is not None:
            _remove_directory(staging_path)
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
        RuntimeError,
    ) as error:
        if staging_path is not None:
            _remove_directory(staging_path)
        raise ModulePackageError("module package is not a valid zip archive") from error
    except OSError as error:
        if staging_path is not None:
            _remove_directory(staging_path)
        raise ModulePackageError(
            "module package storage is unavailable",
            status_code=500,
        ) from error

    manifest = manifest_repository_dict(manifest_model)
    return PreparedModulePackage(
        manifest=manifest,
        module_id=manifest_model.id,
        package_root=package_root,
        staging_path=staging_path,
    )


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _package_dist_files(package_path: Path) -> list[tuple[str, bytes]]:
    dist_path = package_path / "dist"
    if not dist_path.exists():
        return []
    if not dist_path.is_dir() or dist_path.is_symlink():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )

    files: list[tuple[str, bytes]] = []
    total_size = 0

    def storage_error(error: OSError) -> None:
        raise ModulePackageError(
            "module package storage is unavailable",
            status_code=500,
        ) from error

    try:
        for current_root, directory_names, file_names in os.walk(
            dist_path,
            followlinks=False,
            onerror=storage_error,
        ):
            current_path = Path(current_root)
            for directory_name in directory_names:
                if (current_path / directory_name).is_symlink():
                    raise ModulePackageError(
                        "module package storage is unsafe",
                        status_code=500,
                    )
            for file_name in file_names:
                path = current_path / file_name
                if path.is_symlink() or not path.is_file():
                    raise ModulePackageError(
                        "module package storage is unsafe",
                        status_code=500,
                    )
                relative_name = path.relative_to(package_path).as_posix()
                content = path.read_bytes()
                files.append((relative_name, content))
                total_size += len(content)
                if len(files) + 1 > MAX_FILES:
                    raise ModulePackageError("module package contains too many files")
                if total_size > MAX_PACKAGE_BYTES:
                    raise ModulePackageError("module package is too large")
    except OSError as error:
        storage_error(error)
    files.sort(key=lambda item: item[0])
    return files


def _write_deterministic_file(
    archive: zipfile.ZipFile,
    name: str,
    content: bytes,
) -> None:
    member = zipfile.ZipInfo(name, date_time=DETERMINISTIC_TIMESTAMP)
    member.compress_type = zipfile.ZIP_DEFLATED
    member.create_system = 3
    member.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(member, content)


def export_module_package(
    package_root: Path,
    module_id: str,
    revision: int,
    manifest: dict[str, object],
) -> bytes:
    _validate_existing_package_root(package_root)
    module_root = package_root / module_id
    if module_root.is_symlink():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )
    package_path = package_root / module_id / str(revision)
    if package_path.is_symlink():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )
    if not package_path.exists():
        raise ModulePackageError(
            "module package not found",
            status_code=404,
        )
    if not package_path.is_dir():
        raise ModulePackageError(
            "module package storage is unsafe",
            status_code=500,
        )

    manifest_content = _manifest_bytes(manifest)
    dist_files = _package_dist_files(package_path)
    entry = manifest.get("entry")
    if (
        isinstance(entry, dict)
        and entry.get("type") != "external"
        and not any(name == "dist/index.html" for name, _ in dist_files)
    ):
        raise ModulePackageError(
            "module package storage is incomplete",
            status_code=500,
        )
    if len(manifest_content) + sum(len(content) for _, content in dist_files) > (
        MAX_PACKAGE_BYTES
    ):
        raise ModulePackageError("module package is too large")

    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        _write_deterministic_file(archive, "module.json", manifest_content)
        for name, content in dist_files:
            _write_deterministic_file(archive, name, content)
    return output.getvalue()
