"""
Redis 缓存服务 - 提供基金数据的缓存层，提升 API 响应速度
Redis 连接失败时自动降级到 NullCache（无缓存模式）
"""
import os
import json
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class NullCache:
    """无缓存实现（Redis 不可用时降级使用）"""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        return True

    def delete(self, key: str) -> bool:
        return True

    def delete_pattern(self, pattern: str) -> int:
        return 0

    def exists(self, key: str) -> bool:
        return False

    def get_stats(self) -> Dict[str, Any]:
        return {"hits": 0, "misses": 0, "hit_rate": 0, "mode": "null_cache"}


class RedisCache:
    """Redis 缓存实现"""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._stats_lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}

    def get(self, key: str) -> Optional[Any]:
        try:
            value = self._redis.get(key)
            if value is not None:
                with self._stats_lock:
                    self._stats["hits"] += 1
                return json.loads(value)
            with self._stats_lock:
                self._stats["misses"] += 1
            return None
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            with self._stats_lock:
                self._stats["misses"] += 1
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            self._redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
            return True
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            self._redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        try:
            keys = self._redis.keys(pattern)
            if keys:
                return self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis delete_pattern error: {e}")
            return 0

    def exists(self, key: str) -> bool:
        try:
            return bool(self._redis.exists(key))
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = self._stats.copy()
        total = stats["hits"] + stats["misses"]
        stats["hit_rate"] = round(stats["hits"] / total * 100, 2) if total > 0 else 0
        stats["mode"] = "redis"
        return stats


class CacheService:
    """
    缓存服务 - 统一缓存接口

    缓存策略：
    - 基金信息: TTL=24h
    - 基金净值: TTL=1h
    - 基金业绩: TTL=6h
    - 基金评分: TTL=30min
    - 经理信息: TTL=12h
    - 调研报告: TTL=24h
    """

    # TTL 配置（秒）
    TTL_FUND_INFO = 86400       # 24h
    TTL_FUND_NAV = 3600        # 1h
    TTL_FUND_PERFORMANCE = 21600  # 6h
    TTL_FUND_SCORE = 1800      # 30min
    TTL_MANAGER_INFO = 43200    # 12h
    TTL_RESEARCH_REPORT = 86400  # 24h

    # Key 前缀
    KEY_FUND_INFO = "fund:info:"
    KEY_FUND_NAV = "fund:nav:"
    KEY_FUND_PERFORMANCE = "fund:perf:"
    KEY_FUND_RISK = "fund:risk:"
    KEY_FUND_STYLE = "fund:style:"
    KEY_FUND_SCORE = "fund:score:"
    KEY_MANAGER_INFO = "mgr:info:"
    KEY_MANAGER_FUNDS = "mgr:funds:"
    KEY_RESEARCH_REPORT = "rr:report:"

    def __init__(self):
        self._cache: Optional[RedisCache | NullCache] = None
        self._init_cache()

    def _init_cache(self):
        """初始化缓存，失败时降级为 NullCache"""
        try:
            import redis

            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            redis_password = os.getenv("REDIS_PASSWORD")

            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )

            # 测试连接
            redis_client.ping()

            self._cache = RedisCache(redis_client)
            logger.info(f"Redis cache initialized: {redis_host}:{redis_port}")

        except ImportError:
            logger.warning("redis-py not installed. Using NullCache. Install with: pip install redis")
            self._cache = NullCache()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using NullCache (no caching).")
            self._cache = NullCache()

    def _is_available(self) -> bool:
        """检查缓存是否可用"""
        return isinstance(self._cache, RedisCache)

    # ===== Fund Cache =====

    def get_fund_info(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金信息缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_FUND_INFO}{wind_code}")

    def set_fund_info(self, wind_code: str, info: Dict[str, Any]):
        """设置基金信息缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_FUND_INFO}{wind_code}", info, self.TTL_FUND_INFO)

    def get_fund_performance(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金业绩缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_FUND_PERFORMANCE}{wind_code}")

    def set_fund_performance(self, wind_code: str, perf: Dict[str, Any]):
        """设置基金业绩缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_FUND_PERFORMANCE}{wind_code}", perf, self.TTL_FUND_PERFORMANCE)

    def get_fund_risk(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金风险指标缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_FUND_RISK}{wind_code}")

    def set_fund_risk(self, wind_code: str, risk: Dict[str, Any]):
        """设置基金风险指标缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_FUND_RISK}{wind_code}", risk, self.TTL_FUND_PERFORMANCE)

    def get_fund_style(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金风格缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_FUND_STYLE}{wind_code}")

    def set_fund_style(self, wind_code: str, style: Dict[str, Any]):
        """设置基金风格缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_FUND_STYLE}{wind_code}", style, self.TTL_FUND_PERFORMANCE)

    def get_fund_score(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金评分缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_FUND_SCORE}{wind_code}")

    def set_fund_score(self, wind_code: str, score: Dict[str, Any]):
        """设置基金评分缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_FUND_SCORE}{wind_code}", score, self.TTL_FUND_SCORE)

    # ===== Manager Cache =====

    def get_manager_info(self, manager_id: str) -> Optional[Dict[str, Any]]:
        """获取经理信息缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_MANAGER_INFO}{manager_id}")

    def set_manager_info(self, manager_id: str, info: Dict[str, Any]):
        """设置经理信息缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_MANAGER_INFO}{manager_id}", info, self.TTL_MANAGER_INFO)

    def get_manager_funds(self, manager_id: str) -> Optional[List[Dict[str, Any]]]:
        """获取经理管理基金列表缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_MANAGER_FUNDS}{manager_id}")

    def set_manager_funds(self, manager_id: str, funds: List[Dict[str, Any]]):
        """设置经理管理基金列表缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_MANAGER_FUNDS}{manager_id}", funds, self.TTL_MANAGER_INFO)

    # ===== Research Report Cache =====

    def get_research_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """获取调研报告缓存"""
        if not self._is_available():
            return None
        return self._cache.get(f"{self.KEY_RESEARCH_REPORT}{report_id}")

    def set_research_report(self, report_id: str, report: Dict[str, Any]):
        """设置调研报告缓存"""
        if not self._is_available():
            return
        self._cache.set(f"{self.KEY_RESEARCH_REPORT}{report_id}", report, self.TTL_RESEARCH_REPORT)

    # ===== Bulk Operations =====

    def invalidate_fund(self, wind_code: str):
        """使基金相关缓存失效"""
        patterns = [
            f"{self.KEY_FUND_INFO}{wind_code}",
            f"{self.KEY_FUND_PERFORMANCE}{wind_code}",
            f"{self.KEY_FUND_RISK}{wind_code}",
            f"{self.KEY_FUND_STYLE}{wind_code}",
            f"{self.KEY_FUND_SCORE}{wind_code}",
            f"{self.KEY_FUND_NAV}{wind_code}",
        ]
        for p in patterns:
            self._cache.delete(p)

    def invalidate_manager(self, manager_id: str):
        """使经理相关缓存失效"""
        patterns = [
            f"{self.KEY_MANAGER_INFO}{manager_id}",
            f"{self.KEY_MANAGER_FUNDS}{manager_id}",
        ]
        for p in patterns:
            self._cache.delete(p)

    def invalidate_all(self):
        """清空所有缓存（谨慎使用）"""
        self._cache.delete_pattern("*")

    # ===== Statistics =====

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self._cache.get_stats()

    def is_available(self) -> bool:
        """缓存是否可用"""
        return self._is_available()


# 全局单例
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service