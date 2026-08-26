import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_fof_holding_service import FundFofHoldingService


class _Repo:
    def __init__(self):
        self.rows = []

    def replace_period(self, wind_code, rows):
        self.rows = [{"wind_code": wind_code, **row} for row in rows]
        return len(rows)

    def list_latest_periods(self, wind_code, limit=8):
        return list(self.rows)


class _ClassificationRepo:
    def list_fund_peer_group_map(self, codes):
        return {
            "000001.OF": {
                "wind_code": "000001.OF",
                "peer_group_id": "peer-equity",
                "peer_group_name": "股票型-主动权益",
                "asset_class": "equity",
                "strategy_family_key": "active_equity_core",
                "source": "standardized-test",
            }
        }

    def list_fund_identity_map(self, codes):
        identities = {
            "000001.OF": {"wind_code": "000001.OF", "registered_fund_type": "股票型"},
            "511260.OF": {
                "wind_code": "511260.SH",
                "registered_fund_type": "指数型",
                "contract_type": "债券型",
            },
            "160644.OF": {"wind_code": "160644.SZ", "registered_fund_type": "QDII"},
            "180201.OF": {"wind_code": "180201.SZ", "registered_fund_type": "REITs"},
            "159985.OF": {
                "wind_code": "159985.SZ",
                "registered_fund_type": "指数型",
                "contract_type": "其他型",
                "invest_type": "豆粕期货型",
            },
        }
        return {code: identities[code] for code in codes if code in identities}


def main() -> int:
    payload = {
        "ErrCode": 0,
        "Success": True,
        "Expansion": "2026-06-30",
        "Datas": {"fundfofs": [
            {"TZJJDM": f"01{index:04d}", "TZJJMC": f"底层基金{index}", "ZJZBL": "5.00", "RZDF": "0.10"}
            for index in range(1, 7)
        ]},
    }
    rows = FundFofHoldingService.parse_payload(json.dumps(payload), source_url="https://example.test")
    if len(rows) != 6 or rows[0]["underlying_fund_code"] != "010001.OF":
        raise AssertionError(rows)
    if rows[0]["nav_ratio"] != 5.0 or rows[0]["daily_return"] != 0.1:
        raise AssertionError(rows[0])

    repo = _Repo()
    repo.replace_period("FOF.TEST", rows)
    result = FundFofHoldingService(repo=repo).get("FOF.TEST")
    if result.get("status") != "available":
        raise AssertionError(result)
    if (result.get("evidence_gate") or {}).get("status") != "sufficient":
        raise AssertionError(result)
    profile = result.get("professional_profile") or {}
    if profile.get("disclosed_fund_count") != 6 or profile.get("disclosed_nav_ratio") != 30.0:
        raise AssertionError(profile)
    if not profile.get("double_fee_status"):
        raise AssertionError(profile)
    projected = FundFofHoldingService.profile_from_snapshot(result)
    if projected.get("concentration_label") != "中等集中" or projected.get("report_date") != "2026-06-30":
        raise AssertionError(projected)
    style_evidence = FundFofHoldingService.style_evidence(projected)
    if [item.get("value") for item in style_evidence] != ["底层中等集中"]:
        raise AssertionError(style_evidence)
    if style_evidence[0].get("disclosed_fund_count") != 6:
        raise AssertionError(style_evidence)

    classification_map = {
        f"01{index:04d}.OF": {
            "peer_group_id": f"peer-{index}",
            "peer_group_name": "权益类测试" if index <= 4 else "固收类测试",
            "asset_class": "equity" if index <= 4 else "fixed_income",
            "strategy_family_key": "active_equity_core" if index <= 4 else "fixed_income_general",
            "source": "test",
        }
        for index in range(1, 7)
    }
    batch_profiles = FundFofHoldingService.professional_profiles_from_rows(
        {"FOF.TEST": repo.rows},
        classification_map,
    )
    if batch_profiles["FOF.TEST"].get("disclosed_nav_ratio") != 30.0:
        raise AssertionError(batch_profiles)
    batch_profile = batch_profiles["FOF.TEST"]
    if batch_profile.get("classification_coverage") != 1.0:
        raise AssertionError(batch_profile)
    if batch_profile.get("dominant_classification") != "权益类":
        raise AssertionError(batch_profile)
    if batch_profile.get("classification_style_label") != "底层权益基金主导":
        raise AssertionError(batch_profile)
    batch_styles = {item.get("value") for item in FundFofHoldingService.style_evidence(batch_profile)}
    if batch_styles != {"底层中等集中", "底层权益基金主导"}:
        raise AssertionError(batch_styles)

    lookthrough_map = FundFofHoldingService.build_classification_map(
        _ClassificationRepo(),
        ["000001.OF", "511260.OF", "160644.OF", "180201.OF", "159985.OF"],
    )
    if lookthrough_map["000001.OF"].get("classification_level") != "standardized_peer_group":
        raise AssertionError(lookthrough_map)
    if lookthrough_map["511260.OF"].get("wind_code") != "511260.SH":
        raise AssertionError(lookthrough_map)
    expected_assets = {
        "511260.OF": "fixed_income",
        "160644.OF": "cross_market",
        "180201.OF": "reit",
        "159985.OF": "commodities",
    }
    for code, asset_class in expected_assets.items():
        if lookthrough_map[code].get("asset_class") != asset_class:
            raise AssertionError(lookthrough_map[code])

    print("OK FOF public underlying holdings are parsed, persisted and evidence-gated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
