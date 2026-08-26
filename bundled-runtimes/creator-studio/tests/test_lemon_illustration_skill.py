import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "dasheng-lemon-illustrations"
sys.path.insert(0, str(ROOT / "scripts"))

from build_stage3_draft import detect_lemon_illustration_intents, resolve_asset_specs
from build_stage4_transwrite import build_illustration_contract


def test_lemon_illustration_skill_is_project_local_and_registered():
    assert (SKILL_ROOT / "SKILL.md").exists()
    assert (SKILL_ROOT / "config.json").exists()
    assert (SKILL_ROOT / "references" / "lemon-ip.md").exists()
    assert (SKILL_ROOT / "references" / "metaphor-routing.md").exists()
    assert (SKILL_ROOT / "references" / "prompt-template.md").exists()
    assert (SKILL_ROOT / "references" / "qa-checklist.md").exists()

    registry = json.loads(
        (ROOT / "configs" / "video" / "upstream_video_skills.json").read_text(
            encoding="utf-8"
        )
    )
    entry = next(
        repo
        for repo in registry["repositories"]
        if repo["name"] == "ian-xiaohei-illustrations"
    )
    assert entry["license"] == "MIT"
    assert entry["default_external_path"].startswith(
        "${IAN_XIAOHEI_ILLUSTRATIONS_ROOT"
    )
    assert entry["recommended_status"] == "external_upstream_with_local_adapter"


def test_prompt_defaults_to_lemon_person_and_desktop_outputs():
    prompt = (SKILL_ROOT / "references" / "prompt-template.md").read_text(
        encoding="utf-8"
    )
    config = json.loads((SKILL_ROOT / "config.json").read_text(encoding="utf-8"))

    assert "柠檬人" in prompt
    assert "小黑" not in prompt
    assert "#ff00ff" in prompt.lower()
    assert config["character"]["name"] == "柠檬人"
    assert config["output_policy"]["required_root"] == "~/Desktop/自媒体创作"
    assert config["upstream"]["vendor_into_repo"] is False


def test_video_lanes_use_lemon_only_for_conceptual_scenes():
    files = [
        ROOT / "skills" / "dasheng-video-director" / "SKILL.md",
        ROOT / "skills" / "dasheng-video-talking-head" / "SKILL.md",
        ROOT / "skills" / "dasheng-video-explainer-html" / "SKILL.md",
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in files)

    assert "dasheng-lemon-illustrations" in content
    assert "schematic" in content
    assert "must not replace" in content or "cannot be replaced" in content
    assert "zoom/pan alone" in content


def test_detector_routes_explicit_metaphors_and_examples():
    text = (
        "流动性就像一个蓄水池，水位下降时所有船都会下沉。"
        "举个例子，超级IPO会把旧资产里的资金抽走。"
    )

    intents = detect_lemon_illustration_intents(text)

    assert [intent["trigger_type"] for intent in intents] == ["metaphor", "example"]
    assert all(intent["skill"] == "dasheng-lemon-illustrations" for intent in intents)
    assert all(intent["evidence_authenticity"] == "schematic" for intent in intents)
    assert intents[1]["channel_adaptation"]["wechat_article"]["placement"] == "after_source_paragraph"


def test_required_illustration_intent_keeps_draft_assets_incomplete_until_generated(monkeypatch):
    monkeypatch.setattr(
        "build_stage3_draft.build_finance_chart_specs_with_report",
        lambda requests: {"chart_specs": [], "failures": [], "validation_report": {}},
    )
    card = {"topic_id": "topic-metaphor", "title": "比喻测试"}
    reasoning = {"topic_id": "topic-metaphor", "claims": []}
    draft = "市场就像一辆下坡的车，利率是刹车。"

    pending = resolve_asset_specs(card, reasoning, {}, draft_text=draft)
    intent = pending["illustration_intents"][0]
    completed = resolve_asset_specs(
        card,
        reasoning,
        {
            "topic-metaphor": {
                "illustration_intents": [intent],
                "illustration_specs": [
                    {
                        "intent_id": intent["intent_id"],
                        "src": "data:image/jpeg;base64,AA==",
                        "title": "利率刹车",
                    }
                ],
            }
        },
        draft_text=draft,
    )

    assert pending["illustration_status"] == "pending_agent_generation"
    assert "illustration_specs" in pending["asset_missing"]
    assert completed["illustration_status"] == "complete"
    assert completed["asset_status"] == "complete"


def test_transwrite_copies_shared_illustration_contract(tmp_path):
    topic = {
        "topic_id": "topic-shared",
        "illustration_intents": [
            {
                "intent_id": "lemon-illustration-01",
                "trigger_type": "example",
                "source_text": "举个例子，资金像水一样流动。",
                "required": True,
            }
        ],
        "illustration_specs": [],
    }

    contract = build_illustration_contract(topic, tmp_path / "wechat_article")

    assert contract["status"] == "pending_agent_generation"
    assert contract["unresolved"][0]["intent_id"] == "lemon-illustration-01"
    assert Path(contract["file"]).exists()
    assert contract["output_dir"].endswith("wechat_article/lemon_illustrations")
