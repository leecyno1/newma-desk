import importlib
import os
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.cache_service as cache_service


def main() -> int:
    class FakeRedisClient:
        def ping(self):
            raise RuntimeError("auth required")

    fake_redis = types.SimpleNamespace(from_url=lambda *args, **kwargs: FakeRedisClient())

    with mock.patch.dict(sys.modules, {"redis": fake_redis}), mock.patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
        module = importlib.reload(cache_service)
        cache = module.get_cache()

    if cache.__class__.__name__ != "MemoryCache":
        print(f"Expected MemoryCache fallback when Redis ping fails, got: {cache.__class__.__name__}")
        return 1

    print("OK cache backend fallback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
