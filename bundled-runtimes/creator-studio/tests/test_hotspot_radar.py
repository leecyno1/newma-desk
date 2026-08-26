import json
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "scripts"))

from intake_collectors import CollectedItem, CollectorRun
from hotspot_radar import build_hotspot_radar_result, collect_hotspot_radar


def make_run(task_name, items):
    run = CollectorRun()
    run.add_task(task_name, items, {"status": "ready", "sources": {task_name: {"status": "ready", "total": len(items)}}})
    return run


def test_hotspot_radar_preserves_dynamic_items_and_scores_macro_higher():
    public_news = make_run(
        "public_news",
        [
            CollectedItem(
                source="public_news/wallstreetcn-quick",
                channel="public_news",
                title="央行释放降息信号，国债收益率下行",
                url="https://example.com/macro",
                author_name="华尔街见闻",
                summary="宏观政策与利率预期",
                score=72,
                raw={"category": "macro"},
            ),
            CollectedItem(
                source="public_news/10jqka-stock",
                channel="public_news",
                title="新能源车企发布新车型，渠道反馈升温",
                url="https://example.com/auto",
                author_name="同花顺",
                summary="产业新闻",
                score=60,
                raw={"category": "industry"},
            ),
        ],
    )
    public_hot = make_run(
        "public_hot",
        [
            CollectedItem(
                source="public/weibo_hot",
                channel="public_hot",
                title="明星婚礼现场",
                url="https://example.com/ent",
                author_name="微博热搜",
                summary="动态热点",
                score=900000,
            )
        ],
    )

    result = build_hotspot_radar_result(public_news, public_hot)

    titles = [item["title"] for item in result["items"]]
    assert "明星婚礼现场" in titles
    macro = next(item for item in result["items"] if item["url"] == "https://example.com/macro")
    entertainment = next(item for item in result["items"] if item["url"] == "https://example.com/ent")
    assert macro["radar"]["macro_policy_score"] > entertainment["radar"]["macro_policy_score"]
    assert result["summary"]["total_items"] == 3
    assert result["summary"]["capture_role"] == "hotspot_capture"


def test_collect_hotspot_radar_writes_independent_artifact(monkeypatch, tmp_path):
    public_news = make_run(
        "public_news",
        [CollectedItem(source="public_news/bloomberg-markets", channel="public_news", title="Fed signals policy shift", url="https://example.com/fed", author_name="彭博市场")],
    )
    public_hot = make_run(
        "public_hot",
        [CollectedItem(source="public/hn_frontpage", channel="public_hot", title="AI agents trend", url="https://example.com/ai", author_name="HN")],
    )
    monkeypatch.setattr("hotspot_radar.collect_public_news_fallback", lambda raw_dir: public_news)
    monkeypatch.setattr("hotspot_radar.collect_public_fallback", lambda raw_dir: public_hot)

    run = collect_hotspot_radar(tmp_path)

    artifact = tmp_path / "hotspot_radar.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert run.status["hotspot_radar"]["status"] == "ready"
    assert run.status["hotspot_radar"]["total"] == 2
    assert "raw/hotspot_radar.json" in run.artifacts
    assert payload["summary"]["total_items"] == 2
    assert payload["sources"]["public_news"]["status"] == "ready"
    task_payload = run.tasks["public_news"][0].to_payload()
    assert task_payload["radar"]["source_role"] == "global_market_wire"
    assert task_payload["radar"]["macro_policy_score"] > 0
