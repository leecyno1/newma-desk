from instock.web.rotation_handler import _BoundedTTLCache


def test_rotation_cache_is_ttl_bound_and_lru_bounded():
    now = [100.0]
    cache = _BoundedTTLCache(max_entries=2, ttl_seconds=10, clock=lambda: now[0])

    cache.set("first", {"value": 1})
    cache.set("second", {"value": 2})
    assert cache.get("first") == {"value": 1}

    cache.set("third", {"value": 3})
    assert cache.get("second") is None
    assert cache.get("first") == {"value": 1}
    assert cache.get("third") == {"value": 3}
    assert len(cache) == 2

    now[0] = 111.0
    assert cache.get("first") is None
    assert cache.get("third") is None
    assert len(cache) == 0


def test_rotation_cache_copy_isolates_payloads():
    cache = _BoundedTTLCache(max_entries=2, ttl_seconds=10)
    original = {"nested": {"value": 1}}

    cache.set("key", original)
    original["nested"]["value"] = 2
    cached = cache.get("key")
    cached["nested"]["value"] = 3

    assert cache.get("key") == {"nested": {"value": 1}}


def test_rotation_cache_reports_bounded_volatile_capacity():
    cache = _BoundedTTLCache(max_entries=3, ttl_seconds=15)
    cache.set("first", {"value": 1})

    assert cache.stats() == {
        "storage": "process_memory",
        "volatile": True,
        "entries": 1,
        "max_entries": 3,
        "ttl_seconds": 15.0,
    }
