"""Serve five reviewed demonstration snapshots without account or runtime access.

Run as a separate loopback process, not mounted inside the authenticated API.
No database, credentials, network providers, scheduler or Agent is initialized.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse


MODULE_IDS = frozenset({
    "global-situation", "seven-cycle-research", "market-daily",
    "instock-industry-chain", "orchestra-committee",
})
ROOT = Path(__file__).parent
ASSETS = {"demo.js": "text/javascript", "demo.css": "text/css"}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; font-src 'self'; "
    "frame-ancestors 'self' http://127.0.0.1:8766; "
    "base-uri 'none'; object-src 'none'; form-action 'none'"
)


def create_app() -> FastAPI:
    # This file is curated release content, never a user-selected path or database.
    catalog = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
    if set(catalog) != MODULE_IDS:
        raise RuntimeError("Public demo content must contain exactly the five approved modules")
    if not all((ROOT / name).is_file() for name in ("index.html", *ASSETS)):
        raise RuntimeError("Public demo static assets are missing")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def readonly_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD"}:
            response = JSONResponse({"detail": "公开演示仅允许读取，不提供执行或保存接口"}, status_code=405,
                                    headers={"Allow": "GET, HEAD"})
        else:
            response = await call_next(request)
        response.headers.update({
            "Content-Security-Policy": CSP,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "Cross-Origin-Resource-Policy": "same-origin",
        })
        if request.url.path == "/demo/status.json":
            response.headers["Vary"] = "Origin"
            if request.headers.get("origin") == "http://127.0.0.1:8766":
                response.headers["Access-Control-Allow-Origin"] = "http://127.0.0.1:8766"
                response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

    @app.api_route("/demo/", methods=["GET", "HEAD"])
    async def page(request: Request):
        if set(request.query_params) - {"mod"} or len(request.query_params.getlist("mod")) > 1:
            raise HTTPException(400, "公开演示只接受一个mod参数")
        module_id = request.query_params.get("mod", "global-situation")
        if module_id not in MODULE_IDS:
            raise HTTPException(404, "此模组不在公开演示范围内")
        return FileResponse(ROOT / "index.html", media_type="text/html")

    @app.api_route("/demo/health", methods=["GET", "HEAD"])
    async def health():
        return {"status": "ok", "mode": "public-readonly", "contentVersion": "2026-10-22.1", "moduleCount": 5}

    @app.api_route("/demo/status.json", methods=["GET", "HEAD"])
    async def status():
        return {"contract": "newma-desk.public-demo.v1", "mode": "readonly",
                "readinessScope": "reviewed-readonly-snapshot", "live": False,
                "contentVersion": "2026-10-22.1",
                "modules": [{"id": module_id, **catalog[module_id]["publication"]} for module_id in sorted(MODULE_IDS)]}

    @app.api_route("/demo/assets/{name}", methods=["GET", "HEAD"])
    async def asset(name: str):
        if name not in ASSETS:
            raise HTTPException(404)
        return FileResponse(ROOT / name, media_type=ASSETS[name])

    @app.api_route("/demo/api/modules/{module_id}", methods=["GET", "HEAD"])
    async def snapshot(module_id: str):
        if module_id not in MODULE_IDS:
            raise HTTPException(404, "此模组不在公开演示范围内")
        # Cookie, Authorization, identity headers and query scopes are never used.
        publication = catalog[module_id]["publication"]
        return {"schemaVersion": "1.0", "mode": "public-readonly", "moduleId": module_id,
                "live": False,
                "contentVersion": "2026-10-22.1", **publication,
                "disclaimer": "仅展示标明来源和日期的历史快照或明确标注的方法示例；非实时数据、非投资建议，未连接个人工作区。",
                "content": catalog[module_id]}

    return app
