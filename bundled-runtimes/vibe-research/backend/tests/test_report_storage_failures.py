"""资料库故障不冒充空库/成功；只使用临时文件，不接触个人资料。"""
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as native
import myreports as mr

CONTENT = base64.b64encode(b"synthetic report").decode()


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(native, "_INTEGRATED_DOMAIN_RUNTIME", False)
    monkeypatch.setattr(native, "_API_KEY", "storage-test-key")
    return tmp_path, TestClient(native.app, headers={"Authorization": "Bearer storage-test-key"})


def assert_unavailable(response):
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "REPORT_STORAGE_UNAVAILABLE"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "secret-path" not in response.text


@pytest.mark.parametrize("damaged", [b"{", b"{}", b"[null]", b"\xff", b'[{"id":"../outside"}]'])
def test_damaged_index_blocks_all_operations_without_overwrite(library, damaged):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    original = directory / f'{meta["id"]}.txt'
    index = directory / "index.json"
    index.write_bytes(damaged)
    before = set(directory.iterdir())
    for method, path, kwargs in [
        ("GET", "/api/myreports", {}),
        ("GET", f'/api/myreports/file/{meta["id"]}', {}),
        ("GET", f'/api/myreports/{meta["id"]}/earnings-candidates', {}),
        ("POST", "/api/myreports", {"json": {"name": "new.txt", "content_b64": CONTENT}}),
        ("DELETE", f'/api/myreports/{meta["id"]}', {}),
    ]:
        assert_unavailable(client.request(method, path, **kwargs))
    assert index.read_bytes() == damaged
    assert original.read_bytes() == b"synthetic report"
    assert set(directory.iterdir()) == before


def test_missing_index_with_originals_is_not_a_new_library(library):
    directory, client = library
    assert client.get("/api/myreports").json()["data"] == []
    meta = mr.save_report("old.txt", CONTENT)
    (directory / "index.json").unlink()
    assert_unavailable(client.post("/api/myreports", json={"name": "new.txt", "content_b64": CONTENT}))
    assert not (directory / "index.json").exists()
    assert (directory / f'{meta["id"]}.txt').read_bytes() == b"synthetic report"


def test_read_permission_failure_is_not_empty_library(library, monkeypatch):
    directory, client = library
    mr.save_report("old.txt", CONTENT)
    original = Path.read_text
    def deny(path, *args, **kwargs):
        if path == directory / "index.json":
            raise PermissionError("secret-path")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", deny)
    assert_unavailable(client.get("/api/myreports"))


def test_index_commit_failure_keeps_old_documents_and_cleans_new_upload(library, monkeypatch):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    index = directory / "index.json"
    before = index.read_bytes()
    original = mr.os.replace
    def fail_commit(source, destination):
        if destination == index:
            raise OSError("secret-path disk full")
        return original(source, destination)
    monkeypatch.setattr(mr.os, "replace", fail_commit)
    assert_unavailable(client.post("/api/myreports", json={"name": "new.txt", "content_b64": CONTENT}))
    assert_unavailable(client.delete(f'/api/myreports/{meta["id"]}'))
    assert index.read_bytes() == before
    assert list(directory.glob("*.txt")) == [directory / f'{meta["id"]}.txt']
    assert client.get(f'/api/myreports/file/{meta["id"]}').content == b"synthetic report"


def test_file_write_failure_cleans_partial_upload(library, monkeypatch):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    original = Path.write_bytes
    def fail_write(path, blob):
        original(path, blob[:3])
        raise OSError("secret-path disk full")
    monkeypatch.setattr(Path, "write_bytes", fail_write)
    assert_unavailable(client.post("/api/myreports", json={"name": "new.txt", "content_b64": CONTENT}))
    assert mr.list_reports() == [meta]
    assert list(directory.glob("*.txt")) == [directory / f'{meta["id"]}.txt']


def test_delete_failure_restores_index_and_keeps_download(library, monkeypatch):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    original = Path.unlink
    def deny(path, *args, **kwargs):
        if path == directory / f'{meta["id"]}.txt':
            raise PermissionError("secret-path")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", deny)
    assert_unavailable(client.delete(f'/api/myreports/{meta["id"]}'))
    assert client.get("/api/myreports").json()["data"] == [meta]
    assert client.get(f'/api/myreports/file/{meta["id"]}').content == b"synthetic report"


def test_delete_rollback_failure_reports_recovery_needed_without_deleting_file(library, monkeypatch):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    original_unlink, original_save = Path.unlink, mr._save_index
    def deny(path, *args, **kwargs):
        if path == directory / f'{meta["id"]}.txt':
            raise PermissionError("secret-path")
        return original_unlink(path, *args, **kwargs)
    def fail_restore(items, folder):
        if items:
            raise mr.ReportStorageError("恢复失败")
        original_save(items, folder)
    monkeypatch.setattr(Path, "unlink", deny)
    monkeypatch.setattr(mr, "_save_index", fail_restore)
    response = client.delete(f'/api/myreports/{meta["id"]}')
    assert_unavailable(response)
    assert "索引恢复失败" in response.json()["detail"]
    assert (directory / f'{meta["id"]}.txt').read_bytes() == b"synthetic report"


def test_duplicate_and_invalid_metadata_are_not_silently_dropped(library):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    for records in [[meta, meta], [{**meta, "ext": "/../../outside"}], [{**meta, "ts": "yesterday"}]]:
        (directory / "index.json").write_text(json.dumps(records), encoding="utf-8")
        assert_unavailable(client.get("/api/myreports"))


def test_absent_original_can_still_remove_stale_entry(library):
    directory, client = library
    meta = mr.save_report("old.txt", CONTENT)
    (directory / f'{meta["id"]}.txt').unlink()
    assert client.delete(f'/api/myreports/{meta["id"]}').json()["data"] == {"ok": True}
    assert client.get("/api/myreports").json()["data"] == []
