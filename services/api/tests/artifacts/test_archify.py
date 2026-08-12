from vibe_visualization_api.artifacts.archify import (
    inject_newma_theme_adapter,
    to_archify_ir,
)
from vibe_visualization_api.artifacts.models import GraphArtifactCreate


def test_archify_places_parallel_suppliers_in_the_same_dependency_layer() -> None:
    spec = GraphArtifactCreate.model_validate(
        {
            "moduleId": "industry-map",
            "title": "多分支产业链",
            "nodes": [
                {"id": "laser", "label": "激光器芯片"},
                {"id": "detector", "label": "探测器芯片"},
                {"id": "engine", "label": "光引擎"},
                {"id": "module", "label": "光模块"},
                {"id": "network", "label": "网络设备"},
            ],
            "edges": [
                {"source": "laser", "target": "engine"},
                {"source": "detector", "target": "engine"},
                {"source": "engine", "target": "module"},
                {"source": "module", "target": "network"},
            ],
        }
    )

    ir = to_archify_ir(spec)
    positions = {
        component["id"]: component["pos"]
        for component in ir["components"]
    }

    assert positions["laser"][0] == positions["detector"][0]
    assert positions["laser"][1] != positions["detector"][1]
    assert positions["laser"][0] < positions["engine"][0]
    assert positions["engine"][0] < positions["module"][0]
    assert positions["module"][0] < positions["network"][0]


def test_newma_theme_adapter_is_injected_once() -> None:
    source = "<!DOCTYPE html><html><head><title>Graph</title></head><body></body></html>"

    adapted = inject_newma_theme_adapter(source)

    assert "data-newma-archify-theme-adapter" in adapted
    assert "newma:artifact-theme" in adapted
    assert inject_newma_theme_adapter(adapted) == adapted
