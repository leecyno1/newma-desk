import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from vibe_visualization_api.config import Settings, resolve_database_path
from vibe_visualization_api.external_mod_runtimes import resolve_runtime_workspace


def test_market_scan_source_reads_dotenv_and_process_override(tmp_path, monkeypatch):
    monkeypatch.delenv("VR_CN_SCAN_SOURCE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("VR_CN_SCAN_SOURCE=tushare-daily\n")

    assert Settings(_env_file=env_file).cn_scan_source == "tushare-daily"
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "eastmoney")
    assert Settings(_env_file=env_file).cn_scan_source == "eastmoney"


def test_market_scan_source_defaults_and_rejects_unknown(monkeypatch):
    monkeypatch.delenv("VR_CN_SCAN_SOURCE", raising=False)
    assert Settings(_env_file=None).cn_scan_source == "eastmoney"
    monkeypatch.setenv("VR_CN_SCAN_SOURCE", "auto")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_tushare_reads_shared_dotenv_and_keeps_secret_private(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        'TUSHARE_TOKEN="local-test-token"\n'
        "NEWMA_DESK_RUNTIME_PROFILE=core\nVITE_API_PROXY_TARGET=http://localhost:8911\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.tushare_token.get_secret_value() == "local-test-token"
    assert "local-test-token" not in settings.model_dump_json()
    assert "local-test-token" not in repr(settings)


def test_tushare_configuration_priority(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TUSHARE_TOKEN=file-test-token\n")
    monkeypatch.setenv("TUSHARE_TOKEN", "process-test-token")

    assert Settings(_env_file=env_file).tushare_token.get_secret_value() == "process-test-token"
    assert Settings(tushare_token="explicit-test-token", _env_file=env_file).tushare_token.get_secret_value() == "explicit-test-token"


def test_disabling_dotenv_also_disables_legacy_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    (tmp_path / ".env").write_text("TUSHARE_TOKEN=do-not-load\n")

    assert Settings(_env_file=None).tushare_token.get_secret_value() == ""


def test_newma_desk_environment_names_take_priority(monkeypatch) -> None:
    monkeypatch.setenv("NEWMA_DESK_DATABASE_PATH", "runtime/current.db")
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/previous-brand.db")
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/current.db")


def test_newma_dock_environment_names_remain_compatible(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DESK_DATABASE_PATH", raising=False)
    monkeypatch.setenv("NEWMA_DOCK_DATABASE_PATH", "runtime/dock-brand.db")
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/previous-brand.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/dock-brand.db")


def test_vibedesk_environment_names_remain_compatible(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DESK_DATABASE_PATH", raising=False)
    monkeypatch.delenv("NEWMA_DOCK_DATABASE_PATH", raising=False)
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/previous-brand.db")
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/previous-brand.db")


def test_original_legacy_environment_names_remain_compatible(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DESK_DATABASE_PATH", raising=False)
    monkeypatch.delenv("NEWMA_DOCK_DATABASE_PATH", raising=False)
    monkeypatch.delenv("VIBEDESK_DATABASE_PATH", raising=False)
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/legacy.db")


def test_default_allowed_origins_include_external_runtime_overrides(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DESK_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv(
        "NEWMA_DESK_ORCHESTRA_WEB_URL",
        "https://orchestra.example.com",
    )

    settings = Settings(_env_file=None)

    assert "https://orchestra.example.com" in settings.origin_list()


def _write_registry_database(
    database_path: Path,
    *,
    status: str = "published",
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE module_revisions (
              module_id TEXT NOT NULL,
              revision INTEGER NOT NULL,
              status TEXT NOT NULL,
              manifest_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (module_id, revision)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO module_revisions
            VALUES ('market-daily', 1, ?, '{}', '2026-07-28T00:00:00Z')
            """,
            (status,),
        )


def test_empty_newma_desk_database_is_migrated_from_published_legacy_registry(
    tmp_path: Path,
) -> None:
    current = tmp_path / "newma-desk.db"
    current.touch()
    _write_registry_database(tmp_path / "vibedesk.db")

    resolved = resolve_database_path(current)

    assert resolved == current
    with sqlite3.connect(current) as connection:
        row = connection.execute(
            "SELECT module_id, status FROM module_revisions"
        ).fetchone()
    assert row == ("market-daily", "published")


def test_existing_new_registry_is_never_replaced_by_legacy_registry(
    tmp_path: Path,
) -> None:
    current = tmp_path / "newma-desk.db"
    _write_registry_database(current, status="draft")
    _write_registry_database(tmp_path / "vibedesk.db")

    resolved = resolve_database_path(current)

    assert resolved == current
    with sqlite3.connect(current) as connection:
        status = connection.execute(
            "SELECT status FROM module_revisions"
        ).fetchone()[0]
    assert status == "draft"


def test_non_pristine_new_database_falls_back_without_being_overwritten(
    tmp_path: Path,
) -> None:
    current = tmp_path / "newma-desk.db"
    with sqlite3.connect(current) as connection:
        connection.execute("CREATE TABLE local_state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO local_state VALUES ('keep-me')")
    legacy = tmp_path / "vibedesk.db"
    _write_registry_database(legacy)

    resolved = resolve_database_path(current)

    assert resolved == legacy
    with sqlite3.connect(current) as connection:
        value = connection.execute("SELECT value FROM local_state").fetchone()[0]
    assert value == "keep-me"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=value",
    ],
)
def test_mod_web_urls_must_be_exact_http_origins(value: str) -> None:
    for field_name in (
        "investment_web_url",
        "trading_web_url",
        "seven_cycle_web_url",
        "deepsee_web_url",
        "instock_web_url",
        "orchestra_web_url",
        "orchestra_api_url",
    ):
        with pytest.raises(ValidationError, match="Mod web URL"):
            Settings(**{field_name: value}, _env_file=None)


def test_deepsee_defaults_to_its_independent_local_service() -> None:
    settings = Settings(_env_file=None)

    assert settings.deepsee_web_url == "http://127.0.0.1:8001"
    assert "http://127.0.0.1:8001" in settings.origin_list()


def test_seven_cycle_defaults_to_its_independent_local_service() -> None:
    settings = Settings(_env_file=None)

    assert settings.seven_cycle_web_url == "http://127.0.0.1:4174"
    assert "http://127.0.0.1:4174" in settings.origin_list()


def test_crucix_is_fixed_to_the_local_read_only_runtime() -> None:
    settings = Settings(_env_file=None)

    assert settings.crucix_url == "http://127.0.0.1:3117"
    with pytest.raises(ValidationError, match="Crucix URL"):
        Settings(crucix_url="https://crucix.example.com", _env_file=None)


def test_research_and_trading_default_to_in_tree_mod_projects() -> None:
    settings = Settings(_env_file=None)
    project_root = Path(__file__).resolve().parents[3]

    assert settings.domain_suite_workspace_venvs is False
    assert settings.investment_workspace == (
        project_root / "mod-projects" / "vibe-research"
    )
    assert settings.trading_workspace == (
        project_root / "mod-projects" / "vibe-trading"
    )
    assert settings.investment_web_url == "http://127.0.0.1:8911"
    assert settings.trading_web_url == "http://127.0.0.1:8911"
    assert settings.research_base_url == "http://127.0.0.1:8911/api/research"


def test_empty_external_workspace_environment_uses_descriptor_discovery(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NEWMA_DESK_DEEPSEE_WORKSPACE", "")

    settings = Settings(_env_file=None)

    assert settings.deepsee_workspace == resolve_runtime_workspace(
        "deepsee", "source"
    )
    assert settings.deepsee_workspace != Path(".")
