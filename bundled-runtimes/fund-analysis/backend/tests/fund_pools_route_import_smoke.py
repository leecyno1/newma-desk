import os
import sys
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.fund_pools import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    paths = {route.path for route in app.routes}
    expected = {
        '/api/fund-pools',
        '/api/fund-pools/{pool_id}/members',
        '/api/fund-pools/members/{member_id}',
    }
    if not expected.issubset(paths):
        print(f"Missing fund pool routes: {paths}")
        return 1
    print('OK fund pool route imports')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
