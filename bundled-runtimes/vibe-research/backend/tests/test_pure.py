"""纯逻辑单测（无网络、快、确定）：市场前缀、估值计算、行情解析。"""
import json
import math

import astock
import market_terminal


def test_get_prefix():
    assert astock.get_prefix("600519") == "sh"
    assert astock.get_prefix("900001") == "sh"   # 9 开头也是沪
    assert astock.get_prefix("000001") == "sz"
    assert astock.get_prefix("300750") == "sz"
    assert astock.get_prefix("832000") == "bj"   # 8 开头北交所
    assert astock.get_prefix("920992") == "bj"   # 北交所启用 920 新代码段
    assert astock.get_prefix("510300") == "sh"   # 沪 ETF（issue #10：曾误判 sz → 行情为 0）
    assert astock.get_prefix("588000") == "sh"   # 科创 50 ETF
    assert astock.get_prefix("159915") == "sz"   # 深 ETF 15 开头走默认 sz
    assert astock.get_prefix("000300") == "sh"   # 沪深 300 指数，腾讯代码是 sh000300


def test_legacy_kline_uses_unified_market_terminal(monkeypatch):
    captured = {}

    def fake_get_ohlcv(symbol, **kwargs):
        captured["symbol"] = symbol
        captured.update(kwargs)
        return {
            "items": [{
                "timestamp": 1_700_000_000_000,
                "open": 10.0,
                "close": 10.5,
                "high": 11.0,
                "low": 9.8,
                "volume": 1234,
                "turnover": 5678,
            }],
        }

    monkeypatch.setattr(market_terminal, "get_ohlcv", fake_get_ohlcv)

    rows = astock.kline("000300", category=4, offset=480)

    assert captured == {
        "symbol": "000300",
        "market": "CN",
        "timeframe": "1d",
        "limit": 480,
        "adjust": "qfq",
    }
    assert rows == [{
        "datetime": 1_700_000_000_000,
        "open": 10.0,
        "close": 10.5,
        "high": 11.0,
        "low": 9.8,
        "vol": 1234,
        "amount": 5678,
    }]


def test_calc_peg():
    assert astock.calc_peg(20, 0.2) == 20 / (0.2 * 100)  # =1.0
    assert astock.calc_peg(20, 0) == float("inf")        # 增速<=0 → inf
    assert astock.calc_peg(20, -0.1) == float("inf")


def test_pe_digestion():
    assert astock.pe_digestion(30, 0.2) == 0.0           # 当前<=目标PE 无需消化
    assert astock.pe_digestion(25, 0.2, target_pe=30) == 0.0
    assert astock.pe_digestion(60, 0.2) > 0              # 高于目标需消化年数
    assert astock.pe_digestion(60, 0) == float("inf")    # 零增速永远消化不掉


def _gtimg_line(**overrides) -> str:
    # 构造一条腾讯行情返回行：v_sh600519="1~名~代码~价~..."（≥53 字段）。
    parts = ["0"] * 55
    parts[1] = overrides.get("name", "贵州茅台")
    parts[3] = overrides.get("price", "1194.45")
    parts[39] = overrides.get("pe_ttm", "18.05")
    parts[44] = overrides.get("mcap", "15000")
    parts[46] = overrides.get("pb", "6.41")
    return 'v_sh600519="' + "~".join(parts) + '";'


def test_parse_gtimg():
    out = astock._parse_gtimg(_gtimg_line())
    assert "600519" in out
    q = out["600519"]
    assert q["name"] == "贵州茅台"
    assert q["price"] == 1194.45
    assert q["pe_ttm"] == 18.05
    assert q["pb"] == 6.41
    assert q["mcap_yi"] == 15000


def test_parse_gtimg_bad_line_ignored():
    # 字段不足 / 无引号的行应被安全跳过，不抛异常。
    assert astock._parse_gtimg("garbage;no_quotes_here;") == {}
    assert astock._parse_gtimg("") == {}


def test_fund_flow_falls_back_to_sina_when_eastmoney_is_empty(monkeypatch):
    class EastmoneyResponse:
        @staticmethod
        def json():
            return {"data": None}

    class SinaResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps([{
                "opendate": "2026-08-21",
                "trade": "943.0",
                "changeratio": "0.042",
                "netamount": "3600000000",
                "r0_net": "3500000000",
            }]).encode()

    monkeypatch.setattr(astock, "em_get", lambda *_args, **_kwargs: EastmoneyResponse())
    monkeypatch.setattr(astock.urllib.request, "urlopen", lambda *_args, **_kwargs: SinaResponse())

    rows = astock.stock_fund_flow_120d("300308")

    assert rows[0]["source"] == "sina-money-flow"
    assert rows[0]["main_net"] == 3_500_000_000
    assert rows[0]["change_pct"] == 4.2


def test_parse_tencent_compact_minute_rows():
    bars = market_terminal._parse_tencent_rows([
        ["202607241415", "1295.30", "1297.32", "1297.62", "1295.21", "592.00"],
    ])
    assert len(bars) == 1
    assert bars[0]["open"] == 1295.30
    assert bars[0]["close"] == 1297.32
    assert bars[0]["high"] == 1297.62
    assert bars[0]["low"] == 1295.21
    assert bars[0]["volume"] == 592.0


def test_tencent_intraday_ohlcv_normalizes_rows(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "data": {
                    "sh600519": {
                        "m5": [
                            ["202607241415", "1295.30", "1297.32", "1297.62", "1295.21", "592.00"],
                        ],
                    },
                },
            }

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._tencent_intraday_ohlcv("600519", "5m", 100)
    assert len(bars) == 1
    assert bars[0]["close"] == 1297.32


def test_eastmoney_ohlcv_normalizes_rows(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "rc": 0,
                "data": {
                    "klines": [
                        "2026-08-20,1290.00,1297.32,1300.00,1285.00,1234,5678900.00,1.2,0.5,6.4,0.1",
                    ],
                },
            }

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._eastmoney_ohlcv("600519", "1d", 100, "qfq")
    assert len(bars) == 1
    assert bars[0]["close"] == 1297.32
    assert bars[0]["turnover"] == 5678900.0


def test_sina_cn_ohlcv_normalizes_rows(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{
                "day": "2026-08-20",
                "open": "1290.00",
                "close": "1297.32",
                "high": "1300.00",
                "low": "1285.00",
                "volume": "1234",
            }]

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._sina_cn_ohlcv("600519", "1d", 100)
    assert len(bars) == 1
    assert bars[0]["close"] == 1297.32
    assert bars[0]["turnover"] == 0


def test_sina_us_daily_ohlcv_normalizes_rows(monkeypatch):
    class Response:
        text = 'var([{"d":"2026-08-14","o":"306.00","h":"307.49","l":"304.30","c":"305.93","v":"28229375","a":"0"}])'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._sina_us_daily_ohlcv("AAPL", 100)
    assert len(bars) == 1
    assert bars[0]["close"] == 305.93
    assert bars[0]["volume"] == 28_229_375


def test_sina_us_intraday_ohlcv_normalizes_rows(monkeypatch):
    class Response:
        text = 'var([{"d":"2026-08-14 15:55:00","o":"305.80","h":"306.10","l":"305.70","c":"305.93","v":"1000","a":"305930"}])'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._sina_us_intraday_ohlcv("AAPL", "5m", 100)
    assert len(bars) == 1
    assert bars[0]["close"] == 305.93


def test_tencent_hk_ohlcv_normalizes_rows(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "data": {
                    "hk00981": {
                        "day": [["2026-08-14", "70.750", "70.800", "72.350", "68.800", "170311814"]],
                    },
                },
            }

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return Response()

    monkeypatch.setattr(market_terminal.requests, "get", fake_get)
    bars = market_terminal._tencent_hk_ohlcv("00981", "1d", 100)
    assert captured == {
        "url": market_terminal.TENCENT_HK_KLINE_URL,
        "params": {"param": "hk00981,day,,,100,"},
    }
    assert len(bars) == 1
    assert bars[0]["close"] == 70.8


def test_tencent_hk_intraday_ohlcv_uses_incremental_volume(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "data": {
                    "hk00981": {
                        "data": [{
                            "date": "20260814",
                            "data": ["0930 70.000 100 7000", "0931 71.000 300 21200"],
                        }],
                    },
                },
            }

    monkeypatch.setattr(market_terminal.requests, "get", lambda *args, **kwargs: Response())
    bars = market_terminal._tencent_hk_intraday_ohlcv("00981", "5m", 100)
    assert len(bars) == 1
    assert bars[0]["open"] == 70
    assert bars[0]["close"] == 71
    assert bars[0]["volume"] == 300


def test_yahoo_ohlcv_sends_authenticated_crumb(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1_776_384_000],
                        "indicators": {"quote": [{
                            "open": [70.75], "close": [70.8], "high": [72.35], "low": [68.8], "volume": [170_311_814],
                        }]},
                    }],
                },
            }

    class Session:
        def get(self, url, **kwargs):
            captured.update(kwargs.get("params") or {})
            return Response()

    monkeypatch.setattr(market_terminal, "_yahoo_session", lambda: (Session(), "test-crumb"))
    bars = market_terminal._yahoo_ohlcv("HK", "00981", "1d", 100)
    assert captured["crumb"] == "test-crumb"
    assert bars[0]["close"] == 70.8
