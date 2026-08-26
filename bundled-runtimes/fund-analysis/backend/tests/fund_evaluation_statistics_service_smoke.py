from services.peer_comparison_service import PeerComparisonService
from services.professional_scoring_service import ProfessionalScoringService


class StatisticsPeerComparisonService(PeerComparisonService):
    def _peer_universe(self, wind_code, target_context=None):
        classification = {
            "status": "classified",
            "peer_group_id": "peer-active",
            "peer_group": "主动权益-核心均衡",
            "primary_benchmark": "中证800",
            "evaluation_profile_key": "active_equity",
            "minimum_peer_count": 5,
        }
        funds = [
            {
                "wind_code": f"00000{index}.OF",
                "name": f"基金{index}",
                "type": "股票型",
                "establishment_date": "2020-01-01",
            }
            for index in range(1, 7)
        ]
        target = {
            **funds[0],
            "classification": classification,
            "research_profile": {"peer_group": classification["peer_group"]},
        }
        return target, funds, "standardized_peer_group_membership"

    def _metric_map(self, wind_codes, fund_rows=None, preloaded_panels=None):
        result = {}
        for index, code in enumerate(wind_codes, start=1):
            result[code] = {
                "1y": {
                    "annualized_return": -0.02 + index * 0.025,
                    "max_drawdown": -0.30 + index * 0.025,
                    "annualized_volatility": 0.30 - index * 0.02,
                    "sharpe_ratio": index * 0.2,
                    "calmar_ratio": index * 0.25,
                    "positive_return_ratio": 0.45 + index * 0.03,
                },
                "latest": {},
            }
        return result


if __name__ == "__main__":
    service = StatisticsPeerComparisonService(scoring_service=ProfessionalScoringService())
    result = service.build_peer_statistics("000001.OF", window="1y")

    assert result["status"] == "sufficient", result
    assert result["peer_group"] == "主动权益-核心均衡", result
    assert result["classified_peer_count"] == 6, result
    assert result["scored_peer_count"] == 6, result
    assert result["current"]["rank"] == 6, result
    assert sum(item["count"] for item in result["distribution"]) == 6, result
    assert result["summary"]["average"] is not None, result
    assert len(result["ranking"]) == 6, result
    assert result["ranking"][0]["rank"] == 1, result
    assert result["ranking"][0]["grade"] in {"S", "A", "B", "C", "D", "E"}, result
    assert result["ranking"][0]["data_coverage"]["required_metric_count"] == 3, result
    assert result["unscored_peer_count"] == 0, result
    assert {item["key"] for item in result["dimensions"]} >= {
        "return", "risk", "risk_adjusted", "consistency",
    }, result
    assert result["boundary"].startswith("仅比较同一分类"), result

    print("OK peer evaluation statistics expose distribution, dimension averages and current position")
