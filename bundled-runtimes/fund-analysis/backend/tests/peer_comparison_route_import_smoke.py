import os
import sys
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.funds import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    paths = {route.path for route in app.routes}
    expected = {
        "/api/funds/{wind_code}/peer-percentiles",
        "/api/funds/compare-matrix",
    }
    if not expected.issubset(paths):
        print(f"Missing peer comparison paths: {paths}")
        return 1
    print("OK peer comparison routes import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
