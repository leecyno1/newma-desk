from pathlib import Path

from fastapi.testclient import TestClient

from tests.model_gateway.fakes import FakeModelAdapter
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def test_model_gateway_discovers_and_invokes_selected_model(tmp_path: Path) -> None:
    adapter = FakeModelAdapter()
    database_path = tmp_path / "model.db"
    application = create_app(
        Settings(
            runtime_dir=tmp_path,
            database_path=database_path,
            model_default_adapter=adapter.id,
        ),
        model_adapters=[adapter],
    )

    with TestClient(application) as client:
        providers = client.get("/api/model/providers")
        response = client.post(
            "/api/model/responses",
            json={"prompt": "hello", "model": "chosen-model"},
        )

    assert providers.status_code == 200
    assert providers.json()["providers"] == [
        {
            "id": "fake-model",
            "capabilities": ["chat", "module.explain"],
            "default": True,
        }
    ]
    assert response.status_code == 200
    assert response.json() == {
        "answer": "fake model: hello",
        "adapter": "fake-model",
        "model": "chosen-model",
    }
    assert adapter.requests[0].prompt == "hello"
    assert database_path.exists() is False
