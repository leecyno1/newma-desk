import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import funds, market_indices


SNAPSHOT = {
    "index_code": "HSI",
    "as_of_date": "2026-07-31",
    "source": "hang_seng_indexes.official",
    "constituents": [
        {
            "constituent_code": "01109.HK",
            "constituent_name": "华润置地",
            "industry": "地产建筑",
            "weight": 0.012,
            "evidence_url": "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsie.pdf",
        },
        {
            "constituent_code": "00700.HK",
            "constituent_name": "腾讯控股",
            "industry": "信息技术",
            "weight": None,
            "evidence_url": "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsie.pdf",
        },
    ],
}


class Repo:
    def get_latest_on_or_before(self, index_code, as_of_date):
        assert index_code == "HSI"
        return SNAPSHOT if as_of_date >= "2026-07-31" else None

    def get_latest(self, index_code):
        assert index_code == "HSCI-INDUSTRY"
        return SNAPSHOT


def main():
    original_get_repo = market_indices._get_repo
    market_indices._get_repo = lambda: Repo()
    try:
        app = FastAPI()
        app.include_router(market_indices.router)
        response = TestClient(app).get("/api/market-indices/HSI/constituents?as_of_date=2026-08-01")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["snapshot_as_of_date"] == "2026-07-31", payload
        assert payload["coverage"]["constituent_count"] == 2, payload
        assert payload["coverage"]["weighted_constituent_count"] == 1, payload
        assert payload["coverage"]["published_weight"] == 0.012, payload
        assert TestClient(app).get("/api/market-indices/HSI/constituents?as_of_date=2026-06-30").status_code == 404
    finally:
        market_indices._get_repo = original_get_repo

    import repositories

    original_repo_getter = repositories.get_market_index_constituent_repo
    repositories.get_market_index_constituent_repo = lambda: Repo()
    try:
        holdings = [
            {"stock_code": "01109.HK", "industry": "未知", "fund_nav_weight": 0.2},
            {"stock_code": "600000.SH", "industry": "银行", "fund_nav_weight": 0.3},
        ]
        evidence = funds._enrich_holding_industry_evidence(holdings)
        summary = funds._holding_summary(holdings)
        assert holdings[0]["industry"] == "地产建筑", holdings
        assert holdings[0]["industry_source"] == "hang_seng_indexes.official", holdings
        assert evidence["matched_holding_count"] == 1, evidence
        assert summary["market_buckets"] == [
            {"market": "沪市", "weight": 0.3},
            {"market": "港股", "weight": 0.2},
        ], summary
    finally:
        repositories.get_market_index_constituent_repo = original_repo_getter

    print("OK index snapshots and Hong Kong holding industries expose point-in-time evidence")


if __name__ == "__main__":
    main()
