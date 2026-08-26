from __future__ import annotations

import sqlite3

import security_master


def test_normalize_covers_sh_sz_bj_and_keeps_st():
    assert security_master._normalize({"f12": "600519", "f14": "贵州茅台"}, "SH")["exchange"] == "SH"
    assert security_master._normalize({"f12": "300308", "f14": "中际旭创"}, "SZ")["exchange"] == "SZ"
    assert security_master._normalize({"f12": "830799", "f14": "艾融软件"}, "BJ")["exchange"] == "BJ"
    assert security_master._normalize({"f12": "000001", "f14": "平安银行"}, "SZ") is not None
    assert security_master._normalize({"f12": "510300", "f14": "沪深300ETF"}, "SH") is None
    assert security_master._normalize({"f12": "000016", "f14": "上证50"}, "SH") is None
    assert security_master._normalize({"f12": "810014", "f14": "莱特定转"}, "BJ") is None


def test_search_reads_persistent_master(tmp_path, monkeypatch):
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    with security_master._connect() as connection:
        connection.execute(
            """INSERT INTO securities
            (code, name, exchange, market, asset_type, security_type, industry, list_date, status, source, updated_at)
            VALUES ('300308', '中际旭创', 'SZ', 'CN', 'stock', 'A股', '通信设备', '', 'active', 'test', 'now')"""
        )
    rows = security_master.search("中际旭创")
    assert rows[0]["symbol"] == "300308"
    assert rows[0]["exchange"] == "SZ"
