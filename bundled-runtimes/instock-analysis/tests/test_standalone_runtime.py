from argparse import Namespace

import pytest

from instock.runtime import configure_runtime


def arguments(**overrides):
    return Namespace(**{"data_url": "https://data.example/api/research", "market_services_url": None, "state_dir": None,
                        "host": "127.0.0.1", "port": 19988, **overrides})


def test_standalone_paths_do_not_write_inside_installed_package(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    state = configure_runtime(arguments(), env)
    assert state == tmp_path / "instock-analysis"
    assert env["INSTOCK_SKIP_DB"] == "1"
    assert env["INSTOCK_RUNTIME_MODE"] == "standalone"
    assert env["INSTOCK_MARKET_DATA_PROVIDER"] == "http"
    assert env["INSTOCK_LOG_DIR"] == str(state / "logs")
    assert env["INSTOCK_ANALYSIS_HISTORY_DB_PATH"] == str(state / "analysis_history.sqlite3")
    assert env["INSTOCK_WEB_PORT"] == "19988"


def test_existing_storage_paths_are_not_silently_moved(tmp_path):
    env = {"INSTOCK_ANALYSIS_HISTORY_DB_PATH": str(tmp_path / "existing.sqlite3")}
    configure_runtime(arguments(state_dir=str(tmp_path / "new")), env)
    assert env["INSTOCK_ANALYSIS_HISTORY_DB_PATH"] == str(tmp_path / "existing.sqlite3")


def test_desk_entry_preserves_legacy_storage_and_operator_overrides(tmp_path):
    legacy = tmp_path / "instock"
    env = {"INSTOCK_LOG_DIR": str(tmp_path / "operator-logs"),
           "INSTOCK_SECTOR_FUND_FLOW_DB_PATH": str(tmp_path / "operator-flow.sqlite3")}
    configure_runtime(arguments(mode="desk", state_dir=str(legacy / "cache"), log_dir=str(legacy / "log")), env)
    assert env["INSTOCK_RUNTIME_MODE"] == "newma-desk-attached"
    assert env["INSTOCK_ANALYSIS_HISTORY_DB_PATH"] == str(legacy / "cache/analysis_history.sqlite3")
    assert env["INSTOCK_ROTATION_SHADOW_DB_PATH"] == str(legacy / "cache/rotation_shadow_state.sqlite3")
    assert env["INSTOCK_SECTOR_FUND_FLOW_DB_PATH"] == str(tmp_path / "operator-flow.sqlite3")
    assert env["INSTOCK_LOG_DIR"] == str(tmp_path / "operator-logs")


def test_public_cli_configures_desk_before_importing_server(monkeypatch, tmp_path):
    import sys
    from types import ModuleType
    from instock.runtime import main

    monkeypatch.setattr("os.environ", {})
    observed = []
    server = ModuleType("instock.web.web_service")
    server.main = lambda: observed.append(dict(__import__("os").environ))
    monkeypatch.setitem(sys.modules, "instock.web.web_service", server)
    main(["--mode", "desk", "--port", "19996", "--data-url", "https://data.example/api",
          "--market-services-url", "https://market.example", "--state-dir", str(tmp_path / "cache"),
          "--log-dir", str(tmp_path / "logs")])
    assert len(observed) == 1
    assert observed[0]["INSTOCK_RUNTIME_MODE"] == "newma-desk-attached"
    assert observed[0]["INSTOCK_WEB_PORT"] == "19996"
    assert observed[0]["INSTOCK_LOG_DIR"] == str(tmp_path / "logs")
    assert observed[0]["INSTOCK_MARKET_SERVICES_URL"] == "https://market.example"


def test_data_service_must_be_explicit_and_cannot_embed_credentials():
    with pytest.raises(ValueError, match="配置兼容"):
        configure_runtime(arguments(data_url=None), {})
    with pytest.raises(ValueError, match="不含凭据"):
        configure_runtime(arguments(data_url="https://user:secret@data.example/api"), {})


def test_provider_supports_project_owned_configuration(monkeypatch):
    from instock.core.market_data_provider import get_market_data_provider
    monkeypatch.setenv("INSTOCK_MARKET_DATA_PROVIDER", "http")
    monkeypatch.setenv("INSTOCK_DATA_URL", "https://data.example/api/research")
    get_market_data_provider.cache_clear()
    try:
        provider = get_market_data_provider()
        assert provider.base_url == "https://data.example/api/research"
    finally:
        get_market_data_provider.cache_clear()


def test_market_services_origin_is_explicit_and_validated(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    configure_runtime(arguments(market_services_url="https://calendar.example/"), env)
    assert env["INSTOCK_MARKET_SERVICES_URL"] == "https://calendar.example"
    for invalid in ["https://user:secret@calendar.example", "https://calendar.example/api", "file:///tmp/calendar"]:
        with pytest.raises(ValueError, match="基础数据服务"):
            configure_runtime(arguments(market_services_url=invalid), {})
