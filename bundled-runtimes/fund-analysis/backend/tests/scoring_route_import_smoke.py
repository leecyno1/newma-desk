import os
import sys
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.scoring import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    paths = {route.path for route in app.routes}
    expected = {"/api/scoring/fund/{wind_code}", "/api/scoring/fund/{wind_code}/recalculate"}
    if not expected.issubset(paths):
        print(f"Missing scoring paths: {paths}")
        return 1
    print("OK scoring route imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
