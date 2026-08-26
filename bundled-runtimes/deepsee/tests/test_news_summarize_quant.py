import os
import sys
import json
import threading


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_news_summarize_appends_quant(monkeypatch):
    from app.routers import news as news_router
    from app.services import llm_client
    from app.services import news_client

    # Avoid network: provide a single normalized news item within 72h.
    now_ms = 1_760_000_000_000
    fake_items = [
        {
            "id": "n1",
            "source_name": "X",
            "source_id": "x",
            "title": "黄金大涨",
            "url": "https://example.com",
            "pub_ts": now_ms,
        }
    ]

    monkeypatch.setattr(news_router, "direct_from_sources_json", lambda limit=50, q=None: {"items": fake_items})
    monkeypatch.setattr(news_router, "normalize_items", lambda raw, **kwargs: {"items": fake_items})
    monkeypatch.setattr(news_client, "_load_source_whitelist", lambda: [])

    def fake_chat(messages, temperature=0.3, model_override=None, force_json=False, **kwargs):
        return json.dumps(
            {
                "markdown": "# 新闻舆情监测\n- 总体基调：测试 #n1\n",
                "quant": {"topics": [{"topic": "黄金", "bullish_ids": ["n1"], "bearish_ids": [], "neutral_ids": []}]},
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(llm_client, "siliconflow_chat", fake_chat)

    res = news_router.summarize_news({"limit": 1, "temperature": 0.3})
    assert res["status"] == "ok"
    assert "## 量化分析" in (res.get("markdown") or "")


def test_builtin_news_analysis_builds_lightweight_alpha_hypotheses(monkeypatch):
    from app.services import news_engine

    now_ms = 1_760_000_000_000
    monkeypatch.setattr(news_engine.time, "time", lambda: now_ms / 1000)
    items = [
        {
            "id": "ai-1",
            "source_id": "wallstreetcn-quick",
            "source_name": "华尔街见闻",
            "title": "云厂商上调 AI 算力资本开支，光模块订单增长",
            "summary": "多家云厂商继续增加数据中心投资。",
            "pub_ts": now_ms - 30 * 60 * 1000,
            "heat_score": 86,
            "derived": {"tone": "positive", "category": "technology"},
        },
        {
            "id": "ai-2",
            "source_id": "stcn",
            "source_name": "证券时报",
            "title": "AI 服务器需求增长，先进制程芯片供给仍偏紧",
            "summary": "产业链订单能见度提升。",
            "pub_ts": now_ms - 90 * 60 * 1000,
            "heat_score": 74,
            "derived": {"tone": "positive", "category": "technology"},
        },
    ]

    analysis = news_engine.analyze_news(items)

    assert analysis["analysis_framework"] == "serenity-alpha-lite"
    assert analysis["alpha_hypotheses"]
    hypothesis = analysis["alpha_hypotheses"][0]
    assert hypothesis["theme"] == "AI 算力与半导体"
    assert hypothesis["direction"] == "positive"
    assert hypothesis["event"] == items[0]["title"]
    assert hypothesis["transmission"]["demand_supply"]
    assert hypothesis["transmission"]["earnings"]
    assert hypothesis["transmission"]["pricing"]
    assert hypothesis["beneficiaries"]
    assert hypothesis["validation_signals"]
    assert hypothesis["falsifiers"]
    assert hypothesis["confidence"] >= 60
    assert hypothesis["evidence_count"] == 2
    assert {row["id"] for row in hypothesis["evidence"]} == {"ai-1", "ai-2"}


def test_news_frontend_renders_alpha_chain():
    html_path = os.path.join(PROJECT_ROOT, "static", "index.html")
    html = open(html_path, encoding="utf-8").read()

    assert 'id="newsAlphaList"' in html
    assert "function renderNewsAlphaHypotheses" in html
    assert "analysis.alpha_hypotheses" in html


def test_builtin_news_remote_sources_are_collected_concurrently(monkeypatch):
    from app.services import news_engine

    sources = tuple(
        news_engine.NewsSource(f"source-{idx}", f"来源{idx}", f"https://example.com/{idx}")
        for idx in range(3)
    )
    barrier = threading.Barrier(len(sources), timeout=2)
    translation_calls = []

    monkeypatch.setattr(news_engine, "NEWS_SOURCES", sources)
    monkeypatch.setattr(news_engine, "_load_local_news_items", lambda **kwargs: ([], {"ok": False}))
    monkeypatch.delenv("NEWS_ONLINE_TRANSLATION_ENABLED", raising=False)
    monkeypatch.setattr(news_engine, "_translate_titles_google", lambda titles: translation_calls.append("google") or {})
    monkeypatch.setattr(news_engine, "_translate_titles_batch", lambda titles: translation_calls.append("llm") or {})

    def fake_fetch(source, timeout=8):
        barrier.wait()
        return [
            {
                "id": source.id,
                "source_id": source.id,
                "source_name": source.name,
                "title": f"{source.name} AI 算力订单增长",
                "url": source.url,
                "pub_ts": 1_760_000_000_000,
                "derived": {"tone": "positive", "category": "technology"},
            }
        ]

    monkeypatch.setattr(news_engine, "_fetch_source", fake_fetch)

    payload = news_engine.collect_news(limit=10, force=True)

    assert payload["total"] == 3
    assert {item["source_id"] for item in payload["items"]} == {source.id for source in sources}
    assert translation_calls == []
