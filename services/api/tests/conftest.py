from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    test_settings = Settings(
        runtime_dir=tmp_path,
        database_path=tmp_path / "vibe-visualization.db",
        allowed_origins="http://127.0.0.1:5888,http://127.0.0.1:5891",
    )
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
