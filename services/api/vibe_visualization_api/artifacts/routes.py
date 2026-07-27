from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse

from vibe_visualization_api.artifacts.archify import (
    ArchifyRenderer,
    to_archify_ir,
)
from vibe_visualization_api.artifacts.models import (
    ArtifactRecord,
    GraphArtifactCreate,
    ReplayArtifactCreate,
    ReplayArtifactRecord,
)
from vibe_visualization_api.artifacts.replay_html import render_replay_html
from vibe_visualization_api.artifacts.store import ArtifactStore


router = APIRouter(prefix="/api/artifacts", tags=["mod artifacts"])


def get_artifact_store(request: Request) -> ArtifactStore:
    return request.app.state.artifact_store


def get_archify_renderer(request: Request) -> ArchifyRenderer:
    return request.app.state.archify_renderer


@router.post("", response_model=ArtifactRecord, status_code=201)
def create_artifact(
    spec: GraphArtifactCreate,
    store: ArtifactStore = Depends(get_artifact_store),
    renderer: ArchifyRenderer = Depends(get_archify_renderer),
) -> ArtifactRecord:
    ir = to_archify_ir(spec)
    html = renderer.render(ir)
    return store.create(spec, ir, html)


@router.get("", response_model=list[ArtifactRecord])
def list_artifacts(
    module_id: str,
    response: Response,
    status: Literal["draft", "published"] | None = None,
    store: ArtifactStore = Depends(get_artifact_store),
) -> list[ArtifactRecord]:
    response.headers["Cache-Control"] = "no-store"
    return store.list(module_id, status=status)


@router.get("/latest", response_model=ArtifactRecord)
def latest_artifact(
    module_id: str,
    response: Response,
    status: Literal["draft", "published"] | None = None,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ArtifactRecord:
    response.headers["Cache-Control"] = "no-store"
    return store.latest(module_id, status=status)


@router.post("/replays", response_model=ReplayArtifactRecord, status_code=201)
def create_replay_artifact(
    spec: ReplayArtifactCreate,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ReplayArtifactRecord:
    return store.create_replay(spec, render_replay_html(spec))


@router.get("/replays", response_model=list[ReplayArtifactRecord])
def list_replay_artifacts(
    module_id: str,
    response: Response,
    status: Literal["draft", "published"] | None = None,
    store: ArtifactStore = Depends(get_artifact_store),
) -> list[ReplayArtifactRecord]:
    response.headers["Cache-Control"] = "no-store"
    return store.list_replays(module_id, status=status)


@router.get("/replays/latest", response_model=ReplayArtifactRecord)
def latest_replay_artifact(
    module_id: str,
    response: Response,
    status: Literal["draft", "published"] | None = None,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ReplayArtifactRecord:
    response.headers["Cache-Control"] = "no-store"
    return store.latest_replay(module_id, status=status)


@router.get("/replays/{artifact_id}", response_model=ReplayArtifactRecord)
def get_replay_artifact(
    artifact_id: str,
    response: Response,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ReplayArtifactRecord:
    response.headers["Cache-Control"] = "no-store"
    return store.get_replay(artifact_id)


@router.post("/replays/{artifact_id}/publish", response_model=ReplayArtifactRecord)
def publish_replay_artifact(
    artifact_id: str,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ReplayArtifactRecord:
    return store.publish_replay(artifact_id)


@router.get("/replays/{artifact_id}/view", response_class=HTMLResponse)
def view_replay_artifact(
    artifact_id: str,
    store: ArtifactStore = Depends(get_artifact_store),
) -> HTMLResponse:
    return HTMLResponse(
        store.read_replay_html(artifact_id),
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "font-src data:; connect-src 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{artifact_id}", response_model=ArtifactRecord)
def get_artifact(
    artifact_id: str,
    response: Response,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ArtifactRecord:
    response.headers["Cache-Control"] = "no-store"
    return store.get(artifact_id)


@router.post("/{artifact_id}/publish", response_model=ArtifactRecord)
def publish_artifact(
    artifact_id: str,
    store: ArtifactStore = Depends(get_artifact_store),
) -> ArtifactRecord:
    return store.publish(artifact_id)


@router.get("/{artifact_id}/view", response_class=HTMLResponse)
def view_artifact(
    artifact_id: str,
    store: ArtifactStore = Depends(get_artifact_store),
) -> HTMLResponse:
    return HTMLResponse(
        store.read_html(artifact_id),
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Security-Policy": (
                "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; font-src data:; connect-src 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
