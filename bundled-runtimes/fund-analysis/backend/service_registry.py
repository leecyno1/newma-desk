"""
服务注册表 - 解决模块间循环引用
数据源：Tushare
"""
import os
import time
import logging
from typing import Optional

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

# 数据源：Tushare
DATA_SOURCE = os.environ.get("DATA_SOURCE", "tushare").lower()


def init_services(scoring_eng=None, tushare_svc=None, pg_engine=None):
    global _scoring_engine, _tushare_service, _pg_engine
    if tushare_svc is not None:
        _tushare_service = tushare_svc
    if scoring_eng is not None:
        _scoring_engine = scoring_eng
    if pg_engine is not None:
        _pg_engine = pg_engine


_tushare_service: Optional["TushareDataService"] = None
_scoring_engine: Optional["FundScoringEngine"] = None
_pg_engine = None


def get_data_service():
    """获取当前数据服务（Tushare）"""
    global _tushare_service

    if _tushare_service is None:
        from services.tushare_service import TushareDataService
        _tushare_service = TushareDataService()
    return _tushare_service


def get_tushare_service() -> "TushareDataService":
    global _tushare_service
    if _tushare_service is None:
        from services.tushare_service import TushareDataService
        _tushare_service = TushareDataService()
    return _tushare_service


def get_strict_tushare_service() -> "TushareDataService":
    """获取严格真实数据服务；缺少 Tushare 凭据或 SDK 时直接失败，禁止 mock。"""
    from services.tushare_service import TushareDataService

    return TushareDataService(strict_no_mock=True)


def get_scoring_engine() -> "FundScoringEngine":
    global _scoring_engine
    if _scoring_engine is None:
        from services.scoring_engine import FundScoringEngine
        _scoring_engine = FundScoringEngine()
    return _scoring_engine


def get_pg_engine():
    """获取 PostgreSQL SQLAlchemy 引擎（核心数据存储）"""
    global _pg_engine
    if _pg_engine is None:
        try:
            from sqlalchemy import create_engine
            pg_url = get_database_url("postgresql://postgres@localhost:5432/fund_analysis")
            _pg_engine = create_engine(pg_url, pool_pre_ping=True)
            logger.info("PostgreSQL connected")
        except Exception as e:
            logger.warning(f"PostgreSQL not available: {e}")
            _pg_engine = None
    return _pg_engine
