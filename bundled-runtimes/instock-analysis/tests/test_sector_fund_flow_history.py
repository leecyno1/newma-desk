from instock.core.rotation.sector_fund_flow_history import SectorFundFlowHistory


def rows(net=3.5):
    return [{
        "industry": "通信",
        "sector_fund_flow": {"state": "available", "net": net},
    }]


def test_sector_fund_flow_history_upserts_same_day_and_survives_recreation(tmp_path):
    path = tmp_path / "flows.sqlite3"
    history = SectorFundFlowHistory(str(path))
    assert history.upsert("2026-08-12", rows(3.5)) is True
    assert history.upsert("2026-08-12", rows(7.0)) is True
    history.upsert("2026-08-11", rows(-2.0))

    restarted = SectorFundFlowHistory(str(path))
    assert restarted.recent(before="2026-08-13", limit=5) == [
        {"as_of": "2026-08-12", "flows": [{"industry": "通信", "net": 7.0}]},
        {"as_of": "2026-08-11", "flows": [{"industry": "通信", "net": -2.0}]},
    ]
    assert restarted.stats()["entries"] == 2


def test_sector_fund_flow_history_skips_empty_desk_flow(tmp_path):
    history = SectorFundFlowHistory(str(tmp_path / "flows.sqlite3"))
    assert history.upsert("2026-08-13", [{
        "industry": "通信", "sector_fund_flow": {"state": "unavailable", "net": 0},
    }]) is False
    assert history.stats()["entries"] == 0
