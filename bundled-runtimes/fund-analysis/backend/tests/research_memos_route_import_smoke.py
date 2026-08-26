import os
import sys
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.research_memos import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    paths = {route.path for route in app.routes}
    expected = {"/api/research-memos/fund/{wind_code}"}
    if not expected.issubset(paths):
        print(f"Missing research memo paths: {paths}")
        return 1
    print("OK research memo route imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
