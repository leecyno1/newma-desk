import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

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


CURRENT_DATABASE_NAME = "newma-desk.db"
LEGACY_DATABASE_NAMES = (
    "newma-dock.db",
    "vibedesk.db",
    "vibe-visualization.db",
)


def _default_database_path() -> Path:
    current = Path("runtime") / CURRENT_DATABASE_NAME
    for legacy_name in LEGACY_DATABASE_NAMES:
        legacy = current.with_name(legacy_name)
        if legacy.exists() and not current.exists():
            return legacy
    return current


def _module_revision_count(
    database_path: Path,
    *,
    published_only: bool = False,
) -> int | None:
    try:
        if not database_path.is_file() or database_path.stat().st_size == 0:
            return 0
        with sqlite3.connect(
            f"{database_path.resolve().as_uri()}?mode=ro",
            uri=True,
        ) as connection:
            table_exists = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'module_revisions'
                """
            ).fetchone()
            if table_exists is None:
                return 0
            where_clause = " WHERE status = 'published'" if published_only else ""
            row = connection.execute(
                f"SELECT COUNT(*) FROM module_revisions{where_clause}"
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    return int(row[0]) if row is not None else 0


def _database_has_application_rows(database_path: Path) -> bool | None:
    try:
        if not database_path.is_file() or database_path.stat().st_size == 0:
            return False
        with sqlite3.connect(
            f"{database_path.resolve().as_uri()}?mode=ro",
            uri=True,
        ) as connection:
            table_names = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            for (table_name,) in table_names:
                quoted_name = str(table_name).replace('"', '""')
                if (
                    connection.execute(
                        f'SELECT 1 FROM "{quoted_name}" LIMIT 1'
                    ).fetchone()
                    is not None
                ):
                    return True
    except (OSError, sqlite3.Error):
        return None
    return False


def _migrate_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.name}.migrating-{os.getpid()}-{uuid4().hex}"
    )
    expected_published = _module_revision_count(source, published_only=True)
    if not expected_published:
        raise sqlite3.DatabaseError("legacy database has no published Mods")
    try:
        with sqlite3.connect(
            f"{source.resolve().as_uri()}?mode=ro",
            uri=True,
        ) as source_connection:
            with sqlite3.connect(temporary) as target_connection:
                source_connection.backup(target_connection)
        migrated_published = _module_revision_count(
            temporary,
            published_only=True,
        )
        if migrated_published != expected_published:
            raise sqlite3.DatabaseError("database migration verification failed")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_database_path(configured_path: Path) -> Path:
    """Resolve the renamed database without overwriting existing user data.

    A pristine ``newma-desk.db`` is migrated from the first legacy database
    containing published Mods. If the new database already contains any data,
    it is never overwritten; when its registry is empty, the populated legacy
    database remains the non-destructive fallback.
    """

    configured_path = configured_path.expanduser()
    if configured_path.name != CURRENT_DATABASE_NAME:
        return configured_path

    current_revision_count = _module_revision_count(configured_path)
    if current_revision_count:
        return configured_path

    legacy_path = next(
        (
            configured_path.with_name(name)
            for name in LEGACY_DATABASE_NAMES
            if (
                _module_revision_count(
                    configured_path.with_name(name),
                    published_only=True,
                )
                or 0
            )
            > 0
        ),
        None,
    )
    if legacy_path is None:
        return configured_path

    if _database_has_application_rows(configured_path) is False:
        try:
            _migrate_database(legacy_path, configured_path)
        except (OSError, sqlite3.Error):
            return legacy_path
        return configured_path

    return legacy_path


def _default_archify_root() -> Path:
    return Path(__file__).resolve().parents[3] / "vendor" / "archify"


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_investment_workspace() -> Path:
    return _default_project_root() / "mod-projects" / "vibe-research"


def _default_trading_workspace() -> Path:
    return _default_project_root() / "mod-projects" / "vibe-trading"


def _default_portfolio_center_dist() -> Path:
    return _default_project_root() / "modules" / "portfolio-center" / "dist"


def _default_creator_studio_workspace() -> Path:
    return resolve_runtime_workspace("creator-studio", "source")


def _default_creator_studio_dist() -> Path:
    return _default_project_root() / "modules" / "creator-studio" / "dist"


def _default_workflow_center_dist() -> Path:
    return _default_project_root() / "modules" / "workflow-center" / "dist"


def _default_policy_analysis_dist() -> Path:
    return _default_project_root() / "modules" / "policy-analysis" / "dist"


def _default_capital_flow_dist() -> Path:
    return _default_project_root() / "modules" / "capital-flow" / "dist"


def _default_external_finance_pilot_descriptor() -> Path:
    return _default_project_root() / "config" / "external-finance-mod-pilots.json"


def _default_finance_project_intake_descriptor() -> Path:
    return _default_project_root() / "config" / "finance-project-intake.json"


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
        env_prefix="NEWMA_DESK_",
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
    openai_fallback_models: str = ""
    openai_api_key_required: bool = True
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_version: str = "2023-06-01"
    anthropic_max_tokens: int = Field(default=4096, ge=1, le=65536)
    model_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    agent_default_adapter: str = "codex-cli"
    agent_timeout_seconds: float = Field(default=300.0, gt=0, le=900)
    agent_batch_concurrency: int = Field(default=3, ge=1, le=16)
    enable_domain_suites: bool = False
    domain_suite_workspace_venvs: bool = False
    workspace_root: Path = Path(".")
    investment_workspace: Path = Field(default_factory=_default_investment_workspace)
    trading_workspace: Path = Field(default_factory=_default_trading_workspace)
    portfolio_center_dist: Path = Field(default_factory=_default_portfolio_center_dist)
    creator_studio_workspace: Path = Field(
        default_factory=_default_creator_studio_workspace
    )
    creator_studio_dist: Path = Field(default_factory=_default_creator_studio_dist)
    workflow_center_dist: Path = Field(default_factory=_default_workflow_center_dist)
    policy_analysis_dist: Path = Field(default_factory=_default_policy_analysis_dist)
    capital_flow_dist: Path = Field(default_factory=_default_capital_flow_dist)
    capital_flow_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    policy_rsshub_base_url: str = ""
    policy_collector_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    policy_refresh_seconds: float = Field(default=14400, ge=300, le=86400)
    external_finance_pilot_descriptor: Path = Field(
        default_factory=_default_external_finance_pilot_descriptor
    )
    finance_project_intake_descriptor: Path = Field(
        default_factory=_default_finance_project_intake_descriptor
    )
    deepsee_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("deepsee", "source")
    )
    seven_cycle_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("seven-cycle", "source")
    )
    instock_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("instock", "source")
    )
    fund_analysis_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("fund-analysis", "source")
    )
    orchestra_frontend_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("orchestra", "frontend")
    )
    orchestra_backend_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("orchestra", "backend")
    )
    world_intel_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("world-intel", "source")
    )
    crucix_workspace: Path = Field(
        default_factory=lambda: resolve_runtime_workspace("crucix", "source")
    )
    mod_workspace_overrides: str = ""
    investment_web_url: str = "http://127.0.0.1:8911"
    trading_web_url: str = "http://127.0.0.1:8911"
    creator_studio_web_url: str = "http://127.0.0.1:8911"
    seven_cycle_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("seven-cycle", "web")
    )
    deepsee_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("deepsee", "web")
    )
    instock_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("instock", "web")
    )
    fund_research_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("fund-analysis", "web")
    )
    fund_analysis_api_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("fund-analysis", "api")
    )
    orchestra_web_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("orchestra", "web")
    )
    orchestra_api_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("orchestra", "api")
    )
    world_intel_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("world-intel", "api")
    )
    crucix_url: str = Field(
        default_factory=lambda: resolve_runtime_origin("crucix", "api")
    )
    mod_store_dir: Path = Path("mods")
    mod_store_git_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    mod_store_github_token: SecretStr = SecretStr("")
    # Standard managed nodes use 8788. c10375 is the explicit 8787 exception
    # and must override this through NEWMA_DESK_HERMES_WEBUI_BASE_URL.
    hermes_webui_base_url: str = "http://127.0.0.1:8788"
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
    trading_api_key: SecretStr = SecretStr("")
    portfolio_quote_timeout_seconds: float = Field(default=2.5, gt=0, le=30)
    legacy_portfolio_path: Path = Path("~/.vibe-research/portfolio.json")
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
            EnvSettingsSource(settings_cls, env_prefix="NEWMA_DOCK_"),
            EnvSettingsSource(settings_cls, env_prefix="VIBEDESK_"),
            EnvSettingsSource(settings_cls, env_prefix="VIBE_VIS_"),
            dotenv_settings,
            DotEnvSettingsSource(
                settings_cls,
                env_file=".env",
                env_prefix="NEWMA_DOCK_",
            ),
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

    @field_validator("policy_rsshub_base_url")
    @classmethod
    def validate_policy_rsshub_base_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError("Policy RSSHub base URL must be an HTTP URL")
        return value.rstrip("/")

    @field_validator("crucix_url")
    @classmethod
    def validate_crucix_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Crucix URL must be a 127.0.0.1 HTTP origin")
        return f"http://{parsed.netloc}"

    @field_validator(
        "investment_web_url",
        "trading_web_url",
        "creator_studio_web_url",
        "seven_cycle_web_url",
        "deepsee_web_url",
        "instock_web_url",
        "fund_research_web_url",
        "fund_analysis_api_url",
        "orchestra_web_url",
        "orchestra_api_url",
        "world_intel_url",
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
