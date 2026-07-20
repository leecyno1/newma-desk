from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_VIS_", env_file=".env")

    runtime_dir: Path = Path("runtime")
    database_path: Path = Path("runtime/vibe-visualization.db")
    allowed_origins: str = "http://127.0.0.1:5888,http://127.0.0.1:5891"
    agent_default_adapter: str = "openai-compatible"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.6"
    agent_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    data_service_public_mode: bool = False
    trade_confirmation_secret: SecretStr = SecretStr("")

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

    def origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


def get_settings() -> Settings:
    return Settings()
