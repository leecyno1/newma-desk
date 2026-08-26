from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    CORS_ALLOW_ORIGINS: str | None = None

    # chatlog
    CHATLOG_HTTP_BASE: str = Field(default="http://127.0.0.1:5030")
    CHATLOG_DIR: str | None = None
    CHATLOG_HTTP_SESSION_TIMEOUT_SECONDS: int = Field(default=5)
    CHATLOG_HTTP_TIMEOUT_SECONDS: int = Field(default=10)
    WX_CLI_BIN: str | None = None
    WX_CLI_TIMEOUT_SECONDS: int = Field(default=45)
    WX_CLI_SESSION_LIMIT: int = Field(default=200)

    # n8n webhooks
    N8N_REPLY_WEBHOOK: str | None = None
    N8N_SUMMARY_WEBHOOK: str | None = None
    N8N_CONTACT_WEBHOOK: str | None = None
    N8N_SEND_WEBHOOK: str | None = None
    N8N_AUTH_TOKEN: str | None = None

    # API
    API_TOKEN: str | None = None
    API_AUTH_REQUIRED: bool = Field(default=False)
    AGENT_API_TOKEN: str | None = None
    AGENT_API_TOKENS: str | None = None
    AGENT_API_ALLOWLIST: str | None = None
    AGENT_API_BLOCKLIST: str | None = None

    # DB
    DATABASE_URL: str = Field(default="sqlite:///./data/app.db")

    # Server
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8001)
    SYNC_INTERVAL_SECONDS: int | None = Field(default=0)
    EMAIL_SYNC_INTERVAL_SECONDS: int | None = Field(default=0)
    SUMMARY_OVERLAY_INTERVAL_SECONDS: int | None = Field(default=3600)

    # LLM
    SILICONFLOW_API_KEY: str | None = None
    SILICONFLOW_API_URL: str | None = "https://app.watertimber.us/v1"
    SILICONFLOW_MODEL: str | None = "gpt-5.5"
    SILICONFLOW_TOOL_MODEL: str | None = "MiniMax-M3"
    AI_MAX_PARALLEL: int = 32
    # Newma-Desk Agent Gateway. Disabled by default until batch output is verified.
    DESK_AGENT_ENABLED: bool = False
    DESK_AGENT_BASE_URL: str = "http://127.0.0.1:8911"
    DESK_AGENT_TOKEN: str | None = None
    DESK_AGENT_MODULE_ID: str = "deepsee-news"
    DESK_AGENT_TIMEOUT_SECONDS: int = Field(default=180)
    ONEPAGE_IMAGE_MODE: str = Field(default="auto")  # auto | image | local
    ONEPAGE_IMAGE_API_URL: str | None = None
    ONEPAGE_IMAGE_API_KEY: str | None = None
    ONEPAGE_IMAGE_MODEL: str = Field(default="MiniMax-M3")
    ONEPAGE_IMAGE_SIZE: str = Field(default="1024x1536")
    ONEPAGE_IMAGE_QUALITY: str = Field(default="medium")

    # Market data
    TUSHARE_TOKEN: str | None = None

    # WeChatPadPro
    WECHATPAD_HTTP_BASE: str | None = None  # e.g., http://60.205.58.39:1238
    WECHATPAD_TEXT_PATH: str | None = "/api/v1/message/sendText"  # fallback path for text sending

    # Extensions / Adapters
    LANGBOT_ADAPTER_LOG_DIR: str | None = None  # e.g., ./data/adapters

    MS_TENANT: str | None = "consumers"  # common/organizations/consumers

    # NewsNow aggregation (server on :4445)
    NEWSNOW_ENABLED: bool = True
    NEWSNOW_API_BASE: str = Field(default="http://localhost:4445")
    NEWSNOW_CACHE_TTL: int = Field(default=300)  # seconds
    # 默认每小时刷新一次（可用 .env 覆盖）
    NEWSNOW_REFRESH_INTERVAL_SECONDS: int | None = Field(default=3600)  # 0 = disabled (manual only)
    # 每3小时写入一次新闻舆情底层快照（datasets JSON）
    NEWS_SNAPSHOT_INTERVAL_SECONDS: int | None = Field(default=10800)
    AGGREGATION_RETENTION_DAYS: int = Field(default=90)
    AGGREGATION_RETENTION_INTERVAL_SECONDS: int = Field(default=86400)

    # Optional: MediaCrawlerPro server base (meeting recorder controls proxy)
    MEDIA_SERVER_BASE: str | None = None
    MEDIA_COLLECTOR_DAILY_ENABLED: bool = True
    MEDIA_COLLECTOR_DAILY_HOUR: int = Field(default=5)
    MEDIA_COLLECTOR_DAILY_MINUTE: int = Field(default=0)
    MEDIA_COLLECTOR_TIMEOUT_SECONDS: int = Field(default=240)
    MEDIA_COLLECTOR_AUTO_BOOTSTRAP: bool = Field(default=True)
    MEDIA_COLLECTOR_BOOTSTRAP_TIMEOUT_SECONDS: int = Field(default=60)

    # Media cache lifecycle
    MEDIA_CACHE_CLEANUP_ENABLED: bool = True
    MEDIA_CACHE_TTL_HOURS: int = Field(default=720)
    MEDIA_CACHE_MAX_MB: int = Field(default=256)
    MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS: int = Field(default=86400)

settings = Settings()
