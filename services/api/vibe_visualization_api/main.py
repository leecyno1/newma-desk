from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vibe_visualization_api.config import settings


app = FastAPI(title="vibe-visualization API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origin_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/api/health")
def health() -> dict[str, bool | str]:
    return {
        "ok": True,
        "service": "vibe-visualization-api",
        "version": "0.1.0",
    }
