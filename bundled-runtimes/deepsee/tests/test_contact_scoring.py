import os
import sys
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Contact, Message
from app.routers import contacts as contacts_router


def _make_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    return path, TestingSession


def test_extract_prediction_events_detects_stock_industry_and_index_calls():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "继续看好601899，未来3个月大概率跑赢沪深300，建议加仓。",
            "derived": {"summary": "ai: 看好紫金矿业未来3个月表现"},
        },
        {
            "id": 2,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "半导体未来一年压力仍大，建议回避。",
            "derived": {"summary": "ai: 半导体板块偏谨慎"},
        },
        {
            "id": 3,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "我判断沪深300未来一个月会迎来反弹。",
            "derived": {"summary": "ai: 沪深300短期有望反弹"},
        },
        {
            "id": 4,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "512480这个芯片ETF建议关注，未来一个月反弹概率较大。",
            "derived": {"summary": "ai: 芯片ETF短期有望反弹"},
        },
    ]

    events = scoring.extract_prediction_events(messages, focus_contact_ids={"wxid_focus"})

    assert len(events) == 4
    assert [event["asset_type"] for event in events] == ["stock", "industry", "index", "etf"]
    assert events[0]["asset_code"] == "601899"
    assert events[0]["direction"] == "bullish"
    assert events[0]["horizon_flags"]["3m"] is True
    assert events[1]["asset_name"] == "半导体"
    assert events[1]["direction"] == "bearish"
    assert events[1]["horizon_flags"]["1y"] is True
    assert events[2]["asset_code"] == "sh000300"
    assert events[2]["direction"] == "bullish"
    assert events[2]["horizon_flags"]["1m"] is True
    assert events[3]["asset_code"] == "512480"
    assert events[3]["benchmark_code"] == "sh000300"


def test_extract_prediction_events_can_resolve_named_assets_without_numeric_code():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "我继续看好紫金矿业，未来3个月有望跑赢沪深300。",
            "derived": {"summary": "ai: 看好紫金矿业未来表现"},
        },
        {
            "id": 2,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "芯片ETF这里建议继续关注，一个月内可能有反弹。",
            "derived": {"summary": "ai: 芯片ETF短期可能反弹"},
        },
    ]

    events = scoring.extract_prediction_events(
        messages,
        focus_contact_ids={"wxid_focus"},
        asset_lookup_resolver=lambda text: (
            {"asset_type": "stock", "asset_code": "601899", "asset_name": "紫金矿业"}
            if "紫金矿业" in text
            else {"asset_type": "etf", "asset_code": "512480", "asset_name": "半导体ETF"}
            if "芯片ETF" in text
            else None
        ),
    )

    assert len(events) == 2
    assert events[0]["asset_type"] == "stock"
    assert events[0]["asset_code"] == "601899"
    assert events[0]["asset_name"] == "紫金矿业"
    assert events[1]["asset_type"] == "etf"
    assert events[1]["asset_code"] == "512480"


def test_extract_prediction_events_selects_board_specific_benchmarks():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "继续看好688111，未来一个月表现有望继续走强。",
        },
        {
            "id": 2,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "继续看好300750，未来一个月表现有望继续走强。",
        },
        {
            "id": 3,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "继续看好430047，未来一个月表现有望继续走强。",
        },
    ]

    events = scoring.extract_prediction_events(messages, focus_contact_ids={"wxid_focus"})

    assert [event["benchmark_code"] for event in events] == ["sh000688", "sz399006", "bj899050"]


def test_extract_prediction_events_assigns_event_kind_topic_key_and_risk_alert_defaults():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "半导体未来一年压力仍大，建议回避。",
            "derived": {"summary": "ai: 半导体板块偏谨慎"},
        },
        {
            "id": 2,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "继续看好601899，未来3个月大概率跑赢沪深300，建议加仓。",
            "derived": {"summary": "ai: 看好紫金矿业未来3个月表现"},
        },
    ]

    events = scoring.extract_prediction_events(messages, focus_contact_ids={"wxid_focus"})

    assert events[0]["event_kind"] == "risk_alert"
    assert events[0]["topic_key"] == "半导体"
    assert events[0]["signal_strength"] > 0.5
    assert events[0]["source_type"] == "wechat"
    assert events[0]["is_actionable"] is True
    assert events[1]["event_kind"] == "price_call"
    assert events[1]["topic_key"] == "601899"
    assert events[1]["is_actionable"] is True


def test_extract_prediction_events_marks_roadshow_invite_as_non_actionable():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_focus",
            "sender_name": "张三",
            "timestamp": now,
            "content_text": "下周有银行板块路演交流，欢迎报名参加，重点讨论招商银行。",
            "derived": {"summary": "银行板块路演通知"},
        }
    ]

    events = scoring.extract_prediction_events(
        messages,
        focus_contact_ids={"wxid_focus"},
        asset_lookup_resolver=lambda text: {"asset_type": "stock", "asset_code": "600036", "asset_name": "招商银行"},
    )

    assert len(events) == 1
    assert events[0]["event_kind"] == "roadshow_invite"
    assert events[0]["is_actionable"] is False
    assert events[0]["direction"] == "neutral"


def test_extract_prediction_events_to_db_inserts_neutral_roadshow_invites():
    from app.models import ContactPredictionEvent
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_research", name="张三", alias="银行研究员", rating=70))
            db.add(
                Message(
                    sender_id="wxid_research",
                    sender_name="张三",
                    timestamp=datetime(2026, 6, 24, 9, 30, 0),
                    content_text="下周有招商银行600036路演交流，欢迎报名参加。",
                )
            )
            db.commit()

            result = scoring.extract_prediction_events_to_db(db, contact_ids={"wxid_research"})
            event = db.query(ContactPredictionEvent).one()

            assert result["inserted"] == 1
            assert event.event_kind == "roadshow_invite"
            assert event.is_actionable is False
            assert event.direction == "neutral"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_extract_prediction_events_skips_sales_contacts_by_default():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    messages = [
        {
            "id": 1,
            "sender_id": "wxid_sales",
            "sender_name": "程一天中信建投销售",
            "timestamp": now,
            "content_text": "继续看好601899，未来3个月大概率跑赢沪深300，建议加仓。",
            "derived": {"summary": "ai: 转发观点"},
        },
        {
            "id": 2,
            "sender_id": "wxid_research",
            "sender_name": "陈晨国海证券能源",
            "timestamp": now,
            "content_text": "继续看好601899，未来3个月大概率跑赢沪深300，建议加仓。",
            "derived": {"summary": "ai: 原创观点"},
        },
    ]

    events = scoring.extract_prediction_events(messages, focus_contact_ids={"wxid_sales", "wxid_research"})

    assert len(events) == 1
    assert events[0]["contact_id"] == "wxid_research"


def test_sales_contact_detector_uses_contact_identity_not_view_text():
    from app.services import contact_scoring as scoring

    assert scoring.is_sales_contact_payload({"name": "张三", "alias": "中信证券销售"})
    assert not scoring.is_sales_contact_payload({"name": "张三", "alias": "地产销售数据研究"})


def test_get_focus_contact_ids_auto_selects_recent_research_contacts_when_unconfigured():
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            now = datetime.utcnow()
            db.add_all(
                [
                    Contact(id="wxid_research_recent", name="陈晨国海证券能源", alias="能源研究员", rating=66),
                    Contact(id="wxid_sales_recent", name="程一天", alias="中信证券销售", rating=90),
                    Contact(id="gh_media", name="公众号", alias="公众号", rating=80),
                ]
            )
            db.commit()
            for idx in range(4):
                db.add(
                    Message(
                        sender_id="wxid_research_recent",
                        sender_name="陈晨国海证券能源",
                        timestamp=now - timedelta(days=idx),
                        content_text="继续看好紫金矿业，未来三个月有望跑赢。",
                    )
                )
            for idx in range(6):
                db.add(
                    Message(
                        sender_id="wxid_sales_recent",
                        sender_name="程一天中信证券销售",
                        timestamp=now - timedelta(days=idx),
                        content_text="转发路演邀请，欢迎报名。",
                    )
                )
            db.add(
                Message(
                    sender_id="gh_media",
                    sender_name="公众号",
                    timestamp=now,
                    content_text="公众号推送",
                )
            )
            db.add(
                Message(
                    sender_id="12345@chatroom",
                    sender_name="群聊",
                    timestamp=now,
                    content_text="群聊消息",
                )
            )
            db.commit()

            ids = scoring.get_focus_contact_ids(db)

            assert "wxid_research_recent" in ids
            assert "wxid_sales_recent" not in ids
            assert "gh_media" not in ids
            assert "12345@chatroom" not in ids
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_summarize_contact_score_aggregates_hits_excess_and_manual_weight():
    from app.services import contact_scoring as scoring

    evaluations = [
        {"horizon_code": "1m", "direction_hit": True, "excess_return": 0.08, "event_score": 82},
        {"horizon_code": "3m", "direction_hit": True, "excess_return": 0.15, "event_score": 88},
        {"horizon_code": "1y", "direction_hit": False, "excess_return": -0.06, "event_score": 36},
    ]

    summary = scoring.summarize_contact_score(
        contact_id="wxid_focus",
        evaluations=evaluations,
        manual_rating=62,
    )

    assert summary["sample_size"] == 3
    assert summary["hit_rate_overall"] == 4 / 7
    assert round(summary["accuracy_by_horizon"]["1m"], 4) == 0.6
    assert round(summary["accuracy_by_horizon"]["1y"], 4) == 0.4
    assert summary["auto_rating"] > 50
    assert summary["final_rating"] >= 50
    assert summary["manual_rating"] == 62
    assert "frequency_penalty" in summary


def test_summarize_contact_score_uses_cluster_count_for_frequency_penalty():
    from app.services import contact_scoring as scoring

    duplicated = [
        {
            "horizon_code": "1m",
            "direction_hit": True,
            "excess_return": 0.05,
            "event_score": 78,
            "cluster_id": "cluster-gold-1",
            "event_kind": "price_call",
        }
        for _ in range(30)
    ]

    deduped = duplicated[:]
    summary = scoring.summarize_contact_score(
        contact_id="wxid_focus",
        evaluations=deduped,
        manual_rating=60,
    )

    assert summary["sample_size"] == 1
    assert summary["frequency_penalty"] == 0.0
    assert summary["accuracy_score"] >= 50
    assert summary["score_breakdown"]["direction_accuracy_score"] >= 50


def test_summarize_contact_score_ignores_non_actionable_events_for_accuracy():
    from app.services import contact_scoring as scoring

    evaluations = [
        {
            "horizon_code": "1m",
            "direction_hit": False,
            "excess_return": -0.08,
            "event_score": 22,
            "cluster_id": "cluster-roadshow",
            "event_kind": "roadshow_invite",
            "is_actionable": False,
        },
        {
            "horizon_code": "3m",
            "direction_hit": True,
            "excess_return": 0.12,
            "event_score": 84,
            "cluster_id": "cluster-stock",
            "event_kind": "price_call",
            "is_actionable": True,
        },
    ]

    summary = scoring.summarize_contact_score(
        contact_id="wxid_focus",
        evaluations=evaluations,
        manual_rating=60,
    )

    assert summary["sample_size"] == 1
    assert round(summary["hit_rate_overall"], 4) == 0.6
    assert summary["accuracy_score"] > 55


def test_summarize_contact_score_computes_service_value_from_event_mix():
    from app.services import contact_scoring as scoring

    now = datetime(2026, 4, 13, 9, 30, 0)
    evaluations = [
        {
            "horizon_code": "1m",
            "direction_hit": True,
            "excess_return": 0.08,
            "event_score": 82,
            "cluster_id": "cluster-gold-1",
            "event_kind": "price_call",
        },
        {
            "horizon_code": "3m",
            "direction_hit": True,
            "excess_return": 0.11,
            "event_score": 86,
            "cluster_id": "cluster-roadshow-1",
            "event_kind": "roadshow_invite",
        },
    ]
    event_rows = [
        {
            "source_time": now - timedelta(days=7),
            "event_kind": "price_call",
            "topic_key": "紫金矿业",
            "confidence": 0.88,
            "signal_strength": 0.88,
            "asset_code": "601899",
            "event_cluster_id": "cluster-gold-1",
        },
        {
            "source_time": now - timedelta(days=20),
            "event_kind": "roadshow_invite",
            "topic_key": "黄金板块",
            "confidence": 0.76,
            "signal_strength": 0.76,
            "asset_code": "518880",
            "event_cluster_id": "cluster-roadshow-1",
        },
        {
            "source_time": now - timedelta(days=35),
            "event_kind": "strategy_exchange",
            "topic_key": "贵金属",
            "confidence": 0.72,
            "signal_strength": 0.72,
            "asset_code": "518880",
            "event_cluster_id": "cluster-roadshow-1",
        },
    ]

    summary = scoring.summarize_contact_score(
        contact_id="wxid_focus",
        evaluations=evaluations,
        manual_rating=60,
        event_rows=event_rows,
        as_of=now,
    )

    assert summary["service_value_score"] > 50
    assert "value_breakdown" in summary
    assert summary["value_breakdown"]["roadshow_value_score"] > 50
    assert summary["value_breakdown"]["timeliness_score"] > 50
    assert summary["value_breakdown"]["coverage_depth_score"] > 50


def test_contact_scorecard_endpoint_returns_value_breakdown():
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation, ContactScoreSnapshot
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_value",
                name="王五",
                alias="王总",
                rating=73,
                stats={"manual_rating": 60},
            )
            db.add(contact)
            db.commit()

            roadshow = ContactPredictionEvent(
                contact_id="wxid_value",
                source_time=datetime(2026, 2, 1, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.81,
                horizon_flags={"1m": True, "3m": True, "1y": False},
                raw_text="建议参加黄金主题路演，并继续看好紫金矿业。",
                normalized_text="建议参加黄金主题路演并继续看好紫金矿业",
                status="evaluated",
                event_kind="roadshow_invite",
                topic_key="黄金主题",
                signal_strength=0.81,
                source_type="wechat",
                event_cluster_id="wxid_value|黄金主题|bullish|roadshow_invite|24640",
            )
            pitch = ContactPredictionEvent(
                contact_id="wxid_value",
                source_time=datetime(2026, 3, 1, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.88,
                horizon_flags={"1m": True, "3m": True, "1y": False},
                raw_text="继续看好紫金矿业未来一个月表现。",
                normalized_text="继续看好紫金矿业未来一个月表现",
                status="evaluated",
                event_kind="price_call",
                topic_key="紫金矿业",
                signal_strength=0.88,
                source_type="wechat",
                event_cluster_id="wxid_value|紫金矿业|bullish|price_call|24642",
            )
            db.add_all([roadshow, pitch])
            db.commit()
            db.refresh(roadshow)
            db.refresh(pitch)

            db.add_all(
                [
                    ContactPredictionEvaluation(
                        event_id=roadshow.id,
                        horizon_code="3m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        absolute_return=0.12,
                        excess_return=0.08,
                        event_score=83,
                        evaluated_at=datetime(2026, 5, 5, 15, 0, 0),
                    ),
                    ContactPredictionEvaluation(
                        event_id=pitch.id,
                        horizon_code="1m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        absolute_return=0.16,
                        excess_return=0.11,
                        event_score=88,
                        evaluated_at=datetime(2026, 4, 5, 15, 0, 0),
                    ),
                ]
            )
            db.commit()

            scoring.recompute_contact_scores(db, contact_ids={"wxid_value"}, as_of=datetime(2026, 5, 6, 10, 0, 0))
            payload = contacts_router.get_contact_scorecard("wxid_value", db=db)

            assert payload["score"]["service_value_score"] > 50
            assert "value_breakdown" in payload["score"]
            assert payload["score"]["value_breakdown"]["roadshow_value_score"] > 50
            assert payload["score"]["value_breakdown"]["signal_cleanliness_score"] > 50
            assert payload["timeline"][0]["service_value_score"] > 50
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_evaluate_prediction_event_skips_unmatured_horizons_without_fetch():
    from app.services import contact_scoring as scoring

    calls = []

    def fake_fetcher(asset_type, asset_code, start_date, end_date):
        calls.append((asset_type, asset_code))
        return [{"date": "2026-04-12", "close": 10.0}]

    event = {
        "id": 1,
        "source_time": datetime(2026, 4, 12, 9, 0, 0),
        "asset_type": "stock",
        "asset_code": "601899",
        "benchmark_code": "sh000300",
        "direction": "bullish",
        "horizon_flags": {"1m": True, "3m": True, "1y": True},
    }

    out = scoring.evaluate_prediction_event(
        event,
        as_of=datetime(2026, 4, 13, 9, 0, 0),
        price_fetcher=fake_fetcher,
    )

    assert out == []
    assert calls == []


def test_evaluate_prediction_events_to_db_skips_non_actionable_roadshows(monkeypatch):
    from app.models import ContactPredictionEvaluation, ContactPredictionEvent
    from app.services import contact_scoring as scoring

    calls = []

    def fake_fetch_market_series(*args, **kwargs):
        calls.append(args)
        return [{"date": "2026-01-01", "close": 10.0}, {"date": "2026-02-02", "close": 11.0}]

    monkeypatch.setattr(scoring, "fetch_market_series", fake_fetch_market_series)

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_research", name="张三", alias="银行研究员", rating=70))
            db.add(
                ContactPredictionEvent(
                    contact_id="wxid_research",
                    source_time=datetime(2026, 1, 1, 9, 0, 0),
                    asset_type="stock",
                    asset_code="600036",
                    asset_name="招商银行",
                    direction="neutral",
                    benchmark_code="sh000300",
                    confidence=0.45,
                    horizon_flags={"1m": True, "3m": False, "1y": False},
                    event_kind="roadshow_invite",
                    is_actionable=False,
                    raw_text="招商银行路演交流，欢迎报名参加。",
                    normalized_text="招商银行路演交流，欢迎报名参加。",
                    status="extracted",
                )
            )
            db.commit()

            result = scoring.evaluate_prediction_events_to_db(
                db,
                contact_ids={"wxid_research"},
                as_of=datetime(2026, 2, 5, 9, 0, 0),
            )

            assert result["evaluated"] == 0
            assert db.query(ContactPredictionEvaluation).count() == 0
            assert calls == []
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_evaluate_prediction_event_marks_risk_alert_hit_when_drawdown_is_large():
    from app.services import contact_scoring as scoring

    def fake_fetcher(asset_type, asset_code, start_date, end_date):
        return [
            {"date": "2026-01-01", "close": 10.0},
            {"date": "2026-01-15", "close": 8.2},
            {"date": "2026-01-31", "close": 9.4},
        ]

    event = {
        "id": 1,
        "source_time": datetime(2026, 1, 1, 9, 0, 0),
        "asset_type": "industry",
        "asset_code": "512480",
        "benchmark_code": "sh000300",
        "direction": "bearish",
        "event_kind": "risk_alert",
        "horizon_flags": {"1m": True, "3m": False, "1y": False},
    }

    out = scoring.evaluate_prediction_event(
        event,
        as_of=datetime(2026, 2, 5, 9, 0, 0),
        price_fetcher=fake_fetcher,
    )

    assert len(out) == 1
    assert out[0]["direction_hit"] is True
    assert out[0]["meta"]["risk_rule"] == "drawdown_or_negative_return"
    assert out[0]["meta"]["max_drawdown"] <= -0.15


def test_evaluate_prediction_event_adds_verification_metadata():
    from app.services import contact_scoring as scoring

    def fake_fetcher(asset_type, asset_code, start_date, end_date):
        if asset_type == "index":
            return [
                {"date": "2026-01-01", "close": 100.0},
                {"date": "2026-02-01", "close": 103.0},
                {"date": "2026-04-01", "close": 106.0},
            ]
        return [
            {"date": "2026-01-01", "close": 10.0},
            {"date": "2026-02-01", "close": 11.0},
            {"date": "2026-04-01", "close": 12.0},
        ]

    event = {
        "id": 1,
        "source_time": datetime(2026, 1, 1, 9, 0, 0),
        "asset_type": "stock",
        "asset_code": "601899",
        "benchmark_code": "sh000300",
        "direction": "bullish",
        "event_kind": "price_call",
        "horizon_flags": {"1m": True, "3m": True, "1y": False},
    }

    out = scoring.evaluate_prediction_event(
        event,
        as_of=datetime(2026, 4, 5, 9, 0, 0),
        price_fetcher=fake_fetcher,
    )

    assert [row["horizon_code"] for row in out] == ["1m", "3m"]
    assert out[0]["meta"]["verification_method"] == "asset_vs_benchmark"
    assert out[0]["meta"]["verification_grade"] in {"confirmed", "strong_confirmed"}
    assert out[0]["meta"]["signed_excess_return"] > 0


def test_backfill_prediction_event_metadata_updates_legacy_rows():
    from app.models import ContactPredictionEvent
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_focus",
                name="张三",
                alias="张总",
                rating=74,
                stats={"manual_rating": 60},
            )
            db.add(contact)
            db.commit()

            legacy = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_time=datetime(2026, 1, 5, 9, 0, 0),
                asset_type="industry",
                asset_code="512480",
                asset_name="半导体",
                direction="bearish",
                benchmark_code="sh000300",
                confidence=0.66,
                horizon_flags={"1m": True, "3m": True, "1y": False},
                raw_text="半导体未来一年压力仍大，建议回避。",
                normalized_text="半导体未来一年压力仍大建议回避",
                status="extracted",
            )
            db.add(legacy)
            db.commit()
            db.refresh(legacy)

            result = scoring.backfill_prediction_event_metadata(db, contact_ids={"wxid_focus"})
            refreshed = db.get(ContactPredictionEvent, legacy.id)

            assert result["updated"] == 1
            assert refreshed.event_kind == "risk_alert"
            assert refreshed.topic_key == "半导体"
            assert refreshed.event_cluster_id
            cluster = db.query(scoring.ContactSignalCluster).filter_by(id=refreshed.event_cluster_id).first()
            assert cluster is not None
            assert cluster.topic_key == "半导体"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_backfill_prediction_event_metadata_updates_benchmark_code():
    from app.models import ContactPredictionEvent
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_benchmark", name="张三", alias="科创研究员", rating=70))
            legacy = ContactPredictionEvent(
                contact_id="wxid_benchmark",
                source_time=datetime(2026, 1, 5, 9, 0, 0),
                asset_type="stock",
                asset_code="688111",
                asset_name="金山办公",
                direction="bullish",
                benchmark_code="sh000300",
                confidence=0.72,
                horizon_flags={"1m": True, "3m": False, "1y": False},
                raw_text="继续看好688111，未来一个月表现有望继续走强。",
                normalized_text="继续看好688111，未来一个月表现有望继续走强。",
                status="extracted",
            )
            db.add(legacy)
            db.commit()
            db.refresh(legacy)

            result = scoring.backfill_prediction_event_metadata(db, contact_ids={"wxid_benchmark"})
            refreshed = db.get(ContactPredictionEvent, legacy.id)

            assert result["updated"] == 1
            assert refreshed.benchmark_code == "sh000688"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_endpoint_returns_predictions_and_curve_data():
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation, ContactScoreSnapshot

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_focus",
                name="张三",
                alias="张总",
                rating=74,
                stats={"manual_rating": 60, "auto_rating": 80},
            )
            msg = Message(
                sender_id="wxid_focus",
                sender_name="张三",
                timestamp=datetime(2026, 1, 5, 9, 0, 0),
                content_text="继续看好601899，未来3个月跑赢沪深300。",
                direction="in",
                type="text",
                derived={"summary": "ai: 看好601899未来表现"},
            )
            db.add(contact)
            db.add(msg)
            db.commit()
            db.refresh(msg)

            event = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_message_id=msg.id,
                source_time=msg.timestamp,
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.82,
                horizon_flags={"1m": True, "3m": True, "1y": True},
                raw_text=msg.content_text,
                normalized_text="看好601899未来3个月跑赢沪深300",
                status="evaluated",
            )
            db.add(event)
            db.commit()
            db.refresh(event)

            pending_event = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_time=datetime.utcnow() - timedelta(days=10),
                asset_type="stock",
                asset_code="300750",
                asset_name="宁德时代",
                direction="bullish",
                benchmark_code="sz399006",
                confidence=0.76,
                horizon_flags={"1m": True, "3m": False, "1y": False},
                raw_text="继续看好宁德时代，一个月内景气改善。",
                normalized_text="继续看好宁德时代，一个月内景气改善",
                status="extracted",
            )
            db.add(pending_event)
            db.commit()

            db.add(
                ContactPredictionEvaluation(
                    event_id=event.id,
                    horizon_code="3m",
                    benchmark_code="sh000300",
                    entry_price=18.2,
                    evaluation_price=21.3,
                    benchmark_entry=3900.0,
                    benchmark_evaluation=4010.0,
                    absolute_return=0.1703,
                    excess_return=0.1421,
                    direction_hit=True,
                    event_score=86,
                    evaluated_at=datetime(2026, 4, 5, 15, 0, 0),
                )
            )
            db.add(
                ContactScoreSnapshot(
                    contact_id="wxid_focus",
                    score_total=74,
                    score_auto=80,
                    score_manual=60,
                    hit_rate_overall=1.0,
                    accuracy_1m=0.0,
                    accuracy_3m=1.0,
                    accuracy_1y=0.0,
                    excess_mean=0.1421,
                    stability_score=78,
                    frequency_penalty=0.0,
                    sample_size=1,
                    as_of=datetime(2026, 4, 5, 15, 0, 0),
                )
            )
            db.commit()

            payload = contacts_router.get_contact_scorecard("wxid_focus", db=db)

            assert payload["contact"]["id"] == "wxid_focus"
            assert payload["score"]["final_rating"] == 74
            assert payload["score"]["sample_size"] == 1
            assert "accuracy_score" in payload["score"]
            assert "service_value_score" in payload["score"]
            assert "score_breakdown" in payload["score"]
            validated_prediction = next(item for item in payload["predictions"] if item["asset_code"] == "601899")
            assert validated_prediction["evaluations"][0]["direction_hit"] is True
            assert payload["timeline"][0]["score_total"] == 74
            assert payload["analytics"]["total_predictions"] == 2
            assert payload["analytics"]["pending_predictions"] == 1
            assert payload["analytics"]["asset_summary"][0]["asset_code"] == "601899"
            assert payload["analytics"]["horizon_summary"][1]["horizon_code"] == "3m"
            assert payload["analytics"]["recent_hits"][0]["direction_hit"] is True
            assert payload["analytics"]["horizon_event_groups"]["3m"]["hits"][0]["direction_hit"] is True
            assert "sub_scores" in payload["analytics"]
            assert "recommended_action" in payload["analytics"]
            assert "top_hits" in payload["analytics"]
            assert "top_misses" in payload["analytics"]
            assert "cluster_topics" in payload["analytics"]
            assert "case_cards" in payload["analytics"]
            assert "annual_hit_list" in payload["analytics"]
            assert "annual_asset_leaders" in payload["analytics"]
            assert "return_distribution" in payload["analytics"]
            assert "score_explanation" in payload["analytics"]
            assert payload["analytics"]["score_explanation"]["drivers"]
            assert payload["analytics"]["pending_items"][0]["next_verification"]["horizon_code"] == "1m"
            assert payload["analytics"]["pending_items"][0]["next_verification"]["status"] == "pending"
            assert payload["analytics"]["pending_items"][0]["benchmark_name"] == "创业板指"
            assert payload["analytics"]["annual_hit_list"][0]["asset_code"] == "601899"
            assert payload["analytics"]["annual_asset_leaders"][0]["asset_code"] == "601899"
            assert payload["analytics"]["return_distribution"]["positive_count"] == 1
            assert payload["analytics"]["case_cards"][0]["case_type"] in {"hit", "miss"}
            assert validated_prediction["thesis_card"]["thesis_status"] in {"validated", "mixed", "disproved", "pending"}
            assert validated_prediction["thesis_card"]["best_horizon_code"] == "3m"
            assert validated_prediction["thesis_card"]["best_score"] == 86
            assert validated_prediction["thesis_card"]["latest_excess_return"] == 0.1421
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_list_contacts_exposes_compact_score_summary():
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_focus",
                name="张三",
                alias="张总",
                rating=76,
                stats={"manual_rating": 60, "auto_rating": 82, "sample_size": 3, "hit_rate_overall": 2 / 3},
            )
            db.add(contact)
            db.commit()

            event1 = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_time=datetime(2026, 1, 5, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.82,
                horizon_flags={"1m": True, "3m": True, "1y": True},
                raw_text="继续看好紫金矿业",
                normalized_text="看好紫金矿业",
                status="evaluated",
            )
            event2 = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_time=datetime(2026, 2, 7, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bearish",
                confidence=0.72,
                horizon_flags={"1m": True, "3m": True, "1y": True},
                raw_text="短期谨慎",
                normalized_text="紫金矿业短期谨慎",
                status="evaluated",
            )
            event3 = ContactPredictionEvent(
                contact_id="wxid_focus",
                source_time=datetime(2026, 3, 9, 9, 0, 0),
                asset_type="etf",
                asset_code="512480",
                asset_name="半导体ETF",
                direction="bullish",
                confidence=0.66,
                horizon_flags={"1m": True, "3m": True, "1y": True},
                raw_text="芯片etf可能反弹",
                normalized_text="芯片ETF短期反弹",
                status="extracted",
            )
            db.add_all([event1, event2, event3])
            db.commit()
            db.refresh(event1)
            db.refresh(event2)

            db.add_all(
                [
                    ContactPredictionEvaluation(
                        event_id=event1.id,
                        horizon_code="1m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        excess_return=0.12,
                        event_score=84,
                        evaluated_at=datetime(2026, 2, 6, 15, 0, 0),
                    ),
                    ContactPredictionEvaluation(
                        event_id=event2.id,
                        horizon_code="1m",
                        benchmark_code="sh000300",
                        direction_hit=False,
                        excess_return=-0.08,
                        event_score=34,
                        evaluated_at=datetime(2026, 3, 10, 15, 0, 0),
                    ),
                    ContactPredictionEvaluation(
                        event_id=event2.id,
                        horizon_code="3m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        excess_return=0.09,
                        event_score=78,
                        evaluated_at=datetime(2026, 5, 10, 15, 0, 0),
                    ),
                ]
            )
            db.commit()

            rows = contacts_router.list_contacts(
                limit=10,
                offset=0,
                include_labels=False,
                include_score_summary=True,
                db=db,
            )
            assert len(rows) == 1
            summary = rows[0].score_summary
            assert summary["total_predictions"] == 3
            assert summary["pending_predictions"] == 1
            assert summary["top_asset_name"] == "紫金矿业"
            assert round(summary["hit_rate_1m"], 4) == 0.5
            assert round(summary["hit_rate_3m"], 4) == 1.0
            assert "accuracy_score" in summary
            assert "service_value_score" in summary
            assert "recent_90d_score" in summary["sub_scores"]["recommendation_accuracy"]
            assert "delta_recent_90d" in summary["sub_scores"]["recommendation_accuracy"]
            assert "recommended_action" in summary
            assert "warning_flags" in summary
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_list_contacts_exposes_sales_flag_for_filtering():
    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(
                Contact(
                    id="wxid_sales",
                    name="程一天中信建投销售",
                    alias="程一天",
                    rating=65,
                    stats={"manual_rating": 60},
                )
            )
            db.add(
                Contact(
                    id="wxid_research",
                    name="陈晨国海证券能源",
                    alias="陈晨",
                    rating=78,
                    stats={"manual_rating": 60},
                )
            )
            db.commit()

            rows = contacts_router.list_contacts(limit=10, offset=0, include_labels=False, include_score_summary=True, db=db)
            by_id = {row.id: row.model_dump() for row in rows}

            assert by_id["wxid_sales"]["role"] == "sales"
            assert by_id["wxid_sales"]["is_sales"] is True
            assert by_id["wxid_research"]["role"] == "research"
            assert by_id["wxid_research"]["is_sales"] is False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_watch_endpoint_and_summary_fields():
    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_watch",
                name="赵六",
                alias="赵总",
                rating=68,
                stats={"manual_rating": 58, "auto_rating": 72},
            )
            db.add(contact)
            db.commit()

            payload = contacts_router.toggle_contact_watch("wxid_watch", enabled=True, reason="继续观察回撤修复", db=db)
            assert payload["enabled"] is True
            assert payload["status"] == "watching"
            assert payload["reason"] == "继续观察回撤修复"

            rows = contacts_router.list_contacts(limit=10, offset=0, include_labels=False, include_score_summary=True, db=db)
            assert len(rows) == 1
            assert rows[0].watch["enabled"] is True
            assert rows[0].watch["reason"] == "继续观察回撤修复"
            assert rows[0].score_summary["watching"] is True
            assert rows[0].score_summary["watch_reason"] == "继续观察回撤修复"

            scorecard = contacts_router.get_contact_scorecard("wxid_watch", db=db)
            assert scorecard["contact"]["watch"]["enabled"] is True
            assert scorecard["contact"]["watch"]["reason"] == "继续观察回撤修复"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_includes_primary_asset_market_curve(monkeypatch):
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_curve",
                name="李四",
                alias="李总",
                rating=81,
                stats={"manual_rating": 65, "auto_rating": 88, "sample_size": 2, "hit_rate_overall": 1.0},
            )
            db.add(contact)
            db.commit()

            event = ContactPredictionEvent(
                contact_id="wxid_curve",
                source_time=datetime(2026, 2, 1, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.9,
                horizon_flags={"1m": True, "3m": True, "1y": True},
                raw_text="继续看好紫金矿业",
                normalized_text="看好紫金矿业未来继续上涨",
                status="evaluated",
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            db.add(
                ContactPredictionEvaluation(
                    event_id=event.id,
                    horizon_code="1m",
                    benchmark_code="sh000300",
                    direction_hit=True,
                    excess_return=0.11,
                    event_score=86,
                    evaluated_at=datetime(2026, 3, 1, 15, 0, 0),
                )
            )
            db.commit()

            monkeypatch.setattr(
                "app.services.contact_scoring.fetch_market_series",
                lambda asset_type, asset_code, start_date, end_date, config=None: [
                    {"date": "2026-01-28", "close": 17.8},
                    {"date": "2026-02-01", "close": 18.2},
                    {"date": "2026-02-15", "close": 19.1},
                    {"date": "2026-03-01", "close": 20.4},
                ],
            )

            payload = contacts_router.get_contact_scorecard("wxid_curve", db=db)

            assert payload["market_curve"]["asset_code"] == "601899"
            assert payload["market_curve"]["asset_name"] == "紫金矿业"
            assert payload["market_curve"]["count"] == 4
            assert payload["market_curve"]["items"][0]["close"] == 17.8
            assert payload["market_curve"]["anchor_points"][0]["direction"] == "bullish"
            assert payload["market_curves"][0]["asset_code"] == "601899"
            assert payload["market_curves"][0]["items"][0]["close"] == 17.8
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_includes_multiple_asset_market_curves(monkeypatch):
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_multi_curve", name="王五", alias="王总", rating=88))
            db.commit()

            rows = [
                ("601899", "紫金矿业", datetime(2026, 2, 1, 9, 0, 0), 90),
                ("300750", "宁德时代", datetime(2026, 2, 5, 9, 0, 0), 82),
            ]
            for code, name, source_time, score in rows:
                event = ContactPredictionEvent(
                    contact_id="wxid_multi_curve",
                    source_time=source_time,
                    asset_type="stock",
                    asset_code=code,
                    asset_name=name,
                    direction="bullish",
                    confidence=0.86,
                    horizon_flags={"1m": True},
                    raw_text=f"继续看好{name}",
                    normalized_text=f"看好{name}未来继续上涨",
                    status="evaluated",
                )
                db.add(event)
                db.commit()
                db.refresh(event)
                db.add(ContactPredictionEvaluation(event_id=event.id, horizon_code="1m", direction_hit=True, excess_return=0.08, event_score=score))
            db.commit()

            def fake_fetch(asset_type, asset_code, start_date, end_date, config=None):
                base = 10 if asset_code == "601899" else 100
                return [
                    {"date": "2026-02-01", "close": base},
                    {"date": "2026-02-15", "close": base * 1.08},
                    {"date": "2026-03-01", "close": base * 1.15},
                ]

            monkeypatch.setattr("app.services.contact_scoring.fetch_market_series", fake_fetch)

            payload = contacts_router.get_contact_scorecard("wxid_multi_curve", db=db)

            codes = [item["asset_code"] for item in payload["market_curves"]]
            assert codes[:2] == ["601899", "300750"]
            assert len(payload["market_curves"]) == 2
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_prioritizes_latest_pending_assets_and_exposes_market_freshness(monkeypatch):
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_recent_curves", name="周七", alias="周总", rating=86))
            db.commit()

            old_event = ContactPredictionEvent(
                contact_id="wxid_recent_curves",
                source_time=datetime(2026, 2, 1, 9, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.9,
                horizon_flags={"1m": True},
                raw_text="长期看好紫金矿业",
                normalized_text="长期看好紫金矿业",
                status="evaluated",
            )
            db.add(old_event)
            db.commit()
            db.refresh(old_event)
            db.add(
                ContactPredictionEvaluation(
                    event_id=old_event.id,
                    horizon_code="1m",
                    direction_hit=True,
                    excess_return=0.2,
                    event_score=99,
                )
            )

            recent_events = [
                ("300750", "宁德时代", datetime(2026, 7, 12, 10, 0, 0)),
                ("300750", "宁德时代", datetime(2026, 7, 11, 10, 0, 0)),
                ("688256", "寒武纪", datetime(2026, 7, 10, 10, 0, 0)),
            ]
            for code, name, source_time in recent_events:
                db.add(
                    ContactPredictionEvent(
                        contact_id="wxid_recent_curves",
                        source_time=source_time,
                        asset_type="stock",
                        asset_code=code,
                        asset_name=name,
                        direction="bullish",
                        confidence=0.88,
                        horizon_flags={"1m": True},
                        raw_text=f"继续看好{name}",
                        normalized_text=f"继续看好{name}",
                        status="extracted",
                    )
                )
            db.commit()

            def fake_fetch(asset_type, asset_code, start_date, end_date, config=None):
                prices = {"300750": (240.0, 252.5), "688256": (1380.0, 1428.8), "601899": (17.8, 18.6)}
                first, last = prices[asset_code]
                return [
                    {"date": "2026-07-10", "close": first},
                    {"date": "2026-07-13", "close": last},
                ]

            monkeypatch.setattr("app.services.contact_scoring.fetch_market_series", fake_fetch)

            payload = contacts_router.get_contact_scorecard("wxid_recent_curves", db=db)
            curves = payload["market_curves"]

            assert [curve["asset_code"] for curve in curves] == ["300750", "688256", "601899"]
            assert len({curve["asset_code"] for curve in curves}) == len(curves)
            assert curves[0]["is_pending"] is True
            assert curves[0]["latest_recommendation_time"] == "2026-07-12T10:00:00"
            assert curves[0]["latest_market_date"] == "2026-07-13"
            assert curves[0]["latest_close"] == 252.5
            assert isinstance(curves[0]["data_age_days"], int)
            assert curves[0]["data_age_days"] >= 0
            assert curves[-1]["is_pending"] is False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_groups_repeated_view_anchors_by_date_and_direction(monkeypatch):
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            db.add(Contact(id="wxid_anchor", name="赵六", alias="赵总", rating=82))
            db.commit()

            rows = [
                (datetime(2026, 2, 1, 9, 0, 0), "bullish", "第一次看好紫金矿业"),
                (datetime(2026, 2, 1, 15, 0, 0), "bullish", "继续看好紫金矿业"),
                (datetime(2026, 2, 15, 9, 0, 0), "bearish", "短期看空紫金矿业"),
            ]
            for source_time, direction, text in rows:
                event = ContactPredictionEvent(
                    contact_id="wxid_anchor",
                    source_time=source_time,
                    asset_type="stock",
                    asset_code="601899",
                    asset_name="紫金矿业",
                    direction=direction,
                    confidence=0.8,
                    horizon_flags={"1m": True},
                    raw_text=text,
                    normalized_text=text,
                    status="evaluated",
                )
                db.add(event)
                db.commit()
                db.refresh(event)
                db.add(ContactPredictionEvaluation(event_id=event.id, horizon_code="1m", direction_hit=True, excess_return=0.05, event_score=80))
            db.commit()

            monkeypatch.setattr(
                "app.services.contact_scoring.fetch_market_series",
                lambda asset_type, asset_code, start_date, end_date, config=None: [
                    {"date": "2026-02-01", "close": 18.2},
                    {"date": "2026-02-15", "close": 19.1},
                    {"date": "2026-03-01", "close": 20.4},
                ],
            )

            payload = contacts_router.get_contact_scorecard("wxid_anchor", db=db)
            anchors = payload["market_curves"][0]["anchor_points"]

            assert anchors[0]["date"] == "2026-02-01"
            assert anchors[0]["direction"] == "bullish"
            assert anchors[0]["count"] == 2
            assert anchors[0]["label"] == "看好 ×2"
            assert anchors[1]["direction"] == "bearish"
            assert anchors[1]["label"] == "看空"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_includes_event_timeline_categories():
    from app.models import ContactPredictionEvent

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_timeline",
                name="王五",
                alias="王总",
                rating=69,
                stats={"manual_rating": 58, "auto_rating": 74, "sample_size": 3, "hit_rate_overall": 0.66},
            )
            db.add(contact)
            db.commit()

            db.add_all(
                [
                    ContactPredictionEvent(
                        contact_id="wxid_timeline",
                        source_time=datetime(2026, 3, 1, 10, 0, 0),
                        asset_type="stock",
                        asset_code="600036",
                        asset_name="招商银行",
                        direction="bullish",
                        confidence=0.78,
                        raw_text="建议下周来参加我们银行板块路演交流。",
                        normalized_text="建议下周来参加我们银行板块路演交流",
                        status="extracted",
                    ),
                    ContactPredictionEvent(
                        contact_id="wxid_timeline",
                        source_time=datetime(2026, 3, 3, 9, 0, 0),
                        asset_type="index",
                        asset_code="sh000300",
                        asset_name="沪深300",
                        direction="bearish",
                        confidence=0.66,
                        raw_text="这里短期风险较大，建议谨慎。",
                        normalized_text="这里短期风险较大建议谨慎",
                        status="extracted",
                    ),
                    ContactPredictionEvent(
                        contact_id="wxid_timeline",
                        source_time=datetime(2026, 3, 5, 13, 0, 0),
                        asset_type="stock",
                        asset_code="601899",
                        asset_name="紫金矿业",
                        direction="bullish",
                        confidence=0.82,
                        raw_text="继续推荐紫金矿业，适合做配置。",
                        normalized_text="继续推荐紫金矿业适合做配置",
                        status="extracted",
                    ),
                ]
            )
            db.commit()

            payload = contacts_router.get_contact_scorecard("wxid_timeline", db=db)

            kinds = [item["event_kind"] for item in payload["analytics"]["event_timeline"]]
            assert "roadshow_invite" in kinds
            assert "risk_alert" in kinds
            assert "stock_pitch" in kinds
            assert payload["analytics"]["sub_scores"]["roadshow_value"]["samples"] >= 1
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_contact_scorecard_annual_hit_list_excludes_non_actionable_hits():
    from app.models import ContactPredictionEvent, ContactPredictionEvaluation

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_annual",
                name="赵六",
                alias="赵总",
                rating=70,
                stats={"manual_rating": 60, "auto_rating": 75},
            )
            db.add(contact)
            db.commit()

            roadshow = ContactPredictionEvent(
                contact_id="wxid_annual",
                source_time=datetime(2026, 3, 1, 10, 0, 0),
                asset_type="stock",
                asset_code="002405",
                asset_name="四维图新",
                direction="bearish",
                confidence=0.7,
                event_kind="roadshow_invite",
                is_actionable=False,
                normalized_text="自动驾驶主题调研邀请",
                raw_text="自动驾驶主题调研邀请",
                status="evaluated",
            )
            thesis = ContactPredictionEvent(
                contact_id="wxid_annual",
                source_time=datetime(2026, 3, 2, 10, 0, 0),
                asset_type="stock",
                asset_code="601899",
                asset_name="紫金矿业",
                direction="bullish",
                confidence=0.88,
                event_kind="stock_pitch",
                is_actionable=True,
                normalized_text="继续看好紫金矿业",
                raw_text="继续看好紫金矿业",
                status="evaluated",
            )
            db.add_all([roadshow, thesis])
            db.commit()
            db.refresh(roadshow)
            db.refresh(thesis)

            db.add_all(
                [
                    ContactPredictionEvaluation(
                        event_id=roadshow.id,
                        horizon_code="1m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        absolute_return=-0.12,
                        excess_return=-0.1,
                        event_score=90,
                        evaluated_at=datetime(2026, 4, 1, 15, 0, 0),
                    ),
                    ContactPredictionEvaluation(
                        event_id=thesis.id,
                        horizon_code="1m",
                        benchmark_code="sh000300",
                        direction_hit=True,
                        absolute_return=0.18,
                        excess_return=0.14,
                        event_score=92,
                        evaluated_at=datetime(2026, 4, 2, 15, 0, 0),
                    ),
                ]
            )
            db.commit()

            payload = contacts_router.get_contact_scorecard("wxid_annual", db=db)

            assert len(payload["analytics"]["annual_hit_list"]) == 1
            assert payload["analytics"]["annual_hit_list"][0]["asset_code"] == "601899"
            assert payload["analytics"]["annual_asset_leaders"][0]["asset_code"] == "601899"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_backfill_prediction_event_metadata_sets_non_actionable_flag_for_roadshow():
    from app.models import ContactPredictionEvent
    from app.services import contact_scoring as scoring

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            contact = Contact(
                id="wxid_non_actionable",
                name="钱七",
                alias="钱总",
                rating=66,
                stats={"manual_rating": 58},
            )
            db.add(contact)
            db.commit()

            legacy = ContactPredictionEvent(
                contact_id="wxid_non_actionable",
                source_time=datetime(2026, 3, 9, 7, 49, 50),
                asset_type="stock",
                asset_code="002405",
                asset_name="四维图新",
                direction="bearish",
                confidence=0.7,
                raw_text="自动驾驶主题调研邀请，欢迎报名参加四维图新交流。",
                normalized_text="自动驾驶主题调研邀请欢迎报名参加四维图新交流",
                status="evaluated",
            )
            db.add(legacy)
            db.commit()
            db.refresh(legacy)

            result = scoring.backfill_prediction_event_metadata(db, contact_ids={"wxid_non_actionable"})
            refreshed = db.get(ContactPredictionEvent, legacy.id)

            assert result["updated"] == 1
            assert refreshed.event_kind == "roadshow_invite"
            assert refreshed.is_actionable is False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
