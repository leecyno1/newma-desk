import copy
import json
from pathlib import Path

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research.supply_chain import (
    IndustryChainResearchEngine,
    IndustryChainResearchError,
    SupplyChainResearchEngine,
    SupplyChainResearchError,
)
from instock.web.industry_chain_handler import IndustryChainResearchHandler
from instock.web.supply_chain_handler import SupplyChainResearchHandler


ROOT = Path(__file__).resolve().parents[1]


def research_packet():
    return {
        "schema_version": "1.0",
        "theme": "AI 光通信扩产瓶颈",
        "market": "CN",
        "as_of": "2026-08-08",
        "evidence": [
            {
                "id": "ev-order",
                "claim": "客户扩产公告确认高速光模块需求增长",
                "strength": "strong",
                "source_type": "filing",
                "source_ref": "newma://filings/ev-order",
                "observed_at": "2026-08-07",
            },
            {
                "id": "ev-capacity",
                "claim": "产能建设周期超过两个季度",
                "strength": "medium",
                "source_type": "project_record",
                "source_ref": "newma://projects/ev-capacity",
                "observed_at": "2026-08-06",
            },
            {
                "id": "ev-company",
                "claim": "公司披露相关业务收入占比提升",
                "strength": "strong",
                "source_type": "filing",
                "source_ref": "newma://filings/ev-company",
                "observed_at": "2026-08-08",
            },
        ],
        "layers": [
            {
                "id": "optical-engine",
                "name": "光引擎与关键器件",
                "constraint": "验证周期和良率限制供给爬坡",
                "ratings": {
                    "demand_pressure": 5,
                    "chokepoint_severity": 5,
                    "supplier_concentration": 4,
                    "expansion_difficulty": 4,
                    "substitution_difficulty": 4,
                },
                "evidence_ids": ["ev-order", "ev-capacity"],
            },
            {
                "id": "generic-components",
                "name": "普通零部件",
                "constraint": "供应商较多，替代路线清晰",
                "ratings": {
                    "demand_pressure": 4,
                    "chokepoint_severity": 2,
                    "supplier_concentration": 1,
                    "expansion_difficulty": 2,
                    "substitution_difficulty": 1,
                },
                "evidence_ids": ["ev-order"],
            },
        ],
        "candidates": [
            {
                "symbol": "300502.SZ",
                "name": "示例公司",
                "market": "CN",
                "layer_id": "optical-engine",
                "ratings": {
                    "exposure_purity": 4,
                    "valuation_disconnect": 3,
                    "catalyst_timing": 4,
                    "financial_resilience": 4,
                },
                "penalties": {
                    "dilution_financing": 0,
                    "governance": 0,
                    "geopolitics": 1,
                    "liquidity": 0,
                    "hype_risk": 1,
                    "accounting_quality": 0,
                    "cyclicality": 1,
                    "alternative_design_risk": 1,
                },
                "evidence_ids": ["ev-company", "ev-capacity"],
                "invalidation": [
                    "两个季度内替代供应商完成批量认证",
                    "相关业务毛利率连续两个报告期下降",
                ],
            }
        ],
    }


def industry_chain_packet():
    packet = research_packet()
    packet["schema_version"] = "2.0"
    packet["chain"] = {
        "nodes": [
            {
                "id": "optical-engine",
                "name": "光引擎与关键器件",
                "stage": "midstream",
                "role": "承接上游器件并形成高速光模块核心能力",
                "evidence_ids": ["ev-order", "ev-capacity"],
            },
            {
                "id": "generic-components",
                "name": "普通零部件",
                "stage": "upstream",
                "role": "提供可替代的通用零部件",
                "evidence_ids": ["ev-order"],
            },
        ],
        "links": [
            {
                "source": "generic-components",
                "target": "optical-engine",
                "relation": "向核心光引擎提供通用零部件",
                "criticality": 2,
                "evidence_ids": ["ev-order"],
            }
        ],
    }
    for layer in packet["layers"]:
        layer["node_id"] = layer["id"]
    return packet


def test_engine_ranks_layers_and_candidates_with_traceable_evidence():
    result = IndustryChainResearchEngine().analyze(industry_chain_packet())

    assert result["engine"] == {
        "name": "instock-industry-chain-research",
        "version": "2.3.1",
        "methodology": "industry-chain-topology-bottleneck-evidence-ranking-v1",
        "calibrated_backtest": False,
    }
    assert result["theme"] == "AI 光通信扩产瓶颈"
    assert result["data_state"] == "complete"
    assert result["layers"][0]["id"] == "optical-engine"
    assert result["layers"][0]["priority_score"] > result["layers"][1]["priority_score"]
    assert result["candidates"][0]["symbol"] == "300502.SZ"
    assert result["candidates"][0]["evidence_summary"]["strong"] == 1
    assert result["candidates"][0]["research_priority"] in {
        "top_priority", "high_priority", "worth_tracking"
    }
    assert result["chain"]["critical_nodes"][0]["id"] == "optical-engine"
    assert result["summary"]["chain_node_count"] == 2
    assert result["summary"]["chain_link_count"] == 1
    assert result["snapshot"]["snapshot_id"].startswith("instock-industry-chain-research:")
    assert result["snapshot"]["provenance"]["provider"] == "newma-desk-agent"
    assert result["snapshot"]["result"]["summary"]["candidate_count"] == 1
    assert result["snapshot"]["result"]["evidence"]["candidates"][0]["symbol"] == "300502.SZ"


def test_chain_without_company_candidates_preserves_relationship_evidence():
    packet = industry_chain_packet()
    packet["candidates"] = []
    result = IndustryChainResearchEngine().analyze(packet)
    assert result["candidates"] == []
    assert result["summary"]["top_candidate"] is None
    assert result["summary"]["candidate_count"] == 0
    assert result["summary"]["chain_link_count"] == 1
    assert result["data_state"] == "partial"
    assert "no_supported_company_candidates" in result["limitations"]
    assert result["snapshot"]["result"]["evidence"]["candidates"] == []
    assert result["verification"]["sources_verified"] is False


def test_relationships_without_bottleneck_ratings_remain_partial_and_unranked():
    packet = industry_chain_packet()
    packet.update(layers=[], candidates=[], notes="联网未获准，来源与关系仍待原文核验。")
    result = IndustryChainResearchEngine().analyze(packet)
    assert result["summary"]["chain_link_count"] == 1
    assert result["summary"]["top_layer"] is None
    assert result["summary"]["top_chain_node"] is None
    assert result["chain"]["critical_nodes"] == []
    assert all(row["bottleneck_score"] is None and row["criticality_score"] is None
               for row in result["chain"]["nodes"])
    assert result["summary"]["notes"] == packet["notes"]
    assert result["snapshot"]["result"]["summary"]["notes"] == packet["notes"]
    assert result["data_state"] == "partial"
    assert "no_supported_bottleneck_layers" in result["limitations"]
    assert result["verification"]["sources_verified"] is False
    schema = json.loads((ROOT / "integrations/newma-desk/schemas/industry-chain-research-packet.schema.json").read_text())
    assert schema["properties"]["layers"]["minItems"] == 0


def test_missing_layers_do_not_allow_dangling_candidates_or_empty_legacy_topology():
    packet = industry_chain_packet()
    packet["layers"] = []
    with pytest.raises(IndustryChainResearchError, match="layer_id 不存在"):
        IndustryChainResearchEngine().analyze(packet)
    legacy = research_packet()
    legacy.update(layers=[], candidates=[])
    with pytest.raises(IndustryChainResearchError, match="layers"):
        IndustryChainResearchEngine().analyze(legacy)


def test_engine_caps_priority_when_candidate_has_no_strong_evidence():
    packet = industry_chain_packet()
    packet["evidence"][2]["strength"] = "weak"
    packet["evidence"][1]["strength"] = "weak"

    result = SupplyChainResearchEngine().analyze(packet)

    candidate = result["candidates"][0]
    assert candidate["research_priority"] == "early_lead"
    assert candidate["confidence"] == "low"
    assert "candidate_without_strong_or_medium_evidence:300502.SZ" in result["limitations"]
    assert result["data_state"] == "partial"


def test_engine_does_not_treat_same_source_claims_as_high_confidence():
    packet = industry_chain_packet()
    packet["evidence"][1]["strength"] = "strong"
    packet["evidence"][1]["source_ref"] = packet["evidence"][2]["source_ref"]

    result = SupplyChainResearchEngine().analyze(packet)

    candidate = result["candidates"][0]
    assert candidate["evidence_summary"]["strong"] == 2
    assert candidate["evidence_summary"]["source_count"] == 1
    assert candidate["confidence"] == "medium"
    assert candidate["research_priority"] != "top_priority"
    assert "candidate_evidence_source_concentration:300502.SZ" in result["limitations"]


def test_engine_rejects_unknown_factor_and_dangling_evidence():
    packet = industry_chain_packet()
    packet["layers"][0]["ratings"]["made_up_factor"] = 5
    with pytest.raises(SupplyChainResearchError, match="未知评分字段"):
        SupplyChainResearchEngine().analyze(packet)

    packet = industry_chain_packet()
    packet["candidates"][0]["evidence_ids"] = ["missing"]
    with pytest.raises(SupplyChainResearchError, match="不存在的证据"):
        SupplyChainResearchEngine().analyze(packet)


def test_engine_is_deterministic_except_for_generation_time():
    packet = industry_chain_packet()
    first = SupplyChainResearchEngine().analyze(copy.deepcopy(packet))
    second = SupplyChainResearchEngine().analyze(copy.deepcopy(packet))

    assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]
    assert first["layers"] == second["layers"]
    assert first["candidates"] == second["candidates"]


def test_legacy_schema_remains_available_through_compatibility_alias():
    result = SupplyChainResearchEngine().analyze(research_packet())

    assert result["schema_version"] == "1.0"
    assert result["canonical_schema_version"] == "2.0"
    assert "legacy_packet_without_explicit_chain_topology" in result["limitations"]
    assert result["chain"]["links"] == []
    assert SupplyChainResearchError is IndustryChainResearchError


def test_evidence_catalogue_and_directed_links_survive_result_and_snapshot():
    packet = industry_chain_packet()
    result = IndustryChainResearchEngine().analyze(packet)
    assert result["evidence"] == packet["evidence"]
    assert result["verification"] == {
        "scope": "structure_references_dates",
        "sources_verified": False,
        "ratings_origin": "input_packet",
    }
    archive = result["snapshot"]["result"]["evidence"]
    assert archive["sources"] == result["evidence"]
    assert archive["chain"]["links"] == result["chain"]["links"]
    for link in archive["chain"]["links"]:
        assert set(link["evidence_ids"]) <= {item["id"] for item in archive["sources"]}


def test_adopted_revenue_can_support_company_facts_but_not_relationships_or_bottlenecks():
    packet = industry_chain_packet()
    packet["evidence"][-1]["source_type"] = "user-adopted-filing-row"
    packet["evidence"][-1]["strength"] = "unverified"
    result = IndustryChainResearchEngine().analyze(packet)
    assert result["evidence"][-1]["strength"] == "unverified"
    for target in ("link", "layer"):
        invalid = copy.deepcopy(packet)
        row = invalid["chain"]["links"][0] if target == "link" else invalid["layers"][0]
        row["evidence_ids"].append(packet["evidence"][-1]["id"])
        with pytest.raises(IndustryChainResearchError, match="主营收入材料不能"):
            IndustryChainResearchEngine().analyze(invalid)


def test_published_packet_schema_and_non_research_example_match_engine_contract():
    schema = json.loads((
        ROOT / "integrations" / "newma-desk" / "schemas" /
        "industry-chain-research-packet.schema.json"
    ).read_text("utf-8"))
    example = json.loads((
        ROOT / "integrations" / "newma-desk" / "examples" /
        "supply-chain-research.packet.json"
    ).read_text("utf-8"))

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
    assert set(schema["$defs"]["layer_ratings"]["required"]) == {
        "demand_pressure", "chokepoint_severity", "supplier_concentration",
        "expansion_difficulty", "substitution_difficulty",
    }
    assert set(schema["$defs"]["candidate_penalties"]["required"]) == {
        "dilution_financing", "governance", "geopolitics", "liquidity",
        "hype_risk", "accounting_quality", "cyclicality", "alternative_design_risk",
    }
    assert "非真实研究结论" in example["theme"]
    result = SupplyChainResearchEngine().analyze(example)
    assert result["summary"]["top_candidate"] == "EXAMPLE.CN"
    assert result["data_state"] == "partial"


class IndustryChainResearchHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([
            (r"/api/v1/industry-chain/research", IndustryChainResearchHandler),
            (r"/api/v1/rotations/supply-chain-research", SupplyChainResearchHandler),
        ])

    def setUp(self):
        get_analysis_snapshot_registry().clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        get_analysis_snapshot_registry().clear()

    def test_post_returns_v1_contract_and_registers_snapshot(self):
        response = self.fetch(
            "/api/v1/industry-chain/research",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(industry_chain_packet(), ensure_ascii=False),
        )
        payload = json.loads(response.body)

        assert response.code == 200
        assert payload["ok"] is True
        assert payload["meta"]["api_version"] == "1.0"
        snapshot_id = payload["data"]["snapshot"]["snapshot_id"]
        assert get_analysis_snapshot_registry().get(snapshot_id)["snapshot_id"] == snapshot_id

    def test_post_rejects_invalid_packet_with_structured_error(self):
        response = self.fetch(
            "/api/v1/industry-chain/research",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"schema_version": "1.0"}),
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["error"]["code"] == "invalid_research_packet"
