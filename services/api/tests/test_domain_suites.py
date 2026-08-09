import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.sessions import ModSessionService
from vibe_visualization_api.domain_suites import (
    DomainSuiteRuntime,
    ResearchApiAdapter,
    SpaStaticFiles,
    TradingApiAdapter,
    _set_trading_api_key,
    mount_domain_suites,
)


def _session_headers(
    service: ModSessionService,
    *permissions: str,
    module_id: str = "alpha-lab",
    instance_id: str = "frame-1",
) -> dict[str, str]:
    token, _ = service.issue(
        instance_id=instance_id,
        user_id="local-user",
        workspace_id="local-workspace",
        module_id=module_id,
        revision=1,
        actions=[],
        permissions=list(permissions),
    )
    return {
        "X-Newma-Desk-Mod-Session": token,
        "X-Newma-Desk-Instance-Id": instance_id,
    }


def test_research_adapter_exposes_legacy_api_without_double_prefix() -> None:
    research = FastAPI()

    @research.get("/api/health")
    def health():
        return {"ok": True}

    host = FastAPI()
    host.mount("/api/research", ResearchApiAdapter(research))

    with TestClient(host) as client:
        direct = client.get("/api/research/health")
        compatible = client.get("/api/research/api/health")

    assert direct.status_code == 200
    assert compatible.status_code == 200


def test_trading_adapter_adds_server_credential_without_exposing_it_to_mod() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/alpha/list")
    def alpha_list(request: Request):
        return {"authorization": request.headers.get("authorization")}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        headers = _session_headers(sessions, "trading.read")
        headers["Authorization"] = "Bearer browser-value"
        response = client.get(
            "/api/trading/alpha/list",
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {"authorization": "Bearer server-secret"}


def test_trading_adapter_requires_mod_session_for_alpha_job_streams() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/alpha/bench/job-1/stream")
    def stream(request: Request):
        return {"authorization": request.headers.get("authorization")}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        missing = client.get("/api/trading/alpha/bench/job-1/stream")
        allowed = client.get(
            "/api/trading/alpha/bench/job-1/stream",
            headers=_session_headers(sessions, "trading.compute"),
        )

    assert missing.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json() == {"authorization": "Bearer server-secret"}


def test_trading_adapter_rejects_native_agent_endpoints() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/sessions")
    def list_sessions(request: Request):
        return {"authorization": request.headers.get("authorization")}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        response = client.get(
            "/api/trading/sessions",
            headers=_session_headers(sessions, "trading.read"),
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "This native Trading capability is replaced by Newma-Desk"
    }


def test_trading_adapter_requires_a_scoped_session_for_backtest_reads() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/runs")
    def runs(request: Request):
        return {"authorization": request.headers.get("authorization")}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        missing = client.get("/api/trading/runs")
        wrong_grant = client.get(
            "/api/trading/runs",
            headers=_session_headers(
                sessions,
                "trading.compute",
                module_id="backtest-lab",
            ),
        )
        allowed = client.get(
            "/api/trading/runs",
            headers=_session_headers(
                sessions,
                "trading.read",
                module_id="backtest-lab",
            ),
        )

    assert missing.status_code == 401
    assert wrong_grant.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"authorization": "Bearer server-secret"}


def test_trading_adapter_accepts_legacy_newma_dock_instance_header() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/runs")
    def runs(request: Request):
        return {
            "authorization": request.headers.get("authorization"),
            "legacy_instance": request.headers.get("x-newma-dock-instance-id"),
        }

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    headers = _session_headers(
        sessions,
        "trading.read",
        module_id="backtest-lab",
    )
    headers["X-Newma-Dock-Instance-Id"] = headers.pop(
        "X-Newma-Desk-Instance-Id"
    )
    with TestClient(host) as client:
        response = client.get("/api/trading/runs", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "authorization": "Bearer server-secret",
        "legacy_instance": None,
    }


def test_trading_adapter_authorizes_scoped_backtest_compute_actions() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.post("/runs/quick")
    def quick_run(request: Request):
        return {"authorization": request.headers.get("authorization")}

    @trading.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str, request: Request):
        return {
            "run_id": run_id,
            "authorization": request.headers.get("authorization"),
        }

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        missing = client.post("/api/trading/runs/quick")
        wrong_grant = client.post(
            "/api/trading/runs/quick",
            headers=_session_headers(
                sessions,
                "trading.read",
                module_id="backtest-lab",
            ),
        )
        headers = _session_headers(
            sessions,
            "trading.compute",
            module_id="backtest-lab",
        )
        created = client.post("/api/trading/runs/quick", headers=headers)
        cancelled = client.post(
            "/api/trading/runs/run-1/cancel",
            headers=headers,
        )

    assert missing.status_code == 401
    assert wrong_grant.status_code == 403
    assert created.status_code == 200
    assert created.json() == {"authorization": "Bearer server-secret"}
    assert cancelled.status_code == 200
    assert cancelled.json() == {
        "run_id": "run-1",
        "authorization": "Bearer server-secret",
    }


def test_trading_adapter_keeps_live_mutations_behind_desk_confirmation() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.post("/live/runner/start")
    def start_runner():
        return {"ok": True}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )

    with TestClient(host) as client:
        response = client.post(
            "/api/trading/live/runner/start",
            headers=_session_headers(
                sessions,
                "trading.runtime",
                module_id="trade-desk",
            ),
        )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Live Trading changes require the Newma-Desk confirmation flow"
    }


def test_trading_adapter_authorizes_settings_without_model_settings() -> None:
    trading = FastAPI()
    sessions = ModSessionService("test-secret")

    @trading.get("/settings/data-sources")
    def data_sources(request: Request):
        return {"authorization": request.headers.get("authorization")}

    @trading.get("/settings/llm")
    def llm_settings():
        return {"provider": "native"}

    host = FastAPI()
    host.mount(
        "/api/trading",
        TradingApiAdapter(trading, "server-secret", sessions),
    )
    headers = _session_headers(
        sessions,
        "trading.settings",
        module_id="trading-settings",
    )

    with TestClient(host) as client:
        data_sources = client.get(
            "/api/trading/settings/data-sources",
            headers=headers,
        )
        llm_settings = client.get(
            "/api/trading/settings/llm",
            headers=headers,
        )

    assert data_sources.status_code == 200
    assert data_sources.json() == {"authorization": "Bearer server-secret"}
    assert llm_settings.status_code == 403


def test_trading_api_key_environment_replaces_or_generates_private_value(
    monkeypatch,
) -> None:
    monkeypatch.setenv("API_AUTH_KEY", "stale-secret")

    configured = _set_trading_api_key("current-secret")
    assert configured == "current-secret"
    assert os.environ["API_AUTH_KEY"] == "current-secret"

    generated = _set_trading_api_key("")
    assert generated
    assert generated != "stale-secret"
    assert os.environ["API_AUTH_KEY"] == generated


def test_spa_static_files_falls_back_to_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>suite</main>", encoding="utf-8")
    host = FastAPI()
    host.mount(
        "/mod-runtime/research",
        SpaStaticFiles(directory=str(tmp_path), html=True),
    )

    with TestClient(host) as client:
        response = client.get("/mod-runtime/research/daily-review")

    assert response.status_code == 200
    assert "suite" in response.text


def test_domain_suites_are_opt_in_for_isolated_app_factories(tmp_path: Path) -> None:
    settings = Settings(
        enable_domain_suites=False,
        investment_workspace=tmp_path / "research",
        trading_workspace=tmp_path / "trading",
        _env_file=None,
    )
    host = FastAPI()

    runtime = mount_domain_suites(host, settings)

    assert runtime == DomainSuiteRuntime(
        mounted={"research": False, "trading": False}
    )
    assert all("domain-suites" not in getattr(route, "path", "") for route in host.routes)
