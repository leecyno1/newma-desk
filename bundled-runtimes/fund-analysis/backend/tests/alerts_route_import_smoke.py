import os
import sys
from fastapi import FastAPI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.alerts import router


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    paths = {route.path for route in app.routes}
    expected = {
        '/api/alerts',
        '/api/alerts/rules',
        '/api/alerts/events/{event_id}',
        '/api/alerts/scan',
    }
    if not expected.issubset(paths):
        print(f"Missing alert routes: {paths}")
        return 1
    print('OK alert route imports')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
