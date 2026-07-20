from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.control_plane.repository import ModuleRepository
from vibe_visualization_api.control_plane.routes import get_repository
from vibe_visualization_api.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    default_database_path = Path("runtime/vibe-visualization.db")
    assert not default_database_path.exists()

    test_settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "app-settings.db",
    )
    application = create_app(test_settings)
    repository = ModuleRepository(tmp_path / "registry.db")
    application.dependency_overrides[get_repository] = lambda: repository

    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.dependency_overrides.clear()

    assert not default_database_path.exists()
