from fastapi import APIRouter, Depends, Response

from vibe_visualization_api.config import Settings, get_settings
from vibe_visualization_api.snapshots.models import Snapshot, SnapshotSummary
from vibe_visualization_api.snapshots.store import SnapshotStore


router = APIRouter(prefix="/api/modules", tags=["snapshots"])


def get_snapshot_store(settings: Settings = Depends(get_settings)) -> SnapshotStore:
    return SnapshotStore(settings.runtime_dir, settings.database_path)


@router.get("/{module_id}/snapshot", response_model=Snapshot)
def get_latest_snapshot(
    module_id: str,
    response: Response,
    store: SnapshotStore = Depends(get_snapshot_store),
) -> Snapshot:
    response.headers["Cache-Control"] = "no-store"
    return store.latest_success(module_id)


@router.get("/{module_id}/snapshots", response_model=list[SnapshotSummary])
def list_snapshots(
    module_id: str,
    response: Response,
    store: SnapshotStore = Depends(get_snapshot_store),
) -> list[SnapshotSummary]:
    response.headers["Cache-Control"] = "no-store"
    return [
        SnapshotSummary(
            id=snapshot.id,
            module_id=snapshot.module_id,
            created_at=snapshot.created_at,
            url=f"/api/modules/{module_id}/snapshots/{snapshot.id}",
        )
        for snapshot in store.list_success(module_id)
    ]


@router.get("/{module_id}/snapshots/{snapshot_id}", response_model=Snapshot)
def get_immutable_snapshot(
    module_id: str,
    snapshot_id: str,
    response: Response,
    store: SnapshotStore = Depends(get_snapshot_store),
) -> Snapshot:
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return store.get_success(module_id, snapshot_id)
