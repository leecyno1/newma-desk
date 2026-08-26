"""Tests for SQLite TTL cache."""

import tempfile
import time
from pathlib import Path

import pytest

from world_intel_mcp.cache import Cache


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(db_path=tmp_path / "test_cache.db")


def test_set_and_get(cache: Cache) -> None:
    cache.set("key1", {"value": 42}, ttl_seconds=60)
    result = cache.get("key1")
    assert result == {"value": 42}


def test_get_missing_key(cache: Cache) -> None:
    assert cache.get("nonexistent") is None


def test_ttl_expiration(cache: Cache) -> None:
    cache.set("ephemeral", "data", ttl_seconds=1)
    assert cache.get("ephemeral") == "data"
    time.sleep(1.1)
    assert cache.get("ephemeral") is None


def test_overwrite(cache: Cache) -> None:
    cache.set("key", "v1", ttl_seconds=60)
    cache.set("key", "v2", ttl_seconds=60)
    assert cache.get("key") == "v2"


def test_delete(cache: Cache) -> None:
    cache.set("key", "val", ttl_seconds=60)
    cache.delete("key")
    assert cache.get("key") is None


def test_evict_expired(cache: Cache) -> None:
    cache.set("fresh", "yes", ttl_seconds=300)
    cache.set("stale", "no", ttl_seconds=1)
    time.sleep(1.1)
    removed = cache.evict_expired()
    assert removed == 1
    assert cache.get("fresh") == "yes"
    assert cache.get("stale") is None


def test_stats(cache: Cache) -> None:
    cache.set("a", 1, ttl_seconds=300)
    cache.set("b", 2, ttl_seconds=300)
    stats = cache.stats()
    assert stats["total_entries"] == 2
    assert stats["active_entries"] == 2


def test_complex_values(cache: Cache) -> None:
    data = {"nested": {"list": [1, 2, 3], "bool": True, "null": None}}
    cache.set("complex", data, ttl_seconds=60)
    assert cache.get("complex") == data


def test_default_path_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "custom-cache.db"
    monkeypatch.setenv("WORLD_INTEL_CACHE_DB", str(db_path))

    cache = Cache()
    try:
        assert cache.db_path == db_path
        cache.set("env", "ok", ttl_seconds=60)
        assert cache.get("env") == "ok"
    finally:
        cache.close()


def test_default_path_falls_back_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad_path = tmp_path / "cache-dir"
    bad_path.mkdir()
    monkeypatch.setenv("WORLD_INTEL_CACHE_DB", str(bad_path))

    cache = Cache()
    try:
        expected = Path(tempfile.gettempdir()) / "world-intel-mcp" / "cache.db"
        assert cache.db_path == expected
        cache.set("fallback", "ok", ttl_seconds=60)
        assert cache.get("fallback") == "ok"
    finally:
        cache.close()
