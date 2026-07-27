from pathlib import Path

import pytest
from pydantic import ValidationError

from vibe_visualization_api.config import Settings
from vibe_visualization_api.external_mod_runtimes import resolve_runtime_workspace


def test_newma_dock_environment_names_take_priority(monkeypatch) -> None:
    monkeypatch.setenv("NEWMA_DOCK_DATABASE_PATH", "runtime/current.db")
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/previous-brand.db")
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/current.db")


def test_vibedesk_environment_names_remain_compatible(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DOCK_DATABASE_PATH", raising=False)
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/previous-brand.db")
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/previous-brand.db")


def test_original_legacy_environment_names_remain_compatible(monkeypatch) -> None:
    monkeypatch.delenv("NEWMA_DOCK_DATABASE_PATH", raising=False)
    monkeypatch.delenv("VIBEDESK_DATABASE_PATH", raising=False)
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/legacy.db")


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


def test_research_and_trading_default_to_in_tree_mod_projects() -> None:
    settings = Settings(_env_file=None)
    project_root = Path(__file__).resolve().parents[3]

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
    monkeypatch.setenv("NEWMA_DOCK_DEEPSEE_WORKSPACE", "")

    settings = Settings(_env_file=None)

    assert settings.deepsee_workspace == resolve_runtime_workspace(
        "deepsee", "source"
    )
    assert settings.deepsee_workspace != Path(".")
