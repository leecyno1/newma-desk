import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_claim_evidence_ledger import (
    apply_claim_ids_to_scene_plan,
    audit_claim_ledger,
    build_claim_ledger,
    build_review_html,
    build_spoken_revision_html,
    build_spoken_revision_sheet,
)


def scene(
    scene_id: str,
    start: float,
    title: str,
    *,
    relation: str | None = None,
    asset_id: str | None = None,
    source_locator: dict | None = None,
) -> dict:
    item = {
        "id": scene_id,
        "title": title,
        "narration": title,
        "start_sec": start,
        "end_sec": start + 3,
        "duration_sec": 3,
        "beat_class": "claim",
    }
    if relation:
        item["evidence_binding"] = {
            "claim_id": scene_id,
            "claim_text": title,
            "relation": relation,
            "source_locator": source_locator,
            "confidence": "high" if relation == "direct" else "low",
        }
    if asset_id:
        item["evidence_asset_ids"] = [asset_id]
        item["evidence_authenticity"] = "real_data" if relation == "direct" else "user_claim_card"
    return item


def claim_spec(*claims: dict) -> dict:
    return {
        "schema_version": "dasheng.video.claim_spec.v1",
        "target_claim_range": {"minimum": 1, "maximum": 12},
        "claims": list(claims),
    }


def test_builder_groups_micro_scenes_and_marks_directly_proven_claim():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "腾讯回购规模上升",
                relation="direct",
                asset_id="tencent-buyback-table",
                source_locator={"kind": "annual_report_table", "page": 64, "row": "share repurchases"},
            ),
            scene("s2", 3, "管理层用真金白银表达态度"),
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_buyback",
            "title": "腾讯回购提供估值信号",
            "claim_text": "腾讯持续回购，构成管理层认为估值具有吸引力的可观察信号。",
            "claim_type": "fact",
            "scene_ids": ["s1", "s2"],
            "evidence_requirements": ["腾讯官方回购数量或金额"],
        }
    )

    ledger = build_claim_ledger(plan, spec, source_scene_plan="/tmp/scene-plan.json")

    assert ledger["claims"][0]["scene_ids"] == ["s1", "s2"]
    assert ledger["claims"][0]["evidence_status"] == "directly_proven"
    assert ledger["claims"][0]["evidence_items"][0]["asset_id"] == "tencent-buyback-table"
    assert ledger["claims"][0]["time_range"] == {"start_sec": 0.0, "end_sec": 6.0}
    assert audit_claim_ledger(ledger, plan)["status"] == "pass"


def test_context_evidence_does_not_prove_a_valuation_comparison():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "腾讯估值低于Meta",
                relation="context",
                asset_id="price-chart",
                source_locator={"kind": "price_series", "window": "6m"},
            )
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_valuation",
            "title": "中美科技估值折价",
            "claim_text": "腾讯相对 Meta 存在可比估值折价。",
            "claim_type": "comparison",
            "scene_ids": ["s1"],
            "evidence_requirements": ["同口径 forward PE 与日期"],
        }
    )

    ledger = build_claim_ledger(plan, spec)
    report = audit_claim_ledger(ledger, plan)

    assert ledger["claims"][0]["evidence_status"] == "context_only"
    assert report["status"] == "fail"
    assert "claim_not_directly_proven" in {item["code"] for item in report["failures"]}


def test_all_explicit_evidence_requirements_must_be_satisfied():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "恒生科技包含腾讯等权重股，同时业绩正在改善",
                relation="direct",
                asset_id="hstech-factsheet",
                source_locator={"kind": "factsheet", "page": 1},
            )
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_structure_and_results",
            "title": "指数结构与业绩改善",
            "claim_text": "恒生科技既覆盖核心权重股，其公司业绩也在改善。",
            "claim_type": "fact",
            "scene_ids": ["s1"],
            "evidence_requirements": [
                {
                    "id": "index_structure",
                    "description": "恒生科技官方成分与权重",
                    "required": True,
                    "satisfied_by_asset_ids": ["hstech-factsheet"],
                },
                {
                    "id": "company_results",
                    "description": "权重公司最新业绩表",
                    "required": True,
                    "satisfied_by_asset_ids": ["company-results-table"],
                },
            ],
        }
    )

    ledger = build_claim_ledger(plan, spec)

    assert ledger["claims"][0]["evidence_status"] == "missing_evidence"
    assert ledger["claims"][0]["evidence_requirements"][0]["satisfied"] is True
    assert ledger["claims"][0]["evidence_requirements"][1]["satisfied"] is False


def test_claim_level_evidence_items_can_satisfy_core_claim_without_fake_scene_binding():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [scene("s1", 0, "腾讯相对Meta存在估值折价")],
    }
    spec = claim_spec(
        {
            "id": "claim_valuation",
            "title": "估值折价",
            "claim_text": "腾讯相对 Meta 存在估值折价。",
            "claim_type": "comparison",
            "scene_ids": ["s1"],
            "evidence_requirements": [
                {
                    "id": "same_date_pe",
                    "description": "同日同口径 PE",
                    "required": True,
                    "satisfied_by_asset_ids": ["valuation-table"],
                }
            ],
            "evidence_items": [
                {
                    "asset_id": "valuation-table",
                    "relation": "direct",
                    "authenticity": "real_data",
                    "source_locator": {"kind": "dataset", "rows": ["0700.HK", "META"]},
                    "confidence": "medium",
                    "claim_text": "同一抓取时间的 forward PE 对比",
                }
            ],
        }
    )

    ledger = build_claim_ledger(plan, spec)

    assert ledger["claims"][0]["evidence_status"] == "directly_proven"
    assert ledger["claims"][0]["evidence_items"][0]["scene_id"] is None
    assert audit_claim_ledger(ledger, plan)["status"] == "pass"


def test_direct_evidence_that_contradicts_the_claim_cannot_pass_the_gate():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [scene("s1", 0, "资金已经从美韩轮动到港股")],
    }
    spec = claim_spec(
        {
            "id": "claim_rotation",
            "title": "资金轮动",
            "claim_text": "资金已经从美韩轮动到港股。",
            "claim_type": "causal",
            "scene_ids": ["s1"],
            "evidence_requirements": [
                {
                    "id": "relative_return",
                    "description": "跨市场相对表现",
                    "required": True,
                    "satisfied_by_asset_ids": ["cross-market-chart"],
                }
            ],
            "evidence_items": [
                {
                    "asset_id": "cross-market-chart",
                    "relation": "direct",
                    "authenticity": "real_data",
                    "verdict": "contradicts",
                    "source_locator": {"kind": "dataset"},
                }
            ],
        }
    )

    ledger = build_claim_ledger(plan, spec)
    report = audit_claim_ledger(ledger, plan)

    assert ledger["claims"][0]["evidence_status"] == "missing_evidence"
    assert "claim_evidence_contradicts" in {item["code"] for item in report["failures"]}


def test_context_material_does_not_change_a_disclosed_rumor_into_a_fact():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "市场传闻微信将集成AI Agent",
                relation="context",
                asset_id="tencent-homepage",
                source_locator={"kind": "company_homepage"},
            )
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_wechat_rumor",
            "title": "微信 AI Agent 传闻",
            "claim_text": "市场传闻微信可能集成 AI Agent。",
            "claim_type": "rumor",
            "scene_ids": ["s1"],
            "disclosure_label": "市场传闻，尚无官方确认",
        }
    )

    ledger = build_claim_ledger(plan, spec)

    assert ledger["claims"][0]["evidence_status"] == "assumption"
    assert audit_claim_ledger(ledger, plan)["status"] == "pass"


def test_assumption_requires_an_explicit_on_screen_disclosure():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [scene("s1", 0, "假设微信AI每月收费100元")],
    }
    unsafe_spec = claim_spec(
        {
            "id": "claim_wechat_arpu",
            "title": "微信 AI 收费情景",
            "claim_text": "按每月100元和50%渗透率测算潜在收入。",
            "claim_type": "assumption",
            "scene_ids": ["s1"],
            "evidence_requirements": ["明确标注为作者情景测算"],
        }
    )
    safe_spec = claim_spec(
        {
            **unsafe_spec["claims"][0],
            "disclosure_label": "作者情景测算，非公司指引",
        }
    )

    unsafe_report = audit_claim_ledger(build_claim_ledger(plan, unsafe_spec), plan)
    safe_ledger = build_claim_ledger(plan, safe_spec)
    safe_report = audit_claim_ledger(safe_ledger, plan)

    assert "speculative_claim_missing_disclosure" in {item["code"] for item in unsafe_report["failures"]}
    assert safe_ledger["claims"][0]["evidence_status"] == "assumption"
    assert safe_report["status"] == "pass"


def test_gate_rejects_unassigned_or_multiply_assigned_scenes():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [scene("s1", 0, "第一句"), scene("s2", 3, "第二句")],
    }
    spec = claim_spec(
        {
            "id": "claim_a",
            "title": "A",
            "claim_text": "A",
            "claim_type": "opinion",
            "scene_ids": ["s1"],
            "disclosure_label": "作者观点",
        },
        {
            "id": "claim_b",
            "title": "B",
            "claim_text": "B",
            "claim_type": "opinion",
            "scene_ids": ["s1"],
            "disclosure_label": "作者观点",
        },
    )

    ledger = build_claim_ledger(plan, spec)
    report = audit_claim_ledger(ledger, plan)
    codes = {item["code"] for item in report["failures"]}

    assert "scene_claim_assignment_overlap" in codes
    assert "scene_claim_assignment_missing" in codes


def test_apply_claim_ids_and_review_html_make_the_ledger_a_reviewable_contract():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [scene("s1", 0, "港股科技估值便宜")],
    }
    spec = claim_spec(
        {
            "id": "claim_valuation",
            "title": "估值折价",
            "claim_text": "港股科技存在估值折价。",
            "claim_type": "comparison",
            "scene_ids": ["s1"],
        }
    )
    ledger = build_claim_ledger(plan, spec)

    enriched = apply_claim_ids_to_scene_plan(plan, ledger)
    review = build_review_html(ledger, plan)

    assert enriched["scenes"][0]["core_claim_id"] == "claim_valuation"
    assert enriched["claim_evidence_ledger"]["schema_version"] == "dasheng.video.claim_evidence_ledger.v1"
    assert "估值折价" in review
    assert "status context_only" not in review
    assert "missing_evidence" in review


def test_apply_claim_ids_rebinds_scene_evidence_to_core_claim_without_losing_traceability():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "腾讯回购金额",
                relation="direct",
                asset_id="buyback-table",
                source_locator={"kind": "company_filing", "page": 3},
            )
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_buyback",
            "title": "腾讯回购",
            "claim_text": "腾讯持续回购。",
            "claim_type": "fact",
            "scene_ids": ["s1"],
        }
    )

    enriched = apply_claim_ids_to_scene_plan(plan, build_claim_ledger(plan, spec))
    binding = enriched["scenes"][0]["evidence_binding"]

    assert binding["claim_id"] == "claim_buyback"
    assert binding["micro_claim_id"] == "s1"


def test_pending_spoken_revision_blocks_render_even_when_evidence_is_complete():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [
            scene(
                "s1",
                0,
                "美国和韩国开始崩盘",
                relation="direct",
                asset_id="cross-market-chart",
                source_locator={"kind": "dataset"},
            )
        ],
    }
    spec = claim_spec(
        {
            "id": "claim_rotation",
            "title": "跨市场波动",
            "claim_text": "美韩科技资产波动加大。",
            "claim_type": "fact",
            "scene_ids": ["s1"],
            "evidence_requirements": ["跨市场行情"],
            "spoken_revision_requirements": [
                {
                    "scene_id": "s1",
                    "action": "replace",
                    "replacement_text": "美韩科技资产估值偏高、波动加大",
                    "reason": "真实行情不支持崩盘表述。",
                }
            ],
        }
    )

    ledger = build_claim_ledger(plan, spec)
    report = audit_claim_ledger(ledger, plan)

    assert ledger["claims"][0]["spoken_revision_requirements"][0]["applied"] is False
    assert "spoken_revision_pending" in {item["code"] for item in report["failures"]}


def test_narration_override_satisfies_replace_revision():
    revised_scene = scene(
        "s1",
        0,
        "美国和韩国开始崩盘",
        relation="direct",
        asset_id="cross-market-chart",
        source_locator={"kind": "dataset"},
    )
    revised_scene["narration_override"] = "美韩科技资产估值偏高、波动加大"
    revised_scene["spoken_revision_approved"] = True
    plan = {"schema_version": "dasheng.video.scene_plan.v1", "lane": "talking_head_video", "scenes": [revised_scene]}
    spec = claim_spec(
        {
            "id": "claim_rotation",
            "title": "跨市场波动",
            "claim_text": "美韩科技资产波动加大。",
            "claim_type": "fact",
            "scene_ids": ["s1"],
            "evidence_requirements": ["跨市场行情"],
            "spoken_revision_requirements": [{"scene_id": "s1", "action": "replace"}],
        }
    )

    ledger = build_claim_ledger(plan, spec)
    report = audit_claim_ledger(ledger, plan)

    assert ledger["claims"][0]["spoken_revision_requirements"][0]["applied"] is True
    assert "spoken_revision_pending" not in {item["code"] for item in report["failures"]}


def test_unapproved_narration_override_remains_pending():
    revised_scene = scene(
        "s1",
        0,
        "美国和韩国开始崩盘",
        relation="direct",
        asset_id="cross-market-chart",
        source_locator={"kind": "dataset"},
    )
    revised_scene["narration_override"] = "韩国回撤明显，美国仍在高位"
    plan = {"scenes": [revised_scene]}
    spec = claim_spec(
        {
            "id": "claim_rotation",
            "title": "跨市场波动",
            "claim_text": "韩国回撤，美国仍在高位。",
            "claim_type": "fact",
            "scene_ids": ["s1"],
            "evidence_requirements": ["跨市场行情"],
            "spoken_revision_requirements": [{"scene_id": "s1", "action": "replace"}],
        }
    )

    report = audit_claim_ledger(build_claim_ledger(plan, spec), plan)

    assert "spoken_revision_pending" in {item["code"] for item in report["failures"]}


def test_spoken_revision_sheet_exposes_time_original_and_replacement_for_review():
    plan = {"scenes": [scene("s1", 12.5, "美国和韩国开始崩盘")]}
    spec = claim_spec(
        {
            "id": "claim_rotation",
            "title": "跨市场波动",
            "claim_text": "美韩科技资产波动加大。",
            "claim_type": "opinion",
            "scene_ids": ["s1"],
            "disclosure_label": "作者观点",
            "spoken_revision_requirements": [
                {
                    "scene_id": "s1",
                    "action": "replace",
                    "replacement_text": "美韩科技资产仍在高位，但波动风险上升",
                    "reason": "真实行情不支持崩盘。",
                }
            ],
        }
    )

    sheet = build_spoken_revision_sheet(build_claim_ledger(plan, spec), plan)
    review = build_spoken_revision_html(sheet)

    assert sheet["pending_count"] == 1
    assert sheet["rows"][0]["start_sec"] == 12.5
    assert sheet["rows"][0]["original_text"] == "美国和韩国开始崩盘"
    assert "美韩科技资产仍在高位" in review
