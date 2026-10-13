import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import funds as fund_routes
import repositories
import service_registry


class Cache:
    def __init__(self):
        self.stored = {}

    def get(self, key):
        return self.stored.get(key)

    def set(self, key, value, ttl):
        self.stored[key] = value
        return None


LOCAL_ROWS = [
    {
        "wind_code": "000001.OF",
        "ann_date": "2026-01-20",
        "record_date": "2026-03-10",
        "ex_date": "2026-03-11",
        "pay_date": "2026-03-13",
        "net_ex_date": "2026-03-11",
        "div_proc": "实施",
        "div_cash": 0.05,
        "ear_amount": 500000.0,
        "source": "tushare.fund_div",
    }
]


class LocalDividendsRepo:
    def list_fund_dividends(self, wind_code, limit=50):
        return list(LOCAL_ROWS)


class EmptyDividendsRepo:
    def list_fund_dividends(self, wind_code, limit=50):
        return []


class FallbackDataService:
    def __init__(self):
        self.calls = []

    def get_fund_dividends(self, wind_code):
        self.calls.append(wind_code)
        return [dict(LOCAL_ROWS[0], source="tushare.fund_div")]


class NeverDividendDataService:
    def get_fund_dividends(self, wind_code):
        return []


async def _run(repo, data_service):
    import services.cache_service as cache_service

    original_cache = cache_service.get_cache
    original_repo = repositories.get_fund_dividends_repo
    original_data_service = service_registry.get_data_service
    cache = Cache()
    cache_service.get_cache = lambda: cache
    repositories.get_fund_dividends_repo = lambda: repo
    service_registry.get_data_service = lambda: data_service
    try:
        return cache, await fund_routes.get_fund_dividends("000001.OF", limit=100)
    finally:
        cache_service.get_cache = original_cache
        repositories.get_fund_dividends_repo = original_repo
        service_registry.get_data_service = original_data_service


async def main():
    # 1. 本地优先：库里有分红事件时不触发外部数据源
    cache, result = await _run(LocalDividendsRepo(), FallbackDataService())
    if result.get("source") != "local.postgres.fund_dividends":
        raise AssertionError(f"local dividends must be preferred: {result}")
    if result.get("count") != 1 or result.get("data")[0].get("ex_date") != "2026-03-11":
        raise AssertionError(f"dividend rows must pass through with ex_date: {result}")
    if result["data"][0].get("div_cash") != 0.05:
        raise AssertionError(f"div_cash must round-trip as float: {result['data'][0]}")
    cached = cache.get(next(k for k in cache.stored if "dividends" in k))
    if cached is None:
        raise AssertionError("dividends response must be cached")

    # 2. 本地为空时回退 tushare，并带 lineage
    fallback_service = FallbackDataService()
    _, result = await _run(EmptyDividendsRepo(), fallback_service)
    if not fallback_service.calls:
        raise AssertionError("empty local store must trigger tushare fallback")
    if result.get("source") != "tushare.fund_div" or result.get("count") != 1:
        raise AssertionError(f"fallback must serve tushare rows with lineage: {result}")

    # 3. 从未分红的基金返回空列表属正常情况
    _, result = await _run(EmptyDividendsRepo(), NeverDividendDataService())
    if result.get("count") != 0 or result.get("data") != []:
        raise AssertionError(f"never-dividend fund must return empty list, not an error: {result}")

    print("OK fund dividends route serves local-first with tushare fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
