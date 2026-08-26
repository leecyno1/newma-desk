import os
import subprocess
import sys
import tempfile
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base


def test_app_startup_does_not_eagerly_import_heavy_market_fallbacks():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import app.main; "
                "print(int('akshare' in sys.modules), int('tushare' in sys.modules))"
            ),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout.strip().endswith("0 0"), result.stdout


def _make_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    return path, TestingSession


def test_normalize_asset_identity_covers_stock_index_etf_and_fund():
    from app.services.market_data import normalize_asset_identity

    stock = normalize_asset_identity("stock", "601899")
    index = normalize_asset_identity("index", "sh000300")
    etf = normalize_asset_identity("etf", "512480")
    fund = normalize_asset_identity("fund", "159928")

    assert stock["ts_code"] == "601899.SH"
    assert stock["prefixed_code"] == "sh601899"
    assert index["ts_code"] == "000300.SH"
    assert index["prefixed_code"] == "sh000300"
    assert etf["asset_type"] == "etf"
    assert etf["ts_code"] == "512480.SH"
    assert fund["asset_type"] == "fund"
    assert fund["ts_code"] == "159928.SZ"


def test_fetch_market_series_prefers_tushare_then_falls_back_to_akshare(monkeypatch):
    from app.services import market_data

    calls = []

    def fake_tushare(normalized, start_date, end_date, config):
        calls.append(("tushare", normalized["ts_code"]))
        return []

    def fake_akshare(normalized, start_date, end_date):
        calls.append(("akshare", normalized["prefixed_code"]))
        return [{"date": "2026-01-02", "close": 10.0}]

    monkeypatch.setattr(market_data, "HAS_TUSHARE", True)
    monkeypatch.setattr(market_data, "HAS_AKSHARE", True)
    monkeypatch.setattr(market_data, "_fetch_tushare_series", fake_tushare)
    monkeypatch.setattr(market_data, "_fetch_akshare_series", fake_akshare)

    rows = market_data.fetch_market_series(
        "index",
        "sh000300",
        datetime(2026, 1, 1),
        datetime(2026, 1, 31),
        config={
            "provider_preference": "tushare_first",
            "enable_tushare": True,
            "enable_akshare": True,
            "tushare_token": "token",
        },
    )

    assert rows == [{"date": "2026-01-02", "close": 10.0}]
    assert calls == [("tushare", "000300.SH"), ("akshare", "sh000300")]


def test_fetch_market_series_defaults_to_embedded_a_stock_direct(monkeypatch):
    from app.services import market_data

    calls = []

    def fake_direct(normalized, start_date, end_date):
        calls.append(("a_stock_direct", normalized["prefixed_code"]))
        return [{"date": "2026-07-01", "close": 25.11}]

    monkeypatch.setattr(market_data, "_fetch_a_stock_direct_series", fake_direct)

    rows = market_data.fetch_market_series(
        "stock",
        "601899",
        datetime(2026, 6, 1),
        datetime(2026, 7, 1),
        config={},
    )

    assert rows == [{"date": "2026-07-01", "close": 25.11}]
    assert calls == [("a_stock_direct", "sh601899")]
    assert market_data.market_data_provider_order({})[0] == "a_stock_direct"


def test_fetch_market_series_falls_back_from_embedded_direct_to_akshare(monkeypatch):
    from app.services import market_data

    calls = []

    def fake_direct(normalized, start_date, end_date):
        calls.append("a_stock_direct")
        return []

    def fake_akshare(normalized, start_date, end_date):
        calls.append("akshare")
        return [{"date": "2026-07-01", "close": 4958.98}]

    monkeypatch.setattr(market_data, "HAS_AKSHARE", True)
    monkeypatch.setattr(market_data, "_fetch_a_stock_direct_series", fake_direct)
    monkeypatch.setattr(market_data, "_fetch_akshare_series", fake_akshare)

    rows = market_data.fetch_market_series(
        "index",
        "sh000300",
        datetime(2026, 6, 1),
        datetime(2026, 7, 1),
        config={
            "provider_preference": "a_stock_first",
            "enable_a_stock_direct": True,
            "enable_tushare": False,
            "enable_akshare": True,
            "tushare_token": "",
        },
    )

    assert rows == [{"date": "2026-07-01", "close": 4958.98}]
    assert calls == ["a_stock_direct", "akshare"]


def test_market_data_config_persists_and_masks_tushare_token():
    from app.routers import configs

    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            saved = configs.set_market_data_config(
                {
                    "provider_preference": "a_stock_first",
                    "enable_a_stock_direct": True,
                    "enable_tushare": True,
                    "enable_akshare": True,
                    "tushare_token": "secret-token",
                    "default_benchmark": "sh000300",
                },
                db=db,
            )
            assert saved["status"] == "ok"

            ui = configs.get_market_data_config(db=db)
            assert ui["provider_preference"] == "a_stock_first"
            assert ui["enable_a_stock_direct"] is True
            assert ui["enable_tushare_lookup"] is False
            assert ui["has_tushare_token"] is True
            assert ui["tushare_token"] == ""
            assert ui["default_benchmark"] == "sh000300"
            assert ui["providers"]["a_stock_direct_installed"] is True
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_search_asset_in_text_matches_curated_names():
    from app.services.market_data import search_asset_in_text

    stock = search_asset_in_text("我继续看好紫金矿业未来三个月表现")
    etf = search_asset_in_text("芯片ETF短期值得关注")
    fund = search_asset_in_text("白酒基金最近回撤后可以慢慢看")
    mixed = search_asset_in_text("我继续看好紫金矿业，未来3个月有望跑赢沪深300。")

    assert stock == {"asset_type": "stock", "asset_code": "601899", "asset_name": "紫金矿业"}
    assert etf == {"asset_type": "etf", "asset_code": "512480", "asset_name": "半导体ETF"}
    assert fund == {"asset_type": "fund", "asset_code": "161725", "asset_name": "招商中证白酒指数"}
    assert mixed == {"asset_type": "stock", "asset_code": "601899", "asset_name": "紫金矿业"}


def test_load_asset_lookup_entries_keeps_curated_aliases_when_tushare_duplicates(monkeypatch):
    from app.services import market_data

    monkeypatch.setattr(
        market_data,
        "_fetch_tushare_lookup_entries",
        lambda cfg: [
            {"asset_type": "etf", "asset_code": "512480", "asset_name": "国联安中证全指半导体ETF", "aliases": ["国联安中证全指半导体ETF"]},
        ],
    )
    monkeypatch.setattr(market_data, "HAS_TUSHARE", True)
    market_data._ASSET_LOOKUP_CACHE.clear()

    entries = market_data.load_asset_lookup_entries(
        {
            "provider_preference": "tushare_first",
            "enable_tushare": True,
            "enable_tushare_lookup": True,
            "enable_akshare": True,
            "tushare_token": "token",
        }
    )
    row = next(item for item in entries if item["asset_type"] == "etf" and item["asset_code"] == "512480")
    assert "芯片ETF" in row["aliases"]
    assert "国联安中证全指半导体ETF" in row["aliases"]
