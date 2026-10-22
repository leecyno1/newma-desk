"""Deployment admission is separate from login and per-Mod permissions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository, ModuleAdmissionDeniedError
from vibe_visualization_api.main import create_app
from tests.mod_storage.test_routes import _manifest, _publish, _session_headers
from tests.control_plane.test_packages import _module_zip
from tests.mod_store.test_routes import _write_suite_store


@pytest.mark.parametrize("value", ["*", "macro-monitor,", "macro-monitor,../bad", " ", "MixedCase"])
def test_invalid_allowlist_fails_closed_at_startup(value):
    with pytest.raises(ValidationError):
        Settings(mod_admission_allowlist=value, _env_file=None)


def test_allowlist_is_opt_in_and_normalizes_exact_ids(monkeypatch):
    assert Settings(_env_file=None).mod_admission_allowlist == ""
    monkeypatch.setenv("NEWMA_DESK_MOD_ADMISSION_ALLOWLIST", "macro-monitor, news-radar,macro-monitor")
    assert Settings(_env_file=None).mod_admission_allowlist == "macro-monitor,news-radar"


def test_unadmitted_old_mod_cannot_be_registered_published_signed_or_invoked(tmp_path):
    db = tmp_path / "desk.db"
    original = ModuleRepository(db)
    old = original.create_draft(_manifest("not-admitted"))
    original.publish(old.module_id, old.revision)
    old_draft = original.create_draft(_manifest("not-admitted"))
    settings = Settings(database_path=db, runtime_dir=tmp_path, enable_domain_suites=False,
                        mod_admission_allowlist="market-daily", _env_file=None)
    with TestClient(create_app(settings, data_services=[])) as api:
        _publish(api, _manifest("market-daily"))
        _session_headers(api, module_id="market-daily")
        old_token, _ = api.app.state.mod_session_service.issue(
            instance_id="old", user_id="test", workspace_id="test", module_id="not-admitted",
            revision=old.revision, actions=["market.refresh"], permissions=["market.read"],
        )
        for prefix in ("/api/mods", "/api/modules"):
            assert [item["moduleId"] for item in api.get(prefix).json()] == ["market-daily"]
            requests = [
                (f"{prefix}/drafts", _manifest("not-admitted")),
                (f"{prefix}/not-admitted/revisions/{old_draft.revision}/publish", None),
                (f"{prefix}/not-admitted/sessions", {"workspaceId": "test", "instanceId": "test"}),
                (f"{prefix}/not-admitted/actions/market.refresh", {"input": {}}),
            ]
            for path, body in requests:
                response = api.post(path, json=body, headers={"X-User-Id": "test"})
                assert response.status_code == 403, response.text
                assert response.headers["cache-control"] == "no-store"
            assert api.post(f"{prefix}/not-admitted/actions/market.refresh", json={"input": {}}, headers={
                "Authorization": "Bearer " + old_token, "X-Newma-Desk-Instance-Id": "old",
            }).status_code == 403
        # Store install is rejected before reading/fetching a catalog descriptor.
        api.app.state.mod_store_service._snapshot = lambda: pytest.fail("must not fetch an unadmitted Mod")
        assert api.post("/api/store/mods/not-admitted/install").status_code == 403
        package = _module_zip(manifest={**_manifest("not-admitted"), "entry": {"type": "static", "url": "/mods/not-admitted/"}})
        result = api.post("/api/mods/import", files={"package": ("test.zip", package, "application/zip")})
        assert result.status_code == 403, result.text
        assert not (tmp_path / "module-packages" / "not-admitted").exists()
        # The existing database and published version are unchanged, not erased.
        assert original.get_published("not-admitted").revision == old.revision


def test_batch_install_is_atomic_and_rejects_reenable_shortcut(tmp_path):
    db = tmp_path / "desk.db"
    original = ModuleRepository(db)
    original.install_batch([_manifest("not-admitted")])
    original.disable("not-admitted")
    restricted = ModuleRepository(db, allowed_module_ids=frozenset({"market-daily"}))
    with pytest.raises(ModuleAdmissionDeniedError):
        restricted.install_batch([_manifest("market-daily"), _manifest("not-admitted")])
    assert restricted.list_installed() == []
    assert original.list_installed()[0].status == "disabled"
    with pytest.raises(ModuleAdmissionDeniedError):
        restricted.rollback("not-admitted", 1)
    assert original.list_installed()[0].status == "disabled"


def test_project_install_cannot_include_unadmitted_siblings(tmp_path):
    settings = Settings(database_path=tmp_path / "desk.db", runtime_dir=tmp_path / "runtime",
                        mod_store_dir=_write_suite_store(tmp_path), enable_domain_suites=False,
                        mod_admission_allowlist="example-overview", _env_file=None)
    with TestClient(create_app(settings, data_services=[])) as api:
        result = api.post("/api/store/projects/example-suite/install")
        assert result.status_code == 403, result.text
        assert api.get("/api/mods").json() == []
