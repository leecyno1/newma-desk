import json
from fastapi.testclient import TestClient

from vibe_visualization_api.global_intel.app import create_app
from vibe_visualization_api.global_intel.runtime import Settings
from vibe_visualization_api.global_intel import release


def test_health_identity_is_fixed_and_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    expected = release.process_release()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEWMA_SOURCE_COMMIT", "f" * 40)
    monkeypatch.setattr(release, "load_release", lambda _path: {"sourceCommit": "f" * 40})
    with TestClient(create_app(Settings(database_path=tmp_path / "topics.db", world_intel_url="", crucix_url=""))) as client:
        first = client.get("/api/health").json()
        assert first["release"] == expected
        assert first["runtime"]["instance"]["id"]
        assert first["runtime"]["instance"]["started_at"]
        first["release"]["sourceCommit"] = "mutated-client-copy"
        second = client.get("/api/health").json()
        assert second["release"] == expected
        assert first["runtime"] == second["runtime"]
        assert second["agent"] == "host-only"
        assert second["sources"] == {"worldIntelConfigured": False, "crucixConfigured": False}
        assert client.get("/api/crucix/snapshot").status_code == 503


def test_missing_or_other_project_release_is_unknown(tmp_path):
    path = tmp_path / "_release.json"
    assert release.load_release(path)["sourceCommit"] is None
    path.write_text(json.dumps({"projectId": "policy-analysis", "sourceCommit": "a" * 40}), encoding="utf-8")
    assert release.load_release(path)["sourceCommit"] is None


def test_release_preserves_dirty_candidates_and_rejects_invalid_identity_fields(tmp_path):
    path = tmp_path / "_release.json"
    identity = {"projectId": "global-intelligence", "packageVersion": "0.1.0",
                "sourceCommit": "a" * 40, "sourceDirty": True}
    path.write_text(json.dumps(identity), encoding="utf-8")
    assert release.load_release(path) == identity
    path.write_text(json.dumps({**identity, "sourceCommit": "main", "sourceDirty": "false"}), encoding="utf-8")
    result = release.load_release(path)
    assert result["sourceCommit"] is None and result["sourceDirty"] is None
