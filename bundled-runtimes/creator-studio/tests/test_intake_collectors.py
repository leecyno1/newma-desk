import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "scripts"))

from intake_collectors import (
    CollectedItem,
    CollectorRun,
    collect_simple_intake,
    collect_local_service,
    json_hot_items,
    media_item_to_item,
    merge_news_items,
    message_to_item,
    mp_article_to_item,
    parse_html_hot_items,
    parse_atom_or_rss,
    parse_tophub_html,
    public_news_items,
)
from run_stage1_intake import build_simple_intake_tasks


def test_message_to_item_keeps_relevant_local_chat_anchor():
    row = {
        "id": "msg-1",
        "chat_id": "chat-a",
        "content_text": "今天会议讨论 OpenAI agent 工作流和公众号选题。",
        "timestamp": 1717200000,
        "talker_name": "选题群",
        "sender_name": "Lee",
        "derived": {"display_summary": "OpenAI agent 工作流会议纪要"},
        "meta": {"display_title": "OpenAI agent 工作流会议纪要"},
        "importance_score": 7,
    }

    item = message_to_item(row, "http://127.0.0.1:8001")

    assert item is not None
    assert item.channel == "local_chat"
    assert item.source == "local_chat/messages"
    assert item.url == "dasheng-local://messages/msg-1"
    assert item.score == 7


def test_message_to_item_uses_0913_wechat_link_payload():
    row = {
        "id": 84958,
        "chat_id": "3896225238@chatroom",
        "sender_name": "国泰海通固收研究",
        "talker_name": "国泰海通—南方基金投研交流",
        "timestamp": "2026-05-25T18:42:23",
        "type": "link",
        "content_text": "【国债期货】关注国债期货增仓：关注新增的“非常规”配债力量",
        "meta": {
            "source": "wechat_gateway",
            "contents": {
                "title": "【国债期货】关注国债期货增仓：关注新增的“非常规”配债力量",
                "desc": "国债期货增仓的背后，新的配置力量和对债市的影响",
                "url": "http://mp.weixin.qq.com/s/example",
                "sourcedisplayname": "国泰海通固收研究",
            },
            "display_title": "【国债期货】关注国债期货增仓：关注新增的“非常规”配债力量",
        },
        "importance_score": 50,
    }

    item = message_to_item(row, "http://127.0.0.1:8001")

    assert item is not None
    assert item.title == "【国债期货】关注国债期货增仓：关注新增的“非常规”配债力量"
    assert item.url == "http://mp.weixin.qq.com/s/example"
    assert item.author_name == "国泰海通固收研究"
    assert item.channel == "local_chat"


def test_message_to_item_filters_irrelevant_short_noise():
    row = {"id": "msg-2", "content_text": "晚饭吃什么", "talker_name": "闲聊群"}

    assert message_to_item(row, "http://127.0.0.1:8001") is None


def test_message_to_item_filters_raw_xml_payload_without_display_title():
    row = {
        "id": "msg-xml",
        "type": "image",
        "content_text": '<?xml version="1.0"?><msg><img aeskey="x" /></msg>',
        "talker_name": "投研交流群",
        "meta": {"source": "wechat_gateway", "contents": {}},
    }

    assert message_to_item(row, "http://127.0.0.1:8001") is None


def test_mp_article_to_item_maps_0913_article_payload():
    item = mp_article_to_item(
        {
            "id": "local-gh-161085",
            "channel_name": "财文社",
            "publish_time": "2026-08-04T17:03:11",
            "title": "财经时局分析",
            "summary": "来自 0913 公众号聚合接口",
            "url": "https://mp.weixin.qq.com/s/example",
            "heat": 997,
        },
        "http://127.0.0.1:8001",
    )

    assert item is not None
    assert item.source == "local_mp/8001"
    assert item.channel == "wechat"
    assert item.author_name == "财文社"
    assert item.url == "https://mp.weixin.qq.com/s/example"
    assert item.score == 997


def test_media_item_to_item_maps_0913_self_media_payload():
    item = media_item_to_item(
        {
            "id": "search-ai-newsnow-1",
            "platform": "newsnow",
            "time": "2026-08-04T05:01:35+08:00",
            "title": "AI 办公市场正在变化",
            "url": "https://www.zhihu.com/question/1",
            "summary": "来自 0913 自媒体聚合接口",
            "stats": {"heat": 88},
        },
        "http://127.0.0.1:8001",
    )

    assert item is not None
    assert item.source == "local_media/newsnow"
    assert item.channel == "content_research"
    assert item.url == "https://www.zhihu.com/question/1"
    assert item.score == 88


def test_merge_news_items_combines_same_upstream_story_and_preserves_sources():
    local = CollectedItem(
        source="local_news/8001",
        channel="local_news",
        title="韩国央行时隔13年恢复购买实物黄金",
        url="dasheng-local://news/3144057",
        author_name="华尔街见闻",
        raw={"source_id": "wallstreetcn-quick", "id": "3144057"},
    )
    public = CollectedItem(
        source="public_news/wallstreetcn-quick",
        channel="public_news",
        title="韩国央行时隔 13 年后恢复购买实物黄金",
        url="https://wallstreetcn.com/articles/3778584",
        author_name="华尔街见闻",
        score=80,
        raw={"source_id": "wallstreetcn-quick", "id": "3144057"},
    )

    merged = merge_news_items([local], [public])

    assert len(merged) == 1
    assert merged[0].channel == "news"
    assert merged[0].url == "https://wallstreetcn.com/articles/3778584"
    assert merged[0].raw["merged_count"] == 2
    assert {row["source"] for row in merged[0].raw["merged_sources"]} == {
        "local_news/8001",
        "public_news/wallstreetcn-quick",
    }


def test_parse_atom_or_rss_supports_atom_feed():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>AI agents are changing workflows</title>
        <link href="https://example.com/agents" />
        <updated>2026-06-04T08:00:00Z</updated>
        <author><name>Example</name></author>
      </entry>
    </feed>
    """

    items = parse_atom_or_rss(xml, "example_atom", "public_hot", 3)

    assert len(items) == 1
    assert items[0].source == "public/example_atom"
    assert items[0].url == "https://example.com/agents"


def test_zhihu_hot_score_ignores_text_heat_without_crashing():
    payload = {
        "data": [
            {
                "target": {"title": "AI 工具爆发", "url": "https://www.zhihu.com/question/1"},
                "detail_text": "128 万热度",
            }
        ]
    }

    items = json_hot_items(payload, "zhihu_hot", 10)

    assert len(items) == 1
    assert items[0].title == "AI 工具爆发"
    assert items[0].score == 1280000


def test_zhihu_hot_converts_api_question_url_to_public_page():
    payload = {
        "data": [
            {
                "target": {
                    "id": 2045160976878680020,
                    "title": "OpenAI遭美国州政府起诉",
                    "url": "https://api.zhihu.com/questions/2045160976878680020",
                },
                "detail_text": "59 万热度",
            }
        ]
    }

    items = json_hot_items(payload, "zhihu_hot", 10)

    assert items[0].url == "https://www.zhihu.com/question/2045160976878680020"


def test_parse_tophub_html_extracts_hot_rows():
    html = """
    <table class="table"><tbody>
      <tr>
        <td align="center">1.</td>
        <td><a href="https://s.weibo.com/weibo?q=AI" target="_blank">AI 新消息</a></td>
        <td class="ws">25万</td>
      </tr>
    </tbody></table>
    """

    items = parse_tophub_html(html, "weibo_hot", "微博热搜", 5)

    assert len(items) == 1
    assert items[0].source == "public/weibo_hot"
    assert items[0].title == "AI 新消息"
    assert items[0].score == 250000


def test_parse_next_data_html_extracts_hupu_rows():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"res":[{"heat":6604561,"tagId":148002,"rank":1,"tagName":"世界杯冠军之路"}]}}}
    </script>
    """

    items = parse_html_hot_items(html, "hupu_hot", "虎扑热榜", "next_data", 5)

    assert len(items) == 1
    assert items[0].source == "public/hupu_hot"
    assert items[0].url == "https://m.hupu.com/hot/148002"
    assert items[0].score == 6604561


def test_public_news_items_preserve_heat_tone_and_category():
    rows = [
        {
            "id": "10jqka-stock:1",
            "source_id": "10jqka-stock",
            "source_name": "同花顺",
            "title": "英伟达入局PC领域 端侧AI赛道全面打开",
            "url": "https://news.10jqka.com.cn/example.shtml",
            "pub_ts": 1780527658000,
            "region": "cn",
            "category": "technology",
            "summary": "AI PC 产业链受关注",
            "derived": {"tone": "positive", "category": "technology"},
        }
    ]

    items = public_news_items(rows, 10)

    assert len(items) == 1
    assert items[0].channel == "public_news"
    assert items[0].source == "public_news/10jqka-stock"
    assert items[0].score > 0
    assert items[0].raw["tone"] == "positive"
    assert items[0].raw["category"] == "technology"


def test_collector_run_status_preserves_total_from_items():
    run = CollectorRun()
    run.add_task(
        "public_hot",
        [CollectedItem(source="public/test", channel="public_hot", title="AI", url="https://example.com")],
        {"status": "ready"},
    )

    assert run.status["public_hot"]["total"] == 1


def test_build_simple_intake_tasks_maps_collectors_to_stage_channels(monkeypatch, tmp_path):
    fake = CollectorRun()
    fake.add_task(
        "local_chat",
        [
            CollectedItem(
                source="local_chat/messages",
                channel="local_chat",
                title="OpenAI agent 会议纪要",
                url="dasheng-local://messages/1",
                summary="会议讨论公众号选题",
            )
        ],
        {"status": "ready", "base": "http://127.0.0.1:8001"},
    )
    fake.add_task(
        "local_news",
        [
            CollectedItem(
                source="local_news/8001",
                channel="local_news",
                title="Claude agent workflow 新变化",
                url="https://example.com/news",
                summary="AI 工作流新闻",
                score=12,
            )
        ],
        {"status": "ready", "base": "http://127.0.0.1:8001"},
    )
    fake.add_task(
        "public_hot",
        [
            CollectedItem(
                source="public/hn_frontpage",
                channel="public_hot",
                title="AI agents on Hacker News",
                url="https://news.ycombinator.com/item?id=1",
                summary="Hacker News RSS",
            )
        ],
        {"status": "ready"},
    )
    fake.add_task(
        "content_research",
        [
            CollectedItem(
                source="local_media/weibo",
                channel="content_research",
                title="新能源车产业讨论",
                url="https://example.com/media",
                summary="0913 自媒体聚合",
            )
        ],
        {"status": "ready", "base": "http://127.0.0.1:8001"},
    )
    fake.add_task(
        "wechat",
        [
            CollectedItem(
                source="local_mp/8001",
                channel="wechat",
                title="债券市场深度分析",
                url="https://mp.weixin.qq.com/s/example",
                author_name="投研公众号",
                summary="0913 公众号聚合",
            )
        ],
        {"status": "ready", "base": "http://127.0.0.1:8001"},
    )
    fake.artifacts = ["raw/local_messages.json", "raw/public_fallback_items.json"]

    monkeypatch.setattr("run_stage1_intake.collect_simple_intake", lambda raw_dir: fake)

    (
        platform_tasks,
        content_task,
        ai_hot_task,
        report_task,
        wechat_task,
        channels,
        latest_articles,
        curated_articles,
        generic_tasks,
        ports_status,
        artifacts,
    ) = build_simple_intake_tasks(tmp_path)

    assert platform_tasks["x"].status == "skipped"
    assert content_task.status == "ready"
    assert content_task.items[0]["source"] == "local_media/weibo"
    assert report_task.status == "skipped"
    assert wechat_task.status == "ready"
    assert channels["data"]["total"] == 1
    assert latest_articles["data"]["list"][0]["source"] == "local_mp/8001"
    assert curated_articles == {}
    assert generic_tasks["local_chat"].total == 1
    assert generic_tasks["news"].items[0]["url"] == "https://example.com/news"
    assert generic_tasks["news"].items[0]["channel"] == "news"
    assert generic_tasks["public_hot"].total == 1
    assert ai_hot_task.total == 3
    assert "wechat" in ai_hot_task.meta["derived_from"]
    assert ports_status["simple_intake"]["mode"] == "simple"
    assert artifacts == [*fake.artifacts, "raw/merged_news_items.json"]
    assert (tmp_path / "merged_news_items.json").exists()


def test_collect_local_service_does_not_time_filter_messages_by_default(monkeypatch, tmp_path):
    calls = []

    def fake_get_json(url, *, timeout=12, params=None):
        calls.append((url, params or {}))
        if url.endswith("/api/health"):
            return {"status": "ok"}
        if url.endswith("/api/chats"):
            return []
        if url.endswith("/api/messages"):
            return {
                "items": [
                    {
                        "id": 1,
                        "type": "link",
                        "content_text": "【国债期货】关注新增配置力量",
                        "talker_name": "投研交流群",
                        "meta": {
                            "source": "wechat_gateway",
                            "contents": {
                                "title": "【国债期货】关注新增配置力量",
                                "url": "http://mp.weixin.qq.com/s/example",
                                "sourcedisplayname": "投研公众号",
                            },
                        },
                    }
                ]
            }
        if url.endswith("/api/mp/articles"):
            return {
                "items": [
                    {
                        "id": "mp-1",
                        "channel_name": "投研公众号",
                        "title": "半导体周期跟踪",
                        "url": "https://mp.weixin.qq.com/s/example",
                        "summary": "公众号文章摘要",
                    }
                ],
                "source": {"kind": "0913-mp"},
            }
        if url.endswith("/api/media/items"):
            return {
                "items": [
                    {
                        "id": "media-1",
                        "platform": "weibo",
                        "title": "半导体自媒体讨论",
                        "url": "https://weibo.com/example",
                        "summary": "自媒体摘要",
                    }
                ],
                "source": {"kind": "0913-media"},
            }
        if url.endswith("/api/newsfeed/items"):
            return {"items": []}
        raise AssertionError(url)

    monkeypatch.delenv("DASHENG_LOCAL_CHAT_DAYS", raising=False)
    monkeypatch.setattr("intake_collectors.safe_get_json", fake_get_json)

    run = collect_local_service(tmp_path)

    message_params = [params for url, params in calls if url.endswith("/api/messages")][0]
    assert "time_from" not in message_params
    assert message_params["direction"] == "in"
    assert message_params["include_mp_messages"] == "false"
    assert run.status["local_chat"]["total"] == 1
    assert run.status["wechat"]["total"] == 1
    assert run.status["content_research"]["total"] == 1


def test_collect_simple_intake_uses_hotspot_radar_module(monkeypatch, tmp_path):
    local = CollectorRun()
    local.add_task(
        "local_chat",
        [CollectedItem(source="local_chat/messages", channel="local_chat", title="本地会议", url="dasheng-local://messages/1")],
        {"status": "ready"},
    )
    radar = CollectorRun()
    radar.add_task(
        "public_news",
        [CollectedItem(source="public_news/wallstreetcn-quick", channel="public_news", title="央行政策信号", url="https://example.com/macro")],
        {"status": "ready"},
    )
    radar.status["hotspot_radar"] = {"status": "ready", "total": 1, "module": "hotspot_radar"}
    radar.artifacts = ["raw/hotspot_radar.json"]

    monkeypatch.setattr("intake_collectors.collect_local_service", lambda raw_dir: local)
    monkeypatch.setattr("hotspot_radar.collect_hotspot_radar", lambda raw_dir: radar)

    run = collect_simple_intake(tmp_path)

    assert run.status["hotspot_radar"]["module"] == "hotspot_radar"
    assert run.status["public_news"]["total"] == 1
    assert run.tasks["local_chat"][0].title == "本地会议"
    assert "raw/hotspot_radar.json" in run.artifacts
