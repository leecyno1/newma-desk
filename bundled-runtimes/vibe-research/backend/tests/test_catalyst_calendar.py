from datetime import date

from fastapi.testclient import TestClient

import app as app_module
import catalyst_calendar


client = TestClient(app_module.app)


def test_cycle_adapter_only_publishes_qualified_windows(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar,
        "_load_cycle_research",
        lambda: {
            "meta": {"generated": "2026-08-03"},
            "diagnostics": {
                "C7": {
                    "directionPublication": {
                        "status": "limited",
                        "layer": "risk_state_probability",
                        "asOf": "2026-07",
                        "currentLabel": "中性转弱",
                        "horizons": [
                            {"label": "1个月", "months": 1, "probability": 0.8, "accuracy": 0.79, "outcome": "风险偏好", "qualified": True},
                            {"label": "6个月", "months": 6, "probability": 0.5, "accuracy": 0.5, "outcome": "不确定", "qualified": False},
                        ],
                        "exactCycleStatus": "blocked",
                        "assetForecastStatus": "blocked",
                        "gate": {"passed": True},
                        "caveat": "不发布精确拐点",
                    }
                },
                "C4": {"directionPublication": {"status": "blocked", "gate": {"passed": False}}},
            },
        },
    )
    catalyst_calendar._CACHE.clear()

    events, source = catalyst_calendar._cycle_events(
        date(2026, 8, 3),
        date(2026, 12, 31),
    )

    assert source["status"] == "ok"
    assert len(events) == 1
    assert events[0]["id"] == "cycle:C7:2026-07:1"
    assert events[0]["timePrecision"] == "window"
    assert events[0]["importance"] == "high"
    assert events[0]["urgency"] == "medium"
    assert events[0]["dateConfidence"] == "low"
    assert events[0]["cycleContext"]["exactCycleStatus"] == "blocked"


def test_catalyst_endpoint_contract(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar,
        "build_catalyst_feed",
        lambda symbols, days, include_cycles, concepts, include_macro: {
            "schemaVersion": catalyst_calendar.SCHEMA_VERSION,
            "generatedAt": "2026-08-03T00:00:00+00:00",
            "horizon": {"start": "2026-08-03", "end": "2026-11-01", "days": days},
            "coverage": {"markets": ["CN"], "symbols": symbols, "concepts": concepts, "includeMacro": include_macro},
            "items": [],
            "sources": [],
            "gaps": [],
            "disclaimer": "test",
        },
    )

    response = client.get("/api/catalysts?symbols=600519,300308&days=90")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["schemaVersion"] == "newma-desk.catalyst-calendar.v1"
    assert body["coverage"]["symbols"] == ["600519", "300308"]


def test_catalyst_endpoint_accepts_concept_and_macro_scope(monkeypatch):
    captured = {}

    def build(symbols, days, include_cycles, concepts, include_macro):
        captured.update({
            "symbols": symbols,
            "days": days,
            "include_cycles": include_cycles,
            "concepts": concepts,
            "include_macro": include_macro,
        })
        return {
            "schemaVersion": catalyst_calendar.SCHEMA_VERSION,
            "generatedAt": "2026-08-14T00:00:00+00:00",
            "horizon": {"start": "2026-08-14", "end": "2026-09-13", "days": days},
            "coverage": {"markets": ["CN"], "symbols": symbols, "concepts": concepts, "includeMacro": include_macro},
            "items": [], "sources": [], "gaps": [], "disclaimer": "test",
        }

    monkeypatch.setattr(catalyst_calendar, "build_catalyst_feed", build)
    response = client.get("/api/catalysts?concepts=人工智能,机器人&include_macro=false")

    assert response.status_code == 200
    assert captured["concepts"] == ["人工智能", "机器人"]
    assert captured["include_macro"] is False


def test_catalyst_endpoint_rejects_non_a_share_symbol():
    response = client.get("/api/catalysts?symbols=AAPL")
    assert response.status_code == 400


def test_announcement_titles_create_explicit_observation_windows(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar.astock,
        "announcements",
        lambda symbol, limit=20: [
            {
                "date": "2026-08-01",
                "title": "关于回购公司股份方案的公告",
                "type": "公司公告",
                "url": "https://example.com/buyback",
            },
            {
                "date": "2026-08-02",
                "title": "日常经营情况说明",
                "type": "公司公告",
                "url": "https://example.com/routine",
            },
        ],
    )
    catalyst_calendar._CACHE.clear()

    events, source = catalyst_calendar._announcement_events(
        {"600519"},
        date(2026, 8, 14),
        date(2027, 2, 10),
    )

    assert source["status"] == "ok"
    assert len(events) == 1
    assert events[0]["timePrecision"] == "window"
    assert events[0]["dateBasis"] == "announcement-derived"
    assert events[0]["urgency"] == "low"
    assert events[0]["dateConfidence"] == "low"
    assert "不代表事件将在窗口结束日发生" in events[0]["summary"]


def test_earnings_event_exposes_date_revision_history(monkeypatch):
    class Frame:
        empty = False

        @staticmethod
        def to_dict(_orient):
            return [{
                "股票代码": "600519",
                "股票简称": "贵州茅台",
                "首次预约": "2026-08-20",
                "初次变更": "2026-08-25",
                "二次变更": None,
                "三次变更": None,
                "实际披露": None,
            }]

    monkeypatch.setattr(catalyst_calendar.astock, "akshare_call", lambda *args, **kwargs: Frame())
    catalyst_calendar._CACHE.clear()

    events, _source = catalyst_calendar._report_disclosure_events(
        {"600519"},
        date(2026, 8, 14),
        date(2026, 12, 31),
    )

    assert len(events) == 1
    assert events[0]["date"] == "2026-08-25"
    assert events[0]["importance"] == "high"
    assert events[0]["urgency"] == "medium"
    assert events[0]["dateConfidence"] == "medium"
    assert events[0]["dateChange"] == {
        "originalDate": "2026-08-20",
        "currentDate": "2026-08-25",
        "changeCount": 1,
        "direction": "delayed",
    }


def test_macro_calendar_is_kept_separate_from_official_dates(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar.macro_monitor,
        "_load_calendar",
        lambda today, days: ([{
            "id": "macro:cn-cpi",
            "date": "2026-08-17",
            "time": "10:00",
            "region": "中国",
            "title": "中国 7 月 CPI",
            "importance": "high",
            "forecast": 0.8,
            "previous": 0.6,
            "source": {"id": "calendar", "label": "公开日历", "url": "https://example.com"},
            "evidenceId": "macro-calendar:cn-cpi",
            "asOf": "2026-08-14T00:00:00+00:00",
        }], [], []),
    )

    events, source, gaps = catalyst_calendar._macro_calendar_events(
        date(2026, 8, 14),
        date(2026, 9, 14),
    )

    assert source["status"] == "ok"
    assert gaps == []
    assert events[0]["dateBasis"] == "aggregated-calendar"
    assert events[0]["dateConfidence"] == "medium"
    assert "预期 0.8" in events[0]["summary"]


def test_macro_calendar_promotes_only_core_major_releases(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar.macro_monitor,
        "_load_calendar",
        lambda today, days: ([
            {
                "id": "macro:cn-m2",
                "date": "2026-08-17",
                "time": "10:00",
                "region": "中国",
                "title": "中国7月M2货币供应年率(%)",
                "importance": "medium",
                "source": {"id": "calendar", "label": "公开日历"},
                "evidenceId": "macro-calendar:cn-m2",
                "asOf": "2026-08-14T00:00:00+00:00",
            },
            {
                "id": "macro:us-confidence",
                "date": "2026-08-17",
                "time": "22:00",
                "region": "美国",
                "title": "美国8月消费者信心指数",
                "importance": "medium",
                "source": {"id": "calendar", "label": "公开日历"},
                "evidenceId": "macro-calendar:us-confidence",
                "asOf": "2026-08-14T00:00:00+00:00",
            },
        ], [], []),
    )

    events, _source, _gaps = catalyst_calendar._macro_calendar_events(
        date(2026, 8, 14),
        date(2026, 9, 14),
    )

    importance = {event["title"]: event["importance"] for event in events}
    assert importance["中国 货币信贷日程"] == "high"
    assert importance["美国 消费者信心日程"] == "medium"


def test_concept_keywords_create_signal_windows(monkeypatch):
    monkeypatch.setattr(
        catalyst_calendar.newsradar,
        "query_topics",
        lambda **kwargs: {
            "total": 3,
            "generated_at_iso": "2026-08-14T00:00:00+00:00",
            "items": [{
                "id": "topic-ai",
                "headline": "AI 订单与资本开支升温",
                "attention_score": 66,
                "velocity_state": "rising",
                "signal": "opportunity",
                "sources": ["公司公告", "行业媒体"],
                "items": [{"url": "https://example.com/ai"}],
            }],
        },
    )

    events, source, gaps = catalyst_calendar._concept_signal_events(
        ["人工智能"],
        date(2026, 8, 14),
        date(2026, 9, 14),
    )

    assert source["status"] == "ok"
    assert gaps == []
    assert events[0]["dateBasis"] == "signal-window"
    assert events[0]["importance"] == "high"
    assert events[0]["expectedDirection"] == "positive"


def test_geopolitical_concepts_expand_to_common_news_terms(monkeypatch):
    queries = []

    def query_topics(**kwargs):
        queries.append(kwargs["query"])
        if kwargs["query"] != "冲突":
            return {"items": [], "total": 0}
        return {
            "items": [{
                "id": "topic-conflict",
                "headline": "地区冲突风险升温",
                "attention_score": 50,
                "velocity_state": "rising",
                "signal": "risk",
                "sources": ["公开媒体"],
                "items": [],
            }],
            "total": 1,
        }

    monkeypatch.setattr(catalyst_calendar.newsradar, "query_topics", query_topics)

    events, source, gaps = catalyst_calendar._concept_signal_events(
        ["战争"],
        date(2026, 8, 14),
        date(2026, 9, 14),
    )

    assert "冲突" in queries
    assert source["status"] == "ok"
    assert gaps == []
    assert events[0]["title"] == "战争 主题催化观察窗"
