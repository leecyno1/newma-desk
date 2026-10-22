import astock
import gstock
import market_terminal
import equity_research
import pytest


def test_cn_quote_preserves_source_time_not_fetch_time():
    fields = [''] * 60
    fields[1], fields[3], fields[30] = '测试', '100', '20260910161500'
    raw = astock._parse_gtimg('v_sh600519="' + '~'.join(fields) + '";')['600519']
    quote = market_terminal._cn_quote('600519', raw)
    assert quote['priceAsOf'] == '2026-09-10T16:15:00+08:00'
    assert market_terminal._cn_quote('600519', {'price':100})['priceAsOf'] is None


def test_global_quote_source_timezones(monkeypatch):
    fields = [''] * 60
    fields[1], fields[3], fields[30] = '测试', '100', '2026-09-10 16:00:01'
    monkeypatch.setattr(gstock, '_get_text', lambda *a, **kw: 'v_usAAPL="'+'~'.join(fields)+'";')
    raw = gstock._us_quote_tencent('AAPL')
    quote = market_terminal._global_quote('US','AAPL',{'quote':raw})
    assert quote['priceAsOf'] == '2026-09-10T16:00:01-04:00'
    fields[30] = '2026/09/11 16:09:02'
    raw = gstock._hk_quote_tencent('00700')
    assert market_terminal._global_quote('HK','00700',{'quote':raw})['priceAsOf'] == '2026-09-11T16:09:02+08:00'


def test_sina_us_quote_timestamp_is_beijing_time(monkeypatch):
    fields = [''] * 36
    fields[0],fields[1],fields[3] = 'Apple','326.57','2026-09-11 21:24:04'
    monkeypatch.setattr(gstock, '_get_text', lambda *a, **kw: 'var hq_str_gb_aapl="'+','.join(fields)+'";')
    quote = market_terminal._global_quote('US','AAPL',{'quote':gstock._us_quote_sina('AAPL')})
    assert quote['priceAsOf'] == '2026-09-11T21:24:04+08:00'


def test_full_valuation_retains_clock_and_research_does_not_date_forecasts_by_quote(monkeypatch):
    monkeypatch.setattr(astock, 'tencent_quote', lambda _: {'300502': {'name':'测试', 'price':100, 'mcap_yi':5, 'pe_ttm':20, 'pb':2, 'quote_time':'20261019150003'}})
    monkeypatch.setattr(astock, 'profit_forecast', lambda _: [{'年度':'2026', '均值':5, '预测机构数':10}])
    valuation = astock.full_valuation('300502')
    assert valuation['quote_time'] == '20261019150003'
    monkeypatch.setattr(equity_research, '_now_iso', lambda: '2026-10-20T00:30:00+08:00')
    adapter = equity_research.ChinaEquityResearchAdapter(valuation_loader=lambda _: valuation, financial_loader=lambda _: {},
        percentile_loader=lambda _: {'period':'近5年', 'metrics':{'pe_ttm':{'percentile':30}}})
    result = equity_research.EquityResearchService([adapter]).snapshot('300502')
    evidence = {row['id']: row for row in result['evidenceLedger']}
    pe = evidence['valuation.pe_ttm']
    assert pe['asOf'] == '2026-10-19T15:00:03+08:00'
    assert pe['retrievedAt'] == '2026-10-20T00:30:00+08:00'
    assert pe['timeBasis'] == 'source_quote'
    assert evidence['valuation.pe_26e']['asOf'] is None
    assert evidence['valuation.pe_ttm_percentile']['asOf'] is None
    status = next(row for row in result['workflow']['sourceStatus'] if row['id']=='cn-quote-valuation')
    assert status['asOf'] == pe['asOf']
    history = next(row for row in result['workflow']['sourceStatus'] if row['id']=='cn-valuation-history')
    assert history['asOf'] is None
    assert '样本截止日期未提供' in history['message']


@pytest.mark.parametrize('clock', [None, '', '20260230150000', 'bad'])
def test_unknown_cn_clock_never_uses_current_time(clock):
    adapter = equity_research.ChinaEquityResearchAdapter(valuation_loader=lambda _: {'pe_ttm':20, 'quote_time':clock},
        financial_loader=lambda _: {}, percentile_loader=lambda _: {})
    result = adapter.load('300502')
    pe = next(row for row in result.evidence if row.id=='valuation.pe_ttm')
    assert pe.as_of is None and pe.retrieved_at and pe.time_basis == 'unknown'
    assert any('获取时间不代表报价时间' in gap for gap in result.gaps)


def test_cross_source_quote_preserves_each_field_origin_and_does_not_borrow_clock():
    quote = gstock._merge_quotes(
        {'price':100, 'mcap':None, 'source':'sina'},
        {'price':101, 'mcap':2000, 'pe':15, 'source':'tencent', 'quote_time':'2026-10-19 16:00:00', 'quote_timezone':'America/New_York'})
    assert quote['quote_time'] is None
    assert quote['price']==100 and quote['mcap']==2000
    assert market_terminal._global_quote('US', 'AAPL', {'quote':quote})['priceAsOf'] is None
    adapter = equity_research.GlobalEquityResearchAdapter(stock_loader=lambda _: {'code':'AAPL','market':'US','quote':quote})
    result = equity_research.EquityResearchService([adapter]).snapshot('AAPL')
    evidence = {row['id']:row for row in result['evidenceLedger']}
    assert evidence['valuation.price']['asOf'] is None
    assert evidence['valuation.price']['source']=='sina'
    assert evidence['valuation.mcap']['source']=='tencent'
    assert evidence['valuation.mcap']['asOf']=='2026-10-19T16:00:00-04:00'


def test_global_research_keeps_actual_sina_clock_zone():
    adapter = equity_research.GlobalEquityResearchAdapter(stock_loader=lambda _: {'code':'AAPL','market':'US',
        'quote':{'price':100,'source':'sina','quote_time':'2026-10-20 04:00:00','quote_timezone':'Asia/Shanghai'}})
    evidence = adapter.load('AAPL').evidence
    assert next(row for row in evidence if row.id=='valuation.price').as_of == '2026-10-20T04:00:00+08:00'
