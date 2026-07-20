import io
import json
import sqlite3
import stat
import warnings
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "static", "url": "/modules/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def _module_zip(
    *,
    manifest: object = MANIFEST,
    files: dict[str, bytes | str] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        archive.writestr(
            "module.json",
            json.dumps(manifest, ensure_ascii=False),
        )
        package_files = {"dist/index.html": "<h1>行情</h1>"} if files is None else files
        for name, content in package_files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _raw_zip(entries: list[tuple[zipfile.ZipInfo | str, bytes | str]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def _upload(client: TestClient, package: bytes, filename: str = "market.zip"):
    return client.post(
        "/api/modules/import",
        files={"package": (filename, package, "application/zip")},
    )


@pytest.fixture
def valid_module_zip() -> bytes:
    return _module_zip(
        files={
            "dist/index.html": "<h1>行情</h1>",
            "dist/assets/app.js": "console.log('market')",
        }
    )


@pytest.fixture
def traversal_zip() -> bytes:
    return _raw_zip(
        [
            ("module.json", json.dumps(MANIFEST)),
            ("dist/index.html", "ok"),
            ("../outside.txt", "unsafe"),
        ]
    )


def test_import_creates_a_draft_and_never_auto_publishes(
    client: TestClient,
    tmp_path: Path,
    valid_module_zip: bytes,
) -> None:
    response = _upload(client, valid_module_zip)

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["revision"] == 1
    assert client.get("/api/modules").json() == []
    package_root = tmp_path / "module-packages" / "market-daily" / "1"
    assert (package_root / "module.json").is_file()
    assert (package_root / "dist" / "index.html").read_text() == "<h1>行情</h1>"


def test_import_rejects_path_traversal(
    client: TestClient,
    tmp_path: Path,
    traversal_zip: bytes,
) -> None:
    response = _upload(client, traversal_zip, "bad.zip")

    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains an unsafe path"
    assert client.get("/api/modules").json() == []
    assert not (tmp_path / "outside.txt").exists()
    assert not (tmp_path / "module-packages" / "market-daily").exists()


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "/absolute.txt",
        "dist\\windows.txt",
        "unexpected.txt",
    ],
)
def test_import_rejects_unsafe_or_out_of_scope_members(
    client: TestClient,
    unsafe_name: str,
) -> None:
    package = _raw_zip(
        [
            ("module.json", json.dumps(MANIFEST)),
            ("dist/index.html", "ok"),
            (unsafe_name, "unsafe"),
        ]
    )

    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains an unsafe path"


def test_import_rejects_symlinks(client: TestClient) -> None:
    symlink = zipfile.ZipInfo("dist/assets/current.js")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    package = _raw_zip(
        [
            ("module.json", json.dumps(MANIFEST)),
            ("dist/index.html", "ok"),
            (symlink, "../private.js"),
        ]
    )

    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains a link"


def test_import_rejects_duplicate_members(client: TestClient) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        package = _raw_zip(
            [
                ("module.json", json.dumps(MANIFEST)),
                ("dist/index.html", "first"),
                ("dist/index.html", "second"),
            ]
        )

    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains an unsafe path"


@pytest.mark.parametrize(
    ("package", "detail"),
    [
        (
            _raw_zip([("dist/index.html", "ok")]),
            "module package is missing module.json",
        ),
        (
            _module_zip(files={"dist/app.js": "no index"}),
            "module package is missing dist/index.html",
        ),
        (
            _module_zip(manifest={**MANIFEST, "version": "invalid"}),
            "module package contains an invalid manifest",
        ),
    ],
)
def test_import_rejects_incomplete_or_invalid_packages(
    client: TestClient,
    package: bytes,
    detail: str,
) -> None:
    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_external_module_can_import_without_dist(client: TestClient) -> None:
    external_manifest = {
        **MANIFEST,
        "entry": {"type": "external", "url": "https://example.com/market"},
    }

    response = _upload(client, _module_zip(manifest=external_manifest, files={}))

    assert response.status_code == 201
    assert response.json()["status"] == "draft"


def test_import_rejects_too_many_files(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibe_visualization_api.control_plane import packages

    monkeypatch.setattr(packages, "MAX_FILES", 2)
    package = _module_zip(
        files={
            "dist/index.html": "ok",
            "dist/app.js": "too many",
        }
    )

    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == "module package contains too many files"


def test_import_rejects_oversized_uncompressed_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibe_visualization_api.control_plane import packages

    monkeypatch.setattr(packages, "MAX_PACKAGE_BYTES", 1_024)
    package = _module_zip(files={"dist/index.html": "x" * 2_048})

    response = _upload(client, package)

    assert response.status_code == 400
    assert response.json()["detail"] == "module package is too large"


def test_failed_install_rolls_back_registry_and_staging_directory(
    client: TestClient,
    tmp_path: Path,
    valid_module_zip: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibe_visualization_api.control_plane import packages

    def fail_install(
        prepared: packages.PreparedModulePackage,
        revision: int,
    ) -> None:
        raise packages.ModulePackageError(
            "module package could not be installed",
            status_code=500,
        )

    monkeypatch.setattr(
        packages.PreparedModulePackage,
        "install",
        fail_install,
    )

    response = _upload(client, valid_module_zip)

    assert response.status_code == 500
    assert response.json() == {"detail": "module package could not be installed"}
    assert client.get("/api/modules/market-daily/revisions/1").status_code == 404
    package_root = tmp_path / "module-packages"
    assert list(package_root.glob(".import-*")) == []
    with sqlite3.connect(tmp_path / "registry.db") as connection:
        events = connection.execute("SELECT event_type FROM audit_events").fetchall()
    assert events == []


def test_import_does_not_follow_a_module_storage_symlink(
    client: TestClient,
    tmp_path: Path,
    valid_module_zip: bytes,
) -> None:
    package_root = tmp_path / "module-packages"
    outside = tmp_path / "outside-storage"
    package_root.mkdir()
    outside.mkdir()
    (package_root / "market-daily").symlink_to(outside, target_is_directory=True)

    response = _upload(client, valid_module_zip)

    assert response.status_code == 500
    assert response.json() == {"detail": "module package storage is unsafe"}
    assert list(outside.iterdir()) == []
    assert client.get("/api/modules/market-daily/revisions/1").status_code == 404


def test_export_is_deterministic_and_records_audit_events(
    client: TestClient,
    tmp_path: Path,
    valid_module_zip: bytes,
) -> None:
    imported = _upload(client, valid_module_zip).json()
    url = "/api/modules/market-daily/revisions/" f"{imported['revision']}/export"

    first = client.get(url)
    second = client.get(url)

    assert first.status_code == 200
    assert first.headers["content-type"] == "application/zip"
    assert first.headers["content-disposition"] == (
        'attachment; filename="market-daily-r1.zip"'
    )
    assert first.content == second.content
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        assert archive.namelist() == [
            "module.json",
            "dist/assets/app.js",
            "dist/index.html",
        ]
        assert json.loads(archive.read("module.json")) == MANIFEST

    with sqlite3.connect(tmp_path / "registry.db") as connection:
        events = connection.execute(
            "SELECT event_type FROM audit_events ORDER BY id"
        ).fetchall()
    assert events == [("import",), ("export",), ("export",)]


def test_external_export_contains_only_manifest(
    client: TestClient,
) -> None:
    external_manifest = {
        **MANIFEST,
        "entry": {"type": "external", "url": "https://example.com/market"},
    }
    imported = _upload(
        client,
        _module_zip(manifest=external_manifest, files={}),
    ).json()

    response = client.get(
        f"/api/modules/market-daily/revisions/{imported['revision']}/export"
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["module.json"]


def test_export_missing_revision_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/modules/missing/revisions/999/export")

    assert response.status_code == 404
    assert response.json() == {"detail": "module revision not found"}


def test_export_revision_without_installed_package_returns_not_found(
    client: TestClient,
) -> None:
    draft = client.post("/api/modules/drafts", json=MANIFEST).json()

    response = client.get(
        f"/api/modules/market-daily/revisions/{draft['revision']}/export"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "module package not found"}
