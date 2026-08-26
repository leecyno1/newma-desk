import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "scripts"))

from run_stage1_intake import build_event_clusters, build_item, ensure_chinese_topic_title, order_brief_clusters_for_handoff, score_selected_items


def test_score_selected_items_boosts_cross_source_news():
    common = {
        "title": "OpenAI据悉正计划将Codex与ChatGPT合并",
        "url": "dasheng-public-news://openai-codex-chatgpt",
        "author": "同花顺",
        "published_at": "2026-06-04T08:00:00+08:00",
        "summary": "OpenAI Codex ChatGPT 合并",
        "decision": "待分流",
        "raw_payload": {"score": 50},
    }
    public_news = build_item(source="public_news/10jqka-stock", channel="public_news", **common)
    local_news = build_item(
        source="local_news/8001",
        channel="local_news",
        **{**common, "url": "https://news.10jqka.com.cn/example.shtml", "author": "同花顺"},
    )

    selected = [public_news, local_news]
    score_selected_items(selected, datetime.fromisoformat("2026-06-04T09:00:00+08:00"))

    assert all(item.raw_heat_signals["cross_source_hits"] == 2 for item in selected)
    assert all(item.raw_heat_signals["cross_channel_hits"] == 2 for item in selected)
    assert all(item.raw_heat_signals["cross_source_norm"] > 0 for item in selected)
    assert all(item.heat_score >= 60 for item in selected)


def test_event_cluster_titles_are_translated_to_chinese(monkeypatch):
    monkeypatch.setattr(
        "run_stage1_intake.translate_english_to_chinese",
        lambda text: "亚洲股市因科技股回调而下跌",
    )
    item = build_item(
        source="public_news/bloomberg-markets",
        channel="public_news",
        title="Asian Stocks Retreat From Record on Tech",
        url="https://example.com/asian-stocks",
        author="彭博市场",
        published_at="2026-06-04T08:00:00+08:00",
        summary="Asian markets wrap",
        decision="待分流",
        raw_payload={"score": 30},
    )
    score_selected_items([item], datetime.fromisoformat("2026-06-04T09:00:00+08:00"))

    clusters = build_event_clusters([item], "2026-06-04T09:00:00+08:00", "test-run")

    assert clusters[0]["cluster_title_candidate"] == "亚洲股市因科技股回调而下跌"
    assert clusters[0]["cluster_title_original"]


def test_machine_topic_labels_are_polished_to_chinese():
    title, original = ensure_chinese_topic_title("AI / AI工具/工作流", ["AI agent workflow"])

    assert title == "人工智能工具与工作流"
    assert original == "AI / AI工具/工作流"


def test_low_signal_english_fragments_use_chinese_fallback():
    title, original = ensure_chinese_topic_title("me / visiting", ["Me visiting this sub"])

    assert title == "海外社区零散讨论"
    assert original == "me / visiting"


def test_event_cluster_titles_prefer_specific_representative_over_generic_label():
    item = build_item(
        source="public_news/bloomberg-markets",
        channel="public_news",
        title="DeepSeek 融资热说明，AI竞争进入资本耐力阶段",
        url="https://example.com/deepseek-fundraising",
        author="彭博市场",
        published_at="2026-06-04T08:00:00+08:00",
        summary="China’s DeepSeek Set to Join AI Fundraising Frenzy",
        decision="待分流",
        raw_payload={"score": 80},
    )
    score_selected_items([item], datetime.fromisoformat("2026-06-04T09:00:00+08:00"))

    clusters = build_event_clusters([item], "2026-06-04T09:00:00+08:00", "test-run")

    assert "DeepSeek" in clusters[0]["cluster_title_candidate"]
    assert clusters[0]["cluster_title_candidate"] != "人工智能工具与工作流"


def test_hotspot_radar_metadata_is_preserved_in_intake_record():
    item = build_item(
        source="public_news/bloomberg-markets",
        channel="public_news",
        title="亚洲货币防线升温，美元压力正在外溢到新兴市场",
        url="https://example.com/asia-currency-defense",
        author="彭博市场",
        published_at="2026-06-04T08:00:00+08:00",
        summary="Asian authorities are ramping up their currency defense.",
        decision="待分流",
        raw_payload={
            "score": 76,
            "radar": {
                "capture_role": "hotspot_capture",
                "source_role": "global_market_wire",
                "macro_policy_score": 0.91,
                "kept_by": "dynamic_capture_no_content_filter",
            },
        },
    )

    record = item.to_record("2026-06-04_090000", 1, "2026-06-04T09:00:00+08:00")

    assert record["radar"]["source_role"] == "global_market_wire"
    assert record["radar"]["macro_policy_score"] == 0.91
    assert record["raw_heat_signals"]["hotspot_macro_policy_score"] == 0.91


def test_intake_record_includes_capture_quality():
    item = build_item(
        source="public_news/bloomberg-markets",
        channel="public_news",
        title="亚洲货币防线升温，美元压力正在外溢到新兴市场",
        url="https://example.com/asia-currency-defense",
        author="彭博市场",
        published_at="2026-06-04T08:00:00+08:00",
        summary="Asian authorities are ramping up their currency defense.",
        decision="待分流",
        raw_payload={"score": 76, "debug_snapshot_path": "raw/bloomberg-markets.xml"},
    )

    record = item.to_record("2026-06-04_090000", 1, "2026-06-04T09:00:00+08:00")

    assert record["capture_quality"]["title_real"] is True
    assert record["capture_quality"]["has_original_url"] is True
    assert record["capture_quality"]["content_length"] > 20
    assert record["capture_quality"]["capture_mode"] == "public_news"
    assert record["capture_quality"]["debug_snapshot_path"] == "raw/bloomberg-markets.xml"


def test_brief_cluster_order_penalizes_same_source_role_crowding():
    clusters = [
        {
            "cluster_id": "global-1",
            "priority_score": 20,
            "hotspot_macro_policy_score": 0.6,
            "authority_score": 1.2,
            "timeliness_score": 1.0,
            "source_diversity": 1,
            "source_mix": {"public_news": 1},
            "hotspot_source_roles": {"global_market_wire": 1},
        },
        {
            "cluster_id": "global-2",
            "priority_score": 19,
            "hotspot_macro_policy_score": 0.6,
            "authority_score": 1.2,
            "timeliness_score": 1.0,
            "source_diversity": 1,
            "source_mix": {"public_news": 1},
            "hotspot_source_roles": {"global_market_wire": 1},
        },
        {
            "cluster_id": "macro-cn",
            "priority_score": 16,
            "hotspot_macro_policy_score": 0.45,
            "authority_score": 1.2,
            "timeliness_score": 1.0,
            "source_diversity": 2,
            "source_mix": {"public_news": 1, "local_chat": 1},
            "hotspot_source_roles": {"macro_finance_wire": 1},
        },
    ]

    ordered = order_brief_clusters_for_handoff(clusters)

    assert ordered[0]["cluster_id"] == "global-1"
    assert ordered[1]["cluster_id"] == "macro-cn"
