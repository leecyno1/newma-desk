import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
