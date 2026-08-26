from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_catalog_module():
    path = ROOT / "scripts/build_project_catalog.py"
    spec = importlib.util.spec_from_file_location("build_project_catalog", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_project_catalog_is_current():
    module = load_catalog_module()
    expected = module.build_catalog().rstrip() + "\n"
    actual = (ROOT / "docs/PROJECT_CATALOG.md").read_text(encoding="utf-8")
    assert actual == expected


def test_reserved_registry_counts_and_paths_are_consistent():
    registry = json.loads((ROOT / "configs/external/reserved_projects.json").read_text(encoding="utf-8"))
    projects = registry["projects"]
    candidates = registry["reserve_candidates"]
    rejected = registry["rejected"]
    summary = registry["summary"]

    assert summary["retained_projects"] == len(projects)
    assert summary["reserve_candidates"] == len(candidates)
    assert len(rejected) > 0

    rows = projects + candidates
    names = [row["name"] for row in rows]
    paths = [row["local_path"] for row in rows]
    assert len(names) == len(set(names))
    assert len(paths) == len(set(paths))
    assert all(row.get("repo", "").startswith("https://") for row in rows)
    assert all(path.startswith("vendor/") for path in paths)


def test_upstream_patch_registry_references_public_patch_files():
    registry = json.loads((ROOT / "configs/external/upstream_patches.json").read_text(encoding="utf-8"))
    rows = registry["patches"]
    assert rows
    assert len({row["id"] for row in rows}) == len(rows)
    for row in rows:
        patch = ROOT / row["patch_file"]
        assert patch.is_file(), row["id"]
        assert patch.read_text(encoding="utf-8").startswith("diff --git ")
        assert str(row["root"]).startswith("vendor/")
        assert row["files"]
