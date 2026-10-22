from __future__ import annotations

import json

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research.research_book import ResearchBookEngine, ResearchBookError
from instock.web.research_book_handler import ResearchBookHandler


def _register_fixture_snapshot(snapshot_id="instock-stock-research-dossier:fixture"):
    return get_analysis_snapshot_registry().register({
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "generated_at": "2026-08-11T10:00:00+08:00",
        "analysis": {"name": "instock-stock-research-dossier", "version": "1.0.0"},
        "parameters": {}, "data_window": {"coverage": "complete", "end_date": "2026-08-11"},
        "provenance": {}, "freshness": {"state": "current"},
        "input": {"digest": "sha256:fixture", "summary": {}},
        "result": {"digest": "sha256:fixture", "summary": {"symbol": "300502", "market": "CN",
            "name": "测试公司", "sector": "通信", "conclusion": "仅供验收的观察判断",
            "tensions": ["产业链证伪：订单取消，且回款下降"], "strengths": [],
            "gaps": ["客户暴露未核实，不能推断实际收入"], "invalidation_conditions": ["交付连续两季下降，且无新增订单"]}},
    })


def _packet():
    return {
        "schema_version": "instock-research-book-packet-v1",
        "name": "核心观察组合",
        "as_of": "2026-08-11",
        "items": [
            {
                "symbol": "300502", "name": "新易盛", "market": "CN",
                "sector": "通信", "target_weight_pct": 25,
                "thesis": "高速光模块需求与交付能力需持续核验",
                "invalidation": ["订单增速显著低于预期", "现金转化持续恶化"],
                "risk_tags": ["高估值", "客户集中"],
                "snapshot_ids": ["instock-stock-research-dossier:fixture"],
            },
            {
                "symbol": "000001", "name": "平安银行", "market": "CN",
                "sector": "银行", "target_weight_pct": 15,
                "thesis": "资产质量和息差企稳仍需跟踪",
                "invalidation": ["不良率持续抬升"],
                "risk_tags": ["宏观信用"],
                "snapshot_ids": ["missing:snapshot"],
            },
        ],
    }


def test_research_book_resolves_snapshots_and_aggregates_exposure_and_risk():
    registry = get_analysis_snapshot_registry()
    registry.clear()
    _register_fixture_snapshot()

    result = ResearchBookEngine().analyze(_packet())

    assert result["engine"]["name"] == "instock-research-book"
    assert result["summary"] == {
        "items": 2,
        "total_target_weight_pct": 40.0,
        "cash_weight_pct": 60.0,
        "resolved_snapshots": 1,
        "missing_snapshots": 1,
        "data_state": "partial",
    }
    assert result["exposures"]["sectors"] == [
        {"name": "通信", "weight_pct": 25.0},
        {"name": "银行", "weight_pct": 15.0},
    ]
    assert result["exposures"]["risks"][0] == {"name": "客户集中", "weight_pct": 25.0}
    assert result["items"][0]["snapshot_coverage"] == "complete"
    assert result["items"][1]["snapshot_coverage"] == "missing"
    assert "position_concentration:300502" in result["warnings"]
    assert result["snapshot"]["snapshot_id"].startswith("instock-research-book:")
    assert registry.get(result["snapshot"]["snapshot_id"]) == result["snapshot"]


@pytest.mark.parametrize("change,state", [
    ({"symbol": "000001"}, "security_mismatch"),
    ({"symbol": "300502.SH", "item_symbol": "300502.SZ"}, "security_mismatch"),
    ({"market": "US"}, "market_mismatch"),
    ({"end_date": "2026-08-12"}, "after_cutoff"),
    ({"end_date": None}, "date_unknown"),
    ({"engine": "other-engine"}, "scope_unverified"),
])
def test_reference_rejects_wrong_security_market_date_and_unknown_scope(change, state):
    snapshot = _register_fixture_snapshot()
    for key in ("symbol", "market"):
        if key in change: snapshot["result"]["summary"][key] = change[key]
    if "end_date" in change: snapshot["data_window"]["end_date"] = change["end_date"]
    if "engine" in change: snapshot["analysis"]["name"] = change["engine"]
    get_analysis_snapshot_registry().register(snapshot)
    packet = _packet(); packet["items"] = packet["items"][:1]
    if "item_symbol" in change: packet["items"][0]["symbol"] = change["item_symbol"]
    result = ResearchBookEngine().analyze(packet)
    assert result["items"][0]["snapshot_references"][0]["state"] == state
    assert result["summary"]["resolved_snapshots"] == 0
    assert result["data_state"] == "partial"


def test_matched_partial_source_stays_partial_and_retains_original_risks():
    snapshot = _register_fixture_snapshot()
    snapshot["data_window"]["coverage"] = "partial"
    get_analysis_snapshot_registry().register(snapshot)
    packet = _packet(); packet["items"] = packet["items"][:1]
    result = ResearchBookEngine().analyze(packet)
    ref = result["items"][0]["snapshot_references"][0]
    assert ref["state"] == "resolved"
    assert result["data_state"] == "partial"
    assert ref["research"]["tensions"] == ["产业链证伪：订单取消，且回款下降"]
    assert any(warning.startswith("source_incomplete:") for warning in result["warnings"])


def test_dossier_handoff_keeps_full_text_zero_weight_and_source_date():
    snapshot = _register_fixture_snapshot()
    draft = ResearchBookEngine().draft_from_dossier(snapshot["snapshot_id"], symbol="300502.SZ")
    assert draft["as_of"] == "2026-08-11"
    assert draft["item"]["target_weight_pct"] == 0
    assert draft["item"]["risk_tags"] == ["产业链证伪：订单取消，且回款下降", "客户暴露未核实，不能推断实际收入"]
    assert draft["item"]["invalidation"] == ["交付连续两季下降，且无新增订单"]
    for symbol, market in [("000001", "CN"), ("300502", "US")]:
        with pytest.raises(ResearchBookError, match="不符"):
            ResearchBookEngine().draft_from_dossier(snapshot["snapshot_id"], symbol=symbol, market=market)
    snapshot["result"]["summary"].pop("gaps")
    get_analysis_snapshot_registry().register(snapshot)
    with pytest.raises(ResearchBookError, match="旧公司档案"):
        ResearchBookEngine().draft_from_dossier(snapshot["snapshot_id"], symbol="300502")


def test_chain_review_context_only_follows_the_matched_security_direct_links():
    snapshot = _register_fixture_snapshot("chain:book-review")
    snapshot["analysis"]["name"] = "instock-industry-chain-research"
    snapshot["parameters"] = {"theme": "测试供应链", "market": "CN"}
    snapshot["result"]["evidence"] = {
        "candidates": [{"symbol": "300502.SZ", "market": "CN", "layer_id": "l1", "evidence_ids": ["s1"]}],
        "layers": [{"id": "l1", "node_id": "b"}],
        "chain": {"nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "links": [
            {"source": "a", "target": "b", "evidence_ids": ["s1"]},
            {"source": "c", "target": "a", "evidence_ids": ["s2"]}]},
        "sources": [{"id": "s1", "claim": "直接关系"}, {"id": "s2", "claim": "不应传播的其他关系"}],
    }
    registry = get_analysis_snapshot_registry(); registry.register(snapshot)
    packet = _packet(); packet["items"] = packet["items"][:1]
    packet["items"][0]["snapshot_ids"] = [snapshot["snapshot_id"]]
    ref = ResearchBookEngine().analyze(packet)["items"][0]["snapshot_references"][0]
    assert ref["state"] == "resolved"
    context = ref["review_context"]["research_context"]
    assert context["theme"] == "测试供应链"
    assert [(link["source"], link["target"]) for link in context["chain"]["links"]] == [("a", "b")]
    assert [source["id"] for source in context["evidence"]] == ["s1"]
    assert "note" not in json.dumps(ref, ensure_ascii=False)
    packet["items"][0]["symbol"] = "000001"
    assert "review_context" not in ResearchBookEngine().analyze(packet)["items"][0]["snapshot_references"][0]
    packet["items"][0]["symbol"] = "300502"
    snapshot["result"]["evidence"]["candidates"].append({"symbol": "300502.SZ", "market": "CN", "layer_id": "l2"})
    registry.register(snapshot)
    ref = ResearchBookEngine().analyze(packet)["items"][0]["snapshot_references"][0]
    assert ref["state"] == "scope_ambiguous"
    assert "review_context" not in ref


def test_research_origin_keeps_only_a_locator_and_never_claims_to_verify_it():
    packet = _packet()
    origin = {"researchOriginId": "a" * 32, "originUserId": "u", "originWorkspaceId": "w",
              "snapshotId": packet["items"][0]["snapshot_ids"][0]}
    packet["items"][0]["research_origin"] = origin
    result = ResearchBookEngine().analyze(packet)
    assert result["items"][0]["research_origin"] == origin
    assert "research_origin" not in result["snapshot"]["result"]["summary"]
    origin["excerpt"] = "private text must be separately authorized"
    with pytest.raises(ResearchBookError, match="不能包含原文"):
        ResearchBookEngine().analyze(packet)
    origin.pop("excerpt")
    origin["snapshotId"] = "unlinked:source"
    with pytest.raises(ResearchBookError, match="未关联对应来源快照"):
        ResearchBookEngine().analyze(packet)


def test_research_book_rejects_overallocated_or_thesis_free_items():
    packet = _packet()
    packet["items"][0]["target_weight_pct"] = 90
    packet["items"][1]["target_weight_pct"] = 20
    with pytest.raises(ResearchBookError, match="总目标权重不能超过 100"):
        ResearchBookEngine().analyze(packet)

    packet = _packet()
    packet["items"][0]["thesis"] = ""
    with pytest.raises(ResearchBookError, match="thesis 不能为空"):
        ResearchBookEngine().analyze(packet)


class ResearchBookHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/v1/research-books", ResearchBookHandler)])

    def test_post_returns_research_book(self):
        get_analysis_snapshot_registry().clear()
        _register_fixture_snapshot()
        response = self.fetch(
            "/api/v1/research-books", method="POST",
            headers={"Content-Type": "application/json"}, body=json.dumps(_packet()),
        )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["ok"] is True
        assert payload["data"]["summary"]["items"] == 2
        assert payload["meta"]["history"]["module_id"] == "research-book"

    def test_get_handoff_and_reject_security_mismatch(self):
        snapshot = _register_fixture_snapshot()
        url = f"/api/v1/research-books?sourceSnapshotId={snapshot['snapshot_id']}&symbol="
        response = self.fetch(url + "300502.SZ")
        assert response.code == 200
        assert json.loads(response.body)["data"]["item"]["target_weight_pct"] == 0
        assert self.fetch(url + "000001").code == 400

    def test_post_rejects_invalid_json(self):
        response = self.fetch("/api/v1/research-books", method="POST", body="{broken", raise_error=False)
        assert response.code == 400
        assert json.loads(response.body)["error"]["code"] == "invalid_json"
