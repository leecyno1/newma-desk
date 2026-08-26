import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_director_timeline import Caption, build_talking_head_timeline, group_captions
from video_explainer_storyboard import build_explainer_storyboard, parse_html_article
from render_html_anything_scene_pack_video import build_mmx_speech_command
from render_html_anything_scene_pack_video import build_qc_report
from render_html_anything_scene_pack_video import allocate_voice_durations, combined_narration_text
from video_driver_rules import classify_beat, score_driver


def test_talking_head_timeline_contains_director_layers():
    captions = [
        Caption(0.0, 1.2, "这一次美股AI波动，"),
        Caption(1.2, 3.4, "核心不是情绪，而是资金约束。"),
        Caption(3.4, 6.5, "OpenAI和SpaceX潜在融资可能达到1500亿美元。"),
        Caption(6.5, 9.0, "这会带来板块内部的抽血效应。"),
    ]

    timeline = build_talking_head_timeline(captions, title="AI真的等于美国吗", duration=9.0)

    assert timeline["schema_version"] == "dasheng.talking_head_timeline.v1"
    assert timeline["lane"] == "talking_head_video"
    assert timeline["aspect"] == "16:9"
    assert timeline["segments"]
    assert any(segment["overlay"]["type"] == "real_data_chart_or_table" for segment in timeline["segments"])
    assert any(segment["beat_class"] == "evidence_data" for segment in timeline["segments"])
    assert all("driver_scores" in segment for segment in timeline["segments"])
    assert all("audio" in segment for segment in timeline["segments"])
    assert timeline["qc_targets"]["fake_data_charts"] == "forbidden"


def test_group_captions_preserves_semantic_beats():
    captions = [
        Caption(0.0, 1.0, "第一句，"),
        Caption(1.0, 3.2, "到这里结束。"),
        Caption(3.2, 5.0, "第二句继续，"),
        Caption(5.0, 7.2, "也完整结束。"),
    ]

    groups = group_captions(captions, min_sec=2.0, max_sec=5.0)

    assert len(groups) == 2
    assert groups[0].text.endswith("。")


def test_explainer_storyboard_extracts_article_structure(tmp_path):
    html_file = tmp_path / "article.html"
    html_file.write_text(
        """
        <html><head><title>楼市的微妙时刻</title></head><body>
        <h1>楼市的微妙时刻</h1>
        <h2>政策变化</h2>
        <p>专项债可以作为城市更新项目资本金，这会改变项目启动门槛。</p>
        <table><tr><th>指标</th><th>变化</th></tr><tr><td>土地出让收入</td><td>-27.2%</td></tr></table>
        <img src="chart.png" alt="土地财政变化图">
        </body></html>
        """,
        encoding="utf-8",
    )

    article = parse_html_article(html_file)
    router = {
        "schema_version": "test.router.v1",
        "part_router": {
            "opening_hook": {"primary": "frame-glitch-title", "alternates": ["frame-liquid-bg-hero"], "candidates": [{"template_id": "frame-glitch-title", "reason": "hook"}]},
            "warning_or_risk": {"primary": "deck-safety-alert", "alternates": [], "candidates": [{"template_id": "deck-safety-alert", "reason": "risk"}]},
            "data_table": {"primary": "data-report", "alternates": ["finance-report"], "candidates": [{"template_id": "data-report", "reason": "table"}]},
            "closing_outro": {"primary": "frame-logo-outro", "alternates": [], "candidates": [{"template_id": "frame-logo-outro", "reason": "outro"}]},
        },
    }
    storyboard = build_explainer_storyboard(article, source_html=str(html_file), router=router)

    assert storyboard["schema_version"] == "dasheng.explainer_storyboard.v1"
    assert storyboard["lane"] == "explainer_html_video"
    assert storyboard["renderer"] == "html-video"
    assert any(scene["type"] == "table" for scene in storyboard["scenes"])
    assert any(scene["variables"].get("chart_policy") == "reuse_real_table_or_chart" for scene in storyboard["scenes"])
    assert "fake_chart" in storyboard["style"]["avoid"]
    assert storyboard["scenes"][0]["template_id"] == "frame-glitch-title"
    assert any(scene["template_id"] == "data-report" for scene in storyboard["scenes"])
    assert all("content_part" in scene for scene in storyboard["scenes"])
    assert all("timing" in scene for scene in storyboard["scenes"])
    assert all("beat_class" in scene for scene in storyboard["scenes"])
    assert all("driver_scores" in scene for scene in storyboard["scenes"])
    assert all("director_state" in scene for scene in storyboard["scenes"])
    assert all("motion" in scene for scene in storyboard["scenes"])


def test_cli_outputs_are_json_serializable(tmp_path):
    timeline = build_talking_head_timeline(
        [Caption(0, 4, "这里有一个20%的变化。")],
        title="测试",
        duration=4,
    )
    path = tmp_path / "timeline.json"
    path.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["segments"][0]["id"] == "beat_001"


def test_mmx_speech_command_uses_configured_auth_not_inline_key(tmp_path):
    text_file = tmp_path / "scene.txt"
    output = tmp_path / "scene.wav"

    command = build_mmx_speech_command(
        text_file,
        output,
        model="speech-2.8-hd",
        voice="Chinese (Mandarin)_Radio_Host",
        speed=1.08,
        language="Chinese",
    )

    assert command[:3] == ["mmx", "speech", "synthesize"]
    assert "--text-file" in command
    assert str(text_file) in command
    assert "--out" in command
    assert str(output) in command
    assert "Chinese (Mandarin)_Radio_Host" in command
    assert "--api-key" not in command


def test_single_voice_narration_and_duration_allocation():
    scenes = [
        {"title": "标题", "narration": "短句。"},
        {"title": "逻辑", "narration": "这是一段明显更长的旁白，用来承载主要论证。"},
        {"title": "结论", "narration": "收束。"},
    ]

    text = combined_narration_text(scenes)
    durations = allocate_voice_durations(scenes, 30.0)

    assert "短句。" in text
    assert "这是一段明显更长的旁白" in text
    assert len(durations) == 3
    assert round(sum(durations), 3) == 30.0
    assert durations[1] > durations[0]
    assert durations[1] > durations[2]


def test_video_qc_fails_visible_labels_and_unsourced_evidence(tmp_path):
    scene_html = tmp_path / "scene.html"
    scene_html.write_text(
        """
        <html><body>
        <main><h1>关键数据</h1><p>template_id: data-report</p></main>
        <script>var hidden = "data-director-policy";</script>
        </body></html>
        """,
        encoding="utf-8",
    )
    manifest = {
        "scenes": [
            {
                "id": "scene_001",
                "content_part": "data_table",
                "beat_class": "evidence_data",
                "start_sec": 45,
                "end_sec": 52,
                "duration_sec": 7,
                "title": "关键数据",
                "narration": "这是一张证据表。",
                "variables": {},
                "motion_policy": {"animation": "gsap_table_scan"},
                "html": str(scene_html),
            }
        ]
    }
    report = build_qc_report(
        manifest,
        output_dir=tmp_path,
        silent_result={"final_video": str(tmp_path / "missing.mp4"), "duration_sec": 7},
        voice_result=None,
    )
    codes = {item["code"] for item in report["failures"]}

    assert report["status"] == "fail"
    assert "evidence_gap_too_long" in codes
    assert "evidence_without_real_data" in codes
    assert "visible_workflow_label" in codes
    assert (tmp_path / "video_qc_report.json").exists()


def test_video_qc_allows_normal_positioning_word(tmp_path):
    scene_html = tmp_path / "scene.html"
    scene_html.write_text("<html><body><main>WATCH: POLICY · LIQUIDITY · POSITIONING</main></body></html>", encoding="utf-8")
    manifest = {
        "scenes": [
            {
                "id": "scene_001",
                "content_part": "warning_or_risk",
                "beat_class": "objection",
                "start_sec": 0,
                "end_sec": 6,
                "duration_sec": 6,
                "title": "风险",
                "narration": "风险提示。",
                "variables": {},
                "motion_policy": {"animation": "gsap_alert_stack"},
                "html": str(scene_html),
            }
        ]
    }
    report = build_qc_report(
        manifest,
        output_dir=tmp_path,
        silent_result={"final_video": str(tmp_path / "missing.mp4"), "duration_sec": 6},
        voice_result=None,
    )

    assert report["status"] == "pass"


def test_video_qc_warns_when_voiceover_stretches_timeline(tmp_path):
    scene_html = tmp_path / "scene.html"
    scene_html.write_text("<html><body><main>结论</main></body></html>", encoding="utf-8")
    manifest = {
        "scenes": [
            {
                "id": "scene_001",
                "content_part": "closing_outro",
                "beat_class": "recap",
                "start_sec": 0,
                "end_sec": 10,
                "duration_sec": 10,
                "title": "结论",
                "narration": "结论。",
                "variables": {},
                "motion_policy": {"animation": "resolve_fade_in"},
                "html": str(scene_html),
            }
        ]
    }
    report = build_qc_report(
        manifest,
        output_dir=tmp_path,
        silent_result={"final_video": str(tmp_path / "missing.mp4"), "duration_sec": 10},
        voice_result={"final_video": str(tmp_path / "missing.mp4"), "duration_sec": 14},
    )

    assert report["status"] == "pass"
    assert any(item["code"] == "voiceover_stretches_visual_timeline" for item in report["warnings"])


def test_video_qc_warns_for_too_many_transition_cards(tmp_path):
    scenes = []
    for idx in range(1, 9):
        scene_html = tmp_path / f"scene_{idx}.html"
        scene_html.write_text(f"<html><body><main>场景 {idx}</main></body></html>", encoding="utf-8")
        scenes.append(
            {
                "id": f"scene_{idx:03d}",
                "content_part": "transition" if idx in {2, 4, 6, 8} else "chapter_divider",
                "beat_class": "chapter",
                "start_sec": idx * 2,
                "end_sec": idx * 2 + 2,
                "duration_sec": 2,
                "title": f"场景 {idx}",
                "narration": f"场景 {idx}。",
                "variables": {},
                "motion_policy": {"animation": "gsap_fast_cut"},
                "html": str(scene_html),
            }
        )
    report = build_qc_report(
        {"scenes": scenes},
        output_dir=tmp_path,
        silent_result={"final_video": str(tmp_path / "missing.mp4"), "duration_sec": 16},
        voice_result=None,
    )

    assert report["status"] == "pass"
    assert any(item["code"] == "too_many_standalone_transition_cards" for item in report["warnings"])


def test_video_driver_rules_classify_data_and_score():
    beat_class = classify_beat("OpenAI 和 SpaceX 的融资规模可能达到 1500 亿美元。", index=3)
    scores = score_driver(
        "OpenAI 和 SpaceX 的融资规模可能达到 1500 亿美元。",
        beat_class=beat_class,
        duration=5.0,
        seconds_since_speaker=12.0,
        index=3,
        lane="talking_head",
    )

    assert beat_class == "evidence_data"
    assert scores["evidence_need"] >= 0.9
    assert scores["trust_debt"] > 0
