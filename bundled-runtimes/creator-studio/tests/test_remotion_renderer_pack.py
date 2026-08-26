import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_remotion_renderer_pack as renderer_pack
from build_remotion_renderer_pack import (
    CANONICAL_FAMILIES,
    assign_renderer_family,
    build_renderer_contract,
    build_showcase_plan,
    route_scene_plan,
    write_renderer_project,
)
from video_renderer_contract_gate import REQUIRED_CONSUMED_FIELDS, audit_renderer_contract


def base_scene(scene_id: str, **overrides) -> dict:
    item = {
        "id": scene_id,
        "title": scene_id,
        "narration": scene_id,
        "start_sec": 0,
        "end_sec": 3,
        "duration_sec": 3,
        "beat_class": "claim",
        "template_id": "legacy-template",
        "speaker_state": "full",
        "material_state": "none",
        "pip_shape": "none",
        "transition_in": "hard_cut",
        "transition_out": "hard_cut",
        "html_animation_behavior": "keyword_reveal",
        "audio": {"duck_bgm": True, "sfx": None},
    }
    item.update(overrides)
    return item


def test_renderer_pack_has_distinct_real_families_and_consumes_director_fields():
    contract = build_renderer_contract()
    signatures = {
        (item["component"], item["variant"], item["motion_signature"])
        for item in contract["templates"].values()
    }

    assert len(CANONICAL_FAMILIES) == 11
    assert len(signatures) == 11
    assert REQUIRED_CONSUMED_FIELDS <= set(contract["consumed_scene_fields"])
    assert contract["audio_architecture"] == {
        "voice": "single_continuous_root_track",
        "scene_video": "muted_visual_only",
        "bgm": "separate_continuous_root_track",
    }


def test_showcase_varies_speaker_composition_instead_of_repeating_one_pip():
    plan = build_showcase_plan()
    compositions = [
        (scene["speaker_state"], scene["material_state"], scene["pip_shape"])
        for scene in plan["scenes"]
    ]

    assert len({item[0] for item in compositions}) >= 5
    assert all(not (compositions[index] == compositions[index + 1] == compositions[index + 2]) for index in range(len(compositions) - 2))


def test_family_router_uses_semantics_instead_of_legacy_template_names():
    assert assign_renderer_family(base_scene("speaker")) == "speaker-anchor"
    assert assign_renderer_family(
        base_scene("chart", material_state="chart_fullscreen", beat_class="evidence_data")
    ) == "data-line-chart"
    assert assign_renderer_family(
        base_scene("valuation", core_claim_id="claim_03_company_valuation_discount", beat_class="evidence_data")
    ) == "valuation-compare"
    assert assign_renderer_family(
        base_scene("document", material_state="document_fullscreen", beat_class="evidence_document")
    ) == "document-exact-crop"
    assert assign_renderer_family(base_scene("recap", beat_class="recap")) == "recap-outro"


def test_routed_scene_plan_passes_renderer_contract_gate_for_all_families():
    scenes = []
    for index, template_id in enumerate(CANONICAL_FAMILIES, start=1):
        scenes.append(
            base_scene(
                f"s{index}",
                start_sec=(index - 1) * 3,
                end_sec=index * 3,
                template_id=template_id,
            )
        )
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": scenes,
    }

    report = audit_renderer_contract(plan, build_renderer_contract())

    assert report["status"] == "pass"
    assert report["metrics"]["implementation_signature_count"] == 11


def test_route_scene_plan_preserves_source_template_and_adds_family():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1", beat_class="recap")],
    }

    routed = route_scene_plan(plan)

    assert routed["scenes"][0]["source_template_id"] == "legacy-template"
    assert routed["scenes"][0]["template_id"] == "recap-outro"
    assert routed["scenes"][0]["renderer_family"] == "recap-outro"


def test_commercial_renderer_uses_dedicated_route_and_vertical_dimensions(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "commercial_promo_video",
        "aspect": "9:16",
        "render_mode": "showcase",
        "allow_placeholders": True,
        "commercial": {"brand_tokens": {"primary_color": "#143CFF"}},
        "scenes": [
            base_scene(
                "cta",
                beat_class="cta",
                preferred_renderer_family="recap-outro",
                safe_area_slots={"cta": "center_action", "subtitle": "bottom_caption"},
            )
        ],
    }

    routed = route_scene_plan(plan)
    result = write_renderer_project(tmp_path / "commercial_renderer", routed)
    payload = json.loads(result["scene_plan"].read_text(encoding="utf-8"))

    assert routed["renderer"] == "dasheng-remotion-commercial-promo.v1"
    assert routed["scenes"][0]["commercial_safe_area_slots"]["cta"] == "center_action"
    assert payload["width"] == 1080
    assert payload["height"] == 1920
    assert routed["scenes"][0]["renderer_family"] == "recap-outro"


def test_vox_route_uses_dedicated_continuous_collage_renderer():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "vox_explainer_video",
        "scenes": [
            base_scene(
                "vox",
                type="evidence_map",
                narrative_function="evidence_map",
                visual={"nodes": ["央行", "ETF", "实物"]},
            )
        ],
    }

    routed = route_scene_plan(plan)
    scene = routed["scenes"][0]

    assert routed["renderer"] == "dasheng-remotion-vox-collage.v2"
    assert scene["renderer_family"] == "vox-editorial-collage"
    assert scene["vox_state"] == "evidence_map"
    assert scene["visual"]["world_id"] == "shared_paper_evidence_world"


def test_vox_route_preserves_timed_subtitles_emphasis_and_entity_labels():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "vox_explainer_video",
        "scenes": [
            base_scene(
                "vox-text",
                type="mechanism_explainer",
                narrative_function="mechanism_explainer",
                subtitle_timing_source="asr-aligned-to-script",
                subtitle_cues=[{"text": "央行开始增持。", "startMs": 120, "endMs": 1320, "timingSource": "asr-aligned-to-script"}],
                emphasis_cues=[{"text": "定价权换手", "startMs": 850, "endMs": 1800, "x": 50, "y": 18}],
                entity_labels=[{"text": "央行", "entityType": "organization", "startMs": 200, "endMs": 2600, "x": 32, "y": 44}],
            )
        ],
    }

    scene = route_scene_plan(plan)["scenes"][0]

    assert scene["captions"][0]["startMs"] == 120
    assert scene["subtitle_timing_source"] == "asr-aligned-to-script"
    assert scene["visual"]["emphasis_cues"][0]["text"] == "定价权换手"
    assert scene["visual"]["entity_labels"][0]["text"] == "央行"


def test_route_scene_plan_hydrates_claim_assets_into_renderer_visuals(tmp_path):
    chart_path = tmp_path / "cross_market.json"
    chart_path.write_text(
        json.dumps(
            {
                "dates": ["2026-07-01", "2026-07-02", "2026-07-03"],
                "provider": "Verified market feed",
                "series": [
                    {"name": "恒生科技", "values": [100, 103, 105]},
                    {"name": "纳斯达克", "values": [100, 101, 102]},
                ],
            }
        ),
        encoding="utf-8",
    )
    valuation_path = tmp_path / "valuation.json"
    valuation_path.write_text(
        json.dumps(
            {
                "provider": "Same-source quote API",
                "metric": "PE (TTM)",
                "rows": [
                    {
                        "company_name": "腾讯",
                        "company_pe_ttm": 15.9,
                        "peer_name": "Meta",
                        "peer_pe_ttm": 24.1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    document_path = tmp_path / "official-page.png"
    document_path.write_bytes(b"image")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            base_scene(
                "chart",
                title="三个市场的相对表现",
                core_claim_id="claim_chart",
                material_state="chart_fullscreen",
            ),
            base_scene(
                "valuation",
                title="腾讯相对 Meta 的 PE 折价",
                core_claim_id="claim_valuation",
                material_state="chart_fullscreen",
            ),
            base_scene(
                "document",
                title="官方回购披露",
                core_claim_id="claim_document",
                material_state="document_fullscreen",
            ),
        ],
    }
    ledger = {
        "claims": [
            {
                "id": "claim_chart",
                "claim_type": "comparison",
                "evidence_items": [
                    {
                        "asset_id": "cross_market",
                        "relation": "direct",
                        "verdict": "supports",
                        "authenticity": "real_data",
                        "source_locator": {"json_path": str(chart_path), "provider": "Verified market feed"},
                    }
                ],
            },
            {
                "id": "claim_valuation",
                "claim_type": "comparison",
                "evidence_items": [
                    {
                        "asset_id": "peer_valuation",
                        "relation": "direct",
                        "verdict": "supports",
                        "authenticity": "real_data",
                        "source_locator": {"json_path": str(valuation_path), "provider": "Same-source quote API"},
                    }
                ],
            },
            {
                "id": "claim_document",
                "claim_type": "fact",
                "evidence_items": [
                    {
                        "asset_id": "official_buyback",
                        "relation": "direct",
                        "verdict": "supports",
                        "authenticity": "source_screenshot",
                        "source_locator": {
                            "local_png": str(document_path),
                            "url": "https://example.com/official.pdf",
                            "page": 6,
                        },
                    }
                ],
            },
        ]
    }

    routed = route_scene_plan(plan, claim_ledger=ledger)
    scenes = {scene["id"]: scene for scene in routed["scenes"]}

    assert scenes["chart"]["renderer_family"] == "data-line-chart"
    assert scenes["chart"]["visual"]["series"][0]["name"] == "恒生科技"
    assert scenes["chart"]["visual"]["labels"] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert scenes["valuation"]["renderer_family"] == "valuation-compare"
    assert scenes["valuation"]["visual"]["metrics"][0] == {
        "label": "腾讯",
        "value": 15.9,
        "peer": "Meta",
        "peer_value": 24.1,
    }
    assert scenes["document"]["renderer_family"] == "document-exact-crop"
    assert scenes["document"]["visual"]["document_src"] == str(document_path)
    assert scenes["document"]["visual"]["evidence_relation"] == "direct"


def test_rumor_context_screenshot_routes_to_product_ui_instead_of_fake_document(tmp_path):
    screenshot = tmp_path / "investor-home.png"
    screenshot.write_bytes(b"image")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            base_scene(
                "rumor",
                title="假设微信 AI 自动整理群聊",
                core_claim_id="claim_rumor",
                material_state="document_fullscreen",
                evidence_binding={"relation": "context", "confidence": "low"},
            )
        ],
    }
    ledger = {
        "claims": [
            {
                "id": "claim_rumor",
                "claim_type": "rumor",
                "disclosure_label": "市场传闻 / 功能示意，尚无官方确认",
                "evidence_items": [
                    {
                        "asset_id": "context_home",
                        "relation": "context",
                        "verdict": "neutral",
                        "authenticity": "source_screenshot",
                        "source_locator": {"local_png": str(screenshot), "url": "https://example.com/investors"},
                    }
                ],
            }
        ]
    }

    routed = route_scene_plan(plan, claim_ledger=ledger)
    scene = routed["scenes"][0]

    assert scene["renderer_family"] == "product-ui"
    assert "document_src" not in scene["visual"]
    assert "市场传闻" in scene["visual"]["context"]
    assert scene["visual"]["tasks"] == ["收到用户指令", "假设微信 AI 自动整理群聊", "返回结果（功能示意）"]


def test_claim_level_asset_contract_ignores_stale_scene_chart_binding(tmp_path):
    stale_chart = tmp_path / "stale-chart.json"
    stale_chart.write_text(
        json.dumps({"dates": ["d1", "d2"], "series": [{"name": "旧图", "values": [1, 2]}]}),
        encoding="utf-8",
    )
    official_table = tmp_path / "official-table.json"
    official_table.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "company": "阿里",
                        "facts": [{"metric": "PPU deployment", "display_value": ">100,000", "page": 5}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            base_scene(
                "forecast",
                title="如果芯片量产，估值可能重估",
                core_claim_id="claim_forecast",
                material_state="chart_fullscreen",
                evidence_asset_ids=["stale_chart"],
            )
        ],
    }
    ledger = {
        "claims": [
            {
                "id": "claim_forecast",
                "claim_type": "forecast",
                "disclosure_label": "条件推演",
                "evidence_requirements": [
                    {"satisfied_by_asset_ids": ["official_chip_status"]}
                ],
                "evidence_items": [
                    {
                        "scene_id": "forecast",
                        "asset_id": "stale_chart",
                        "relation": "context",
                        "source_locator": {"json_path": str(stale_chart)},
                    },
                    {
                        "scene_id": None,
                        "asset_id": "official_chip_status",
                        "relation": "context",
                        "source_locator": {"json_path": str(official_table)},
                    },
                ],
            }
        ]
    }

    scene = route_scene_plan(plan, claim_ledger=ledger)["scenes"][0]

    assert scene["renderer_family"] == "logic-flow"
    assert scene["evidence_asset_ids"] == []
    assert "series" not in scene["visual"]


def test_renderer_selects_the_claim_asset_relevant_to_each_scene(tmp_path):
    token_cost = tmp_path / "token-cost.json"
    token_cost.write_text(
        json.dumps(
            {
                "baseline": {"model": "GPT-4", "input_usd_per_1m": 30, "output_usd_per_1m": 60},
                "current_models": [
                    {
                        "model": "DeepSeek-V4-Flash",
                        "input_cache_miss_usd_per_1m": 0.14,
                        "output_usd_per_1m": 0.28,
                        "output_vs_gpt4_pct": 0.47,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        json.dumps(
            {
                "models": [
                    {"model": "DeepSeek V4 Flash", "score": 37},
                    {"model": "Hy3-preview", "score": 34},
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            base_scene(
                "cost",
                title="Token 成本已经进入 1% 量级",
                core_claim_id="claim_models",
                beat_class="evidence_data",
                material_state="chart_fullscreen",
            ),
            base_scene(
                "score",
                title="Hy3 和 V4 Flash 的评分接近",
                core_claim_id="claim_models",
                beat_class="evidence_data",
                material_state="chart_fullscreen",
            ),
        ],
    }
    ledger = {
        "claims": [
            {
                "id": "claim_models",
                "claim_type": "causal",
                "evidence_items": [
                    {
                        "asset_id": "model_token_cost_history_table",
                        "relation": "direct",
                        "verdict": "supports",
                        "authenticity": "real_data",
                        "source_locator": {"json_path": str(token_cost)},
                    },
                    {
                        "asset_id": "hunyuan_model_benchmark_table",
                        "relation": "direct",
                        "verdict": "supports",
                        "authenticity": "source_screenshot",
                        "source_locator": {"json_path": str(benchmark)},
                    },
                ],
            }
        ]
    }

    scenes = {scene["id"]: scene for scene in route_scene_plan(plan, claim_ledger=ledger)["scenes"]}

    assert scenes["cost"]["visual"]["asset_id"] == "model_token_cost_history_table"
    assert scenes["score"]["visual"]["asset_id"] == "hunyuan_model_benchmark_table"


def test_project_writer_emits_distinct_tsx_components_without_forbidden_shortcuts(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "aspect": "16:9",
        "scenes": [base_scene("s1")],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    family_source = (result["project_dir"] / "src" / "families" / "index.tsx").read_text(encoding="utf-8")
    video_source = (result["project_dir"] / "src" / "DirectorVideo.tsx").read_text(encoding="utf-8")
    combined = (family_source + video_source).lower()

    for component in [item["component"] for item in CANONICAL_FAMILIES.values()]:
        assert component in family_source
    for field in REQUIRED_CONSUMED_FIELDS:
        assert field in video_source or field in family_source
    assert "zoompan" not in combined
    assert "scanline" not in combined
    assert "yellow" not in combined
    assert "const pipSafeRight" in family_source
    assert "商业航天估值" in family_source
    assert result["renderer_contract"].exists()
    assert result["scene_plan"].exists()


def test_renderer_keeps_nonoverlapping_scene_transitions_visually_opaque(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1", transition_in="cross_dissolve", transition_out="cross_dissolve")],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    video_source = (result["project_dir"] / "src" / "DirectorVideo.tsx").read_text(encoding="utf-8")

    assert "exitOpacity" not in video_source
    assert "enterOpacity * exitOpacity" not in video_source
    assert "transition_in === 'cross_dissolve'" in video_source
    assert "const clipPath = 'inset(0%)'" in video_source


def test_renderer_passes_semantic_motion_behavior_instead_of_hash_seed(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1", html_animation_behavior="axis_draw_series_trace_endpoint_annotation")],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    video_source = (result["project_dir"] / "src" / "DirectorVideo.tsx").read_text(encoding="utf-8")
    family_source = (result["project_dir"] / "src" / "families" / "index.tsx").read_text(encoding="utf-8")
    combined = video_source + family_source

    assert "motionBehavior={html_animation_behavior}" in video_source
    assert "motionStage" in family_source
    assert "behaviorSeed" not in combined


def test_family_renderer_keeps_scene_start_readable_and_adds_late_semantic_cues(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1")],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    family_source = (result["project_dir"] / "src" / "families" / "index.tsx").read_text(encoding="utf-8")

    assert "const titleProgress = 0.55 +" in family_source
    for cue in [
        "chartLateCue",
        "valuationLateCue",
        "documentLateCue",
        "logicLateCue",
        "productLateCue",
        "splitLateCue",
    ]:
        assert cue in family_source


def test_chart_renderer_uses_one_shared_scale_and_sparse_date_labels(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1")],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    family_source = (result["project_dir"] / "src" / "families" / "index.tsx").read_text(encoding="utf-8")

    assert "const allChartValues = series.flatMap" in family_source
    assert "chartPoints(item.values, 1300, 470, chartMin, chartMax)" in family_source
    assert "const labelTickIndexes" in family_source


def test_production_asset_gate_rejects_placeholder_document_and_broll():
    assert hasattr(renderer_pack, "audit_renderer_assets")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "document",
                template_id="document-exact-crop",
                material_state="document_fullscreen",
                visual={"source": "https://example.com/report"},
            ),
            base_scene(
                "broll",
                start_sec=3,
                end_sec=6,
                template_id="broll-fullscreen",
                material_state="broll_fullscreen",
                visual={"context": "factory"},
            ),
        ],
    }

    report = renderer_pack.audit_renderer_assets(route_scene_plan(plan))

    assert report["status"] == "fail"
    assert {item["code"] for item in report["failures"]} == {
        "document_asset_missing",
        "broll_asset_missing",
    }


def test_production_asset_gate_rejects_context_screenshot_as_document_proof(tmp_path):
    document = tmp_path / "context.png"
    document.write_bytes(b"image")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "document",
                template_id="document-exact-crop",
                material_state="document_fullscreen",
                visual={
                    "document_src": str(document),
                    "source": "https://example.com/investors",
                    "evidence_relation": "context",
                },
            )
        ],
    }

    report = renderer_pack.audit_renderer_assets(route_scene_plan(plan))

    assert report["status"] == "fail"
    assert {item["code"] for item in report["failures"]} == {"document_evidence_not_direct"}


def test_showcase_mode_explicitly_allows_placeholder_visuals():
    assert hasattr(renderer_pack, "audit_renderer_assets")
    report = renderer_pack.audit_renderer_assets(build_showcase_plan())

    assert report["status"] == "pass"
    assert report["allow_placeholders"] is True


def test_production_asset_gate_blocks_failed_claim_evidence_gate():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "production",
        "claim_evidence_gate_status": "fail",
        "pending_spoken_revision_count": 2,
        "scenes": [base_scene("speaker")],
    }

    report = renderer_pack.audit_renderer_assets(route_scene_plan(plan))

    assert report["status"] == "fail"
    assert {item["code"] for item in report["failures"]} == {"claim_evidence_gate_failed"}


def test_review_mode_allows_failed_claim_gate_but_keeps_warning():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "review",
        "claim_evidence_gate_status": "fail",
        "pending_spoken_revision_count": 2,
        "scenes": [base_scene("speaker")],
    }

    report = renderer_pack.audit_renderer_assets(route_scene_plan(plan))

    assert report["status"] == "pass"
    assert {item["code"] for item in report["warnings"]} == {"claim_evidence_gate_pending_review"}


def test_project_writer_links_scene_media_and_emits_asset_gate(tmp_path):
    document = tmp_path / "report.png"
    document.write_bytes(b"image")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "document",
                template_id="document-exact-crop",
                material_state="document_fullscreen",
                visual={
                    "document_src": str(document),
                    "source": "https://example.com/report",
                    "document_title": "Official report",
                },
            )
        ],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    payload = json.loads(result["scene_plan"].read_text(encoding="utf-8"))
    linked = result["project_dir"] / "public" / payload["scenes"][0]["visual"]["document_src"]

    assert linked.samefile(document)
    assert result["asset_gate"].exists()
    assert json.loads(result["asset_gate"].read_text(encoding="utf-8"))["status"] == "pass"


def test_vox_layered_scene_gate_and_recursive_asset_linking(tmp_path):
    cutout = tmp_path / "gold-bars.png"
    cutout.write_bytes(b"image")
    layers = [
        {
            "id": f"layer_{index}",
            "asset_type": "image" if index == 0 else "paper",
            "src": str(cutout) if index == 0 else None,
            "depth": index * 40,
            "entry_path": [
                {"at": 0, "x": -80 + index, "y": 40, "z": -30, "rotation": -4, "scale": 0.8, "opacity": 0},
                {"at": 0.3, "x": 0, "y": 0, "z": 0, "rotation": 0, "scale": 1, "opacity": 1},
            ],
        }
        for index in range(8)
    ]
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "vox_explainer_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "vox",
                speaker_state="hidden",
                visual={
                    "scene_layers": layers,
                    "camera_keyframes": [{"at": 0, "z": 0}, {"at": 1, "z": 280}],
                },
            )
        ],
    }

    routed = route_scene_plan(plan)
    report = renderer_pack.audit_renderer_assets(routed)
    assert report["status"] == "pass"

    result = write_renderer_project(tmp_path / "renderer", routed)
    payload = json.loads(result["scene_plan"].read_text(encoding="utf-8"))
    linked_src = payload["scenes"][0]["visual"]["scene_layers"][0]["src"]
    assert linked_src.startswith("assets/scenes/001_vox/layers/")
    assert (result["project_dir"] / "public" / linked_src).samefile(cutout)


def test_vox_layered_scene_gate_rejects_flat_whole_image_motion(tmp_path):
    still = tmp_path / "whole-frame.png"
    still.write_bytes(b"image")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "vox_explainer_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "vox",
                speaker_state="hidden",
                visual={
                    "scene_layers": [{"id": "whole", "asset_type": "image", "src": str(still)}],
                    "camera_keyframes": [{"at": 0, "z": 0}, {"at": 1, "z": 40}],
                },
            )
        ],
    }

    report = renderer_pack.audit_renderer_assets(route_scene_plan(plan))
    codes = {item["code"] for item in report["failures"]}
    assert "vox_independent_layer_count_low" in codes
    assert "vox_motion_vocabulary_low" in codes


def test_project_writer_blocks_production_placeholders(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "render_mode": "production",
        "scenes": [
            base_scene(
                "document",
                template_id="document-exact-crop",
                material_state="document_fullscreen",
            )
        ],
    }

    with pytest.raises(ValueError, match="production renderer assets are incomplete"):
        write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))


def test_project_writer_links_large_media_into_public_assets(tmp_path):
    source_video = tmp_path / "roughcut.mp4"
    bgm = tmp_path / "bgm.wav"
    source_video.write_bytes(b"video")
    bgm.write_bytes(b"audio")
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [base_scene("s1")],
    }

    result = write_renderer_project(
        tmp_path / "renderer",
        route_scene_plan(plan),
        source_video=str(source_video),
        bgm_src=str(bgm),
    )
    payload = __import__("json").loads(result["scene_plan"].read_text(encoding="utf-8"))

    assert payload["source_video"] == "assets/source_video.mp4"
    assert payload["bgm_src"] == "assets/bgm.wav"
    assert (result["project_dir"] / "public" / payload["source_video"]).samefile(source_video)
    assert (result["project_dir"] / "public" / payload["bgm_src"]).samefile(bgm)


def test_director_keeps_one_continuous_voice_track_and_mutes_scene_video(tmp_path):
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            base_scene("s1", start_sec=0, end_sec=2, duration_sec=2, speaker_state="full"),
            base_scene("s2", start_sec=2, end_sec=4, duration_sec=2, speaker_state="hidden"),
        ],
    }

    result = write_renderer_project(tmp_path / "renderer", route_scene_plan(plan))
    video_source = (result["project_dir"] / "src" / "DirectorVideo.tsx").read_text(encoding="utf-8")
    speaker_layer = video_source.split("const SpeakerLayer", 1)[1].split("const SceneClip", 1)[0]

    assert "const MasterVoiceTrack" in video_source
    assert "<Audio src={staticFile(sourceVideo)} volume={voiceGain} />" in video_source
    assert "{source_video ? <MasterVoiceTrack sourceVideo={source_video} voiceGain={voice_gain} /> : null}" in video_source
    assert "muted" in speaker_layer
    assert "volume={1}" not in speaker_layer
    assert "scene.speaker_state.includes('pip') ? 3 : 1" in speaker_layer
