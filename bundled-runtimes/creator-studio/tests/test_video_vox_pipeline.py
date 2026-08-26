import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_explainer_storyboard import parse_html_article  # noqa: E402
from video_pipeline_governance import load_pipeline, validate_artifact, validate_pipeline_manifest  # noqa: E402
from video_scene_plan_quality_gate import audit_scene_plan  # noqa: E402
from video_tool_registry import load_tool_registry  # noqa: E402
from video_vox_storyboard import VOX_STATE_MACHINE, build_vox_storyboard  # noqa: E402


def write_article(path: Path) -> None:
    path.write_text(
        """
        <html><head><title>半导体周期为什么重新定价</title></head><body>
        <h1>半导体周期为什么重新定价</h1>
        <h2>历史背景</h2><p>过去三轮周期都同时受到库存、资本开支和终端需求影响。</p>
        <h2>传导机制</h2><p>库存先变化，价格和资本开支随后调整，最后传导到利润。</p>
        <h2>产业现场</h2><p>公司发布会、工厂扩产和客户访谈提供了观察产业变化的直接窗口。</p>
        <h2>风险与边界</h2><p>如果终端需求没有恢复，价格反弹可能只是一段补库存行情。</p>
        <h2>结论</h2><p>更稳妥的判断需要同时观察库存、价格和真实订单。</p>
        <table><tr><th>指标</th><th>变化</th></tr><tr><td>库存天数</td><td>-12%</td></tr></table>
        </body></html>
        """,
        encoding="utf-8",
    )


def test_vox_storyboard_is_question_led_and_evidence_bounded(tmp_path):
    article_path = tmp_path / "article.html"
    write_article(article_path)

    storyboard = build_vox_storyboard(parse_html_article(article_path), source_html=str(article_path))
    functions = [scene["narrative_function"] for scene in storyboard["scenes"]]

    assert storyboard["lane"] == "vox_explainer_video"
    assert storyboard["aspect"] == "16:9"
    assert storyboard["narrative_mode"] == "question_led_investigation"
    assert storyboard["central_question"].endswith("？")
    assert 3 <= len(storyboard["evidence_map"]) <= 6
    assert functions == VOX_STATE_MACHINE
    assert "counterargument" in functions
    assert storyboard["scenes"][-1]["epistemic_status"] == "qualified_conclusion"
    assert all(scene["asset_strategy"]["generic_background_is_last_resort"] for scene in storyboard["scenes"])
    assert storyboard["visual_bible"]["system"] == "vox_editorial_paper_collage"
    assert validate_artifact("visual_bible", storyboard["visual_bible"]) == []
    assert all(scene["visual_system"] == "vox_editorial_paper_collage" for scene in storyboard["scenes"])
    assert all(scene["director_shots"] for scene in storyboard["scenes"])
    assert all(
        all(8 <= shot["duration_sec"] <= 12 or shot.get("duration_exception") for shot in scene["director_shots"])
        for scene in storyboard["scenes"]
    )
    assert all(
        all(2.5 <= beat["duration_sec"] <= 5 for shot in scene["director_shots"] for beat in shot["micro_beats"])
        for scene in storyboard["scenes"]
    )
    assert all(scene["micro_shots"][0]["continuity_anchor"] == "shared_paper_evidence_world" for scene in storyboard["scenes"])
    assert all(scene["image2_scene_policy"]["mode"] == "one_complete_scene_still_per_director_shot" for scene in storyboard["scenes"])
    assert all(scene["image2_shot_packet"]["mode"] == "image2_scene_to_video" for scene in storyboard["scenes"])
    assert all(scene["image2_shot_packet"]["exact_text_overlay"] == "remotion_only" for scene in storyboard["scenes"])
    assert all(all(shot["shot_size"] and shot["focus"] and shot["crop_scale"] for shot in scene["director_shots"]) for scene in storyboard["scenes"])
    assert storyboard["visual_bible"]["generation_route"]["prompt_packet"] == ["image_prompt", "motion_prompt", "duration_sec", "sound_cue"]


def test_vox_pipeline_manifest_and_scene_schema_validate(tmp_path):
    registry = load_tool_registry()
    report = validate_pipeline_manifest(load_pipeline("vox_explainer"), registry=registry, project_root=PROJECT_ROOT)
    assert report["status"] == "pass", json.dumps(report, ensure_ascii=False, indent=2)

    article_path = tmp_path / "article.html"
    write_article(article_path)
    storyboard = build_vox_storyboard(parse_html_article(article_path), source_html=str(article_path))
    storyboard["schema_version"] = "dasheng.video.scene_plan.v1"
    assert validate_artifact("scene_plan", storyboard) == []
    assert audit_scene_plan(storyboard)["status"] == "pass"


def test_vox_quality_gate_rejects_missing_counterargument():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "vox_explainer_video",
        "central_question": "为什么会变化？",
        "evidence_map": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "scenes": [
            {
                "id": f"scene_{index:03d}",
                "title": state,
                "narrative_function": state,
                "start_sec": index * 4,
                "end_sec": index * 4 + 4,
                "duration_sec": 4,
                "beat_class": "claim",
                "html_animation_behavior": "live_motion",
                "micro_shots": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
            }
            for index, state in enumerate([item for item in VOX_STATE_MACHINE if item != "counterargument"], 0)
        ],
    }

    report = audit_scene_plan(plan)
    assert report["status"] == "fail"
    assert any(item["code"] == "vox_narrative_state_missing" for item in report["failures"])


def test_director_cli_builds_dedicated_vox_package(tmp_path):
    article_path = tmp_path / "article.html"
    write_article(article_path)
    output_dir = tmp_path / "自媒体创作" / "vox_run"

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "vox_explainer_video",
            "--article-html",
            str(article_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    first_result = json.loads(proc.stdout)
    assert first_result["status"] == "pending_storyboard_review"
    assert (output_dir / "video_content_brief.md").exists()
    assert (output_dir / "narration_script.rewritten.md").exists()
    assert (output_dir / "script_rewrite_gate.json").exists()
    assert (output_dir / "narrative_storyboard.json").exists()
    assert (output_dir / "storyboard_review.md").exists()
    assert (output_dir / "storyboard_review.html").exists()
    assert not (output_dir / "scene_plan.json").exists()
    assert not (output_dir / "vox_visual_bible.json").exists()

    narrative_storyboard = json.loads((output_dir / "narrative_storyboard.json").read_text(encoding="utf-8"))
    assert all("director_shots" not in scene and "micro_shots" not in scene for scene in narrative_storyboard["scenes"])
    decision_path = output_dir / "storyboard_review_decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "dasheng.storyboard_review_decision.v1",
                "status": "approved",
                "decisions": [
                    {
                        "scene_id": scene["id"],
                        "decision": "approved",
                        "approved": True,
                        "template_override": "",
                        "notes": "",
                    }
                    for scene in narrative_storyboard["scenes"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    gate_path = output_dir / "storyboard_review_gate.json"
    gate_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/validate_storyboard_review_gate.py"),
            "--storyboard",
            str(output_dir / "narrative_storyboard.json"),
            "--decision",
            str(decision_path),
            "--output",
            str(gate_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert gate_proc.returncode == 0, gate_proc.stderr

    production_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "vox_explainer_video",
            "--article-html",
            str(article_path),
            "--output-dir",
            str(output_dir),
            "--storyboard-review-gate",
            str(gate_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert production_proc.returncode == 0, production_proc.stderr
    assert json.loads(production_proc.stdout)["status"] == "production_plan_ready"
    scene_plan = json.loads((output_dir / "scene_plan.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((output_dir / "director_checkpoint.json").read_text(encoding="utf-8"))
    assert scene_plan["lane"] == "vox_explainer_video"
    assert scene_plan["central_question"]
    assert any(scene["narrative_function"] == "counterargument" for scene in scene_plan["scenes"])
    assert all(scene.get("tool_routing", {}).get("primary_stack") for scene in scene_plan["scenes"])
    assert all(scene.get("story_segment_id") and scene.get("director_shots") for scene in scene_plan["scenes"])
    assert all(
        shot.get("story_segment_id") == scene["story_segment_id"] and shot.get("core_claim_id") == scene.get("core_claim_id")
        for scene in scene_plan["scenes"]
        for shot in scene["director_shots"]
    )
    assert checkpoint["pipeline_id"] == "vox_explainer"
    assert checkpoint["status"] == "approved"
    assert (output_dir / "vox_storyboard.raw.json").exists()
    assert (output_dir / "vox_visual_bible.json").exists()
    assert (output_dir / "storyboard_review.html").exists()
