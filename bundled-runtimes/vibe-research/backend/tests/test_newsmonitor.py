from datetime import datetime, timezone

from newsmonitor import build_news_monitor


def _item(title, source, ts, *, summary="", url=""):
    return {
        "title": title,
        "source": source,
        "source_url": f"https://{source.lower().replace(' ', '')}.example/rss",
        "summary": summary,
        "url": url or f"https://example.com/{abs(hash((title, source)))}",
        "time": "08-13 08:00",
        "ts": ts,
    }


def test_monitor_clusters_multi_source_event_and_scores_change():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 10, tzinfo=timezone.utc).timestamp())
    previous = int(datetime(2026, 8, 12, 20, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "semi",
        "name": "半导体 / 芯片",
        "items": [
            _item("HBM4 memory chip validation reaches 9.2Gbps", "Tech Wire", current),
            _item("新思科技完成 HBM4 存储芯片 9.2Gbps 验证", "芯片观察", current - 600),
            _item("HBM4 chip validation enters testing stage", "Research Lab", previous),
        ],
    }]

    result = build_news_monitor(industries, now=now)
    topic = result["topics"][0]

    assert topic["source_count"] == 3
    assert topic["mention_count"] == 3
    assert topic["velocity_state"] == "rising"
    assert topic["heat_velocity_pct"] == 100
    assert topic["spread_level"] in {"多源扩散", "广泛传播"}
    assert topic["attention_level"] in {"留意", "重点"}


def test_monitor_surfaces_reporting_tone_and_explicit_denial_without_claiming_truth():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "consumer",
        "name": "消费电子 / 数码",
        "items": [
            _item("网传品牌将更换供应商，消息尚未证实", "市场快讯", current),
            _item("公司否认更换供应商传闻，称相关内容不实", "Company News", current - 300),
        ],
    }]

    result = build_news_monitor(industries, now=now)
    topic = result["topics"][0]

    assert topic["verification_status"] == "存在争议"
    assert "未确认" in topic["verification_label"]
    assert "否认" in topic["verification_label"]
    assert topic["signal"] == "watch"
    assert "不判定真伪" in result["caveat"]


def test_monitor_keeps_unrelated_single_source_stories_separate():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "ai",
        "name": "AI / 大模型",
        "items": [
            _item("OpenAI releases a new reasoning model", "OpenAI", current),
            _item("Japanese firms remain slow to adopt AI", "BBC Business", current - 300),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["topic_count"] == 2


def test_monitor_does_not_merge_stories_on_a_broad_sector_term():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "bio",
        "name": "生物医药 / 健康",
        "items": [
            _item("Biopharma drawdown creates a chance to rebuild biotech", "Market View", current),
            _item("Biotech startup searches the globe for eczema drugs", "Health Wire", current - 300),
            _item("China biotech debate returns to Boston", "Conference News", current - 600),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["topic_count"] == 3
    assert len({topic["id"] for topic in result["topics"]}) == 3


def test_monitor_does_not_merge_different_cases_on_generic_legal_wording():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "macro",
        "name": "财经 / 宏观",
        "items": [
            _item("SEC Charges Toms River Trio in Alleged Fraud", "SEC", current),
            _item("SEC Charges Adit Ventures Management in Alleged Fraud", "SEC", current - 300),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["topic_count"] == 2


def test_monitor_does_not_merge_different_products_from_the_same_brand():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "consumer",
        "name": "消费电子 / 数码",
        "items": [
            _item("One UI 9.5 shows up on a Galaxy phone before Samsung is even done with One UI 9", "Phone Wire", current),
            _item("Samsung reportedly abandons plans to give the Galaxy S27 a variable-aperture camera", "Mobile News", current - 300),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["topic_count"] == 2


def test_monitor_does_not_treat_technical_terms_or_benefit_claims_as_fact_checks():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "science",
        "name": "科学 / 前沿",
        "items": [
            _item("Quantum error correction improves processor stability", "Science Wire", current),
            _item("Backtrack-Free Cursive", "Developer News", current - 60),
            _item("Can I claim 50% of my spouse's Social Security?", "Finance Help", current - 120),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["flagged_topic_count"] == 0
    assert all(topic["verification_status"] == "常规报道" for topic in result["topics"])


def test_monitor_separates_verification_from_event_risk():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "consumer",
        "name": "消费电子 / 数码",
        "items": [
            _item("Fairphone 6+ is rumored to launch next month", "Phone Wire", current),
        ],
    }]

    topic = build_news_monitor(industries, now=now)["topics"][0]

    assert topic["verification_status"] == "待核实"
    assert topic["signal"] == "watch"
    assert topic["sentiment"] == "neutral"


def test_monitor_ignores_ambiguous_technical_and_product_words():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "science",
        "name": "科学 / 前沿",
        "items": [
            _item("OneCell CUT&Tag captures epigenomic reprogramming", "Nature", current),
            _item("WorkBuddy 产品升级并改进知识管理", "Tech Wire", current - 60),
            _item("Hackers gain SYSTEM access through a configuration error", "Security Wire", current - 120),
            _item("No funding for the launch programme", "Space Wire", current - 180),
            _item("两市融资余额继续增加", "财经快讯", current - 240),
            _item("通信行业获融资净买入居首", "财经快讯", current - 300),
            _item("Drones tested in a live war game", "Defense Wire", current - 360),
        ],
    }]

    result = build_news_monitor(industries, now=now)

    assert result["summary"]["risk_topic_count"] == 0
    assert result["summary"]["opportunity_topic_count"] == 0


def test_monitor_keeps_explicit_recall_and_funding_signals():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "auto",
        "name": "汽车 / 新能源车",
        "items": [
            _item("Ford recalls 90,000 EVs after trim defect", "Auto Wire", current),
            _item("Battery startup raises $50m in new funding", "Energy News", current - 60),
        ],
    }]

    result = build_news_monitor(industries, now=now)
    signals = {topic["headline"]: topic["signal"] for topic in result["topics"]}

    assert signals["Ford recalls 90,000 EVs after trim defect"] == "risk"
    assert signals["Battery startup raises $50m in new funding"] == "opportunity"


def test_monitor_ranks_material_events_above_promotions_and_generic_guides():
    now = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
    current = int(datetime(2026, 8, 13, 11, tzinfo=timezone.utc).timestamp())
    industries = [{
        "key": "tech",
        "name": "科技 / 互联网",
        "items": [
            _item("Company reports revenue growth and higher profit", "Business Wire", current),
            _item("August coupon deals offer a 10% discount", "Shopping Guide", current),
            _item("How to improve warehouse storage organization", "Industry Blog", current),
            _item("Biotech signs a royalty deal for a new therapy", "Health Wire", current),
        ],
    }]

    result = build_news_monitor(industries, now=now)
    topics = {topic["headline"]: topic for topic in result["topics"]}

    material = topics["Company reports revenue growth and higher profit"]
    promotion = topics["August coupon deals offer a 10% discount"]
    guide = topics["How to improve warehouse storage organization"]
    commercial_deal = topics["Biotech signs a royalty deal for a new therapy"]
    assert len(topics) == 4
    assert material["attention_score"] > guide["attention_score"] > promotion["attention_score"]
    assert promotion["ranking_adjustment"] <= -10
    assert guide["ranking_adjustment"] < 0
    assert "促销内容降权" not in commercial_deal["ranking_reasons"]
