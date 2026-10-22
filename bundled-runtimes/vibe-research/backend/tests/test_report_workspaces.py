"""Real file routes + signed Desk sessions, isolated from personal documents."""
import base64
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app as native
import myreports
from vibe_visualization_api.control_plane.sessions import ModSessionService
from vibe_visualization_api.domain_suites import ResearchApiAdapter


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(myreports, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(native, "_INTEGRATED_DOMAIN_RUNTIME", True)
    monkeypatch.setattr(native, "_API_KEY", "native-server-only")
    service = ModSessionService("file-tests-only")
    repo = SimpleNamespace(get_published=lambda _: SimpleNamespace(revision=2))
    host = FastAPI()
    host.mount("/api/research", ResearchApiAdapter(native.app, service, lambda: repo, "native-server-only"))
    return TestClient(host), service


def headers(service, user="u1", workspace="w1", module="research-library", permissions=None, revision=2):
    token, _ = service.issue(instance_id="test-frame", user_id=user, workspace_id=workspace,
        module_id=module, revision=revision, actions=[],
        permissions=["investment.files"] if permissions is None else permissions)
    return {"Authorization": f"Bearer {token}", "X-Newma-Desk-Instance-Id": "test-frame"}


def upload(client, auth, name="合成研究.txt"):
    response = client.post("/api/research/myreports", headers=auth,
        json={"name": name, "content_b64": base64.b64encode(b"synthetic report").decode()})
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def test_user_workspace_isolation_and_shared_authorized_earnings(files):
    client, service = files
    owner = headers(service)
    rid = upload(client, owner)
    for other in [headers(service, user="u2"), headers(service, workspace="w2")]:
        assert client.get("/api/research/myreports", headers=other).json()["data"] == []
        assert client.get(f"/api/research/myreports/file/{rid}", headers=other).status_code == 404
        assert client.get(f"/api/research/myreports/{rid}/earnings-candidates?notes=true", headers=other).status_code == 404
        assert client.delete(f"/api/research/myreports/{rid}", headers=other).json()["data"] == {"ok": False}
    earnings = headers(service, module="earnings-workbench")
    assert client.get(f"/api/research/myreports/file/{rid}", headers=earnings).content == b"synthetic report"
    assert client.get("/api/research/api/myreports", headers=owner).json()["data"][0]["id"] == rid
    assert client.delete(f"/api/research/myreports/{rid}", headers=owner).json()["data"]["ok"]
    assert client.get(f"/api/research/myreports/file/{rid}", headers=owner).status_code == 404


def test_spoofed_headers_do_not_select_storage_and_native_files_stay_native(files):
    client, service = files
    old = myreports.save_report("old.txt", base64.b64encode(b"native private").decode())
    auth = {**headers(service), "X-User-Id": "u2", "X-Workspace-Id": "w2"}
    rid = upload(client, auth)
    assert myreports.list_reports(scope=("u1", "w1"))[0]["id"] == rid
    assert myreports.list_reports(scope=("u2", "w2")) == []
    assert myreports.list_reports()[0]["id"] == old["id"]
    assert client.get(f'/api/research/myreports/file/{old["id"]}', headers=auth).status_code == 404


@pytest.mark.parametrize("path,method", [
    ("myreports", "GET"), ("myreports", "POST"), ("myreports/x", "DELETE"),
    ("myreports/file/x", "GET"), ("myreports/x/earnings-candidates", "GET"),
    ("api/myreports", "GET"),
])
def test_all_file_routes_reject_missing_sessions(files, path, method):
    client, _ = files
    assert client.request(method, f"/api/research/{path}", headers={"Authorization": "Bearer native-server-only"}).status_code == 401


def test_permission_instance_revision_and_module_are_checked(files):
    client, service = files
    for auth in [headers(service, permissions=["storage.write"]), headers(service, revision=1),
                 headers(service, module="watchlist"), {**headers(service), "X-Newma-Desk-Instance-Id": "other"}]:
        assert client.get("/api/research/myreports", headers=auth).status_code == 403


def test_integrated_native_path_cannot_bypass_adapter(files):
    assert TestClient(native.app).get("/api/myreports", headers={"Authorization": "Bearer native-server-only"}).status_code == 401


def test_scoped_extraction_receives_only_the_owners_file(files, monkeypatch):
    import earnings_import
    client, service = files
    owner = headers(service)
    rid = upload(client, owner, "test.pdf")
    seen = []
    def extract(path, report_id, name, **kwargs):
        seen.append(path)
        return {"reportId": report_id, "name": name}
    monkeypatch.setattr(earnings_import, "extract_report", extract)
    assert client.get(f"/api/research/myreports/{rid}/earnings-candidates", headers=owner).status_code == 200
    assert seen == [myreports.report_path(rid, scope=("u1", "w1"))[0]]
    assert client.get(f"/api/research/myreports/{rid}/earnings-candidates", headers=headers(service, user="u2")).status_code == 404
    assert len(seen) == 1


def test_damaged_workspace_returns_storage_error_without_affecting_other_users(files):
    client, service = files
    owner = headers(service)
    rid = upload(client, owner)
    path = myreports.report_path(rid, scope=("u1", "w1"))[0]
    (path.parent / "index.json").write_bytes(b"{")
    response = client.get("/api/research/myreports", headers=owner)
    assert response.status_code == 503
    assert response.json()["code"] == "REPORT_STORAGE_UNAVAILABLE"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert client.delete(f"/api/research/myreports/{rid}", headers=owner).status_code == 503
    assert path.read_bytes() == b"synthetic report"
    other = headers(service, workspace="w2")
    assert client.get("/api/research/myreports", headers=other).json()["data"] == []
    assert upload(client, other)
