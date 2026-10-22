"""Installed entry point for the existing standalone/Desk domain runtime."""
from pathlib import Path

from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def create_app(frontend_dist: str | None = None):
    import sys
    # Legacy domain imports stay local to this installed package, never Desk.
    directory = str(Path(__file__).resolve().parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    from app import app
    if frontend_dist:
        dist = Path(frontend_dist).resolve(strict=True)
        if not (dist / "index.html").is_file():
            raise ValueError("frontend_dist must contain a built index.html")
        app.mount("/mod-runtime/research", FrontendFiles(directory=dist, html=True), name="desk-frontend")
        app.mount("/", FrontendFiles(directory=dist, html=True), name="frontend")
    return app


def main():
    import argparse
    import os
    import uvicorn
    parser = argparse.ArgumentParser(description="Standalone Vibe Research API and frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18954)
    parser.add_argument("--frontend-dist")
    parser.add_argument("--integrated", action="store_true", help="Use host-owned Agent and portfolio scheduling")
    parser.add_argument("--no-background", action="store_true", help="Disable automatic data refresh tasks")
    args = parser.parse_args()
    if args.integrated:
        os.environ["NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"
    if args.no_background:
        os.environ["VR_DISABLE_BACKGROUND_TASKS"] = "1"
    uvicorn.run(create_app(args.frontend_dist), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
