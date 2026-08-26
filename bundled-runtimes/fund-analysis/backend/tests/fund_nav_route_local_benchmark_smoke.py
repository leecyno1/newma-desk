import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import funds as fund_routes
import repositories
import service_registry


class Cache:
    def get(self, key):
        return None

    def set(self, key, value, ttl):
        return None


class NavRepo:
    def get_nav_series(self, wind_code, start_date, end_date):
        return [
            {"date": "2026-01-02", "nav": 1.0, "benchmark_nav": 3000.0},
            {"date": "2026-01-03", "nav": 1.01, "benchmark_nav": 3030.0},
        ]


class DataService:
    def get_fund_nav(self, *args):
        raise AssertionError("Local NAV must be preferred over an external refetch")


async def main():
    import services.cache_service as cache_service

    original_cache = cache_service.get_cache
    original_nav_repo = repositories.get_nav_repo
    original_data_service = service_registry.get_data_service
    cache_service.get_cache = lambda: Cache()
    repositories.get_nav_repo = lambda: NavRepo()
    service_registry.get_data_service = lambda: DataService()
    try:
        result = await fund_routes.get_fund_nav(
            "INDEX.TEST",
            start_date="2026-01-01",
            end_date="2026-01-31",
            freq="daily",
        )
    finally:
        cache_service.get_cache = original_cache
        repositories.get_nav_repo = original_nav_repo
        service_registry.get_data_service = original_data_service

    if result.get("source") != "local.postgres.fund_nav" or result.get("benchmark_count") != 2:
        raise AssertionError(result)
    if result["data"][1].get("benchmark_nav") != 3030.0:
        raise AssertionError("Benchmark NAV must remain in the browser payload")
    print("OK fund NAV route prefers local evidence and exposes benchmark series")


if __name__ == "__main__":
    asyncio.run(main())
