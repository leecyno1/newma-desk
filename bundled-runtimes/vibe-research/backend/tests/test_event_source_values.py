import pytest

import astock
from types import SimpleNamespace


@pytest.mark.parametrize('payload,empty', [
    ({'success': False, 'code': 9201, 'message': '返回数据为空', 'result': None}, True),
    ({'success': False, 'code': 500, 'message': '查询失败', 'result': None}, False),
    ({'success': False, 'code': 9201, 'message': '接口不可用', 'result': None}, False),
])
def test_datacenter_distinguishes_explicit_empty_code_from_source_failure(monkeypatch, payload, empty):
    monkeypatch.setattr(astock, 'em_get', lambda *a, **k: SimpleNamespace(json=lambda: payload))
    if empty:
        assert astock.eastmoney_datacenter('RPT_LIFT_STAGE', strict=True) == []
    else:
        with pytest.raises(ValueError, match='查询失败'):
            astock.eastmoney_datacenter('RPT_LIFT_STAGE', strict=True)


def test_holder_source_uses_total_share_average_and_disclosure_date(monkeypatch):
    def source(*args, **kwargs):
        assert kwargs['strict'] is True
        return [{'END_DATE': '2026-06-30 00:00:00', 'HOLD_NOTICE_DATE': '2026-08-25 00:00:00',
                 'HOLDER_NUM': 257067, 'HOLDER_NUM_RATIO': 0,
                 'AVG_HOLD_NUM': 5423.70932091634, 'AVG_FREE_SHARES': 99}]
    monkeypatch.setattr(astock, 'eastmoney_datacenter', source)
    row = astock.holder_num_change('300502')[0]
    assert row['avg_shares'] == pytest.approx(5423.70932091634)
    assert row['avg_shares_basis'] == 'total_a_shares_per_holder'
    assert row['published_at'] == '2026-08-25'
    assert row['date'] == '2026-06-30'
    assert row['change_ratio'] == 0


def test_holder_missing_values_stay_unknown(monkeypatch):
    monkeypatch.setattr(astock, 'eastmoney_datacenter', lambda *a, **k: [{}])
    row = astock.holder_num_change('300502')[0]
    for key in ('holder_num', 'change_ratio', 'avg_shares', 'published_at'):
        assert row[key] is None


@pytest.mark.parametrize('close,deal,expected', [(351.3, 351.3, 0), ('100', '95', -5),
    (None, 100, None), (100, None, None), (0, 100, None), ('-', 100, None),
    (float('nan'), 100, None), (100, float('inf'), None)])
def test_block_trade_premium_requires_valid_same_day_prices(monkeypatch, close, deal, expected):
    def source(*args, **kwargs):
        assert kwargs['strict'] is True
        return [{'CLOSE_PRICE': close, 'DEAL_PRICE': deal, 'DISCOUNT_RATIO': 12}]
    monkeypatch.setattr(astock, 'eastmoney_datacenter', source)
    row = astock.block_trade('300502')[0]
    assert row['premium_pct'] == expected
    assert row['amount'] is None


@pytest.mark.parametrize('fetch', [astock.block_trade, astock.holder_num_change, astock.dividend_history, astock.lockup_expiry])
def test_source_failure_is_not_an_empty_success(monkeypatch, fetch):
    def source(*args, **kwargs):
        if kwargs.get('strict'):
            raise RuntimeError('source unavailable')
        return []
    monkeypatch.setattr(astock, 'eastmoney_datacenter', source)
    with pytest.raises(RuntimeError, match='source unavailable'):
        fetch('300502')


def test_dividend_source_uses_current_transfer_column_and_separate_dates(monkeypatch):
    def source(*args, **kwargs):
        assert kwargs['strict'] is True
        return [{'EX_DIVIDEND_DATE': '2026-06-11 00:00:00', 'NOTICE_DATE': '2026-06-04 00:00:00',
                 'PLAN_NOTICE_DATE': '2026-04-24 00:00:00', 'REPORT_DATE': '2025-12-31 00:00:00',
                 'PRETAX_BONUS_RMB': 10, 'IT_RATIO': 4, 'BONUS_RATIO': None,
                 'ASSIGN_PROGRESS': '实施分配', 'IMPL_PLAN_PROFILE': '10转4股派10.00元'}]
    monkeypatch.setattr(astock, 'eastmoney_datacenter', source)
    row = astock.dividend_history('300502')[0]
    assert row['transfer_ratio'] == 4
    assert row['bonus_ratio'] is None
    assert row['bonus_rmb'] == 10
    assert row['published_at'] == '2026-06-04'
    assert row['plan_published_at'] == '2026-04-24'
    assert row['date'] == '2026-06-11'
    assert row['plan_description'] == '10转4股派10.00元'


def test_dividend_missing_dates_and_amounts_do_not_become_zero_or_none_text(monkeypatch):
    monkeypatch.setattr(astock, 'eastmoney_datacenter', lambda *a, **k: [{'EX_DIVIDEND_DATE': None, 'PRETAX_BONUS_RMB': 0}])
    row = astock.dividend_history('300502')[0]
    assert row['date'] is None
    assert row['bonus_rmb'] == 0
    assert row['transfer_ratio'] is None
    assert row['published_at'] is None


def test_lockup_uses_batch_shares_not_float_base_and_splits_calendar(monkeypatch):
    def source(*args, **kwargs):
        assert kwargs['strict'] is True
        assert 'FREE_DATE<' in kwargs['filter_str']
        return [{'FREE_DATE': '2026-10-19', 'FREE_SHARES': 88380, 'CURRENT_FREE_SHARES': 153.4,
                 'ABLE_FREE_SHARES': None, 'FREE_RATIO': 0.0017, 'EUTIME': '2026-10-20'},
                {'FREE_DATE': '2026-10-20', 'CURRENT_FREE_SHARES': 0, 'FREE_RATIO': 0},
                {'FREE_DATE': '2026-10-21', 'CURRENT_FREE_SHARES': 2},
                {'FREE_DATE': '2027-10-21', 'CURRENT_FREE_SHARES': 3}]
    monkeypatch.setattr(astock, 'eastmoney_datacenter', source)
    data = astock.lockup_expiry('300502', trade_date='2026-10-20')
    assert [r['date'] for r in data['history']] == ['2026-10-19']
    assert [r['date'] for r in data['upcoming']] == ['2026-10-20', '2026-10-21']
    assert data['history'][0]['shares'] == 153.4
    assert data['history'][0]['able_shares'] is None
    assert data['history'][0]['published_at'] is None  # EUTIME is not a disclosure date
    assert data['upcoming'][0]['shares'] == 0
