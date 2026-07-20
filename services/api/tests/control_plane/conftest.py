from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.main import create_app


def _path_snapshot(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    default_database_path = Path("runtime/vibe-visualization.db")
    default_database_before = _path_snapshot(default_database_path)

    settings_database_path = tmp_path / "app-settings.db"
    repository_database_path = tmp_path / "registry.db"
    test_settings = Settings(
        runtime_dir=tmp_path,
        database_path=settings_database_path,
    )
    application = create_app(test_settings)
    repository = ModuleRepository(repository_database_path)
    application.dependency_overrides[get_repository] = lambda: repository

    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.dependency_overrides.clear()

    assert repository_database_path.exists()
    assert not settings_database_path.exists()
    assert _path_snapshot(default_database_path) == default_database_before
