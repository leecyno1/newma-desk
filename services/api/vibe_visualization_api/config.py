from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from vibe_visualization_api.external_mod_runtimes import (
    default_external_origins,
    resolve_runtime_origin,
    resolve_runtime_workspace,
)


def _default_database_path() -> Path:
    current = Path("runtime/newma-dock.db")
    for legacy in (
        Path("runtime/vibedesk.db"),
        Path("runtime/vibe-visualization.db"),
    ):
        if legacy.exists() and not current.exists():
            return legacy
    return current


def _default_archify_root() -> Path:
    return Path(__file__).resolve().parents[3] / "vendor" / "archify"


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_investment_workspace() -> Path:
    return _default_project_root() / "mod-projects" / "vibe-research"


def _default_trading_workspace() -> Path:
    return _default_project_root() / "mod-projects" / "vibe-trading"


def _default_allowed_origins() -> str:
    origins = [
        "http://127.0.0.1:5888",
        "http://127.0.0.1:5891",
        "http://127.0.0.1:8911",
        *default_external_origins(),
    ]
    return ",".join(dict.fromkeys(origins))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEWMA_DOCK_",
        env_file=".env",
        env_ignore_empty=True,
    )

    runtime_dir: Path = Path("runtime")
    database_path: Path = Field(default_factory=_default_database_path)
    allowed_origins: str = Field(default_factory=_default_allowed_origins)
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
    agent_default_adapter: str = "codex-cli"
    agent_timeout_seconds: float = Field(default=300.0, gt=0, le=900)
    enable_domain_suites: bool = False
    workspace_root: Path = Path(".")
    investment_workspace: Path = Field(default_factory=_default_investment_workspace)
    trading_workspace: Path = Field(default_factory=_default_trading_workspace)
    deepsee_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("deepsee", "source")
    )
    seven_cycle_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("seven-cycle", "source")
    )
    instock_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("instock", "source")
    )
    orchestra_frontend_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("orchestra", "frontend")
    )
    orchestra_backend_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("orchestra", "backend")
    )
    mod_workspace_overrides: str = ""
    investment_web_url: str = "http://127.0.0.1:8911"
    trading_web_url: str = "http://127.0.0.1:8911"
    seven_cycle_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("seven-cycle", "web")
    )
    deepsee_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("deepsee", "web")
    )
    instock_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("instock", "web")
    )
    orchestra_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("orchestra", "web")
    )
    orchestra_api_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("orchestra", "api")
    )
    mod_store_dir: Path = Path("mods")
    mod_store_git_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    hermes_webui_base_url: str = "http://127.0.0.1:8787"
    hermes_webui_cookie: SecretStr = SecretStr("")
    hermes_webui_csrf_token: SecretStr = SecretStr("")
    hermes_webui_workspace: str = ""
    data_service_dirs: str = "integrations"
    data_service_public_mode: bool = False
    mod_session_secret: SecretStr = SecretStr("")
    mod_session_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    trade_confirmation_secret: SecretStr = SecretStr("")
    research_base_url: str = "http://127.0.0.1:8911/api/research"
    research_api_key: SecretStr = SecretStr("")
    enable_scheduler: bool = False
    scheduler_poll_seconds: float = Field(default=30.0, gt=0, le=3600)
    archify_root: Path = Field(default_factory=_default_archify_root)
    node_binary: str = "node"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            EnvSettingsSource(settings_cls, env_prefix="VIBEDESK_"),
            EnvSettingsSource(settings_cls, env_prefix="VIBE_VIS_"),
            dotenv_settings,
            DotEnvSettingsSource(
                settings_cls,
                env_file=".env",
                env_prefix="VIBEDESK_",
            ),
            DotEnvSettingsSource(
                settings_cls,
                env_file=".env",
                env_prefix="VIBE_VIS_",
            ),
            file_secret_settings,
        )

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

    @field_validator(
        "investment_web_url",
        "trading_web_url",
        "seven_cycle_web_url",
        "deepsee_web_url",
        "instock_web_url",
        "orchestra_web_url",
        "orchestra_api_url",
    )
    @classmethod
    def validate_mod_web_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Mod web URL must be an HTTP(S) origin")
        return f"{parsed.scheme}://{parsed.netloc}"

    def origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]

    def data_service_paths(self) -> list[Path]:
        return [
            Path(value.strip()).expanduser()
            for value in self.data_service_dirs.split(",")
            if value.strip()
        ]


def get_settings() -> Settings:
    return Settings()
