"""Configuration owned by the global intelligence project, not the Desk host."""
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GLOBAL_INTELLIGENCE_", env_file=None, extra="ignore")

    database_path: Path = Path.home() / ".local/state/newma-global/topics.sqlite3"
    world_intel_url: str = ""
    crucix_url: str = ""
    tushare_token: SecretStr = SecretStr("")
    access_mode: Literal["local", "desk"] = "local"
    desk_scope_url: str = ""

    @model_validator(mode="after")
    def validate_access(self):
        from .access import validate_scope_url
        if self.access_mode == "desk":
            validate_scope_url(self.desk_scope_url)
        elif self.desk_scope_url:
            raise ValueError("desk_scope_url requires access_mode=desk")
        return self


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "global_intelligence_settings", None)
    if settings is None:
        raise HTTPException(503, "全球情报运行配置未接入")
    return settings


async def authorize_global_read(request: Request) -> None:
    authorizer = getattr(request.app.state, "global_read_authorizer", None)
    if authorizer is not None:
        await authorizer(request)


async def global_topic_scope(request: Request) -> tuple[str, str] | None:
    authorizer = getattr(request.app.state, "global_topic_authorizer", None)
    return await authorizer(request) if authorizer is not None else None
