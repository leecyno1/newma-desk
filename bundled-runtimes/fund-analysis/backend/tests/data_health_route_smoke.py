import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.data_health import router
from fastapi import FastAPI


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/data-health/summary")
    if response.status_code == 503:
        payload = response.json()
        if "store unavailable" not in payload.get("detail", ""):
            print(f"Expected observable store unavailable detail, got: {payload}")
            return 1
        print("OK data health summary degrades when DB is unavailable")
        return 0
    if response.status_code != 200:
        print(f"Expected 200 or DB-unavailable 503, got {response.status_code}: {response.text}")
        return 1
    payload = response.json()
    for key in ["latest_snapshots", "recent_failed_count", "stale_datasets"]:
        if key not in payload:
            print(f"Missing {key}: {payload}")
            return 1
    print("OK data health summary contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
