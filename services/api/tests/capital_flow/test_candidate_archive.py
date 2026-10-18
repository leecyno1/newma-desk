from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vibe_visualization_api.capital_flow.candidate_archive import archive, archive_detail
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.turnover_candidates import DATASET, RULE
from vibe_visualization_api.capital_flow.routes import router
from vibe_visualization_api.config import get_settings


def save(store, day, count=0, control=True):
    row = {"date": day, "capturedAt": day + "T08:00:00+00:00", "rules": {**RULE, "minOwnRatio": 2.7},
           "baselineStart": "2019-12-01", "baselineEnd": "2019-12-31", "eligibleCount": 90,
           "marketMedianRatio": 1.2, "candidates": [
               {"code": f"{i:06}.SZ", "amountYi": 3, "baselineYi": 1, "ownRatio": 3,
                "marketAdjustedRatio": 2.5, "signalPct": None} for i in range(count)]}
    if control:
        row["eligibleCodes"] = [f"{i:06}.SZ" for i in range(90)]
    return store.save_once(DATASET, RULE["id"], row)


def test_long_archive_range_paging_empty_cohort_and_read_only(tmp_path):
    store = CapitalHistoryStore(tmp_path / "archive.db")
    for n in range(22):
        save(store, (date(2020, 1, 1) + timedelta(days=n)).isoformat())
    first = archive(store, "1990-01-01", "9999-12-31")
    assert first["total"] == 22 and first["pageCount"] == 2 and len(first["rows"]) == 20
    assert first["rows"][0]["signalDate"] == "2020-01-22"
    last = archive(store, "1990-01-01", "9999-12-31", 99)
    assert last["page"] == 2 and len(last["rows"]) == 2
    assert last["rows"][-1]["candidateCount"] == 0
    filtered = archive(store, "2020-01-05", "2020-01-06")
    assert [row["signalDate"] for row in filtered["rows"]] == ["2020-01-06", "2020-01-05"]
    assert archive(store, "2021-01-01", "2022-01-01")["total"] == 0
    assert archive_detail(store, "2020-01-01")["candidates"] == []
    assert archive_detail(store, "2020-02-01") is None
    assert archive(store, "1990-01-01", "9999-12-31") == first


def test_frozen_rules_details_and_missing_control_not_reconstructed(tmp_path):
    store = CapitalHistoryStore(tmp_path / "archive.db")
    before = save(store, "2020-01-01", count=51, control=False)
    first = archive_detail(store, "2020-01-01")
    assert first["candidateCount"] == 51 and len(first["candidates"]) == 50
    assert first["rules"]["minOwnRatio"] == 2.7  # not current RULE
    assert first["controlStatus"] == "missing" and first["controlCount"] is None
    assert first["verification"] == "not-evaluated" and "windows" not in first
    second = archive_detail(store, "2020-01-01", 99)
    assert second["page"] == 2 and second["candidates"][0]["code"] == "000050.SZ"
    assert "eligibleCodes" not in first
    assert store.read(DATASET, RULE["id"], "2020-01-01", "2020-01-01")[0] == [before]
    save(store, "2020-01-02", count=3)
    assert archive_detail(store, "2020-01-02")["controlCount"] == 87


def test_archive_routes_work_without_provider_credentials_and_validate_dates(tmp_path):
    path = tmp_path / "archive.db"
    save(CapitalHistoryStore(path), "2020-01-01", count=1)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(database_path=path, enable_capital_candidate_archive=False,
                                                                    tushare_token=SimpleNamespace(get_secret_value=lambda: ""))
    with TestClient(app) as client:
        root = "/api/capital-flow/turnover-candidate-archive"
        assert client.get(root).json()["total"] == 1
        assert client.get(root + "/2020-01-01").json()["candidateCount"] == 1
        assert client.get(root + "/2020-01-02").status_code == 404
        for query in ("?page=0", "?start=2020-02-30", "?start=2022-01-01&end=2020-01-01"):
            assert client.get(root + query).status_code == 422
        assert client.get(root + "/2020-02-30").status_code == 422
