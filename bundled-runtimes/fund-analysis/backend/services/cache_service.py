"""
缓存服务 - 多层缓存抽象
支持 Redis（生产）、内存（开发）、空缓存（测试）

使用分层缓存策略：
1. Redis 缓存（生产环境）
2. 内存缓存（开发环境，TTL 短）
3. 空缓存（降级模式）

缓存键设计：
- fund:detail:{wind_code}          -> 基金详情
- fund:list:{type}:{page}          -> 基金列表（分页）
- fund:perf:{wind_code}            -> 业绩数据
- fund:risk:{wind_code}             -> 风险指标
- fund:score:{wind_code}           -> 综合评分
- manager:detail:{manager_id}      -> 经理详情
- manager:profile:{manager_id}      -> 经理画像
- holdings:{wind_code}:{quarter}   -> 持仓数据
- nav:{wind_code}:{start}:{end}    -> 净值序列
- report:{id}                       -> 分析报告
- search:{hash}                     -> 筛选结果

TTL 设计：
- 基金列表/详情: 5 分钟
- 业绩/风险/评分: 15 分钟
- 持仓/净值: 1 小时
- 分析报告: 24 小时
- 调研报告: 30 分钟
"""
import os
import json
import hashlib
import logging
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
from functools import wraps
import threading

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 缓存后端抽象
# ─────────────────────────────────────────────


class CacheBackend:
    """缓存后端基类"""

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def get_multi(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取，返回 {key: value} 字典"""
        result = {}
        for key in keys:
            val = self.get(key)
            if val is not None:
                result[key] = val
        return result

    def set_multi(self, items: Dict[str, Any], ttl: int = 300) -> bool:
        """批量设置"""
        for key, value in items.items():
            self.set(key, value, ttl)
        return True

    def invalidate_pattern(self, pattern: str) -> int:
        """按模式删除（谨慎使用，仅空缓存实现）"""
        return 0


class NullCache(CacheBackend):
    """空缓存 - 始终返回 None，不存储任何数据"""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        return True  # 假装成功

    def delete(self, key: str) -> bool:
        return True


class MemoryCache(CacheBackend):
    """内存缓存 - 开发环境用，进程内有效"""

    def __init__(self, max_size: int = 5000, default_ttl: int = 300):
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, expire_time)
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expire_time = self._cache[key]
            if expire_time > 0 and datetime.now().timestamp() > expire_time:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        if ttl is None:
            ttl = self._default_ttl

        with self._lock:
            # LRU 清理
            if len(self._cache) >= self._max_size and key not in self._cache:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]

            expire_time = datetime.now().timestamp() + ttl
            self._cache[key] = (value, expire_time if ttl > 0 else 0)
        return True

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
        return True

    def get_multi(self, keys: List[str]) -> Dict[str, Any]:
        result = {}
        for key in keys:
            val = self.get(key)
            if val is not None:
                result[key] = val
        return result

    def set_multi(self, items: Dict[str, Any], ttl: int = 300) -> bool:
        for key, value in items.items():
            self.set(key, value, ttl)
        return True

    def invalidate_pattern(self, pattern: str) -> int:
        """简单前缀匹配删除"""
        count = 0
        prefix = pattern.rstrip("*")
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
                count += 1
        return count

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2%}",
                "size": len(self._cache),
                "max_size": self._max_size,
            }


class RedisCache(CacheBackend):
    """Redis 缓存 - 生产环境用"""

    def __init__(self, url: str = None, key_prefix: str = "fund:", default_ttl: int = 300):
        import os as _os
        self._url = url or _os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._prefix = key_prefix
        self._default_ttl = default_ttl
        self._client = None
        self._connect()

    def _connect(self):
        try:
            import redis
            self._client = redis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._client.ping()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}. Falling back to memory cache.")
            self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        if self._client is None:
            return None

        try:
            raw = self._client.get(self._key(key))
            if raw is None:
                return None

            data = json.loads(raw)
            # 检查过期标记
            if isinstance(data, dict) and "_expire" in data:
                if datetime.now().timestamp() > data["_expire"]:
                    self._client.delete(self._key(key))
                    return None

            return data.get("v") if isinstance(data, dict) else data
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        if self._client is None:
            return False

        if ttl is None:
            ttl = self._default_ttl

        try:
            expire_time = datetime.now().timestamp() + ttl
            data = {"v": value, "_expire": expire_time} if ttl > 0 else {"v": value}
            serialized = json.dumps(data, ensure_ascii=False, default=str)
            self._client.setex(self._key(key), ttl, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        if self._client is None:
            return False
        try:
            self._client.delete(self._key(key))
            return True
        except Exception:
            return False

    def get_multi(self, keys: List[str]) -> Dict[str, Any]:
        if self._client is None:
            return {}

        try:
            pipeline = self._client.pipeline()
            for key in keys:
                pipeline.get(self._key(key))

            raw_results = pipeline.execute()
            result = {}
            for key, raw in zip(keys, raw_results):
                if raw is not None:
                    try:
                        data = json.loads(raw)
                        val = data.get("v") if isinstance(data, dict) else data
                        result[key] = val
                    except Exception:
                        pass
            return result
        except Exception as e:
            logger.warning(f"Redis get_multi error: {e}")
            return {}

    def set_multi(self, items: Dict[str, Any], ttl: int = 300) -> bool:
        if self._client is None:
            return False

        try:
            pipeline = self._client.pipeline()
            expire_time = datetime.now().timestamp() + ttl

            for key, value in items.items():
                data = {"v": value, "_expire": expire_time} if ttl > 0 else {"v": value}
                serialized = json.dumps(data, ensure_ascii=False, default=str)
                pipeline.setex(self._key(key), ttl, serialized)

            pipeline.execute()
            return True
        except Exception as e:
            logger.warning(f"Redis set_multi error: {e}")
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """使用 SCAN 匹配删除（不阻塞）"""
        if self._client is None:
            return 0

        try:
            wildcard_pattern = pattern if "*" in pattern else f"{pattern}*"
            full_pattern = self._key(wildcard_pattern)
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = self._client.scan(cursor, match=full_pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break

            logger.info(f"Redis invalidated {deleted} keys matching {pattern}")
            return deleted
        except Exception as e:
            logger.warning(f"Redis invalidate_pattern error: {e}")
            return 0


# ─────────────────────────────────────────────
# 全局缓存实例（延迟初始化）
# ─────────────────────────────────────────────

_cache_backend: Optional[CacheBackend] = None
_cache_lock = threading.Lock()


def get_cache() -> CacheBackend:
    """获取缓存后端（自动降级）"""
    global _cache_backend

    if _cache_backend is not None:
        return _cache_backend

    with _cache_lock:
        if _cache_backend is not None:
            return _cache_backend

        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                redis_backend = RedisCache(url=redis_url)
                if redis_backend.is_available():
                    _cache_backend = redis_backend
                    logger.info("Using Redis cache backend")
                    return _cache_backend
            except Exception:
                pass

        # 开发环境用内存缓存
        _cache_backend = MemoryCache(max_size=5000, default_ttl=300)
        logger.info("Using in-memory cache backend (development)")
        return _cache_backend


def reset_cache():
    """重置缓存（用于测试）"""
    global _cache_backend
    with _cache_lock:
        _cache_backend = None


# ─────────────────────────────────────────────
# 缓存键生成
# ─────────────────────────────────────────────


class CacheKey:
    """缓存键构建器"""

    @staticmethod
    def fund_detail(wind_code: str) -> str:
        return f"fund:detail:{wind_code}"

    @staticmethod
    def fund_list(fund_type: str = None, page: int = 1, keyword: str = None) -> str:
        parts = ["fund", "list"]
        if fund_type:
            parts.append(fund_type)
        if keyword:
            parts.append(hashlib.md5(keyword.encode()).hexdigest()[:8])
        parts.append(str(page))
        return ":".join(parts)

    @staticmethod
    def fund_performance(wind_code: str, period: str = None) -> str:
        return f"fund:perf:{wind_code}" + (f":{period}" if period else "")

    @staticmethod
    def fund_risk(wind_code: str) -> str:
        return f"fund:risk:{wind_code}"

    @staticmethod
    def fund_score(wind_code: str) -> str:
        return f"fund:score:{wind_code}"

    @staticmethod
    def manager_detail(manager_id: str) -> str:
        return f"manager:detail:{manager_id}"

    @staticmethod
    def manager_profile(manager_id: str) -> str:
        return f"manager:profile:{manager_id}"

    @staticmethod
    def manager_funds(manager_id: str) -> str:
        return f"manager:funds:{manager_id}"

    @staticmethod
    def holdings(wind_code: str, quarter: str) -> str:
        return f"holdings:{wind_code}:{quarter}"

    @staticmethod
    def nav_series(wind_code: str, start: str = None, end: str = None) -> str:
        return f"nav:{wind_code}:{start or 'start'}:{end or 'end'}"

    @staticmethod
    def report(report_id: str) -> str:
        return f"report:{report_id}"

    @staticmethod
    def screening(hash_key: str) -> str:
        return f"search:{hash_key}"

    @staticmethod
    def barra_exposures(wind_code: str, quarter: str) -> str:
        return f"barra:exposures:{wind_code}:{quarter}"


# ─────────────────────────────────────────────
# TTL 配置（秒）
# ─────────────────────────────────────────────

class TTL:
    SHORT = 60          # 1 分钟
    MEDIUM = 300         # 5 分钟
    LONG = 900          # 15 分钟
    X_LONG = 3600       # 1 小时
    XX_LONG = 86400      # 24 小时
    XXX_LONG = 2592000  # 30 天


# ─────────────────────────────────────────────
# 缓存装饰器
# ─────────────────────────────────────────────


def cached(key_func: callable, ttl: int = TTL.MEDIUM, use_request_key: bool = False):
    """
    缓存装饰器

    用法:
        @cached(lambda args, kwargs: CacheKey.fund_detail(args[0]), ttl=TTL.LONG)
        def get_fund_info(wind_code: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = get_cache()
            cache_key = key_func(args, kwargs)

            # 尝试读取缓存
            cached_val = cache.get(cache_key)
            if cached_val is not None:
                logger.debug(f"[CACHE HIT] {cache_key}")
                return cached_val

            # 执行函数
            result = await func(*args, **kwargs)

            # 写入缓存（结果不为 None）
            if result is not None:
                cache.set(cache_key, result, ttl)
                logger.debug(f"[CACHE SET] {cache_key} (ttl={ttl}s)")

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache = get_cache()
            cache_key = key_func(args, kwargs)

            cached_val = cache.get(cache_key)
            if cached_val is not None:
                logger.debug(f"[CACHE HIT] {cache_key}")
                return cached_val

            result = func(*args, **kwargs)

            if result is not None:
                cache.set(cache_key, result, ttl)
                logger.debug(f"[CACHE SET] {cache_key} (ttl={ttl}s)")

            return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ─────────────────────────────────────────────
# 批量缓存工具
# ─────────────────────────────────────────────


def batch_cache_get(keys: List[str]) -> Dict[str, Any]:
    """批量读取缓存"""
    cache = get_cache()
    return cache.get_multi(keys)


def batch_cache_set(items: Dict[str, Any], ttl: int = TTL.MEDIUM) -> bool:
    """批量写入缓存"""
    cache = get_cache()
    return cache.set_multi(items, ttl)


def invalidate_fund_cache(wind_code: str) -> int:
    """使基金相关所有缓存失效"""
    cache = get_cache()
    patterns = [
        f"fund:detail:{wind_code}",
        f"fund:detail:v",
        "fund:list:",
        f"fund:perf:{wind_code}",
        f"fund:risk:{wind_code}",
        f"fund:score:{wind_code}",
        f"holdings:{wind_code}:",
        f"nav:{wind_code}:",
        f"barra:exposures:{wind_code}:",
    ]

    count = 0
    for pattern in patterns:
        count += cache.invalidate_pattern(pattern)

    return count


def invalidate_manager_cache(manager_id: str) -> int:
    """使经理相关所有缓存失效"""
    cache = get_cache()
    patterns = [
        f"manager:detail:{manager_id}",
        f"manager:profile:{manager_id}",
        f"manager:funds:{manager_id}",
    ]

    count = 0
    for pattern in patterns:
        count += cache.invalidate_pattern(pattern)

    return count


def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计信息"""
    cache = get_cache()
    if hasattr(cache, "stats"):
        return cache.stats()
    else:
        return {"backend": type(cache).__name__}
