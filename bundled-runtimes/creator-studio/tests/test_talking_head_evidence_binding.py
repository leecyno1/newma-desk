import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_talking_head_real_evidence_review import bind_scene_plan, keyword_binding


ASSETS = {
    "chart_tencent_alibaba_xiaomi_6m": {
        "id": "chart_tencent_alibaba_xiaomi_6m",
        "kind": "real_data",
        "title": "腾讯阿里小米走势",
        "path": "/tmp/chart.png",
        "source_url": "https://finance.example/chart",
    },
    "hstech_factsheet_page1": {
        "id": "hstech_factsheet_page1",
        "kind": "source_screenshot",
        "title": "恒生科技 factsheet",
        "path": "/tmp/factsheet.png",
        "source_url": "https://hsi.example/factsheet.pdf",
    },
    "shot_tencent_investors": {
        "id": "shot_tencent_investors",
        "kind": "source_screenshot",
        "title": "腾讯投资者首页",
        "path": "/tmp/tencent.png",
        "source_url": "https://tencent.example/investors",
    },
}


def scene(scene_id: str, title: str) -> dict:
    return {
        "id": scene_id,
        "title": title,
        "narration": title,
        "evidence_refs": [title],
        "speaker_state": "hidden",
        "material_state": "chart_fullscreen",
        "pip_shape": "none",
        "evidence_authenticity": "real_data",
    }


def test_price_chart_is_context_not_direct_evidence_for_pe_claim():
    binding = keyword_binding(scene("valuation", "腾讯14倍，Meta是20多倍"), ASSETS)

    assert binding["asset_ids"] == ["chart_tencent_alibaba_xiaomi_6m"]
    assert binding["evidence_authenticity"] == "user_claim_card"
    assert binding["evidence_binding"]["relation"] == "context"


def test_hstech_factsheet_directly_supports_index_weight_structure():
    binding = keyword_binding(scene("weights", "恒生科技指数主要权重股结构"), ASSETS)

    assert binding["evidence_authenticity"] == "source_screenshot"
    assert binding["evidence_binding"]["relation"] == "direct"
    assert binding["evidence_binding"]["source_locator"]["kind"] == "document_region"


def test_hstech_factsheet_does_not_prove_ipo_risk_has_passed():
    binding = keyword_binding(scene("ipo", "港股大量IPO的风险已经过去"), ASSETS)

    assert binding["asset_ids"] == ["hstech_factsheet_page1"]
    assert binding["evidence_authenticity"] == "user_claim_card"
    assert binding["evidence_binding"]["relation"] == "context"


def test_bind_scene_plan_persists_evidence_contract():
    plan = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "scenes": [scene("weights", "恒生科技指数主要权重股结构")],
    }

    bound, _ = bind_scene_plan(plan, ASSETS)

    assert bound["scenes"][0]["evidence_binding"]["claim_id"] == "weights"
    assert bound["scenes"][0]["evidence_binding"]["relation"] == "direct"
