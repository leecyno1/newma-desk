import asyncio

from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache


def test_bounded_ttl_cache_is_copy_isolated_and_lru_bounded():
    now = [0.0]
    cache = BoundedTTLCache(max_entries=2, ttl_seconds=10, clock=lambda: now[0])
    value = {"rows": [{"symbol": "300502"}]}
    cache.set("a", value)
    value["rows"][0]["symbol"] = "changed"

    first = cache.get("a")
    assert first == {"rows": [{"symbol": "300502"}]}
    first["rows"][0]["symbol"] = "changed-again"
    assert cache.get("a") == {"rows": [{"symbol": "300502"}]}

    cache.set("b", {"value": 2})
    cache.get("a")
    cache.set("c", {"value": 3})
    assert cache.get("b") is None
    assert cache.stats()["entries"] == 2


def test_bounded_ttl_cache_expires_entries():
    now = [0.0]
    cache = BoundedTTLCache(max_entries=2, ttl_seconds=10, clock=lambda: now[0])
    cache.set("a", {"value": 1})
    now[0] = 10.0
    assert cache.get("a") is None
    assert cache.stats()["entries"] == 0


def test_async_task_coalescer_drops_task_from_another_loop():
    coalescer = AsyncTaskCoalescer()

    async def store_task():
        task = asyncio.create_task(asyncio.sleep(0))
        coalescer.set("key", task)
        await task

    asyncio.run(store_task())

    async def read_task():
        assert coalescer.get("key") is None
        assert len(coalescer) == 0

    asyncio.run(read_task())
