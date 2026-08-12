import json
from pathlib import Path

from vibe_visualization_api.external_mod_runtimes import (
    default_external_origins,
    load_runtime_descriptor,
    resolve_runtime_origin,
    resolve_runtime_workspace,
)


def descriptor_file(tmp_path: Path) -> Path:
    descriptor = {
        "schemaVersion": "1.0",
        "roots": [
            {
                "id": "projects",
                "env": "NEWMA_DESK_PROJECTS_ROOT",
                "fallback": {"type": "repo-relative", "path": ".."},
            }
        ],
        "runtimes": [
            {
                "id": "example-runtime",
                "label": "Example",
                "adapter": "example",
                "workspaces": {
                    "source": {
                        "env": "NEWMA_DESK_EXAMPLE_WORKSPACE",
                        "candidates": [
                            {"root": "projects", "path": "example"}
                        ],
                    }
                },
                "endpoints": {
                    "web": {
                        "env": "NEWMA_DESK_EXAMPLE_WEB_URL",
                        "defaultOrigin": "http://127.0.0.1:4321",
                        "healthPath": "/health",
                    }
                },
            }
        ],
    }
    path = tmp_path / "external-mod-runtimes.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    load_runtime_descriptor.cache_clear()
    return path


def test_discovers_workspace_from_shared_runtime_descriptor(tmp_path: Path) -> None:
    project_root = tmp_path / "newma-desk"
    workspace = tmp_path / "example"
    project_root.mkdir()
    workspace.mkdir()
    descriptor = descriptor_file(tmp_path)

    assert resolve_runtime_workspace(
        "example-runtime",
        "source",
        descriptor_path=descriptor,
        project_root=project_root,
        home=tmp_path / "home",
        env={},
    ) == workspace


def test_resolves_endpoint_and_allowed_origin_from_shared_descriptor(
    tmp_path: Path,
) -> None:
    descriptor = descriptor_file(tmp_path)

    assert resolve_runtime_origin(
        "example-runtime", "web", descriptor_path=descriptor, env={}
    ) == "http://127.0.0.1:4321"
    assert default_external_origins(descriptor_path=descriptor, env={}) == [
        "http://127.0.0.1:4321"
    ]


def test_external_origin_defaults_follow_runtime_environment(tmp_path: Path) -> None:
    descriptor = descriptor_file(tmp_path)

    assert default_external_origins(
        descriptor_path=descriptor,
        env={"NEWMA_DESK_EXAMPLE_WEB_URL": "https://example.example.com"},
    ) == ["https://example.example.com"]


def test_previous_brand_environment_names_remain_compatible(
    tmp_path: Path,
) -> None:
    descriptor = descriptor_file(tmp_path)

    assert resolve_runtime_origin(
        "example-runtime",
        "web",
        descriptor_path=descriptor,
        env={"VIBEDESK_EXAMPLE_WEB_URL": "https://legacy.example"},
    ) == "https://legacy.example"
