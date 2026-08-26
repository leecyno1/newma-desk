import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import health
from app.services import deployment_status


class _DummyExecute:
    def scalar(self):
        return 1


class _DummyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return 0


class _DummyDb:
    def execute(self, *_args, **_kwargs):
        return _DummyExecute()

    def query(self, *_args, **_kwargs):
        return _DummyQuery()

    def close(self):
        pass


def test_ready_includes_commercial_launch_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "SessionLocal", lambda: _DummyDb())
    monkeypatch.setattr(
        deployment_status,
        "load_ai_config",
        lambda: {"api_key": "secret", "model_router": {"enabled": True, "main_channels": [{"enabled": True}]}},
    )
    monkeypatch.setattr(deployment_status, "get_background_runtime_snapshot", lambda: {"aggregation_retention": {"enabled": True}})
    monkeypatch.setattr(deployment_status, "probe_chatlog_http", lambda: {"ok": True, "status_code": 200, "latency_ms": 3})
    monkeypatch.setattr(deployment_status.settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    payload = health.ready()
    names = {item.name for item in payload.checks}
    assert "database" in names
    assert "sqlite_fts" in names
    assert "disk_space" in names
    assert "writable_paths" in names
    assert "external_config" in names
    assert "background_loops" in names


def test_prod_lite_env_template_disables_heavy_background_work():
    path = os.path.join(PROJECT_ROOT, ".env.production-lite.example")
    with open(path, "r", encoding="utf-8") as fh:
        body = fh.read()
    assert "SYNC_INTERVAL_SECONDS=0" in body
    assert "EMAIL_SYNC_INTERVAL_SECONDS=0" in body
    assert "NEWSNOW_REFRESH_INTERVAL_SECONDS=0" in body
    assert "NEWS_SNAPSHOT_INTERVAL_SECONDS=0" in body
    assert "AI_MAX_PARALLEL=2" in body


def test_manage_script_exposes_customer_delivery_commands():
    with open(os.path.join(PROJECT_ROOT, "scripts", "manage.sh"), "r", encoding="utf-8") as fh:
        out = fh.read()
    assert "prod-lite" in out
    assert "diagnose" in out
    assert "backup" in out
    assert "restore" in out
    assert "Authorization: Bearer" in out


def test_ready_includes_chatlog_and_llm_dependency_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "SessionLocal", lambda: _DummyDb())
    monkeypatch.setattr(
        deployment_status,
        "load_ai_config",
        lambda: {
            "api_key": "secret",
            "model_router": {"enabled": True, "main_channels": [{"enabled": True, "api_key": "secret"}]},
        },
    )
    monkeypatch.setattr(deployment_status, "get_background_runtime_snapshot", lambda: {})
    monkeypatch.setattr(deployment_status, "probe_chatlog_http", lambda: {"ok": True, "status_code": 200, "latency_ms": 3})
    monkeypatch.setattr(deployment_status.settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    payload = health.ready()
    by_name = {item.name: item for item in payload.checks}
    assert by_name["chatlog_http"].status == "ok"
    assert by_name["llm_config"].status == "ok"


def test_ready_marks_missing_llm_key_as_degraded(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "SessionLocal", lambda: _DummyDb())
    monkeypatch.setattr(
        deployment_status,
        "load_ai_config",
        lambda: {"model_router": {"enabled": True, "main_channels": [{"enabled": True}]}},
    )
    monkeypatch.setattr(deployment_status, "get_background_runtime_snapshot", lambda: {})
    monkeypatch.setattr(deployment_status, "probe_chatlog_http", lambda: {"ok": True, "status_code": 200, "latency_ms": 3})
    monkeypatch.setattr(deployment_status.settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    payload = health.ready()
    by_name = {item.name: item for item in payload.checks}
    assert by_name["llm_config"].status == "fail"
    assert payload.healthy is False


def test_diagnostics_summarizes_customer_support_signals(monkeypatch, tmp_path):
    monkeypatch.setattr(
        deployment_status,
        "load_ai_config",
        lambda: {
            "api_key": "secret",
            "model_router": {"enabled": True, "main_channels": [{"enabled": True, "name": "primary"}]},
        },
    )
    monkeypatch.setattr(deployment_status, "probe_chatlog_http", lambda: {"ok": True, "status_code": 200, "latency_ms": 3})
    monkeypatch.setattr(
        deployment_status,
        "get_background_runtime_snapshot",
        lambda: {"aggregation_retention": {"enabled": True, "running": False, "last_success": "2026-05-04T00:00:00"}},
    )
    monkeypatch.setattr(deployment_status.settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    payload = deployment_status.summarize_diagnostics(_DummyDb())

    assert payload["api_keys"]["llm_api_key_configured"] is True
    assert payload["external_services"]["chatlog_http"]["ok"] is True
    assert payload["background_runtime"]["aggregation_retention"]["enabled"] is True
    assert payload["aggregation_retention"]["retention_days"] == 90
    assert "messages" in payload["aggregation_retention"]["protected_raw_tables"]
    assert payload["aggregation_retention"]["estimated_old_rows"]["tasks"] == 0
