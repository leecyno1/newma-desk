from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.domain_suites import (
    DomainSuiteRuntime,
    ResearchApiAdapter,
    SpaStaticFiles,
    mount_domain_suites,
)


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
