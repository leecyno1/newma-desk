import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def creator_output(tmp_path: Path) -> Path:
    return tmp_path / "自媒体创作" / "director_run"


def test_director_builds_explainer_scene_plan_package(tmp_path):
    output_dir = creator_output(tmp_path) / "explainer"
    article = tmp_path / "article.html"
    article.write_text(
        """
        <html><head><title>地产周期论</title></head><body>
        <h1>地产周期论</h1>
        <h2>01 库存周期</h2>
        <p>房地产不是简单涨跌，而是库存、信用和人口预期共同作用的周期。</p>
        <table><tr><th>指标</th><th>变化</th></tr><tr><td>销售面积</td><td>-20%</td></tr></table>
        </body></html>
        """,
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "explainer_html_video",
            "--article-html",
            str(article),
            "--output-dir",
            str(output_dir),
            "--duration-target-sec",
            "60",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    scene_plan = json.loads((output_dir / "scene_plan.json").read_text(encoding="utf-8"))
    assert result["status"] == "pending_review"
    assert scene_plan["schema_version"] == "dasheng.video.scene_plan.v1"
    assert scene_plan["lane"] == "explainer_html_video"
    assert scene_plan["scenes"]
    assert all("end_sec" in scene for scene in scene_plan["scenes"])
    assert all(scene.get("html_animation_behavior") for scene in scene_plan["scenes"])
    assert all(scene.get("tool_routing", {}).get("primary_stack") for scene in scene_plan["scenes"])
    routing_plan = json.loads((output_dir / "tool_routing_plan.json").read_text(encoding="utf-8"))
    project_registry = json.loads((PROJECT_ROOT / "configs/external/reserved_projects.json").read_text(encoding="utf-8"))
    assert routing_plan["registry_summary"]["projects"] == len(project_registry["projects"])
    assert routing_plan["registry_summary"]["skills"] >= 47
    assert (output_dir / "storyboard_template_review.html").exists()
    assert "工具路由" in (output_dir / "storyboard_template_review.html").read_text(encoding="utf-8")
    assert (output_dir / "director_checkpoint.json").exists()


def test_director_builds_talking_head_scene_plan_package(tmp_path):
    output_dir = creator_output(tmp_path) / "talking_head"
    srt = tmp_path / "proofread.srt"
    srt.write_text(
        """1
00:00:00,000 --> 00:00:02,000
今天讲一个反常识问题。

2
00:00:02,000 --> 00:00:05,500
这个行业的数据下滑了20%，但结构并没有完全崩。

3
00:00:05,500 --> 00:00:09,000
所以真正要看的，是信用和库存的传导链条。
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "talking_head_video",
            "--srt",
            str(srt),
            "--title",
            "地产口播",
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    scene_plan = json.loads((output_dir / "scene_plan.json").read_text(encoding="utf-8"))
    assert scene_plan["schema_version"] == "dasheng.video.scene_plan.v1"
    assert scene_plan["lane"] == "talking_head_video"
    assert scene_plan["scenes"]
    assert all(scene.get("speaker_state") for scene in scene_plan["scenes"])
    assert all(scene.get("material_state") for scene in scene_plan["scenes"])
    assert all(scene.get("pip_shape") for scene in scene_plan["scenes"])
    assert all(scene.get("tool_routing", {}).get("primary_stack") for scene in scene_plan["scenes"])
    assert (output_dir / "talking_head_timeline.raw.json").exists()
    assert (output_dir / "tool_routing_plan.json").exists()
    assert (output_dir / "storyboard_template_review.html").exists()


def test_director_updates_project_run_manifest(tmp_path):
    output_root = creator_output(tmp_path)
    manifest_path = output_root / "project_run_manifest.json"
    init_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/project_run_manifest.py"),
            "init",
            "--title",
            "导演账本测试",
            "--pipeline",
            "explainer_html",
            "--run-id",
            "director_run",
            "--output-root",
            str(output_root),
            "--output",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert init_proc.returncode == 0, init_proc.stderr
    article = tmp_path / "article.html"
    article.write_text("<html><body><h1>账本测试</h1><p>这是一个用于导演分镜的测试。</p></body></html>", encoding="utf-8")

    director_proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "explainer_html_video",
            "--article-html",
            str(article),
            "--output-dir",
            str(output_root / "director"),
            "--project-manifest",
            str(manifest_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert director_proc.returncode == 0, director_proc.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene_stage = next(stage for stage in manifest["stages"] if stage["name"] == "scene_plan")
    assert scene_stage["status"] == "pending_review"
    assert any(item["type"] == "scene_plan" for item in manifest["artifacts"])
    assert any(item["type"] == "tool_routing_plan" for item in manifest["artifacts"])
