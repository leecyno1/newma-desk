import pandas as pd
import pytest

from instock.core.market_data_provider import MarketDataProvider, MarketDataError
from instock.core.selection.stock_candidates import StockCandidateEngine
from instock.core.signals.technical_signal_center import TechnicalSignalCenterEngine


class ScanHistoryProvider(MarketDataProvider):
    def __init__(self):
        dates = pd.bdate_range(end='2026-10-20', periods=280)
        self.frame = pd.DataFrame({
            'date': dates, 'open': 10.0, 'high': 10.1, 'low': 9.9,
            'close': 10.0, 'volume': 10000.0, 'amount': 100000.0,
        })
        self.frame.attrs['upstream_source'] = 'test-daily'
        self.calls = []

    def get_kline(self, symbol, period='daily', limit=480, as_of=None):
        self.calls.append((symbol, limit, as_of))
        # Deliberately includes a newer bar: the consumer must not mix dates.
        return self.frame.copy()


@pytest.mark.parametrize('engine_type', [StockCandidateEngine, TechnicalSignalCenterEngine])
def test_daily_scan_history_ends_at_scan_date(engine_type):
    provider = ScanHistoryProvider()
    item = {'symbol': '000001', 'name': '测试', 'scan_frequency': 'daily',
            'scan_as_of': '2026-10-19T15:00:00+08:00'}
    result = engine_type(provider)._analyze_one(item, 120)
    assert provider.calls == [('000001', 120, '2026-10-19')]
    assert result['data_end'] == '2026-10-19'
    assert result['history_bars'] == 120


@pytest.mark.parametrize('engine_type', [StockCandidateEngine, TechnicalSignalCenterEngine])
def test_daily_scan_without_date_cannot_use_latest_history(engine_type):
    provider = ScanHistoryProvider()
    with pytest.raises(MarketDataError, match='日频扫描缺少有效截止日'):
        engine_type(provider)._analyze_one({'symbol': '000001', 'scan_frequency': 'daily'}, 120)
    assert provider.calls == []

