from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_VIS_", env_file=".env")

    runtime_dir: Path = Path("runtime")
    database_path: Path = Path("runtime/vibe-visualization.db")
    allowed_origins: str = "http://127.0.0.1:5888,http://127.0.0.1:5891"

    def origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
