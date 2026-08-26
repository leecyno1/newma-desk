import importlib
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import service_registry


def main() -> int:
    attempts = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.attempt = len(attempts) + 1
            attempts.append(self.attempt)
            self.admin = self

        def command(self, name: str):
            if self.attempt == 1:
                raise RuntimeError("mongo down")
            return {"ok": 1}

        def get_database(self, name: str):
            return {"name": name, "attempt": self.attempt}

    fake_pymongo = types.SimpleNamespace(MongoClient=FakeClient)

    with mock.patch.dict(sys.modules, {"pymongo": fake_pymongo}):
        module = importlib.reload(service_registry)
        module._db_retry_interval_seconds = 30

        with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 5.0, 31.0]):
            first = module.get_db()
            second = module.get_db()
            third = module.get_db()

    if first is not None:
        print(f"Expected first get_db() to degrade to None, got: {first}")
        return 1

    if second is not None:
        print(f"Expected second get_db() to stay cached as None before retry window, got: {second}")
        return 1

    if third != {"name": "fund_analysis", "attempt": 2}:
        print(f"Expected third get_db() to recover after retry window, got: {third}")
        return 1

    if attempts != [1, 2]:
        print(f"Expected exactly two Mongo connection attempts, got: {attempts}")
        return 1

    print("OK service_registry mongo retry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
