from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_VIS_", env_file=".env")

    runtime_dir: Path = Path("runtime")
    database_path: Path = Path("runtime/vibe-visualization.db")
    allowed_origins: str = "http://127.0.0.1:5888,http://127.0.0.1:5891"
    model_default_adapter: str = "openai-compatible"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.6"
    openai_api_key_required: bool = True
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_version: str = "2023-06-01"
    anthropic_max_tokens: int = Field(default=4096, ge=1, le=65536)
    model_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    agent_default_adapter: str = "hermes-webui"
    agent_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    hermes_webui_base_url: str = "http://127.0.0.1:8787"
    hermes_webui_cookie: SecretStr = SecretStr("")
    hermes_webui_csrf_token: SecretStr = SecretStr("")
    hermes_webui_workspace: str = ""
    data_service_public_mode: bool = False
    trade_confirmation_secret: SecretStr = SecretStr("")
    research_base_url: str = "http://127.0.0.1:8900"
    research_api_key: SecretStr = SecretStr("")
    enable_scheduler: bool = False
    scheduler_poll_seconds: float = Field(default=30.0, gt=0, le=3600)

    @field_validator("openai_base_url")
    @classmethod
    def validate_openai_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "OpenAI-compatible base URL must be an HTTP origin or path"
            )
        return value.rstrip("/")

    @field_validator("hermes_webui_base_url")
    @classmethod
    def validate_hermes_webui_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Hermes WebUI base URL must be an HTTP origin or path")
        return value.rstrip("/")

    @field_validator("anthropic_base_url")
    @classmethod
    def validate_anthropic_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Anthropic base URL must be an HTTP origin or path")
        return value.rstrip("/")

    @field_validator("research_base_url")
    @classmethod
    def validate_research_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Research base URL must be an HTTP origin or path")
        return value.rstrip("/")

    def origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


def get_settings() -> Settings:
    return Settings()
