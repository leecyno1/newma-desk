"""
全局配置设置

管理系统的全局配置参数，包括数据库连接、API配置、缓存设置等。
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseSettings, Field
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Settings(BaseSettings):
    """系统全局配置类"""
    
    # 项目基础配置
    PROJECT_NAME: str = "周期判断系统"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # 数据库配置
    DATABASE_URL: str = Field(default="sqlite:///cycle_analysis.db", env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis缓存配置
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    CACHE_TTL: int = Field(default=3600, env="CACHE_TTL")  # 缓存过期时间（秒）
    
    # 数据源API配置
    AKSHARE_TIMEOUT: int = Field(default=30, env="AKSHARE_TIMEOUT")
    FRED_API_KEY: Optional[str] = Field(default=None, env="FRED_API_KEY")
    YAHOO_FINANCE_TIMEOUT: int = Field(default=30, env="YAHOO_FINANCE_TIMEOUT")
    
    # 数据采集配置
    DATA_UPDATE_INTERVAL: int = Field(default=3600, env="DATA_UPDATE_INTERVAL")  # 数据更新间隔（秒）
    MAX_CONCURRENT_REQUESTS: int = Field(default=5, env="MAX_CONCURRENT_REQUESTS")
    REQUEST_DELAY: float = Field(default=0.5, env="REQUEST_DELAY")  # 请求间隔（秒）
    
    # 数据存储配置
    DATA_DIR: Path = Field(default=Path("data"), env="DATA_DIR")
    BACKUP_DIR: Path = Field(default=Path("backup"), env="BACKUP_DIR")
    LOG_DIR: Path = Field(default=Path("logs"), env="LOG_DIR")
    
    # 日志配置
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_ROTATION: str = Field(default="1 day", env="LOG_ROTATION")
    LOG_RETENTION: str = Field(default="30 days", env="LOG_RETENTION")
    
    # 计算配置
    N_JOBS: int = Field(default=-1, env="N_JOBS")  # 并行计算核心数
    CHUNK_SIZE: int = Field(default=10000, env="CHUNK_SIZE")  # 数据分块大小
    
    # 周期分析配置
    MIN_CYCLE_LENGTH: int = Field(default=6, env="MIN_CYCLE_LENGTH")  # 最小周期长度（月）
    MAX_CYCLE_LENGTH: int = Field(default=720, env="MAX_CYCLE_LENGTH")  # 最大周期长度（月）
    CYCLE_DETECTION_WINDOW: int = Field(default=120, env="CYCLE_DETECTION_WINDOW")  # 周期检测窗口（月）
    
    # 预测配置
    PREDICTION_HORIZON: int = Field(default=12, env="PREDICTION_HORIZON")  # 预测时间范围（月）
    CONFIDENCE_LEVEL: float = Field(default=0.95, env="CONFIDENCE_LEVEL")  # 置信水平
    
    # 可视化配置
    PLOT_WIDTH: int = Field(default=1200, env="PLOT_WIDTH")
    PLOT_HEIGHT: int = Field(default=600, env="PLOT_HEIGHT")
    PLOT_DPI: int = Field(default=100, env="PLOT_DPI")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._create_directories()
    
    def _create_directories(self) -> None:
        """创建必要的目录"""
        directories = [self.DATA_DIR, self.BACKUP_DIR, self.LOG_DIR]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @property
    def database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return {
            "url": self.DATABASE_URL,
            "pool_size": self.DATABASE_POOL_SIZE,
            "max_overflow": self.DATABASE_MAX_OVERFLOW,
            "echo": self.DEBUG
        }
    
    @property
    def redis_config(self) -> Dict[str, Any]:
        """获取Redis配置"""
        return {
            "url": self.REDIS_URL,
            "decode_responses": True,
            "socket_timeout": 5,
            "socket_connect_timeout": 5
        }
    
    @property
    def logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return {
            "level": self.LOG_LEVEL,
            "rotation": self.LOG_ROTATION,
            "retention": self.LOG_RETENTION,
            "format": "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
            "backtrace": True,
            "diagnose": True
        }


# 全局配置实例
settings = Settings() 