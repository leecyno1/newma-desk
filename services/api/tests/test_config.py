from pathlib import Path

import pytest
from pydantic import ValidationError

from vibe_visualization_api.config import Settings


def test_vibedesk_environment_names_take_priority(monkeypatch) -> None:
    monkeypatch.setenv("VIBEDESK_DATABASE_PATH", "runtime/current.db")
    monkeypatch.setenv("VIBE_VIS_DATABASE_PATH", "runtime/legacy.db")

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("runtime/current.db")


def test_legacy_environment_names_remain_compatible(monkeypatch) -> None:
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
    with pytest.raises(ValidationError, match="Mod web URL"):
        Settings(investment_web_url=value, _env_file=None)
