"""Configuration owned by the global intelligence project, not the Desk host."""
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GLOBAL_INTELLIGENCE_", env_file=None, extra="ignore")

    database_path: Path = Path.home() / ".local/state/newma-global/topics.sqlite3"
    world_intel_url: str = ""
    crucix_url: str = ""
    tushare_token: SecretStr = SecretStr("")


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "global_intelligence_settings", None)
    if settings is None:
        raise HTTPException(503, "全球情报运行配置未接入")
    return settings
