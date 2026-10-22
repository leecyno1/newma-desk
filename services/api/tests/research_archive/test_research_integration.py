"""Exercise the shipped Research manifests against the actual Desk mount."""
import base64
import json
from pathlib import Path
import subprocess
import pytest

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def test_shipped_research_files_and_earnings_handoff(tmp_path, monkeypatch):
    pytest.importorskip("requests", reason="requires Research runtime dependencies")
    root = Path(__file__).resolve().parents[4]
    store = subprocess.run(
        ["node", "--input-type=module", "-e",
         "import {loadModStore} from './scripts/lib/mod-store.mjs';"
         "const store = await loadModStore();"
         "console.log(JSON.stringify(store.mods.map(m => m.manifest)));"],
        cwd=root, capture_output=True, text=True, check=True, timeout=30,
    )
    manifests = {item["id"]: item for item in json.loads(store.stdout)}
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("VR_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("VR_DISABLE_BACKGROUND_TASKS", "1")
    monkeypatch.setenv("VR_API_KEY", "isolated-server-only")
    settings = Settings(
        runtime_dir=tmp_path / "desk", database_path=tmp_path / "desk.db",
        enable_domain_suites=True, domain_suite_workspace_venvs=False,
        investment_workspace=root / "bundled-runtimes/vibe-research",
        trading_workspace=tmp_path / "no-trading", enable_workflow_runtime_worker=False,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        # Publish only into this test database, using the normal manifest compiler.
        for mod in ("research-library", "earnings-workbench", "valuation-workbench"):
            created = client.post("/api/mods/drafts", json=manifests[mod])
            assert created.status_code == 201, created.text
            revision = created.json()["revision"]
            assert client.post(f"/api/mods/{mod}/revisions/{revision}/publish").status_code == 200

        def headers(mod, workspace="acceptance"):
            session = client.post(f"/api/mods/{mod}/sessions", headers={"X-User-Id": "synthetic-user"},
                                  json={"instanceId": mod, "workspaceId": workspace})
            assert session.status_code == 201, session.text
            return {"Authorization": f"Bearer {session.json()['accessToken']}",
                    "X-Newma-Desk-Instance-Id": mod}

        library, earnings, valuation = [headers(mod) for mod in
                                       ("research-library", "earnings-workbench", "valuation-workbench")]
        upload = client.post("/api/research/myreports", headers=library, json={
            "name": "synthetic-acceptance.txt", "content_b64": base64.b64encode(b"synthetic evidence only").decode(),
        })
        assert upload.status_code == 200, upload.text
        report_id = upload.json()["data"]["id"]
        file_url = f"/api/research/myreports/file/{report_id}"
        assert client.get(file_url, headers=earnings).content == b"synthetic evidence only"
        assert client.get(file_url, headers=valuation).status_code == 403
        assert client.get(file_url, headers=headers("research-library", "other")).status_code == 404
        assert client.get(file_url).status_code == 401
        legacy = client.get("/api/research/api/myreports", headers=library)
        assert legacy.json()["data"][0]["id"] == report_id
        assert legacy.headers["cache-control"] == "private, no-store"

        value = {"workbooks": [{"id": "synthetic-book", "mode": "reported", "metrics": [
            {"id": "revenue", "reported": 100, "sourceIds": []}], "operatingMetrics": [], "sourceMaterials": []}]}
        path = "/api/mods/earnings-workbench/storage/earnings-workbench/workbooks"
        saved = client.put(path, headers=earnings, json={"expectedRevision": 0, "value": value})
        assert saved.status_code == 200, saved.text
        inputs = client.get("/api/research-archive/earnings-inputs", headers=valuation)
        assert inputs.status_code == 200, inputs.text
        assert inputs.json()["workbooks"][0]["metrics"][0]["reported"] == 100
        assert client.get("/api/research-archive/earnings-inputs",
                          headers=headers("valuation-workbench", "other")).json()["workbooks"] == []
