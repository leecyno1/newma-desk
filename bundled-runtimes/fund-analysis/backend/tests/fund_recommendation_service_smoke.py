import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_recommendation_service import FundRecommendationService
from services.fund_research_snapshot_service import FundResearchSnapshotService


class FakeClassificationRepo:
    def __init__(self, rows):
        self.rows = rows
        self.requested_limit = None

    def list_recommendation_funds(self, peer_group, limit=50, keyword=None):
        self.requested_limit = limit
        return list(self.rows)

    def count_recommendation_funds(self, peer_group, keyword=None):
        return len(self.rows)

    def list_peer_group_coverage_inventory(self, limit=100):
        return [
            {
                "id": "peer-index-hs300",
                "key": "peer-index-hs300",
                "name": "指数-沪深300",
                "minimum_peer_count": 5,
                "classified_count": 35,
                "database_fund_count": 35,
            },
            {
                "id": "peer-index-csi500",
                "key": "peer-index-csi500",
                "name": "指数-中证500",
                "minimum_peer_count": 5,
                "classified_count": 1,
                "database_fund_count": 1,
            },
        ][:limit]


class FakeMetricRepo:
    def __init__(self, panels):
        self.panels = panels

    def get_latest_panels(self, target_type, target_ids):
        assert target_type == "fund"
        return {code: list(self.panels.get(code, [])) for code in target_ids}


class FakeProfileRepo:
    def __init__(self, profiles):
        self.profiles = profiles

    def list_profiles(self, wind_codes):
        return {code: dict(self.profiles.get(code, {})) for code in wind_codes}

    def list_memo_style_suggestions(self, wind_codes):
        return {
            wind_codes[0]: [{"value": "红利", "confidence": 0.91, "status": "llm_suggested"}]
        } if wind_codes else {}


class FakeHoldingStyleRepo:
    def get_latest_map(self, wind_codes):
        return {
            code: {
                "wind_code": code,
                "quarter": "2026Q1",
                "peer_group_id": "peer-index-hs300",
                "peer_group_name": "指数-沪深300",
                "peer_sample_size": 5,
                "minimum_peer_count": 5,
                "style_labels": ["大盘"],
                "peer_percentiles": [{"factor": "SIZE", "percentile": 0.9, "sample_size": 5}],
            }
            for code in wind_codes[:2]
        }


class FakeManagerRepo:
    def list_current_fund_tenure_contexts(self, fund_codes):
        return {}


def _panel(index):
    values = {
        "tracking_error": 0.002 + index * 0.0001,
        "tracking_difference": 0.001 + index * 0.00005,
        "expense_ratio": 0.002 + index * 0.00002,
        "aum": 200.0 - index,
    }
    return [
        {
            "metric_window": "1y" if name in {"tracking_error", "tracking_difference"} else "latest",
            "metric_name": name,
            "metric_value": value,
            "as_of_date": "2026-08-04",
        }
        for name, value in values.items()
    ]


def _row(index, peer_group="指数-沪深300"):
    code = f"{index:06d}.OF"
    return {
        "id": code,
        "wind_code": code,
        "name": f"测试沪深300基金{index}",
        "type": "指数型",
        "nav": 1.0 + index / 100,
        "nav_date": "2026-08-04",
        "total_asset": 200.0 - index,
        "establishment_date": "2018-01-01",
        "performance_data": {"tracking_difference": 0.001 + index * 0.00005},
        "risk_metrics": {"tracking_error": 0.002 + index * 0.0001},
        "raw_data": {"info": {"management_fee": 0.15, "custodian_fee": 0.05}},
        "standardized_peer_group_id": "peer-index-hs300" if peer_group == "指数-沪深300" else "peer-index-csi500",
        "standardized_peer_group_key": "peer-index-hs300" if peer_group == "指数-沪深300" else "peer-index-csi500",
        "standardized_peer_group_name": peer_group,
        "strategy_family_key": "index_broad",
        "asset_class": "index",
        "active_passive": "passive",
        "minimum_peer_count": 5,
        "benchmark_code": "000300.SH",
        "benchmark_name": "沪深300",
    }


def main() -> int:
    for duplicate_method in (
        "_evaluate_candidate",
        "_classification_context",
        "_attach_score_percentiles",
        "_metrics_by_window",
    ):
        if hasattr(FundRecommendationService, duplicate_method):
            raise AssertionError(f"推荐 Module 不得保留重复评价逻辑：{duplicate_method}")

    guessed_name_styles = FundRecommendationService._derived_style_evidence({
        "name": "测试红利价值成长基金",
    })
    if guessed_name_styles:
        raise AssertionError(f"不得仅根据基金名称猜测风格：{guessed_name_styles}")

    if FundRecommendationService._matches_style(
        FundRecommendationService(),
        {
            "style_profile": {"label_evidence": []},
            "research_profile": {},
            "_candidate_metrics": {"max_drawdown": -0.03},
        },
        "低波稳健",
    ):
        raise AssertionError("低回撤表现不能冒充已有证据支持的低波风格标签")

    partial_tenure = FundRecommendationService._manager_tenure_evidence(
        [{
            "metric_window": "manager_tenure",
            "metric_name": "total_return",
            "metric_value": 0.09,
            "as_of_date": "2026-08-13",
            "details": {
                "manager_tenure_start": "2019-01-25",
                "window_start_date": "2023-07-21",
                "window_end_date": "2026-08-13",
                "actual_observations": 747,
            },
        }],
        {"dimension_scores": {"manager_tenure": {"score": None, "included_in_score": False}}},
    )
    if partial_tenure.get("coverage_status") != "partial_since_data_start":
        raise AssertionError(f"推荐证据必须识别经理任期部分覆盖：{partial_tenure}")
    if partial_tenure.get("included_in_score") is not False or "不计分" not in partial_tenure.get("note", ""):
        raise AssertionError(f"部分覆盖经理任期不得进入推荐评分：{partial_tenure}")

    full_tenure = FundRecommendationService._manager_tenure_evidence(
        [{
            "metric_window": "manager_tenure",
            "metric_name": "total_return",
            "metric_value": 0.25,
            "as_of_date": "2026-08-12",
            "details": {
                "manager_tenure_start": "2023-08-14",
                "window_start_date": "2023-08-14",
                "window_end_date": "2026-08-12",
                "actual_observations": 730,
            },
        }],
        {"dimension_scores": {"manager_tenure": {"score": 72.0, "included_in_score": True}}},
    )
    if full_tenure.get("coverage_status") != "full_tenure" or full_tenure.get("included_in_score") is not True:
        raise AssertionError(f"完整经理任期证据应保留计分状态：{full_tenure}")

    long_history_candidate = {
        "wind_code": "long.OF",
        "professional_scoring": {"overall_score": 70},
        "rolling_metrics": {
            "6m": {"total_return": 0.08},
            "1y": {"total_return": 0.16, "annualized_return": 0.16, "max_drawdown": -0.12},
            "3y": {"annualized_return": 0.13, "max_drawdown": -0.20, "sharpe_ratio": 0.9, "as_of_date": "2026-08-14"},
        },
    }
    short_history_candidate = {
        "wind_code": "short.OF",
        "professional_scoring": {"overall_score": 90},
        "rolling_metrics": {"1y": {"annualized_return": 0.30}},
    }
    ordered = sorted([short_history_candidate, long_history_candidate], key=FundRecommendationService._candidate_sort_key)
    if ordered[0]["wind_code"] != "long.OF":
        raise AssertionError(f"长期证据完整基金应优先于只靠短期高分的基金：{ordered}")
    multi_period = FundResearchSnapshotService.project_multi_period_evidence(
        long_history_candidate["rolling_metrics"],
        "active_equity",
    )
    if multi_period.get("status") != "long_term_ready" or multi_period.get("used_in_score") is not True:
        raise AssertionError(f"推荐证据必须披露近 3 年指标及其评分用途：{multi_period}")
    if multi_period.get("consistency_status") != "stable":
        raise AssertionError(f"短长期收益差应生成可解释的一致性状态：{multi_period}")

    a500_evidence = FundRecommendationService._derived_style_evidence({
        "name": "测试中证A500指数增强基金",
        "active_passive": "enhanced",
        "standardized_peer_group_name": "指数增强-中证A500",
        "benchmark_name": "中证A500指数",
    })
    a500_styles = {item.get("value") for item in a500_evidence}
    if "宽基" not in a500_styles or "大盘" in a500_styles:
        raise AssertionError(f"中证A500必须命中最长基准规则，不能误命中中证A50：{a500_evidence}")

    enhanced_style_cases = [
        ("指数增强-中证800", "中证800指数", {"指数增强", "宽基"}),
        ("指数增强-中证2000", "中证2000指数", {"指数增强", "小盘"}),
        ("指数增强-中证A50", "中证A50指数", {"指数增强", "大盘"}),
        ("指数增强-创业板指", "创业板指数", {"指数增强", "成长"}),
        ("指数增强-科创50", "上证科创板50成份指数", {"指数增强", "成长", "行业主题"}),
        ("指数增强-上证50", "上证50指数", {"指数增强", "大盘"}),
    ]
    for peer_group, benchmark_name, expected_styles in enhanced_style_cases:
        evidence = FundRecommendationService._derived_style_evidence({
            "name": f"测试{peer_group}基金",
            "active_passive": "active",
            "standardized_peer_group_name": peer_group,
            "benchmark_name": benchmark_name,
        })
        actual_styles = {item.get("value") for item in evidence}
        if not expected_styles.issubset(actual_styles):
            raise AssertionError(f"新增指数增强组风格标签不完整：{peer_group} {evidence}")

    rows = [_row(index) for index in range(35)]
    rows.append(_row(99, peer_group="指数-中证500"))
    panels = {row["wind_code"]: _panel(index) for index, row in enumerate(rows)}
    panels["000005.OF"] = [
        item for item in panels["000005.OF"] if item["metric_name"] != "tracking_error"
    ]
    rows[5]["risk_metrics"] = {}
    profiles = {
        row["wind_code"]: {
            "peer_group": row["standardized_peer_group_name"],
            "primary_benchmark": row["benchmark_name"],
            "style_label": "大盘成长" if index < 12 else "价值",
            "strategy_tags": ["成长", "主动权益"] if index < 12 else ["价值", "主动权益"],
        }
        for index, row in enumerate(rows)
    }
    profiles["000005.OF"]["style_label"] = "仅缺证基金拥有的风格"
    profiles["000005.OF"]["strategy_tags"] = ["仅缺证风格"]

    classification_repo = FakeClassificationRepo(rows)
    service = FundRecommendationService(
        classification_repo=classification_repo,
        metric_repo=FakeMetricRepo(panels),
        profile_repo=FakeProfileRepo(profiles),
        holding_style_repo=FakeHoldingStyleRepo(),
        manager_repo=FakeManagerRepo(),
    )
    result = service.build_candidate_group("指数-沪深300", style="成长", limit=50)
    unified_evaluations = service.evaluation_service.evaluate_peer_group_from_inputs(
        [row for row in rows if row["standardized_peer_group_name"] == "指数-沪深300"],
        service._profiles_with_style_suggestions(
            [row["wind_code"] for row in rows if row["standardized_peer_group_name"] == "指数-沪深300"],
            [row for row in rows if row["standardized_peer_group_name"] == "指数-沪深300"],
        ),
        panels,
    )

    candidates = result.get("candidates") or []
    if classification_repo.requested_limit < 35:
        raise AssertionError(f"Recommendation service truncated the peer universe: {classification_repo.requested_limit}")
    if len(candidates) != 10:
        raise AssertionError(f"Candidate group must be capped at ten funds: {result}")
    if result.get("peer_universe_count") != 35:
        raise AssertionError(f"Only the exact requested peer group may be counted: {result}")
    if result.get("evidence_eligible_count") != 34:
        raise AssertionError(f"Funds missing required category evidence must be excluded: {result}")
    if result.get("excluded_reason_counts") != {"required_category_evidence_missing": 1}:
        raise AssertionError(f"Recommendation exclusions must disclose their evidence reason: {result}")
    if result.get("style_matched_count") != 11:
        raise AssertionError(f"Style filtering must run across the full eligible peer group: {result}")
    if "仅缺证基金拥有的风格" in (result.get("available_styles") or []):
        raise AssertionError(f"Style options must only come from evidence-eligible funds: {result}")
    if "主动权益" in (result.get("available_styles") or []):
        raise AssertionError(f"Fund classifications must not leak into style options: {result}")
    if "红利" not in (result.get("available_styles") or []):
        raise AssertionError(f"LLM memo style suggestions must become transparent style filters: {result}")
    if any(item.get("research_profile", {}).get("peer_group") != "指数-沪深300" for item in candidates):
        raise AssertionError(f"Cross-category fund leaked into candidate group: {result}")
    if any("成长" not in " ".join(item.get("research_profile", {}).get("strategy_tags") or []) for item in candidates):
        raise AssertionError(f"Selected style must be backed by profile tags: {result}")
    if any(item.get("wind_code") == "000005.OF" for item in candidates):
        raise AssertionError(f"Fund with missing tracking evidence entered candidates: {result}")
    missing_evaluation = (unified_evaluations.get("000005.OF") or {}).get("evaluation") or {}
    if (missing_evaluation.get("evaluation") or {}).get("overall_score") is not None:
        raise AssertionError(f"核心指标缺失时统一基金评价不得输出综合分：{missing_evaluation}")

    scores = [item["professional_scoring"]["overall_score"] for item in candidates]
    if scores != sorted(scores, reverse=True):
        raise AssertionError(f"Candidates must be ordered by category-specific score: {scores}")
    for item in candidates:
        if not item.get("classification_ready") or not item.get("evaluation_ready"):
            raise AssertionError(f"入选候选必须明确标记为已分类且可评价：{item}")
        evidence = item.get("recommendation_evidence") or {}
        if not evidence.get("reasons") or not evidence.get("risks"):
            raise AssertionError(f"Every candidate needs plain-language reasons and risks: {item}")
        if evidence.get("data_as_of") != "2026-08-04":
            raise AssertionError(f"Candidate evidence needs an auditable data date: {item}")
        if evidence.get("methodology_version") != "fund_candidate_group_v6":
            raise AssertionError(f"Candidate method must be versioned: {item}")
        alternatives = evidence.get("alternatives") or []
        if len(alternatives) != 2 or any(option.get("wind_code") == item.get("wind_code") for option in alternatives):
            raise AssertionError(f"Every candidate needs two distinct same-category alternatives: {item}")
        percentile = (item.get("peer_percentiles") or {}).get("metrics", {}).get("professional_score", {}).get("percentile")
        if percentile is None:
            raise AssertionError(f"Category score percentile is missing: {item}")
        percentile_score = (item.get("peer_percentiles") or {}).get("metrics", {}).get("professional_score", {}).get("value")
        if percentile_score != item.get("professional_scoring", {}).get("overall_score"):
            raise AssertionError(f"推荐分数与统一基金评价分数不一致：{item}")
        unified = (unified_evaluations.get(item["wind_code"]) or {}).get("evaluation") or {}
        unified_score = (unified.get("evaluation") or {}).get("overall_score")
        unified_grade = (unified.get("evaluation") or {}).get("overall_grade")
        if (unified_score, unified_grade) != (
            item.get("professional_scoring", {}).get("overall_score"),
            item.get("professional_scoring", {}).get("overall_grade"),
        ):
            raise AssertionError(f"推荐与基金评价 Module 必须共用分数和等级：{item}")

    if result.get("limit") != 10 or result.get("returned") != 10:
        raise AssertionError(f"Public candidate group contract must enforce the ten-fund cap: {result}")
    if result.get("source") != "full_peer_group_category_evaluation":
        raise AssertionError(f"Candidate source must disclose full peer-group evaluation: {result}")
    style_options = {item["value"]: item for item in result.get("available_style_options") or []}
    if style_options.get("大盘", {}).get("matched_count") != 34:
        raise AssertionError(f"Peer group and benchmark positioning should supply auditable large-cap coverage: {result}")
    if style_options.get("大盘", {}).get("derived_count") != 34:
        raise AssertionError(f"Derived positioning must stay separated from confirmed profiles: {result}")
    if style_options.get("大盘", {}).get("quantitative_count") != 2:
        raise AssertionError(f"Holding peer percentiles must stay visible as quantitative style evidence: {result}")
    if any(
        item.get("status") != "derived" or item.get("source") not in {"standardized_peer_group", "standardized_benchmark"}
        for item in candidates
        for item in item.get("research_profile", {}).get("derived_style_evidence") or []
    ):
        raise AssertionError(f"Derived styles must preserve their evidence source and status: {result}")
    if any(key in result for key in ["purchase_amount", "suitability", "position", "trade_action"]):
        raise AssertionError(f"Candidate group leaked out-of-scope decision fields: {result}")

    thin_group = service.build_candidate_group("指数-中证500")
    if thin_group.get("candidates") or thin_group.get("excluded_reason_counts") != {"peer_sample_insufficient": 1}:
        raise AssertionError(f"Recommendation must stop when the classified peer sample is too small: {thin_group}")

    evidence_thin_rows = [_row(index, peer_group="指数-中证500") for index in range(100, 106)]
    for row in evidence_thin_rows[4:]:
        row["performance_data"] = {}
        row["risk_metrics"] = {}
        row["raw_data"] = {}
        row["total_asset"] = None
    evidence_thin_panels = {
        row["wind_code"]: _panel(index) if index < 4 else []
        for index, row in enumerate(evidence_thin_rows)
    }
    evidence_thin_profiles = {
        row["wind_code"]: {
            "peer_group": row["standardized_peer_group_name"],
            "primary_benchmark": row["benchmark_name"],
            "style_label": "中盘",
            "strategy_tags": ["中盘"],
        }
        for row in evidence_thin_rows
    }
    evidence_thin_service = FundRecommendationService(
        classification_repo=FakeClassificationRepo(evidence_thin_rows),
        metric_repo=FakeMetricRepo(evidence_thin_panels),
        profile_repo=FakeProfileRepo(evidence_thin_profiles),
        holding_style_repo=FakeHoldingStyleRepo(),
        manager_repo=FakeManagerRepo(),
    )
    evidence_thin_group = evidence_thin_service.build_candidate_group("指数-中证500")
    if evidence_thin_group.get("candidates") or evidence_thin_group.get("evidence_eligible_count") != 4:
        raise AssertionError(f"Recommendation must stop when complete evaluation samples are below the peer threshold: {evidence_thin_group}")
    if evidence_thin_group.get("excluded_reason_counts", {}).get("peer_evaluation_sample_insufficient") != 1:
        raise AssertionError(f"Recommendation must disclose the complete-evaluation sample shortfall: {evidence_thin_group}")

    evidence_thin_coverage = evidence_thin_service.build_coverage_report()
    evidence_thin_csi500 = next(
        group for group in evidence_thin_coverage.get("groups") or []
        if group.get("key") == "peer-index-csi500"
    )
    if evidence_thin_csi500.get("status") != "partial" or evidence_thin_csi500.get("recommendation_ready_count") != 0:
        raise AssertionError(f"Coverage must not mark a category ready below its complete-evaluation sample threshold: {evidence_thin_coverage}")
    if evidence_thin_csi500.get("missing_reason_counts", {}).get("peer_evaluation_sample_insufficient") != 1:
        raise AssertionError(f"Coverage must disclose the complete-evaluation sample shortfall: {evidence_thin_coverage}")

    coverage = service.build_coverage_report()
    coverage_groups = {group["key"]: group for group in coverage.get("groups") or []}
    hs300 = coverage_groups.get("peer-index-hs300") or {}
    csi500 = coverage_groups.get("peer-index-csi500") or {}
    if hs300.get("metric_ready_count") != 34 or hs300.get("recommendation_ready_count") != 34:
        raise AssertionError(f"Coverage report must use the same evidence gate as recommendations: {coverage}")
    if csi500.get("recommendation_ready_count") != 0 or csi500.get("missing_reason_counts", {}).get("peer_sample_insufficient") != 1:
        raise AssertionError(f"Coverage report must disclose thin peer groups: {coverage}")
    if coverage.get("metric_backfill", {}).get("mock_data_allowed") is not False:
        raise AssertionError(f"Coverage backfill must remain real-data-only: {coverage}")

    print("OK recommendation service scans the full peer group and returns at most ten evidence-backed style candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
