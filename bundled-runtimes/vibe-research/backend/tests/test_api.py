"""API 验证/契约测（FastAPI TestClient）。大多在校验层就返回，不联网、可靠。"""
import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("path", [
    "/api/quote?codes=abc",
    "/api/valuation?code=12",
    "/api/margin?code=notcode",
    "/api/holders?code=1234567",
    "/api/announcements?code=",
])
def test_bad_code_400(path):
    assert client.get(path).status_code == 400


def test_industry_top_range():
    assert client.get("/api/industry?top=2").status_code == 422   # ge=5
    assert client.get("/api/industry?top=999").status_code == 422  # le=50


def test_chat_empty_messages_400():
    r = client.post("/api/chat", json={"messages": [], "llm": {"model": "x", "baseURL": "http://x", "apiKey": "k"}})
    assert r.status_code == 400


def test_chat_api_missing_key_400():
    # API 接入缺 baseURL/apiKey → 400（在开流前拦下）
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "llm": {"provider": "deepseek", "model": "deepseek-chat", "baseURL": "", "apiKey": ""},
    })
    assert r.status_code == 400


def test_chat_cli_not_installed_400():
    # 订阅接入选一个本机没装的 CLI → 400 明确提示（不静默失败）
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "llm": {"provider": "cli-qwen", "model": "qwen-code", "baseURL": "", "apiKey": ""},
    })
    # qwen 一般未装 → 400；若恰好装了 qwen 则会进流式（放宽断言）
    assert r.status_code in (400, 200)


def test_global_stock_404(monkeypatch):
    """无法解析的美股/港股代码 → 404（不 500、不崩）。"""
    import gstock
    monkeypatch.setattr(gstock, "us_hk_stock", lambda q: {})
    assert client.get("/api/global/stock?symbol=ZZZZ").status_code == 404


def test_gstock_quote_full_null_shape():
    """行情取不到时 `_quote_from({})` 仍返回完整 null 形状（契合 GlobalQuote 类型），不是空 dict。"""
    import gstock
    q = gstock._quote_from({})
    assert set(q) == {
        "code", "name", "price", "open", "high", "low", "prev_close",
        "volume", "amount", "turnover_rate", "mcap", "change_pct", "pe",
        "pb", "source",
    }
    assert all(v is None for v in q.values())


def test_gstock_uses_global_stock_data_us_source_order(monkeypatch):
    """美股按 Skill 规则以新浪为主，腾讯/东财只填充缺失字段。"""
    import gstock

    monkeypatch.setattr(
        gstock,
        "_us_quote_sina",
        lambda code: {"price": 101.0, "mcap": None, "source": "sina"},
    )
    monkeypatch.setattr(
        gstock,
        "_us_quote_tencent",
        lambda code: {"price": 102.0, "mcap": 3_000_000_000, "source": "tencent"},
    )
    monkeypatch.setattr(
        gstock,
        "_push2_stock_get",
        lambda secid, fields: {"f48": 8_000_000, "f59": 2},
    )

    quote = gstock._best_quote(
        {"code": "AAPL", "market": "NASDAQ", "secid_prefix": 105}
    )

    assert quote["price"] == 101.0
    assert quote["mcap"] == 3_000_000_000
    assert quote["amount"] == 8_000_000
    assert quote["sources"] == ["sina", "tencent", "eastmoney"]


@pytest.mark.parametrize(
    "query,code,market",
    [
        ("AAPL", "AAPL", "US"),
        ("MSFT.US", "MSFT", "US"),
        ("700", "00700", "HK"),
        ("00700.HK", "00700", "HK"),
    ],
)
def test_gstock_resolves_direct_symbol_when_search_is_unavailable(
    monkeypatch, query, code, market
):
    """公开报价端点可直查代码，东财搜索失败不应让整个页面 404。"""
    import gstock

    monkeypatch.setattr(gstock, "_search", lambda q: None)

    result = gstock.resolve_symbol(query)

    assert result is not None
    assert result["code"] == code
    assert result["market"] == market


def test_etf_announcements_route_uses_fund_source(monkeypatch):
    app_module._ANN_CACHE.clear()
    monkeypatch.setattr(
        app_module.astock,
        "fund_announcements",
        lambda code: [{"date": "2026-08-13", "title": "ETF公告", "fundCode": code}],
    )

    response = client.get("/api/announcements?code=510300&assetType=etf")

    assert response.status_code == 200
    assert response.json()["data"][0]["fundCode"] == "510300"
    app_module._ANN_CACHE.clear()


def test_tencent_search_preserves_etf_asset_type(monkeypatch):
    class Response:
        text = 'v_hint="sh~510300~沪深300ETF~~ETF"'

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(app_module.market_terminal.requests, "get", lambda *args, **kwargs: Response())

    rows = app_module.market_terminal._tencent_search_symbols("510300", limit=3, market="CN")

    assert rows[0]["assetType"] == "etf"
    assert rows[0]["securityType"] == "ETF"


def test_fund_search_supports_name_and_preserves_etf_type(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "Datas": [
                    {
                        "CODE": "110022",
                        "NAME": "易方达消费行业股票",
                        "CATEGORY": 700,
                        "CATEGORYDESC": "基金",
                        "FundBaseInfo": {"FTYPE": "股票型"},
                    },
                    {
                        "CODE": "510300",
                        "NAME": "沪深300ETF华泰柏瑞",
                        "CATEGORY": 700,
                        "CATEGORYDESC": "基金",
                        "FundBaseInfo": {"FTYPE": "指数型-股票"},
                    },
                    {
                        "CODE": "018896",
                        "NAME": "易方达中证消费电子主题ETF联接A",
                        "CATEGORY": 700,
                        "CATEGORYDESC": "基金",
                        "FundBaseInfo": {"FTYPE": "指数型-股票"},
                    },
                    {
                        "CODE": "300308",
                        "NAME": "中际旭创",
                        "CATEGORY": 150,
                        "CATEGORYDESC": "深市",
                    },
                ],
            }

    monkeypatch.setattr(app_module.market_terminal.astock, "em_get", lambda *args, **kwargs: Response())

    rows = app_module.market_terminal._fund_search_symbols("易方达消费", limit=5)

    assert rows[0]["symbol"] == "110022"
    assert rows[0]["assetType"] == "fund"
    assert rows[0]["exchange"] == "OTC"
    assert rows[1]["assetType"] == "etf"
    assert rows[1]["exchange"] == "SH"
    assert rows[2]["assetType"] == "fund"
    assert all(row["symbol"] != "300308" for row in rows)


def test_search_keeps_pinyin_stock_when_fund_also_matches(monkeypatch):
    class SearchResponse:
        text = '{"QuotationCodeTable":{"Data":[]}}'

        @staticmethod
        def raise_for_status():
            return None

    class Session:
        trust_env = True

        @staticmethod
        def get(*args, **kwargs):
            return SearchResponse()

    stock = {
        "symbol": "300308", "name": "中际旭创", "market": "CN", "exchange": "SZ",
        "currency": "CNY", "timezone": "Asia/Shanghai", "assetType": "stock",
        "securityType": "GP-A", "quoteId": "CN:300308", "source": "tencent-search",
    }
    fund = {
        "symbol": "003562", "name": "诺德成长精选C", "market": "CN", "exchange": "OTC",
        "currency": "CNY", "timezone": "Asia/Shanghai", "assetType": "fund",
        "securityType": "混合型-灵活", "quoteId": "150.003562", "source": "eastmoney-fund-search",
    }
    monkeypatch.setattr(app_module.market_terminal.requests, "Session", Session)
    monkeypatch.setattr(app_module.market_terminal, "_tencent_search_symbols", lambda *args, **kwargs: [stock])
    monkeypatch.setattr(app_module.market_terminal, "_fund_search_symbols", lambda *args, **kwargs: [fund])

    rows = app_module.market_terminal.search_symbols("zjxc", limit=5, market="ALL")["items"]

    assert rows[0]["symbol"] == "300308"
    assert rows[0]["assetType"] == "stock"
    assert rows[0]["exchange"] == "SZ"
    assert rows[1]["symbol"] == "003562"


def test_open_fund_search_and_nav_contract(monkeypatch):
    fund = app_module.market_terminal._search_row({
        "MktNum": 150,
        "Code": "110022",
        "Name": "易方达消费行业股票",
        "SecurityTypeName": "基金",
        "QuoteID": "150.110022",
    })
    assert fund["assetType"] == "fund"
    assert fund["exchange"] == "OTC"

    rows = [
        {"date": "2026-08-14", "unitNav": 2.928, "cumulativeNav": 2.928, "changePct": -0.71, "navEvent": "", "subscribeStatus": "开放申购", "redeemStatus": "开放赎回"},
        {"date": "2026-08-13", "unitNav": 2.949, "cumulativeNav": 2.949, "changePct": -0.03, "navEvent": "", "subscribeStatus": "开放申购", "redeemStatus": "开放赎回"},
    ]
    monkeypatch.setattr(app_module.market_terminal.astock, "fund_nav_history", lambda code, limit: rows)
    monkeypatch.setattr(app_module.market_terminal, "_fund_profile", lambda code: {
        "name": "易方达消费行业股票",
        "fundType": "股票型",
        "fundCompany": "易方达基金",
        "fundManager": "萧楠",
        "minimumPurchase": 10.0,
    })

    quote = app_module.market_terminal.get_quote("110022", market="CN", asset_type="fund")
    series = app_module.market_terminal.get_ohlcv("110022", market="CN", timeframe="1d", asset_type="fund")

    assert quote["price"] == 2.928
    assert quote["assetType"] == "fund"
    assert quote["name"] == "易方达消费行业股票"
    assert quote["fundManager"] == "萧楠"
    assert quote["navDate"] == "2026-08-14"
    assert quote["subscribeStatus"] == "开放申购"
    assert series["source"] == "eastmoney-fund-nav"
    assert series["items"][-1]["close"] == 2.928
