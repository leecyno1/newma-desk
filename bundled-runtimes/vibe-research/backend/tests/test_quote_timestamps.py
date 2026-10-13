import astock
import gstock
import market_terminal


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
