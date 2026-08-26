from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from seven_cycle_platform.local_service import (
    LocalServiceConfig,
    _module_command,
    inspect_service,
    serve_child,
    start_service,
    stop_service,
)


def _config(tmp_path: Path) -> LocalServiceConfig:
    return LocalServiceConfig(
        host="127.0.0.1",
        port=4174,
        product_root=Path("products/circle"),
        catalog_root=Path("products/circle/catalogs"),
        web_root=Path("web/dist"),
        state_path=Path("output/services/circle-service.json"),
        log_path=Path("output/services/circle-service.log"),
        project_root=tmp_path,
    )


def test_inspect_service_reports_verified_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import seven_cycle_platform.local_service as service

    config = _config(tmp_path).normalized()
    config.state_path.parent.mkdir(parents=True)
    config.state_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path.resolve()),
                "supervisor_pid": 1234,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_process_alive", lambda pid: pid == 1234)
    monkeypatch.setattr(
        service,
        "_fetch_health",
        lambda url: {"status": "ok", "deployment_id": "abc"},
    )

    result = inspect_service(config)

    assert result["status"] == "running"
    assert result["supervisor_pid"] == 1234
    assert result["health"]["deployment_id"] == "abc"


def test_start_is_idempotent_when_service_is_healthy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import seven_cycle_platform.local_service as service

    config = _config(tmp_path).normalized()
    config.state_path.parent.mkdir(parents=True)
    config.state_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path.resolve()),
                "supervisor_pid": 1234,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_process_alive", lambda pid: pid == 1234)
    monkeypatch.setattr(service, "_fetch_health", lambda url: {"status": "ok"})

    result = start_service(config)

    assert result["action"] == "already_running"
    assert result["status"] == "running"


def test_start_refuses_unmanaged_healthy_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest
    import seven_cycle_platform.local_service as service

    config = _config(tmp_path)
    monkeypatch.setattr(service, "_process_alive", lambda pid: False)
    monkeypatch.setattr(service, "_fetch_health", lambda url: {"status": "ok"})

    with pytest.raises(RuntimeError, match="unmanaged process"):
        start_service(config)


def test_stop_cleans_stale_state_without_signaling(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import seven_cycle_platform.local_service as service

    config = _config(tmp_path).normalized()
    config.state_path.parent.mkdir(parents=True)
    config.state_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path.resolve()),
                "supervisor_pid": 9999,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_process_alive", lambda pid: False)
    monkeypatch.setattr(service, "_fetch_health", lambda url: None)

    result = stop_service(config)

    assert result["action"] == "already_stopped"
    assert result["status"] == "stopped"
    assert not config.state_path.exists()


def test_catalog_startup_repair_is_disabled_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import uvicorn
    import seven_cycle_platform.api as api
    import seven_cycle_platform.local_service as service

    calls: list[str] = []
    monkeypatch.setattr(
        service,
        "repair_latest_catalog_device_drift",
        lambda *args: calls.append("repair"),
    )
    monkeypatch.setattr(api, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)

    assert serve_child(_config(tmp_path)) == 0
    assert calls == []
    assert "--repair-catalog-on-start" not in _module_command(
        "serve-child",
        _config(tmp_path),
    )


def test_catalog_startup_repair_flag_is_forwarded_and_executed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import uvicorn
    import seven_cycle_platform.api as api
    import seven_cycle_platform.local_service as service

    calls: list[tuple[Path, Path, Path]] = []
    monkeypatch.setattr(
        service,
        "repair_latest_catalog_device_drift",
        lambda product_root, catalog_root, web_root: (
            calls.append((product_root, catalog_root, web_root))
            or {"action": "not_needed", "run_id": "test"}
        ),
    )
    monkeypatch.setattr(api, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    config = replace(_config(tmp_path), repair_catalog_on_start=True)

    assert serve_child(config) == 0
    assert calls == [
        (
            (tmp_path / "products/circle").resolve(),
            (tmp_path / "products/circle/catalogs").resolve(),
            (tmp_path / "web/dist").resolve(),
        )
    ]
    assert "--repair-catalog-on-start" in _module_command("serve-child", config)
