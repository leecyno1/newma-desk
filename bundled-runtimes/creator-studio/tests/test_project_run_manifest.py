import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from project_run_manifest import (  # noqa: E402
    add_artifact,
    build_manifest,
    build_summary,
    is_safe_output_root,
    save_manifest,
    set_stage_status,
    validate_manifest,
)


def creator_output(tmp_path: Path) -> Path:
    return tmp_path / "自媒体创作" / "run_001"


def test_build_manifest_initializes_pipeline_stages(tmp_path):
    manifest = build_manifest(
        title="地产周期论",
        pipeline_id="explainer_html",
        output_root=creator_output(tmp_path),
        source_materials=[{"type": "article_html", "path": "/tmp/article.html"}],
        run_id="test_run",
    )

    assert manifest["schema_version"] == "newma.project_run_manifest.v2"
    assert manifest["run_id"] == "test_run"
    assert manifest["lane"] == "explainer_html_video"
    assert [stage["name"] for stage in manifest["stages"]] == [
        "intake",
        "scene_plan",
        "claim_evidence",
        "asset_build",
        "render_qc",
    ]
    assert validate_manifest(manifest) == []


def test_build_manifest_supports_mainline_pipeline(tmp_path):
    manifest = build_manifest(
        title="主链总账本",
        pipeline_id="mainline",
        output_root=creator_output(tmp_path),
        run_id="mainline_run",
    )

    assert manifest["pipeline_id"] == "mainline"
    assert manifest["lane"] == "article"
    assert [stage["name"] for stage in manifest["stages"]] == [
        "intake",
        "brief",
        "draft",
        "transwrite",
        "publish",
        "postmortem",
    ]
    assert validate_manifest(manifest) == []


def test_manifest_rejects_project_and_skills_output_roots(tmp_path):
    safe_root = creator_output(tmp_path)
    unsafe_project_root = PROJECT_ROOT / "自媒体创作" / "run"
    unsafe_skills_root = tmp_path / "自媒体创作" / "skills" / "run"

    assert is_safe_output_root(safe_root)
    assert not is_safe_output_root(unsafe_project_root)
    assert not is_safe_output_root(unsafe_skills_root)


def test_manifest_records_stage_and_artifact(tmp_path):
    manifest = build_manifest(
        title="真人口播测试",
        pipeline_id="talking_head",
        output_root=creator_output(tmp_path),
        run_id="talking_head_run",
    )

    set_stage_status(
        manifest,
        stage_name="scene_plan",
        status="pending_review",
        checkpoint_path="/tmp/director_checkpoint.json",
    )
    add_artifact(
        manifest,
        stage_name="scene_plan",
        artifact_type="scene_plan",
        path="/tmp/scene_plan.json",
    )

    assert validate_manifest(manifest) == []
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    assert scene_stage["status"] == "pending_review"
    assert manifest["artifacts"][0]["type"] == "scene_plan"
    assert build_summary(manifest)["artifact_count"] == 1


def test_manifest_save_roundtrip(tmp_path):
    manifest = build_manifest(
        title="保存测试",
        pipeline_id="style_training",
        output_root=creator_output(tmp_path),
        run_id="style_run",
    )
    output = tmp_path / "manifest.json"
    save_manifest(manifest, output)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["pipeline_id"] == "style_training"
    assert validate_manifest(loaded) == []
