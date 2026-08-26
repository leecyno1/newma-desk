from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
AGENTSCOPE_ROOT = PACKAGE_DIR.parent
PROJECT_ROOT = Path(
    os.getenv("ORCHESTRA_PROJECT_ROOT", str(AGENTSCOPE_ROOT.parent)),
).expanduser()
DATA_DIR = Path(
    os.getenv("ORCHESTRA_DATA_DIR", str(PROJECT_ROOT / ".orchestra")),
).expanduser()


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    database_path: Path = Path(
        os.getenv("ORCHESTRA_DATABASE_PATH", str(DATA_DIR / "orchestra.db")),
    ).expanduser()
    database_url: str | None = os.getenv("ORCHESTRA_DATABASE_URL")
    secret_key_path: Path = Path(
        os.getenv("ORCHESTRA_SECRET_KEY_PATH", str(DATA_DIR / "secret.key")),
    ).expanduser()
    secret_master_key: str | None = os.getenv("ORCHESTRA_SECRET_MASTER_KEY")
    default_user_id: str = os.getenv("ORCHESTRA_DEFAULT_USER_ID", "local-user")
    session_ttl_seconds: int = max(
        300,
        int(os.getenv("ORCHESTRA_SESSION_TTL_SECONDS", "43200")),
    )
    session_cookie_secure: bool = os.getenv(
        "ORCHESTRA_SESSION_COOKIE_SECURE",
        "false",
    ).lower() in {"1", "true", "yes"}
    redis_url: str | None = os.getenv("ORCHESTRA_REDIS_URL")
    redis_queue_prefix: str = os.getenv("ORCHESTRA_REDIS_QUEUE_PREFIX", "orchestra")
    run_workers: int = max(1, int(os.getenv("ORCHESTRA_RUN_WORKERS", "1")))
    job_lease_seconds: int = max(
        15,
        int(os.getenv("ORCHESTRA_JOB_LEASE_SECONDS", "90")),
    )
    job_max_attempts: int = max(
        1,
        int(os.getenv("ORCHESTRA_JOB_MAX_ATTEMPTS", "3")),
    )
    job_retry_base_seconds: float = max(
        0.1,
        float(os.getenv("ORCHESTRA_JOB_RETRY_BASE_SECONDS", "5")),
    )
    queue_poll_seconds: float = max(
        0.1,
        float(os.getenv("ORCHESTRA_QUEUE_POLL_SECONDS", "1")),
    )
    registry_path: Path = PROJECT_ROOT / "agent_profiles.json"
    role_cards_dir: Path = PROJECT_ROOT / "agents"
    codex_skills_root: Path = Path.home() / ".codex" / "skills"
    agent_skills_root: Path = Path.home() / ".agents" / "skills"
    default_mode: str = os.getenv("ORCHESTRA_EXECUTION_MODE", "demo")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.5")
    tushare_token: str | None = os.getenv("TUSHARE_TOKEN")
    tushare_api_url: str = os.getenv("TUSHARE_API_URL", "https://api.tushare.pro")
    tavily_api_key: str | None = os.getenv("TAVILY_API_KEY")
    tavily_api_url: str = os.getenv("TAVILY_API_URL", "https://api.tavily.com/search")
    ima_client_id: str | None = os.getenv("IMA_OPENAPI_CLIENTID") or os.getenv(
        "IMA_CLIENT_ID",
    )
    ima_api_key: str | None = os.getenv("IMA_OPENAPI_APIKEY") or os.getenv("IMA_API_KEY")
    ima_base_url: str = os.getenv("IMA_BASE_URL", "https://ima.qq.com")
    ima_knowledge_base_ids: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("IMA_KNOWLEDGE_BASE_IDS", "").split(",")
        if item.strip()
    )
    financial_tool_timeout: float = max(
        3.0,
        float(os.getenv("ORCHESTRA_FINANCIAL_TOOL_TIMEOUT", "30")),
    )
    max_financial_rows: int = max(
        1,
        int(os.getenv("ORCHESTRA_MAX_FINANCIAL_ROWS", "100")),
    )
    max_web_content_chars: int = max(
        200,
        int(os.getenv("ORCHESTRA_MAX_WEB_CONTENT_CHARS", "1800")),
    )
    max_skill_context_chars: int = max(
        2000,
        int(os.getenv("ORCHESTRA_MAX_SKILL_CONTEXT_CHARS", "7000")),
    )
    max_total_skill_context_chars: int = max(
        10000,
        int(os.getenv("ORCHESTRA_MAX_TOTAL_SKILL_CONTEXT_CHARS", "32000")),
    )
    max_concurrency: int = max(1, int(os.getenv("ORCHESTRA_MAX_CONCURRENCY", "2")))
    agent_progress_interval: float = max(
        2.0,
        float(os.getenv("ORCHESTRA_AGENT_PROGRESS_INTERVAL", "4")),
    )
    max_run_history: int = max(10, int(os.getenv("ORCHESTRA_MAX_RUN_HISTORY", "50")))
    demo_delay: float = max(0.01, float(os.getenv("ORCHESTRA_DEMO_DELAY", "0.12")))


settings = Settings()
