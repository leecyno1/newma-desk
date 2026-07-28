import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def write_descriptor(tmp_path: Path, *, audit: str) -> Path:
    dsa = tmp_path / "dsa"
    quant = tmp_path / "quant"
    dsa.mkdir()
    quant.mkdir()
    descriptor = {
        "schemaVersion": "1.0",
        "pilots": [
            {
                "id": "daily-stock-analysis",
                "label": "Daily Stock Analysis",
                "mode": "analysis-only",
                "audit": {
                    "revision": "a" * 40,
                    "tag": "v1",
                    "reviewedAt": "2026-07-27",
                    "dependencyAudit": audit,
                },
                "activation": {
                    "defaultEnabled": False,
                    "env": "NEWMA_DESK_DSA_ROUTE_TEST_ENABLED",
                },
                "workspace": {
                    "env": "NEWMA_DESK_DSA_ROUTE_TEST_WORKSPACE",
                    "candidates": ["dsa"],
                },
                "runtime": {"origin": f"http://127.0.0.1:{free_port()}"},
                "isolation": {"environmentAllowlist": ["TZ"]},
                "capabilities": {"allow": ["research.analysis-context.read"]},
            },
            {
                "id": "quantdinger",
                "label": "QuantDinger",
                "mode": "paper-only",
                "audit": {
                    "revision": "b" * 40,
                    "tag": "v1",
                    "reviewedAt": "2026-07-27",
                    "dependencyAudit": audit,
                },
                "activation": {
                    "defaultEnabled": False,
                    "env": "NEWMA_DESK_QUANT_ROUTE_TEST_ENABLED",
                },
                "workspace": {
                    "env": "NEWMA_DESK_QUANT_ROUTE_TEST_WORKSPACE",
                    "candidates": ["quant"],
                },
                "runtime": {"origin": f"http://127.0.0.1:{free_port()}"},
                "isolation": {"environmentAllowlist": ["TZ"]},
                "capabilities": {"allow": ["quant.strategy-ledger.read"]},
            },
        ],
    }
    path = tmp_path / "pilots.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return path


def settings(tmp_path: Path, descriptor: Path) -> Settings:
    return Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "dock.db",
        workspace_root=tmp_path,
        external_finance_pilot_descriptor=descriptor,
        _env_file=None,
    )


def test_status_exposes_default_off_pilots_without_registering_mods(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path, write_descriptor(tmp_path, audit="blocked")))

    with TestClient(app) as client:
        response = client.get("/api/finance-pilots")

    assert response.status_code == 200
    assert [item["state"] for item in response.json()["pilots"]] == [
        "disabled",
        "disabled",
    ]


def test_runtime_rejects_manual_activation_when_audit_gate_is_unclean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("NEWMA_DESK_DSA_ROUTE_TEST_ENABLED", "true")
    app = create_app(settings(tmp_path, write_descriptor(tmp_path, audit="blocked")))

    with TestClient(app) as client:
        response = client.post(
            "/api/finance-pilots/daily-stock-analysis/adapt",
            json={"payload": {"subject": {"code": "AAPL"}, "blocks": {}}},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "finance_pilot_activation_blocked"
    assert response.json()["error"]["reasons"] == ["dependency-audit:blocked"]


def test_clean_requested_pilot_can_use_extraction_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("NEWMA_DESK_DSA_ROUTE_TEST_ENABLED", "true")
    app = create_app(
        settings(
            tmp_path,
            write_descriptor(tmp_path, audit="no-known-vulnerabilities"),
        )
    )
    payload = {
        "dataPolicy": "dock-only",
        "analysisContext": {
            "subject": {"code": "AAPL", "stock_name": "Apple", "market": "US"},
            "blocks": {
                "fundamentals": {
                    "status": "available",
                    "source": "Desk Evidence Ledger",
                }
            },
            "dataQuality": {"overallScore": 91, "level": "good"},
        }
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/finance-pilots/daily-stock-analysis/adapt",
            json={"payload": payload},
        )

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == (
        "newma-desk.daily-stock-analysis-context.v1"
    )
    assert response.json()["agentContext"]["availableBlocks"] == ["fundamentals"]
