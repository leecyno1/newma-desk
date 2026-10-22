from __future__ import annotations

import json
from unittest.mock import patch
from datetime import date

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research.event_flow import EventFlowEngine, EventFlowError, resolve_event_flow_snapshot
from instock.web.event_flow_handler import EventFlowHandler


class DeskEventProvider:
    def get_security_event_flow(self, symbol):
        return {
            "sources": {
                "fund_flow": {
                    "id": "fund_flow", "label": "主力资金", "state": "available",
                    "endpoint": "/api/research/api/fund-flow", "units": {"main_net": "元"},
                    "records": 6,
                    "data": [
                        {"date": f"2026-08-{day:02d}", "main_net": value}
                        for day, value in zip(range(10, 4, -1), [2e8, 1e8, -5e7, 8e7, 6e7, -2e7])
                    ],
                },
                "margin": {
                    "id": "margin", "label": "融资融券", "state": "available",
                    "endpoint": "/api/research/api/margin", "units": {"rzye": "元"},
                    "records": 5,
                    "data": [
                        {"date": f"2026-08-{day:02d}", "rzye": 19e9, "rzmre": 2e9, "rzche": 1.5e9, "rqye": 8e7}
                        for day in range(10, 5, -1)
                    ],
                },
                "dragon_tiger": {
                    "id": "dragon_tiger", "label": "龙虎榜", "state": "available",
                    "endpoint": "/api/research/api/dragon-tiger", "units": {"net_buy": "万元"},
                    "records": 1,
                    "data": {
                        "records": [{"date": "2026-07-28", "reason": "日跌幅达到15%", "net_buy": 192753.5, "turnover": 6.16}],
                        "institution": {"net_amt": 210775.1},
                    },
                },
                "block_trade": {
                    "id": "block_trade", "label": "大宗交易", "state": "empty",
                    "endpoint": "/api/research/api/block-trade", "units": {"amount": "元"},
                    "records": 0, "data": [],
                },
                "holders": {
                    "id": "holders", "label": "股东户数", "state": "available",
                    "endpoint": "/api/research/api/holders", "units": {"holder_num": "户"},
                    "records": 1,
                    "data": [{"date": "2026-03-31", "published_at": "2026-04-25", "holder_num": 155489, "change_ratio": 11.48, "avg_shares": 0}],
                },
                "dividend": {
                    "id": "dividend", "label": "分红送转", "state": "available",
                    "endpoint": "/api/research/api/dividend", "units": {"bonus_rmb": "元/每10股"},
                    "records": 1,
                    "data": [{"date": "2026-06-11", "published_at": "2026-06-04", "bonus_rmb": 10, "transfer_ratio": 4, "bonus_ratio": None, "plan": "实施分配"}],
                },
                "lockup": {
                    "id": "lockup", "label": "限售解禁", "state": "available",
                    "endpoint": "/api/research/api/lockup", "units": {"able_shares": "万股"},
                    "records": 1,
                    "data": {"history": [{"date": "2025-06-13", "type": "股权激励限售股份", "able_shares": 153.4, "ratio": 0.0017}], "upcoming": []},
                },
            },
            "failures": [],
        }

    def get_security_announcements(self, symbol):
        return [{"date": "2026-07-20", "title": "2026年半年度业绩预告", "type": "业绩预告", "url": "https://example.test/a"}]

    def get_security_reports(self, symbol, pages=1):
        return [{"publishDate": "2026-07-26", "title": "公司事件点评", "orgSName": "研究机构", "emRatingName": "买入", "pdfUrl": "https://example.test/r.pdf"}]

    def get_security_news(self, symbol, limit=10):
        return [{"发布时间": "2026-08-11 09:30:00", "新闻标题": "资金数据更新", "文章来源": "公开媒体", "新闻链接": "https://example.test/n"}]


def test_holder_observation_is_not_available_before_disclosure():
    engine = EventFlowEngine()
    rows = [{'date': '2026-06-30', 'published_at': '2026-08-25',
             'holder_num': 257067, 'change_ratio': 65.328, 'avg_shares': 5423.7093}]
    assert engine._normalize_holders('300502', '2026-08-24', rows) == []
    event = engine._normalize_holders('300502', '2026-08-25', rows)[0]
    assert event['occurred_at'] == '2026-08-25'
    assert event['details']['observation_date'] == '2026-06-30'
    assert event['details']['published_at'] == '2026-08-25'
    assert event['details']['average_shares_per_holder'] == 5423.71


def test_dividend_plan_uses_disclosure_not_future_ex_date_and_keeps_unknowns():
    row = {'date': '2026-06-11', 'published_at': '2026-06-04', 'bonus_rmb': 10,
           'transfer_ratio': 4, 'bonus_ratio': None, 'plan': '实施分配'}
    engine = EventFlowEngine()
    assert engine._normalize_dividend('300502', '2026-06-03', [row]) == []
    event = engine._normalize_dividend('300502', '2026-06-04', [row])[0]
    assert event['occurred_at'] == '2026-06-04'
    assert event['details']['effective_at'] == '2026-06-11'
    assert event['details']['bonus_shares_per_10'] is None
    assert '转增 4' in event['title'] and '未知' in event['title']
    assert event['evidence_strength'] == 'weak'


def test_undated_dividend_proposal_is_visible_today_without_claiming_payment():
    today = date.today().isoformat()
    event = EventFlowEngine()._normalize_dividend('300502', today, [
        {'date': None, 'published_at': today, 'plan': '董事会预案', 'bonus_rmb': 0,
         'transfer_ratio': 0, 'bonus_ratio': 0}])[0]
    assert '董事会预案' in event['title']
    assert event['details']['cash_dividend_cny_per_10_shares'] == 0
    assert event['details']['effective_at'] is None
    assert '不代表已到账' in event['details']['data_quality_note']


@pytest.mark.parametrize('kind', ['dividend', 'lockup'])
def test_corporate_action_unknown_or_late_disclosure_is_not_historical_evidence(kind):
    engine = EventFlowEngine()
    for published in (None, '2026-08-25', 'invalid'):
        row = {'date': '2026-06-11', 'published_at': published, 'bonus_rmb': 10, 'ratio': 0.1}
        data = [row] if kind == 'dividend' else {'history': [row]}
        assert getattr(engine, f'_normalize_{kind}')('300502', '2026-08-24', data) == []


def test_today_lockup_is_upcoming_and_missing_ratio_is_not_zero_or_strong():
    today = date.today().isoformat()
    row = {'date': today, 'able_shares': None, 'ratio': None, 'type': '限售股'}
    event = EventFlowEngine()._normalize_lockup('300502', today, {'history': [], 'upcoming': [row]})[0]
    assert event['details']['effective_at'] == today
    assert event['details']['able_shares_10k'] is None
    assert event['details']['unlock_ratio'] is None
    assert event['evidence_strength'] == 'weak'
    assert '未知' in event['title']
    assert '不代表实际减持' in event['details']['data_quality_note']


def test_lockup_known_disclosure_retains_future_schedule_in_historical_query():
    row = {'date': '2026-08-30', 'published_at': '2026-08-20', 'ratio': 0.1, 'able_shares': 200}
    event = EventFlowEngine()._normalize_lockup('300502', '2026-08-24', {'history': [row]})[0]
    assert event['occurred_at'] == '2026-08-20'
    assert event['direction'] == 'negative'
    assert event['details']['effective_at'] == '2026-08-30'


def test_holder_unknown_values_and_publication_are_not_flat_or_zero():
    from datetime import date
    engine = EventFlowEngine()
    rows = [{'date': '2026-06-30'}]
    assert engine._normalize_holders('300502', '2026-08-24', rows) == []
    event = engine._normalize_holders('300502', date.today().isoformat(), rows)[0]
    assert event['details']['holder_count'] is None
    assert event['details']['holder_change_pct'] is None
    assert event['details']['average_shares_per_holder'] is None
    assert event['details']['data_quality_note']
    assert '未知' in event['title']
    assert '持平' not in event['title']
    assert event['evidence_strength'] == 'weak'


def test_holder_uses_last_disclosed_period_and_preserves_real_zero_change():
    rows = [
        {'date': '2026-06-30', 'published_at': '2026-08-25', 'change_ratio': 50},
        {'date': '2026-03-31', 'published_at': '2026-04-25', 'holder_num': 100,
         'change_ratio': 0, 'avg_shares': 1000, 'avg_shares_basis': 'total_a_shares_per_holder'},
    ]
    event = EventFlowEngine()._normalize_holders('300502', '2026-07-01', rows)[0]
    assert event['details']['observation_date'] == '2026-03-31'
    assert event['details']['holder_change_pct'] == 0
    assert '持平 0.00%' in event['title']
    assert event['evidence_strength'] == 'strong'


@pytest.mark.parametrize('kind', ['holder_change', 'dividend', 'lockup'])
def test_historical_handoff_does_not_accept_old_snapshot_without_disclosure(kind):
    packet = _packet()
    packet['events'] = [{**packet['events'][0], 'type': kind}]
    result = EventFlowEngine().analyze(packet)
    resolved, warnings = resolve_event_flow_snapshot(result['snapshot']['snapshot_id'], as_of='2026-08-11')
    assert resolved['alerts'] == []
    assert any('披露' in text for text in warnings)


@pytest.mark.parametrize('rows,expected', [
    ([{'amount': 100, 'premium_pct': 0}], 0),
    ([{'amount': 100, 'premium_pct': -2}, {'amount': 300, 'premium_pct': 2}], 1),
    ([{'amount': 100, 'premium_pct': None}], None),
    ([{'amount': 100, 'premium_pct': 2}, {'amount': 100, 'premium_pct': None}], None),
    ([{'amount': None, 'premium_pct': 2}], None),
    ([{'amount': 0, 'premium_pct': 0}], None),
])
def test_weighted_premium_never_assumes_missing_trades_are_at_par(rows, expected):
    event = EventFlowEngine()._normalize_block_trade('300502', '2026-08-11',
        [{'date': '2026-08-10', **row} for row in rows])[0]
    assert event['details']['weighted_premium_pct'] == expected
    if expected is None:
        assert '待核验' in event['title']
        assert event['evidence_strength'] == 'weak'
        assert event['details']['data_quality_note']
    else:
        assert event['evidence_strength'] == 'strong'


def test_missing_numeric_fields_remain_partial_in_company_handoff():
    engine = EventFlowEngine()
    packet = _packet()
    packet['events'] = engine._normalize_block_trade('300502', packet['as_of'],
        [{'date': '2026-08-10', 'amount': 100}])
    result = engine.analyze(packet)
    assert result['data_state'] == 'partial'
    resolved, warnings = resolve_event_flow_snapshot(result['snapshot']['snapshot_id'])
    assert any('数值' in text for text in warnings)
    assert resolved['alerts'][0]['details']['weighted_premium_pct'] is None


def test_explicit_future_disclosure_is_rejected_in_packet():
    packet = _packet()
    packet['events'] = [{**packet['events'][0], 'details': {'published_at': '2026-08-25'}}]
    with pytest.raises(EventFlowError, match='published_at'):
        EventFlowEngine().analyze(packet)


def test_old_snapshot_replay_filters_holder_disclosure_not_just_period():
    engine = EventFlowEngine()
    packet = _packet()
    packet['as_of'] = '2026-08-25'
    packet['events'] = [{**packet['events'][0], 'type': 'holder_change',
        'occurred_at': '2026-06-30', 'details': {'published_at': '2026-08-25'}}]
    result = engine.analyze(packet)
    resolved, warnings = resolve_event_flow_snapshot(result['snapshot']['snapshot_id'], as_of='2026-08-11')
    assert resolved['summary']['deduplicated_events'] == 0
    assert any('披露' in text for text in warnings)


def _daily_rows(count, **metrics):
    import pandas as pd
    return [{'date': day.strftime('%Y-%m-%d'), **metrics}
            for day in pd.bdate_range(end='2026-08-10', periods=count)[::-1]]


@pytest.mark.parametrize('source,metrics,field', [
    ('fund_flow', {'main_net': 100}, 'main_net_5d_cny'),
    ('margin', {'rzmre': 100, 'rzche': 50, 'rzye': 1000, 'rqye': 0}, 'financing_net_5d_cny'),
])
def test_short_flow_sample_does_not_become_a_five_day_total(source, metrics, field):
    event = getattr(EventFlowEngine(), f'_normalize_{source}')('300502', '2026-08-11', _daily_rows(3, **metrics))[0]
    assert event['details'][field] is None
    assert event['details']['window_5d_records'] == 3
    assert event['details']['window_5d_valid_records'] == 3
    assert event['details']['five_day_abs_percentile_pct'] is None
    assert event['direction'] == 'neutral'
    assert '待核验' in event['title']


def test_missing_flow_is_not_zero_and_does_not_compress_the_window():
    rows = _daily_rows(30, main_net=10)
    rows[2]['main_net'] = None
    event = EventFlowEngine()._normalize_fund_flow('300502', '2026-08-11', rows)[0]
    assert event['details']['main_net_5d_cny'] is None
    assert event['details']['main_net_20d_cny'] is None
    assert event['details']['window_5d_valid_records'] == 4
    assert event['details']['window_20d_valid_records'] == 19
    assert event['direction'] == 'neutral'
    assert event['evidence_strength'] == 'weak'


def test_missing_repayment_cannot_be_inferred_from_financing_balance():
    rows = _daily_rows(30, rzmre=100, rzche=50, rzye=1000, rqye=0)
    rows[1]['rzche'] = None
    rows[0]['rzye'] = None
    event = EventFlowEngine()._normalize_margin('300502', '2026-08-11', rows)[0]
    assert event['details']['financing_net_5d_cny'] is None
    assert event['details']['financing_balance_cny'] is None
    assert event['details']['securities_lending_balance_cny'] == 0
    assert '融资余额 未知' in event['title']


def test_flow_duplicates_do_not_inflate_totals_and_conflicts_stay_unknown():
    rows = _daily_rows(30, main_net=10)
    engine = EventFlowEngine()
    event = engine._normalize_fund_flow('300502', '2026-08-11', [rows[0], *rows])[0]
    assert event['details']['main_net_5d_cny'] == 50
    assert event['details']['window_5d_start'] == rows[4]['date']
    conflict = engine._normalize_fund_flow('300502', '2026-08-11', [{**rows[0], 'main_net': 99}, *rows])[0]
    assert conflict['details']['main_net_5d_cny'] is None
    assert conflict['details']['latest_main_net_cny'] is None


def test_percentile_requires_twenty_complete_prior_windows_excluding_current():
    engine = EventFlowEngine()
    rows = _daily_rows(5, main_net=0)
    event = engine._normalize_fund_flow('300502', '2026-08-11', rows)[0]
    assert event['details']['main_net_5d_cny'] == 0
    assert event['details']['main_net_20d_cny'] is None
    assert event['details']['five_day_abs_percentile_pct'] is None
    assert event['details']['percentile_sample_count'] == 0
    rows = _daily_rows(30, main_net=0)
    rows[0]['main_net'] = 10
    event = engine._normalize_fund_flow('300502', '2026-08-11', rows)[0]
    assert event['details']['main_net_20d_cny'] == 10
    assert event['details']['five_day_abs_percentile_pct'] == 100
    assert event['details']['percentile_sample_count'] == 25
    assert event['details']['data_quality_note'] is None


def test_prior_percentile_windows_with_missing_values_are_not_zero_filled():
    rows = _daily_rows(30, main_net=10)
    rows[10]['main_net'] = None
    event = EventFlowEngine()._normalize_fund_flow('300502', '2026-08-11', rows)[0]
    assert event['details']['main_net_5d_cny'] == 50
    assert event['details']['percentile_sample_count'] == 20
    assert event['details']['main_net_20d_cny'] is None


def test_flat_flow_reference_uses_mid_rank_not_false_extreme():
    event = EventFlowEngine()._normalize_fund_flow('300502', '2026-08-11', _daily_rows(30, main_net=0))[0]
    assert event['details']['five_day_abs_percentile_pct'] == 50
    assert event['direction'] == 'neutral'


def test_flow_window_gap_survives_packet_and_company_handoff():
    engine = EventFlowEngine()
    packet = _packet()
    packet['events'] = engine._normalize_fund_flow('300502', packet['as_of'], _daily_rows(3, main_net=100))
    result = engine.analyze(packet)
    assert result['data_state'] == 'partial'
    resolved, warnings = resolve_event_flow_snapshot(result['snapshot']['snapshot_id'])
    assert any('样本' in warning for warning in warnings)
    assert resolved['alerts'][0]['details']['main_net_5d_cny'] is None


def _packet():
    return {
        "schema_version": "instock-event-flow-packet-v1",
        "as_of": "2026-08-11",
        "market": "CN",
        "events": [
            {
                "id": "flow-1", "type": "fund_flow", "symbol": "300502",
                "occurred_at": "2026-08-10", "title": "主力资金净流入",
                "direction": "positive", "magnitude_score": 80,
                "evidence_strength": "strong", "source_ref": "desk://flow/300502/20260810",
            },
            {
                "id": "flow-duplicate", "type": "fund_flow", "symbol": "300502",
                "occurred_at": "2026-08-10", "title": "主力资金净流入重复记录",
                "direction": "positive", "magnitude_score": 40,
                "evidence_strength": "medium", "source_ref": "desk://flow/300502/20260810",
            },
            {
                "id": "risk-1", "type": "announcement", "symbol": "300502",
                "occurred_at": "2026-08-09", "title": "股东减持计划",
                "direction": "negative", "magnitude_score": 70,
                "evidence_strength": "medium", "source_ref": "desk://announcement/300502/risk-1",
            },
            {
                "id": "report-1", "type": "report", "symbol": "000001",
                "occurred_at": "2026-06-01", "title": "行业跟踪报告",
                "direction": "neutral", "magnitude_score": 50,
                "evidence_strength": "weak", "source_ref": "desk://report/000001/1",
            },
        ],
    }


def test_event_flow_deduplicates_scores_freshness_and_groups_symbols():
    get_analysis_snapshot_registry().clear()
    result = EventFlowEngine().analyze(_packet())

    assert result["engine"]["name"] == "instock-event-flow"
    assert result["summary"] == {
        "input_events": 4,
        "deduplicated_events": 3,
        "duplicates_removed": 1,
        "fresh_events": 2,
        "stale_events": 1,
        "symbols": 2,
        "top_event_id": "flow-1",
    }
    assert result["alerts"][0]["id"] == "flow-1"
    assert result["alerts"][0]["freshness"] == "fresh"
    assert result["alerts"][-1]["freshness"] == "stale"
    stock = next(item for item in result["symbol_summary"] if item["symbol"] == "300502")
    assert stock["positive_events"] == 1
    assert stock["negative_events"] == 1
    assert stock["top_event_id"] == "flow-1"
    assert result["snapshot"]["snapshot_id"].startswith("instock-event-flow:")
    assert result["snapshot"]["result"]["evidence"]["alerts"][0]["id"] == "flow-1"
    assert get_analysis_snapshot_registry().get(result["snapshot"]["snapshot_id"]) is not None


def test_event_flow_orders_equal_intensity_by_latest_date():
    packet = _packet()
    packet["events"] = [
        {
            "id": "older", "type": "report", "symbol": "300502",
            "occurred_at": "2026-06-01", "title": "较早事件",
            "direction": "neutral", "magnitude_score": 50,
            "evidence_strength": "medium", "source_ref": "desk://report/older",
        },
        {
            "id": "newer", "type": "report", "symbol": "300502",
            "occurred_at": "2026-07-01", "title": "较新事件",
            "direction": "neutral", "magnitude_score": 50,
            "evidence_strength": "medium", "source_ref": "desk://report/newer",
        },
    ]

    result = EventFlowEngine().analyze(packet)

    assert [item["id"] for item in result["alerts"]] == ["newer", "older"]


@pytest.mark.parametrize("change", [
    {"symbol": "000001"}, {"occurred_at": "2026-08-09"},
    {"type": "announcement"}, {"direction": "negative"},
])
def test_shared_source_does_not_erase_other_security_date_type_or_conflicting_direction(change):
    packet = _packet()
    original = packet["events"][0]
    packet["events"] = [original, {**original, "id": "distinct", **change}]
    result = EventFlowEngine().analyze(packet)
    assert len(result["alerts"]) == 2
    assert result["summary"]["duplicates_removed"] == 0


def test_failed_coverage_cannot_be_complete_when_failure_detail_is_absent():
    packet = _packet()
    packet["events"] = packet["events"][:1]
    result = EventFlowEngine().analyze(packet, coverage={"failed_sources": 1})
    assert result["data_state"] == "partial"
    assert "source_failures_retained_in_coverage" in result["limitations"]


def _related_packet():
    base = {**_packet()['events'][0], 'type': 'news', 'direction': 'neutral'}
    titles = [
        '新易盛:关于收到控股股东、实际控制人、董事长提议回购公司股份的公告',
        '新易盛：董事长提议8亿元至10亿元回购公司股份',
        '新易盛：董事长提议最高10亿元回购',
    ]
    return {**_packet(), 'events': [{**base, 'id': f'buyback-{i}', 'title': title,
        'type': 'announcement' if i == 0 else 'news',
        'source_ref': f'https://example.test/{i}', 'details': {'source': f'来源{i}'}}
        for i, title in enumerate(titles)]}


def test_related_reports_keep_each_source_and_prioritize_announcement_without_verifying_identity():
    packet = _related_packet()
    result = EventFlowEngine().analyze(packet)
    assert len(result['alerts']) == 3
    assert result['summary']['duplicates_removed'] == 0
    group, = result['related_groups']
    assert group['label'] == '回购 · 提议/计划'
    assert group['primary_event_id'] == 'buyback-0'
    assert set(group['event_ids']) == {'buyback-0', 'buyback-1', 'buyback-2'}
    assert group['identity_verified'] is False
    assert group['independent_source_count'] is None
    assert result['snapshot']['result']['evidence']['related_groups'] == [group]
    assert 'related_records_do_not_establish_independent_confirmation' in result['limitations']


def test_related_reports_do_not_mix_company_date_or_progress_and_retain_conflicting_direction():
    packet = _related_packet()
    packet['events'][1]['direction'] = 'positive'
    packet['events'][2]['direction'] = 'negative'
    base = packet['events'][1]
    for i, change in enumerate([
        {'symbol': '000001'}, {'occurred_at': '2026-08-09'},
        {'title': '新易盛：回购股份实施完成'}, {'title': '新易盛：终止回购计划'},
        {'title': '新易盛：回购股份进展公告'}, {'title': '新易盛：多家公司回购增持潮'},
    ]):
        packet['events'].append({**base, 'id': f'other-{i}', 'source_ref': f'https://example.test/other/{i}', **change})
    result = EventFlowEngine().analyze(packet)
    group, = result['related_groups']
    assert set(group['event_ids']) == {'buyback-0', 'buyback-1', 'buyback-2'}
    assert group['direction_conflict'] is True
    resolved, _ = resolve_event_flow_snapshot(result['snapshot']['snapshot_id'], as_of='2026-08-09')
    assert resolved['related_groups'] == []
    assert result['snapshot']['result']['evidence']['related_groups'] == [group]


def test_ambiguous_event_ids_are_retained_without_building_unresolvable_relations():
    packet = _related_packet()
    for event in packet['events']:
        event['id'] = 'reused-by-source'
    result = EventFlowEngine().analyze(packet)
    assert len(result['alerts']) == 3
    assert result['related_groups'] == []


def test_missing_desk_source_has_an_explicit_failure_and_survives_company_handoff():
    provider = DeskEventProvider()
    capital = provider.get_security_event_flow("300502")
    capital["sources"].pop("margin")
    with patch.object(provider, "get_security_event_flow", return_value=capital):
        result = EventFlowEngine().analyze_symbol("300502", as_of="2026-08-11", provider=provider)
    assert result["coverage"]["failed_sources"] == 1
    assert any(row["source"] == "margin" for row in result["failures"])
    resolved, warnings = resolve_event_flow_snapshot(result["snapshot"]["snapshot_id"], symbols=["300502"])
    assert resolved["failures"] == result["failures"]
    assert resolved["coverage"] == result["coverage"]
    assert resolved["data_state"] == "partial"
    assert any("读取失败" in item for item in warnings)


def test_latest_window_filter_never_claims_full_point_in_time_on_handoff():
    result = EventFlowEngine().analyze_symbol("300502", as_of="2026-08-11", provider=DeskEventProvider())
    assert result["snapshot"]["freshness"]["resolution"] == "partial_point_in_time"
    resolved, warnings = resolve_event_flow_snapshot(
        result["snapshot"]["snapshot_id"], symbols=["300502"], as_of="2026-08-09")
    assert resolved["freshness"]["resolution"] == "partial_point_in_time_replay"
    assert "historical_event_replay_is_client_filtered_from_latest_desk_payloads" in resolved["limitations"]
    assert any("不是完整历史" in item for item in warnings)
    assert all(item["occurred_at"] <= "2026-08-09" for item in resolved["alerts"])


def test_malformed_http_report_list_is_a_failed_source_and_survives_handoff(monkeypatch):
    from types import SimpleNamespace
    from instock.core.market_data_provider import NewmaDeskMarketDataProvider

    monkeypatch.setattr("instock.core.market_data_provider.requests.get", lambda *a, **k:
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [None]}))
    provider = DeskEventProvider()
    http_provider = NewmaDeskMarketDataProvider("http://127.0.0.1:8991/api")
    monkeypatch.setattr(provider, "get_security_reports", http_provider.get_security_reports)
    result = EventFlowEngine().analyze_symbol("300502", as_of="2026-08-11", provider=provider)
    assert result["coverage"]["failed_sources"] == 1
    assert result["coverage"]["empty_sources"] == 1  # only the explicitly empty dragon-tiger source
    assert next(row for row in result["coverage"]["sources"] if row["id"] == "reports")["state"] == "failed"
    assert any(row["source"] == "reports" and "格式无效" in row["message"] for row in result["failures"])
    assert any(row["type"] == "announcement" for row in result["alerts"])
    resolved, warnings = resolve_event_flow_snapshot(result["snapshot"]["snapshot_id"], symbols=["300502"])
    assert resolved["failures"] == result["failures"]
    assert resolved["data_state"] == "partial"
    assert any("读取失败" in warning for warning in warnings)


def test_event_flow_rejects_future_or_unknown_event_types():
    packet = _packet()
    packet["events"][0]["occurred_at"] = "2026-08-12"
    with pytest.raises(EventFlowError, match="晚于 as_of"):
        EventFlowEngine().analyze(packet)

    packet = _packet()
    packet["events"][0]["type"] = "social_rumor"
    with pytest.raises(EventFlowError, match="事件类型"):
        EventFlowEngine().analyze(packet)


def test_event_flow_symbol_mode_collects_real_desk_source_shapes():
    result = EventFlowEngine().analyze_symbol(
        "300502.SZ", as_of="2026-08-11", provider=DeskEventProvider()
    )

    assert result["input_mode"] == "desk_symbol"
    assert result["query"] == {"symbol": "300502"}
    assert result["data_source"] == "newma-desk-research"
    assert result["coverage"]["requested_sources"] == 10
    assert result["coverage"]["empty_sources"] == 1
    assert result["coverage"]["failed_sources"] == 0
    assert {"announcement", "report", "news", "fund_flow", "margin", "dragon_tiger", "holder_change", "dividend"}.issubset(
        {item["type"] for item in result["alerts"]}
    )
    assert not any(item['type'] == 'lockup' for item in result['alerts'])
    assert 'corporate_action_rows_excluded_without_timely_disclosure' in result['limitations']
    fund_flow = next(item for item in result["alerts"] if item["type"] == "fund_flow")
    assert fund_flow["details"]["main_net_5d_cny"] == 390_000_000
    assert result["snapshot"]["provenance"]["provider"] == "newma-desk"


class EventFlowHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/v1/event-flows", EventFlowHandler)])

    def test_post_returns_event_radar(self):
        response = self.fetch(
            "/api/v1/event-flows",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(_packet()),
        )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["ok"] is True
        assert payload["data"]["summary"]["duplicates_removed"] == 1

    def test_post_accepts_symbol_query_mode(self):
        with patch(
            "instock.core.research.event_flow.get_market_data_provider",
            return_value=DeskEventProvider(),
        ):
            response = self.fetch(
                "/api/v1/event-flows",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"symbol": "300502", "asOf": "2026-08-11"}),
            )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["data"]["input_mode"] == "desk_symbol"
        assert payload["data"]["coverage"]["requested_sources"] == 10

    def test_post_rejects_invalid_json(self):
        response = self.fetch(
            "/api/v1/event-flows", method="POST", body="{broken", raise_error=False
        )
        assert response.code == 400
        assert json.loads(response.body)["error"]["code"] == "invalid_json"
