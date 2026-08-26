import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib import error as urllib_error

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from path_config import get_project_root

ROOT = get_project_root()
TMP_ROOT = ROOT / '.tmp_test'

import phase2_rebuilder as mod


def project_tempdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_ROOT)


class Phase2AIBriefTests(unittest.TestCase):
    def setUp(self):
        evidence_pool = [
            {
                "title": "油价上行后，美债和黄金同步波动",
                "url": "https://example.com/a",
                "source_type": "聚合新闻",
                "source_tier": "mainstream_media",
                "note": "市场开始重新交易通胀与利率预期。",
                "entities": ["油价", "美联储", "黄金"],
                "trendradar_signal": True,
                "signal_score": 8.4,
                "logic_chain_id": "oil-fed-chain",
            },
            {
                "title": "美联储官员讲话强调通胀粘性",
                "url": "https://example.com/b",
                "source_type": "聚合新闻",
                "source_tier": "official",
                "note": "政策口径偏谨慎，降息预期反复。",
                "entities": ["美联储", "通胀"],
                "trendradar_signal": False,
                "signal_score": 8.0,
                "logic_chain_id": "oil-fed-chain",
            },
            {
                "title": "特朗普关税表态后，市场再估输入型通胀风险",
                "url": "https://example.com/c",
                "source_type": "微博",
                "source_tier": "platform_hotspot",
                "note": "风险溢价与再通胀叙事重新纠缠。",
                "entities": ["特朗普", "关税", "通胀"],
                "trendradar_signal": True,
                "signal_score": 7.7,
                "logic_chain_id": "oil-fed-chain",
            },
        ]
        self.signal_bundle = {
            "requested_topic_count": 8,
            "manual_topics": [{"title": "再通胀不是事件，而是主线", "must_cover": True}],
            "trusted_evidence_pool": evidence_pool,
            "editorial_priority_pool": evidence_pool,
            "logic_chain_summaries": [
                {
                    "chain_id": "oil-fed-chain",
                    "summary_title": "油价 / 美联储",
                    "dominant_tokens": ["油价", "美联储", "通胀"],
                    "top_entities": ["特朗普"],
                    "top_titles": [item["title"] for item in evidence_pool],
                },
                {
                    "chain_id": "semi-chain",
                    "summary_title": "半导体 / 英伟达",
                    "dominant_tokens": ["半导体", "英伟达"],
                    "top_entities": ["英伟达"],
                    "top_titles": ["英伟达回暖不等于半导体全面复苏"],
                },
            ],
        }

    def sample_ai_cards(self):
        cards = []
        for index in range(8):
            cards.append(
                {
                    "topic_id": f"topic-{index}",
                    "topic_kind": "independent",
                    "title": f"再通胀不是事件，而是主线 {index}",
                    "one_line_judgment": "市场表面在交易事件，真正被重估的是通胀和利率预期。",
                    "core_proposition": f"第 {index} 题围绕再通胀和资产定价链条，证明市场主线并不是表面事件。",
                    "why_now": "油价、利率、黄金和政策口径同时出现再定价信号。",
                    "reader_payoff": "帮助读者识别哪些是情绪，哪些是真正影响股债商品的变量。",
                    "source_material_summary": "来源材料主要记录油价、美债、黄金和政策口径同步波动，显示市场开始讨论再通胀链条。",
                    "controversy_points": ["油价上涨究竟是短期地缘事件，还是再通胀主线的一部分。", "政策口径变化是否足以改变资产定价。"],
                    "viewpoint_notes": ["市场观点关注油价和美债联动。", "政策侧观点强调通胀粘性。"],
                    "article_use": "判断稿",
                    "distinctiveness_reason": f"第 {index} 题从不同角度切入，但不重复上一题。",
                    "evidence_gap_summary": "还缺高频通胀与政策预期联动数据。",
                    "proof_requirements": ["拆开油价和利率预期", "验证政策口径变化"],
                    "recommended_data_angles": ["油价与通胀预期对照", "美债收益率变化"],
                    "recommended_visual_angles": ["交易屏", "美联储新闻截图"],
                    "priority_people": ["特朗普"],
                    "priority_orgs": ["美联储"],
                    "priority_news_queries": ["oil inflation fed latest news"],
                    "structure_hint": {
                        "opening": "先指出市场把事件当主线的误判。",
                        "part_1": "拆开油价与通胀预期。",
                        "part_2": "拆开政策口径与利率定价。",
                        "part_3": "落到股债商品如何分化。",
                        "ending": "给出下一步该盯的变量。",
                    },
                }
            )
        return {"topic_cards": cards}

    def test_build_brief_signal_bundle_keeps_real_evidence(self):
        records = [
            mod.IntakeRecord(
                title="油价上行后，美债和黄金同步波动",
                summary="市场开始重新交易通胀与利率预期。",
                source="reports",
                source_item_id="1",
                raw_payload={"url": "https://example.com/a"},
                meta={"run_id": "2026-04-05_170457"},
                source_quality_tier="mainstream_media",
                entities={"commodities": ["油价"], "orgs": ["美联储"]},
                noise_tags=[],
                dynamic_cluster_key="oil-fed",
                dynamic_tokens=["油价", "通胀", "利率"],
                editor_labels=["宏观"],
                trendradar_signal=True,
                freshness_score=0.9,
                heat_score=82.0,
                heat_level="A",
                source_freshness_weight=0.9,
                source_timeliness_weight=0.95,
                source_authority_weight=1.1,
            )
        ]
        aux = {
            "brief_input": {"top_entities": {"orgs": [{"name": "美联储", "count": 3}]}},
            "channel_top10": {"reports": [{"title": "油价上行后，美债和黄金同步波动", "url": "https://example.com/a", "heat_level": "A", "heat_score": 82}]},
            "event_clusters": [{"cluster_id": "oil-fed", "cluster_title_candidate": "油价 / 美联储", "cluster_summary": "样本 1 条", "count": 1, "source_mix": {"reports": 1}, "dominant_entities": ["油价", "美联储"], "dominant_actions": ["波动"], "representative_titles": ["油价上行后，美债和黄金同步波动"], "representative_links": ["https://example.com/a"], "authority_score": 1.1, "timeliness_score": 0.95, "trendradar_coverage": 1.0, "avg_heat_score": 82.0, "noise_ratio": 0.0}],
        }
        bundle = mod.build_brief_signal_bundle("2026-04-05_170457", records, aux, ["再通胀不是事件，而是主线"], 8)
        self.assertEqual(bundle["stats"]["trusted_evidence_count"], 1)
        self.assertEqual(bundle["trusted_evidence_pool"][0]["title"], "油价上行后，美债和黄金同步波动")
        self.assertEqual(bundle["manual_topics"][0]["title"], "再通胀不是事件，而是主线")
        self.assertIn("logic_chain_summaries", bundle)

    def test_normalize_ai_brief_cards_outputs_flat_independent_cards(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        self.assertEqual(len(cards), 8)
        self.assertEqual(cards[0]["topic_kind"], "independent")
        self.assertEqual(cards[0]["mother_topic_id"], cards[0]["topic_id"])
        self.assertEqual(cards[0]["existing_evidence"][0]["url"], "https://example.com/a")
        self.assertIn("来源材料主要记录", cards[0]["source_material_summary"])
        self.assertTrue(cards[0]["controversy_points"])
        self.assertTrue(cards[0]["viewpoint_notes"])
        self.assertTrue(cards[0]["question_units"])
        self.assertTrue(cards[0]["opinion_units"])
        self.assertTrue(cards[0]["case_units"])
        self.assertTrue(cards[0]["solution_units"])

    def test_normalize_ai_brief_cards_preserves_returned_content_units(self):
        ai_result = self.sample_ai_cards()
        ai_result["topic_cards"][0]["question_units"] = ["市场现在到底在交易油价事件，还是再通胀主线？"]
        ai_result["topic_cards"][0]["opinion_units"] = ["油价只是入口，通胀预期才是主线。"]
        ai_result["topic_cards"][0]["case_units"] = ["美债与黄金同步波动。"]
        ai_result["topic_cards"][0]["solution_units"] = ["用油价、通胀预期和美债收益率三组数据交叉验证。"]

        cards = mod.normalize_ai_brief_cards(ai_result, self.signal_bundle)

        self.assertEqual(cards[0]["question_units"][0], "市场现在到底在交易油价事件，还是再通胀主线？")
        self.assertEqual(cards[0]["opinion_units"][0], "油价只是入口，通胀预期才是主线。")
        self.assertEqual(cards[0]["case_units"][0], "美债与黄金同步波动。")
        self.assertEqual(cards[0]["solution_units"][0], "用油价、通胀预期和美债收益率三组数据交叉验证。")

    def test_normalize_ai_brief_cards_enriches_ai_returned_evidence_with_chain(self):
        ai_result = self.sample_ai_cards()
        ai_result["topic_cards"][0]["existing_evidence"] = [
            {
                "title": "特朗普关税表态后，市场再估输入型通胀风险",
                "url": "https://example.com/c",
            }
        ]
        cards = mod.normalize_ai_brief_cards(ai_result, self.signal_bundle)
        self.assertEqual(cards[0]["existing_evidence"][0]["logic_chain_id"], "oil-fed-chain")

    def test_normalize_ai_brief_cards_can_use_event_cluster_representative_evidence(self):
        signal_bundle = dict(self.signal_bundle)
        signal_bundle["editorial_priority_pool"] = [
            {
                **self.signal_bundle["editorial_priority_pool"][0],
                "title": "机器人需要肢体和灵魂",
                "url": "https://mp.weixin.qq.com/s?__biz=robot&mid=1&idx=1&sn=aaa",
            }
        ]
        signal_bundle["trusted_evidence_pool"] = signal_bundle["editorial_priority_pool"]
        signal_bundle["event_clusters"] = [
            {
                "cluster_id": "a-share-sentiment",
                "cluster_summary": "A股开户、ETF资金流与赚钱效应修复形成同一事件簇。",
                "representative_titles": ["A股又到击球区"],
                "representative_links": ["https://mp.weixin.qq.com/s?__biz=market&mid=2&idx=1&sn=bbb"],
                "dominant_entities": ["A股", "ETF"],
                "avg_heat_score": 56.0,
            }
        ]
        ai_result = self.sample_ai_cards()
        ai_result["topic_cards"][0]["existing_evidence"] = [
            {
                "title": "A股又到击球区",
                "url": "https://mp.weixin.qq.com/s?__biz=market&mid=2&idx=1&sn=bbb",
            }
        ]

        cards = mod.normalize_ai_brief_cards(ai_result, signal_bundle)

        self.assertEqual(cards[0]["existing_evidence"][0]["url"], "https://mp.weixin.qq.com/s?__biz=market&mid=2&idx=1&sn=bbb")
        self.assertEqual(cards[0]["existing_evidence"][0]["source_type"], "事件簇代表材料")
        self.assertEqual(cards[0]["existing_evidence"][0]["logic_chain_id"], "a-share-sentiment")

    def test_canonicalize_url_keeps_distinct_wechat_article_ids(self):
        first = mod.canonicalize_url("https://mp.weixin.qq.com/s?__biz=robot&mid=1&idx=1&sn=aaa&mpshare=1")
        second = mod.canonicalize_url("http://mp.weixin.qq.com/s?__biz=market&mid=2&idx=1&sn=bbb&xtrack=1")

        self.assertNotEqual(first, second)
        self.assertNotIn("mpshare", first)
        self.assertNotIn("xtrack", second)

    def test_infer_card_logic_chain_prefers_enriched_evidence_vote(self):
        card = {
            "title": "再通胀不是事件，而是主线",
            "core_proposition": "市场在重新定价通胀和利率预期。",
            "one_line_judgment": "真正被重估的是通胀主线。",
            "priority_people": ["特朗普"],
            "priority_orgs": ["美联储"],
            "existing_evidence": [
                {"title": "美联储官员讲话强调通胀粘性", "logic_chain_id": "oil-fed-chain"},
                {"title": "特朗普关税表态后，市场再估输入型通胀风险", "logic_chain_id": "oil-fed-chain"},
                {"title": "英伟达回暖不等于半导体全面复苏", "logic_chain_id": "semi-chain"},
            ],
        }
        chain_id = mod.infer_card_logic_chain_id(card, self.signal_bundle)
        self.assertEqual(chain_id, "oil-fed-chain")

    def test_build_editorial_priority_pool_filters_weak_lifestyle_items(self):
        records = [
            mod.IntakeRecord(
                title="油价上行后，美债和黄金同步波动",
                summary="市场开始重新交易通胀与利率预期。",
                source="reports",
                source_item_id="1",
                raw_payload={"url": "https://example.com/a"},
                meta={},
                source_quality_tier="mainstream_media",
                entities={"commodities": ["油价"], "orgs": ["美联储"]},
                noise_tags=[],
                dynamic_cluster_key="oil-fed",
                dynamic_tokens=["油价", "通胀", "利率"],
                editor_labels=["宏观"],
                trendradar_signal=True,
                freshness_score=0.9,
                heat_score=82.0,
                heat_level="A",
                source_freshness_weight=0.9,
                source_timeliness_weight=0.95,
                source_authority_weight=1.1,
            ),
            mod.IntakeRecord(
                title="一次成功的饼干🍪！！！",
                summary="今天的烘焙小确幸。",
                source="xhs",
                source_item_id="2",
                raw_payload={"url": "https://example.com/b"},
                meta={},
                source_quality_tier="platform_hotspot",
                entities={},
                noise_tags=[],
                dynamic_cluster_key="cookie",
                dynamic_tokens=["饼干", "烘焙"],
                editor_labels=["其他观察"],
                trendradar_signal=False,
                freshness_score=1.0,
                heat_score=70.0,
                heat_level="A",
                source_freshness_weight=1.0,
                source_timeliness_weight=1.0,
                source_authority_weight=0.95,
            ),
        ]
        logic_chains, logic_chain_map = mod.build_logic_chains(records)
        pool = mod.build_editorial_priority_pool(records, logic_chain_map, limit=10)
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["title"], "油价上行后，美债和黄金同步波动")

    def test_editorial_priority_pool_uses_hotspot_macro_policy_signal(self):
        macro = mod.IntakeRecord(
            title="亚洲货币防线升温，美元压力正在外溢到新兴市场",
            summary="Asian central banks are defending currencies as Federal Reserve pressure spills over.",
            source="public_news/bloomberg-markets",
            source_item_id="1",
            raw_payload={"url": "https://example.com/asia-currency"},
            meta={},
            source_quality_tier="platform_hotspot",
            entities={"countries": ["亚洲"], "orgs": ["美联储"], "policies": ["汇率"]},
            noise_tags=[],
            dynamic_cluster_key="asia-currency",
            dynamic_tokens=["亚洲", "美元", "汇率"],
            editor_labels=["宏观"],
            trendradar_signal=False,
            freshness_score=0.9,
            heat_score=60.0,
            heat_level="B",
            source_freshness_weight=1.2,
            source_timeliness_weight=1.2,
            source_authority_weight=0.95,
            radar_macro_policy_score=0.91,
            radar_source_role="global_market_wire",
        )
        generic_ai = mod.IntakeRecord(
            title="AI工具更新引发开发者讨论",
            summary="开发者关注新工作流能力，但缺少宏观和政策传导。",
            source="public/hn_frontpage",
            source_item_id="2",
            raw_payload={"url": "https://example.com/ai-tool"},
            meta={},
            source_quality_tier="platform_hotspot",
            entities={"sectors": ["AI"]},
            noise_tags=[],
            dynamic_cluster_key="ai-tool",
            dynamic_tokens=["AI", "工具", "工作流"],
            editor_labels=["AI工具"],
            trendradar_signal=False,
            freshness_score=0.9,
            heat_score=60.0,
            heat_level="B",
            source_freshness_weight=1.2,
            source_timeliness_weight=1.2,
            source_authority_weight=0.95,
            radar_macro_policy_score=0.05,
            radar_source_role="tech_builder_hotlist",
        )

        _, logic_chain_map = mod.build_logic_chains([generic_ai, macro])
        pool = mod.build_editorial_priority_pool([generic_ai, macro], logic_chain_map, limit=2)

        self.assertEqual(pool[0]["title"], "亚洲货币防线升温，美元压力正在外溢到新兴市场")
        self.assertEqual(pool[0]["radar_source_role"], "global_market_wire")
        self.assertGreater(pool[0]["radar_macro_policy_score"], pool[1]["radar_macro_policy_score"])

    def test_load_records_reads_hotspot_radar_metadata(self):
        with project_tempdir() as tmpdir:
            path = Path(tmpdir) / "intake_records.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "title": "Asia Steps Up Currency Defense",
                            "summary": "Central banks defend currencies.",
                            "source": "public_news/bloomberg-markets",
                            "source_item_id": "1",
                            "raw_payload": {
                                "url": "https://example.com/asia-currency",
                                "radar": {
                                    "capture_role": "hotspot_capture",
                                    "source_role": "global_market_wire",
                                    "macro_policy_score": 0.91,
                                    "kept_by": "dynamic_capture_no_content_filter",
                                },
                            },
                            "source_quality_tier": "platform_hotspot",
                            "entities": {},
                            "editor_labels": ["宏观"],
                            "heat_score": 56,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            records = mod.load_records(path)

        self.assertEqual(records[0].radar_source_role, "global_market_wire")
        self.assertEqual(records[0].radar_macro_policy_score, 0.91)

    def test_validate_logic_chain_balance_rejects_single_chain_majority(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        ok, reason = mod.validate_logic_chain_balance(cards, self.signal_bundle)
        self.assertFalse(ok)
        self.assertIn("题目过多", reason)

    def test_normalize_ai_brief_cards_rejects_insufficient_output(self):
        short_result = {"topic_cards": self.sample_ai_cards()["topic_cards"][:3]}
        with self.assertRaises(RuntimeError):
            mod.normalize_ai_brief_cards(short_result, self.signal_bundle)

    def test_validate_chinese_topic_language_rejects_english_titles(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        cards[0]["title"] = "Oil price shock is becoming an inflation regime"
        ok, reason = mod.validate_chinese_topic_language(cards)
        self.assertFalse(ok)
        self.assertIn("必须使用中文", reason)

    def test_validate_chinese_topic_language_allows_brand_names_in_chinese_titles(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        cards[0]["title"] = "OpenAI 不是产品发布，而是入口战争"
        ok, reason = mod.validate_chinese_topic_language(cards)
        self.assertTrue(ok, reason)

    def test_write_failure_manifest_marks_ai_only_failed(self):
        with project_tempdir() as tmpdir:
            outdir = Path(tmpdir)
            manifest = mod.write_failure_manifest(outdir, "2026-04-05_170457", Path("/tmp/intake_records.json"), "Pass A 发散生成失败")
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["generation_mode"], "ai_only")
            self.assertEqual(payload["failure_reason"], "Pass A 发散生成失败")

    def test_request_ai_json_records_http_error_detail(self):
        class FakeHTTPError(urllib_error.HTTPError):
            def __init__(self):
                super().__init__(
                    "https://example.com",
                    403,
                    "Forbidden",
                    hdrs=None,
                    fp=BytesIO(b'{"error":{"type":"insufficient_quota"}}'),
                )

        def fake_urlopen(*args, **kwargs):
            raise FakeHTTPError()

        original_config = mod.resolve_brief_ai_config
        original_urlopen = mod.urllib_request.urlopen
        try:
            mod.resolve_brief_ai_config = lambda: {
                "base_url": "https://example.com",
                "api_key": "test",
                "model": "test",
                "timeout_seconds": "1",
            }
            mod.urllib_request.urlopen = fake_urlopen
            result = mod.request_ai_json("system", "user")
            self.assertIsNone(result)
            self.assertIn("insufficient_quota", mod.LAST_AI_ERROR)
        finally:
            mod.resolve_brief_ai_config = original_config
            mod.urllib_request.urlopen = original_urlopen

    def test_write_selected_topics_files_keeps_compat_fields(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        with project_tempdir() as tmpdir:
            outdir = Path(tmpdir)
            template_file, selected_file = mod.write_selected_topics_files(outdir, "2026-04-05_170457", cards)
            template = json.loads(template_file.read_text(encoding="utf-8"))
            selected = json.loads(selected_file.read_text(encoding="utf-8"))
            self.assertEqual(template["candidate_topics"][0]["topic_kind"], "independent")
            self.assertEqual(template["candidate_topics"][0]["mother_topic_id"], template["candidate_topics"][0]["topic_id"])
            self.assertEqual(selected["status"], "pending_editor_review")
            self.assertIn("source_material_summary", template["candidate_topics"][0])
            self.assertIn("controversy_points", template["candidate_topics"][0])
            self.assertIn("question_units", template["candidate_topics"][0])
            self.assertIn("opinion_units", template["candidate_topics"][0])
            self.assertIn("case_units", template["candidate_topics"][0])
            self.assertIn("solution_units", template["candidate_topics"][0])
            self.assertNotIn("ai_outline", template["candidate_topics"][0])

    def test_write_agent_brief_packet_marks_pending_generation(self):
        with project_tempdir() as tmpdir:
            outdir = Path(tmpdir)
            manifest = mod.write_agent_brief_packet(
                outdir,
                "2026-04-05_170457",
                Path("/tmp/intake_records.json"),
                self.signal_bundle,
                {"brief_ai_prompt": "Brief 规则", "brief_card_schema": {"type": "object"}},
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            prompt = (outdir / "brief_agent_prompt.md").read_text(encoding="utf-8")
            self.assertEqual(payload["status"], "pending_agent_generation")
            self.assertEqual(payload["generation_mode"], "agent")
            self.assertIn("Agent", prompt)
            self.assertTrue((outdir / "brief_signal_bundle.json").exists())

    def test_write_ready_brief_artifacts_accepts_agent_cards_without_provider(self):
        cards = mod.normalize_ai_brief_cards(self.sample_ai_cards(), self.signal_bundle)
        signal_bundle = {
            **self.signal_bundle,
            "stats": {
                "raw_record_count": 3,
                "deduped_record_count": 3,
                "trusted_evidence_count": 3,
                "logic_chain_count": 2,
                "manual_topic_count": 1,
                "trendradar_candidate_count": 0,
                "event_cluster_count": 0,
            },
            "channel_top10": {},
            "event_clusters": [],
        }
        with project_tempdir() as tmpdir:
            outdir = Path(tmpdir)
            manifest = mod.write_ready_brief_artifacts(
                outdir,
                "2026-04-05_170457",
                Path("/tmp/intake_records.json"),
                cards,
                signal_bundle,
                "agent",
                top_n=3,
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["generation_mode"], "agent")
            self.assertTrue((outdir / "topic_cards.json").exists())
            self.assertTrue((outdir / "02_编辑Brief库.md").exists())


if __name__ == '__main__':
    unittest.main()
