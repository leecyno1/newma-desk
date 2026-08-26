import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
BUILDER_PATH = PROJECT_ROOT / "skills/dasheng-commercial-promo-video/scripts/build_commercial_promo_package.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("dasheng_commercial_promo_builder_test", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_brief(**overrides) -> dict:
    brief = {
        "title": "大圣产品宣传片",
        "mode": "product_promo",
        "brand": "大圣",
        "product": "AI 内容生产系统",
        "audience": "财经内容创作者",
        "objective": "预约演示",
        "duration_sec": 30,
        "aspect": "9:16",
        "hook": "一篇深度内容，为什么还要手工拆成十种格式？",
        "pain": "文章写完以后，视频、播客和发布仍要重复劳动。",
        "promise": "大圣把一份研究底稿直接送入完整媒体流水线。",
        "benefits": ["自动生成编剧和分镜", "统一完成动画、字幕和渲染"],
        "proof": [{"text": "六条视频流水线统一注册", "evidence_refs": ["pipeline_registry"]}],
        "brand_memory": "一份内容，完整生产。",
        "cta": "立即预约演示",
        "brand_tokens": {"primary_color": "#143CFF", "font_family": "PingFang SC"},
    }
    brief.update(overrides)
    return brief


def test_commercial_builder_writes_reviewable_schema_valid_package(tmp_path):
    builder = load_builder()
    outputs = builder.build_package(sample_brief(), tmp_path / "commercial")

    script = json.loads(outputs["script"].read_text(encoding="utf-8"))
    scene_plan = json.loads(outputs["scene_plan"].read_text(encoding="utf-8"))
    quality = json.loads(outputs["scene_plan_quality_gate"].read_text(encoding="utf-8"))
    routing = json.loads(outputs["tool_routing_plan"].read_text(encoding="utf-8"))
    brand_gate = json.loads(outputs["brand_brief_gate"].read_text(encoding="utf-8"))

    assert script["lane"] == "commercial_promo_video"
    assert script["commercial"]["aspect"] == "9:16"
    assert {segment["beat_class"] for segment in script["segments"]} >= {
        "hook", "product_promise", "feature_benefit", "proof", "brand_memory", "cta"
    }
    assert scene_plan["director_tool_routing"]["director_id"] == "commercial_promo_director"
    assert routing["director_profile"]["id"] == "commercial_promo_director"
    assert not {cap for stage in routing["stage_routes"].values() for cap in stage["unresolved_capabilities"]}
    assert quality["status"] == "pass", json.dumps(quality, ensure_ascii=False, indent=2)
    assert brand_gate["status"] == "pending_review"
    assert outputs["review_html"].is_file()
    assert outputs["checkpoint"].is_file()


def test_commercial_quality_gate_rejects_offer_without_disclaimer(tmp_path):
    builder = load_builder()
    outputs = builder.build_package(sample_brief(offer="限时五折"), tmp_path / "commercial")
    quality = json.loads(outputs["scene_plan_quality_gate"].read_text(encoding="utf-8"))

    assert quality["status"] == "fail"
    assert "commercial_offer_disclaimer_missing" in {item["code"] for item in quality["failures"]}


def test_commercial_director_cli_accepts_commercial_brief(tmp_path):
    brief_path = tmp_path / "commercial_brief.json"
    brief_path.write_text(json.dumps(sample_brief(), ensure_ascii=False), encoding="utf-8")
    output_dir = tmp_path / "自媒体创作" / "commercial_director"
    proc = subprocess.run(
        [
            PYTHON,
            str(PROJECT_ROOT / "scripts/dasheng_video_director.py"),
            "--lane",
            "commercial_promo_video",
            "--commercial-brief",
            str(brief_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["lane"] == "commercial_promo_video"
    assert result["status"] == "pending_review"
    assert (output_dir / "scene_plan.json").is_file()
    assert (output_dir / "brand_brief_gate.json").is_file()
