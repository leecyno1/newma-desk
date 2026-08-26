import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_html_anything_template_router import build_part_router, build_template_roles
from build_html_anything_video_timeline import build_timeline, extract_numeric_metrics
from render_html_anything_timeline_pack import build_pack
from render_html_anything_scene_pack_animated import bgm_volume_filter


def test_router_maps_core_article_video_parts():
    templates = [
        {"id": "frame-glitch-title", "zh_name": "故障标题", "category": "video", "description": "标题转场", "tags": "title"},
        {"id": "frame-liquid-bg-hero", "zh_name": "流体 Hero", "category": "poster", "description": "片头", "tags": "hero"},
        {"id": "frame-flowchart-sticky", "zh_name": "流程图", "category": "video", "description": "流程", "tags": "flowchart"},
        {"id": "frame-data-chart-nyt", "zh_name": "图表", "category": "video", "description": "数据图表", "tags": "chart"},
        {"id": "data-report", "zh_name": "数据报告", "category": "data", "description": "数据表格", "tags": "table chart"},
        {"id": "card-twitter", "zh_name": "推特卡", "category": "card", "description": "金句", "tags": "quote"},
        {"id": "mobile-app", "zh_name": "手机", "category": "mobile", "description": "手机框", "tags": "iphone"},
        {"id": "social-x-post-card", "zh_name": "X卡", "category": "card", "description": "社交帖子", "tags": "twitter chat"},
        {"id": "frame-logo-outro", "zh_name": "结尾", "category": "video", "description": "片尾", "tags": "outro"},
    ]

    roles = build_template_roles(templates)
    router = build_part_router(templates, roles)

    assert router["opening_hook"]["primary"] == "frame-glitch-title"
    assert router["overall_outline"]["primary"] == "frame-flowchart-sticky"
    assert router["data_chart"]["primary"] == "frame-data-chart-nyt"
    assert router["data_table"]["primary"] == "data-report"
    assert router["quote"]["primary"] == "card-twitter"
    assert router["phone_mockup"]["primary"] == "mobile-app"
    assert router["chat_box"]["primary"] == "social-x-post-card"
    assert router["closing_outro"]["primary"] == "frame-logo-outro"


def test_generated_router_config_covers_all_templates_if_present():
    config = PROJECT_ROOT / "configs/video/html_anything_template_router.json"
    if not config.exists():
        return
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["template_count"] >= 70
    assert all(template["roles"] for template in data["templates"])
    assert len(data["template_usage_matrix"]) == data["template_count"]
    assert data["role_map"]["article_image"][0] == "doc-kami-parchment"
    for part in ["article_title", "overall_outline", "data_chart", "data_table", "quote", "phone_mockup", "chat_box"]:
        assert data["part_router"][part]["primary"]
        assert data["part_router"][part]["trigger"]


def test_video_timeline_expands_storyboard_into_template_parts(tmp_path):
    article = tmp_path / "article.html"
    article.write_text("<p><strong>利率就是均值回归的地心引力。</strong></p>", encoding="utf-8")
    router = {
        "schema_version": "test.router.v1",
        "part_router": {
            "article_title": {"primary": "frame-liquid-bg-hero", "candidates": [{"reason": "title"}]},
            "opening_hook": {"primary": "frame-glitch-title", "candidates": [{"reason": "hook"}]},
            "overall_outline": {"primary": "frame-flowchart-sticky", "candidates": [{"reason": "outline"}]},
            "chapter_divider": {"primary": "frame-light-leak-cinema", "candidates": [{"reason": "chapter"}]},
            "warning_or_risk": {"primary": "deck-safety-alert", "candidates": [{"reason": "risk"}]},
            "logic_chain": {"primary": "frame-flowchart-sticky", "candidates": [{"reason": "logic"}]},
            "financial_chart": {"primary": "finance-report", "candidates": [{"reason": "finance"}]},
            "pull_quote": {"primary": "blog-post", "candidates": [{"reason": "quote"}]},
            "transition": {"primary": "frame-glitch-title", "candidates": [{"reason": "transition"}]},
            "data_table": {"primary": "data-report", "candidates": [{"reason": "table"}]},
            "data_chart": {"primary": "frame-data-chart-nyt", "candidates": [{"reason": "chart"}]},
            "closing_outro": {"primary": "frame-logo-outro", "candidates": [{"reason": "outro"}]},
            "brand_mark": {"primary": "frame-logo-outro", "candidates": [{"reason": "brand"}]},
        },
    }
    storyboard = {
        "schema_version": "dasheng.explainer_storyboard.v1",
        "title": "测试视频",
        "scenes": [
            {"id": "scene_001", "type": "hook", "title": "测试视频", "narration": "开头"},
            {
                "id": "scene_002",
                "type": "section",
                "title": "流动性冲击",
                "narration": "12月加息概率100%，美债收益率4.52%。",
                "beat_class": "evidence_data",
                "director_state": "evidence_scene",
                "driver_scores": {"evidence_need": 0.95, "attention_debt": 0.5},
                "driver_score": 0.8,
            },
            {
                "id": "scene_003",
                "type": "table",
                "title": "关键数据",
                "narration": "数据对比。",
                "variables": {
                    "table": [
                        ["指标", "值"],
                        ["纳指", "-4.18%"],
                        ["费城半导体", "-10.26%"],
                        ["标普500", "-2.64%"],
                    ]
                },
            },
            {"id": "scene_004", "type": "outro", "title": "结论", "narration": "结束"},
        ],
    }

    timeline = build_timeline(storyboard, router, article)
    parts = [scene["content_part"] for scene in timeline["timeline"]]
    templates = [scene["template_id"] for scene in timeline["timeline"]]

    assert timeline["scene_count"] > len(storyboard["scenes"])
    assert "overall_outline" in parts
    assert "financial_chart" in parts
    assert "data_table" in parts
    assert "data_chart" in parts
    assert "frame-data-chart-nyt" in templates
    assert timeline["driver_rules_schema"].startswith("dasheng.video_editing_driver_rules")
    assert all("beat_class" in scene for scene in timeline["timeline"])
    assert all("driver_scores" in scene for scene in timeline["timeline"])
    assert any(scene["director_state"] == "evidence_scene" for scene in timeline["timeline"])
    assert all(scene["motion_policy"]["framework"] == "hyperframes" for scene in timeline["timeline"])
    assert any(scene["motion_policy"]["animation"] == "gsap_chart_reveal" for scene in timeline["timeline"])
    assert sum(1 for part in parts if part == "transition") <= 2


def test_video_timeline_extracts_numeric_metrics_for_chart_scenes():
    metrics = extract_numeric_metrics("纳斯达克跌了4.18%，费城半导体指数下跌10.26%，SpaceX融资750亿美元。")

    assert any(item["display"] == "4.18%" for item in metrics)
    assert any(item["display"] == "10.26%" for item in metrics)
    assert any(item["display"] == "750亿美元" for item in metrics)


def test_video_timeline_skips_companion_chart_for_tiny_tables(tmp_path):
    article = tmp_path / "article.html"
    article.write_text("<p>测试</p>", encoding="utf-8")
    router = {
        "schema_version": "test.router.v1",
        "part_router": {
            "article_title": {"primary": "frame-liquid-bg-hero", "candidates": [{"reason": "title"}]},
            "opening_hook": {"primary": "frame-glitch-title", "candidates": [{"reason": "hook"}]},
            "overall_outline": {"primary": "frame-flowchart-sticky", "candidates": [{"reason": "outline"}]},
            "data_table": {"primary": "data-report", "candidates": [{"reason": "table"}]},
            "data_chart": {"primary": "frame-data-chart-nyt", "candidates": [{"reason": "chart"}]},
            "closing_outro": {"primary": "frame-logo-outro", "candidates": [{"reason": "outro"}]},
            "brand_mark": {"primary": "frame-logo-outro", "candidates": [{"reason": "brand"}]},
        },
    }
    storyboard = {
        "schema_version": "dasheng.explainer_storyboard.v1",
        "title": "测试视频",
        "scenes": [
            {"id": "scene_001", "type": "hook", "title": "测试视频", "narration": "开头"},
            {"id": "scene_002", "type": "table", "title": "小表", "narration": "小表。", "variables": {"table": [["指标", "值"], ["纳指", "-4.18%"]]}},
            {"id": "scene_003", "type": "outro", "title": "结论", "narration": "结束"},
        ],
    }

    timeline = build_timeline(storyboard, router, article)
    parts = [scene["content_part"] for scene in timeline["timeline"]]

    assert "data_table" in parts
    assert "data_chart" not in parts


def test_scene_pack_renderer_outputs_html_files(tmp_path):
    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "dasheng.html_anything_video_timeline.v1",
                "title": "测试视频",
                "aspect": "9:16",
                "duration_estimate_sec": 12,
                "timeline": [
                    {
                        "id": "html_scene_001",
                        "content_part": "article_title",
                        "beat_class": "hook",
                        "director_state": "hook_card",
                        "transition_to_next": "impact_cut",
                        "template_id": "frame-liquid-bg-hero",
                        "start_sec": 0,
                        "end_sec": 4,
                        "duration_sec": 4,
                        "title": "测试标题",
                        "narration": "测试标题。",
                        "variables": {},
                    },
                    {
                        "id": "html_scene_002",
                        "content_part": "data_table",
                        "beat_class": "evidence_data",
                        "director_state": "evidence_scene",
                        "transition_to_next": "data_reveal",
                        "audio": {"sfx": "soft_tick", "duck_bgm": True},
                        "template_id": "data-report",
                        "start_sec": 4,
                        "end_sec": 12,
                        "duration_sec": 8,
                        "title": "关键数据",
                        "narration": "真实数据支撑判断。",
                        "variables": {"table": [["指标", "变化"], ["纳指", "-4.18%"]]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = build_pack(timeline_path, tmp_path / "pack")

    assert manifest["scene_count"] == 2
    assert manifest["beat_usage"]["hook"] == 1
    assert manifest["director_usage"]["evidence_scene"] == 1
    assert manifest["transition_usage"]["data_reveal"] == 1
    assert (tmp_path / "pack" / "preview.html").exists()
    assert all(Path(scene["html"]).exists() for scene in manifest["scenes"])
    assert manifest["scenes"][1]["beat_class"] == "evidence_data"
    assert manifest["scenes"][1]["director_state"] == "evidence_scene"
    assert manifest["scenes"][1]["transition_to_next"] == "data_reveal"
    assert "情景数字不构成预测" in Path(manifest["scenes"][1]["html"]).read_text(encoding="utf-8")
    assert manifest["scenes"][1]["motion_policy"]["framework"] == "hyperframes"
    html = Path(manifest["scenes"][1]["html"]).read_text(encoding="utf-8")
    assert "window.gsap" in html
    assert "state-evidence_scene" in html
    assert "transition-data_reveal" in html
    assert "data-director-policy" in html
    assert "data-lottie-role" in html
    assert 'id="lottie-data"' in html
    assert 'data-motion-runtime="dasheng"' in html


def test_flowchart_keeps_outline_visible_without_fullscreen_focus_resets(tmp_path):
    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "dasheng.html_anything_video_timeline.v2",
                "title": "提纲测试",
                "aspect": "16:9",
                "duration_estimate_sec": 9,
                "timeline": [
                    {
                        "id": "outline_001",
                        "content_part": "overall_outline",
                        "beat_class": "logic_chain",
                        "template_id": "frame-flowchart-sticky",
                        "start_sec": 0,
                        "end_sec": 9,
                        "duration_sec": 9,
                        "title": "总提纲",
                        "narration": "先看三个问题。",
                        "variables": {"headings": ["第一部分", "第二部分", "第三部分"]},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = build_pack(timeline_path, tmp_path / "pack")
    html = Path(manifest["scenes"][0]["html"]).read_text(encoding="utf-8")

    assert "focus-stage" not in html
    assert "focusSequence" not in html
    assert "nodeReveal" in html
    assert "--node-delay" in html


def test_semantic_director_templates_render_distinct_components(tmp_path):
    evidence = tmp_path / "evidence.png"
    evidence.write_bytes(b"fake-image-for-html-reference")
    templates = [
        ("route-map-seven", {"headings": [f"问题 {index}" for index in range(1, 8)]}, "route-grid"),
        ("source-web-evidence", {"sources": [{"src": str(evidence), "label": "官网", "url": "https://example.com", "claim": "来源命题"}]}, "web-grid"),
        ("business-flywheel", {"items": ["发射", "卫星", "服务", "现金流"]}, "wheel-stage"),
        ("customer-concentration-funnel", {"suppliers": ["甲", "乙"], "buyers": ["核心客户"]}, "funnel-layout"),
        ("valuation-waterfall", {}, "valuation-chain"),
        ("commercial-proof-ladder", {}, "proof-ladder"),
        ("value-chain-profit-map", {}, "chain-lane"),
        ("investment-signal-gate", {}, "signal-gate"),
        ("direction-price-balance", {}, "balance-beam"),
        ("evidence-discipline-meter", {}, "evidence-level"),
        ("recurring-revenue-streams", {}, "network-core"),
        ("business-model-split", {}, "model-compare"),
        ("value-chain-chapter-bridge", {}, "chain-bridge"),
    ]
    timeline = []
    for index, (template_id, variables, _marker) in enumerate(templates):
        timeline.append(
            {
                "id": f"scene_{index:03d}",
                "content_part": "logic_chain",
                "beat_class": "evidence_data",
                "template_id": template_id,
                "start_sec": index * 6,
                "end_sec": (index + 1) * 6,
                "duration_sec": 6,
                "title": template_id,
                "narration": "用于验证不同导演组件。",
                "variables": variables,
            }
        )
    timeline_path = tmp_path / "timeline.json"
    timeline_path.write_text(
        json.dumps({"schema_version": "dasheng.html_anything_video_timeline.v2", "title": "导演组件", "aspect": "16:9", "timeline": timeline}, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest = build_pack(timeline_path, tmp_path / "pack")

    assert manifest["scene_count"] == len(templates)
    for scene, (_template_id, _variables, marker) in zip(manifest["scenes"], templates):
        html = Path(scene["html"]).read_text(encoding="utf-8")
        assert marker in html
    route_html = Path(manifest["scenes"][0]["html"]).read_text(encoding="utf-8")
    assert route_html.count('class="route-card"') == 7


def test_bgm_policy_raises_chapters_and_recaps_without_flat_full_video_level():
    expression = bgm_volume_filter([(10, 13), (40, 42)], [(90, 100)])

    assert "between(t,10.000,13.000)" in expression
    assert "between(t,90.000,100.000)" in expression
    assert "0.120" in expression
    assert "0.105" in expression
    assert "0.075" in expression


def test_timeline_preserves_storyboard_title_and_aspect(tmp_path):
    article = tmp_path / "article.html"
    article.write_text("<p>商业模式决定估值。</p>", encoding="utf-8")
    router = {
        "schema_version": "test.router.v1",
        "part_router": {
            "article_title": {"primary": "frame-liquid-bg-hero", "candidates": [{"reason": "title"}]},
            "opening_hook": {"primary": "frame-glitch-title", "candidates": [{"reason": "hook"}]},
            "overall_outline": {"primary": "frame-flowchart-sticky", "candidates": [{"reason": "outline"}]},
            "chapter_divider": {"primary": "frame-light-leak-cinema", "candidates": [{"reason": "chapter"}]},
            "closing_outro": {"primary": "frame-logo-outro", "candidates": [{"reason": "outro"}]},
            "brand_mark": {"primary": "frame-logo-outro", "candidates": [{"reason": "brand"}]},
        },
    }
    storyboard = {
        "schema_version": "dasheng.explainer_storyboard.v1",
        "title": "横版测试",
        "aspect": "16:9",
        "scenes": [
            {"id": "scene_001", "type": "hook", "title": "横版测试", "narration": "开头"},
            {"id": "scene_002", "type": "section", "title": "第一章", "narration": "商业模式决定估值。"},
            {"id": "scene_003", "type": "outro", "title": "结论", "narration": "结束"},
        ],
    }

    timeline = build_timeline(storyboard, router, article)

    assert timeline["title"] == "横版测试"
    assert timeline["aspect"] == "16:9"
