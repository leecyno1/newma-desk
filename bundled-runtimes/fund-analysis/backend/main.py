"""
FastAPI 应用入口
"""
import sys
import os
import logging
from pathlib import Path

# 加载 .env 环境变量：后端服务与批处理脚本保持一致，优先读取项目根目录配置。
_backend_dir = Path(__file__).parent
_root_dir = _backend_dir.parent
for _env_file in (_root_dir / ".env.local", _root_dir / ".env", _backend_dir / ".env"):
    if _env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
        print(f"[CONFIG] Loaded .env from {_env_file}")

sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, date
from decimal import Decimal
import math
import uuid
import json

from routes import funds, fund_companies, home, managers, scoring, reports, research_reports, research_memos, research_folders, watchlists
from routes import attribution, barra, brinson, export, data_sync, data_health, metrics, fund_pools, alerts, investment_analysis, fund_browser, market_indices, newma_desk, investment_theses, anomaly_scanner, fund_watches, research_queue, decision_postmortems, research_decision_logs, research_signals, decision_support, portfolio
from service_registry import get_data_service, get_scoring_engine, get_db

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _nan_safe_encoder(obj):
    """处理 NaN/Inf/uuid 序列化"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def clean_nan(value):
    """递归清理 NaN/Inf 值"""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_nan(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


class NaNSafeJSONResponse(JSONResponse):
    """处理 NaN 和 Inf 值的 JSON 响应"""
    def render(self, content) -> bytes:
        cleaned = clean_nan(content)
        return json.dumps(cleaned).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing services...")

    # 初始化缓存（提前，以供其他服务使用）
    from services.cache_service import get_cache
    cache = get_cache()
    logger.info(f"Cache backend: {cache.__class__.__name__}")

    data_svc = get_data_service()
    logger.info(f"Data source: {'Tushare' if data_svc.__class__.__name__ == 'TushareDataService' else 'Wind'} (mock_mode={data_svc.mock_mode})")
    scoring_eng = get_scoring_engine()
    logger.info("Scoring engine initialized")

    # 初始化 PostgreSQL 数据库表
    try:
        from database import init_database
        init_database()
    except Exception as e:
        logger.warning(f"Database init warning: {e}")

    db = get_db()
    if db is not None:
        logger.info("MongoDB connected (research reports)")

    # 初始化向量数据库
    try:
        from services.vector_db_service import get_vector_db
        vector_db = get_vector_db()
        info = vector_db.get_collection_info()
        logger.info(f"Vector DB connected: {info.get('name')} with {info.get('points_count', 0)} points")
    except Exception as e:
        logger.warning(f"Vector DB init warning: {e}")

    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown")


app = FastAPI(
    title="基金分析系统 API",
    description="基金经理评价 · 基金筛选 · Barra风险分析 · Brinson归因 · AI报告生成 | 数据源: Tushare",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=NaNSafeJSONResponse,
)

_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router, tags=["基金"])
app.include_router(home.router, tags=["选基首页"])
app.include_router(fund_browser.router, tags=["基金浏览器"])
app.include_router(fund_companies.router, tags=["基金公司"])
app.include_router(managers.router, tags=["基金经理"])
app.include_router(scoring.router, tags=["评分系统"])
app.include_router(reports.router, tags=["AI报告"])
app.include_router(research_reports.router, tags=["调研纪要"])
app.include_router(research_memos.router, tags=["证据研究备忘录"])
app.include_router(research_folders.router, tags=["本地调研纪要文件夹"])
app.include_router(attribution.router, tags=["基金业绩归因"])
app.include_router(barra.router, tags=["Barra风险分析"])
app.include_router(brinson.router, tags=["Brinson归因"])
app.include_router(export.router, tags=["数据导出"])
app.include_router(data_sync.router, tags=["数据同步"])
app.include_router(data_health.router, tags=["数据健康"])
app.include_router(metrics.router, tags=["指标快照"])
app.include_router(fund_pools.router, tags=["基金池"])
app.include_router(market_indices.router, tags=["市场指数"])
app.include_router(watchlists.router, tags=["我的自选"])
app.include_router(alerts.router, tags=["预警中心"])
app.include_router(investment_analysis.router, tags=["高级投资分析"])
app.include_router(newma_desk.router, tags=["Newma Desk"])
app.include_router(investment_theses.router, tags=["投资论点"])
app.include_router(anomaly_scanner.router, tags=["异常筛查"])
app.include_router(fund_watches.router, tags=["观察项"])
app.include_router(research_queue.router, tags=["研究队列"])
app.include_router(decision_postmortems.router, tags=["决策复盘"])
app.include_router(research_decision_logs.router, tags=["研究决策记录"])
app.include_router(research_signals.router, tags=["研究信号雷达"])
app.include_router(decision_support.router, tags=["决策支持"])
app.include_router(portfolio.router, tags=["基金组合"])


@app.get("/api/health")
async def health_check():
    from service_registry import DATA_SOURCE
    from database import check_database_health
    data_svc = get_data_service()
    database_health = check_database_health(min_fund_count=1)
    status = "ok" if database_health.get("status") == "ok" else "degraded"
    payload = {
        "status": status,
        "service": "fund-analysis-api",
        "version": "2.0.0",
        "data_source": DATA_SOURCE,
        "mock_mode": data_svc.mock_mode,
        "database": database_health,
    }
    if status != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/api/config")
async def get_config():
    from service_registry import DATA_SOURCE
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    compatible_provider = provider in {"siliconflow", "deepseek", "openai-compatible"}

    def _valid_secret(name: str) -> bool:
        value = (os.environ.get(name) or "").strip()
        return len(value) >= 30

    if provider in {"siliconflow", "deepseek"}:
        compatible_key_configured = _valid_secret("SILICONFLOW_API_KEY") or _valid_secret("LLM_API_KEY")
    elif provider == "openai-compatible":
        compatible_key_configured = bool(
            _valid_secret("OPENAI_COMPATIBLE_API_KEY")
            or _valid_secret("LLM_API_KEY")
            or _valid_secret("OPENAI_API_KEY")
        )
    else:
        compatible_key_configured = False
    anthropic_key_configured = _valid_secret("ANTHROPIC_API_KEY")
    return {
        "data_source": DATA_SOURCE,
        "tushare_token_configured": bool(os.environ.get("TUSHARE_TOKEN")),
        "anthropic_api_configured": anthropic_key_configured,
        "llm_provider": provider,
        "llm_model": os.environ.get("LLM_MODEL") or os.environ.get("SILICONFLOW_MODEL") or os.environ.get("OPENAI_COMPATIBLE_MODEL"),
        "llm_base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("SILICONFLOW_BASE_URL") or os.environ.get("OPENAI_COMPATIBLE_BASE_URL"),
        "llm_api_configured": compatible_key_configured if compatible_provider else anthropic_key_configured,
        "siliconflow_api_configured": bool(
            _valid_secret("SILICONFLOW_API_KEY") or _valid_secret("LLM_API_KEY")
        ) if provider in {"siliconflow", "deepseek"} else False,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
