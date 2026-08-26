import os
import sys
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.metrics import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    routes = {route.path for route in app.routes}
    expected = {"/api/metrics/fund/{fund_code}", "/api/metrics/fund/{fund_code}/recalculate"}
    if not expected.issubset(routes):
        print(f"Missing expected metric routes. routes={routes}")
        return 1
    client = TestClient(app)
    response = client.get("/api/metrics/health")
    if response.status_code != 200 or response.json().get("status") != "ok":
        print(f"Expected metrics health ok, got {response.status_code}: {response.text}")
        return 1
    print("OK metrics route import and health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
