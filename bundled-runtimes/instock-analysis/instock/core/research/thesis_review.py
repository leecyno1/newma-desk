"""Mechanical source comparisons, not a semantic thesis or trading verdict."""

from datetime import date


REVIEW_INTERVAL_DAYS = 90


def _text(value):
    return " ".join(str(value or "").split())


def review_thesis(item, as_of):
    reasons, comparisons = [], []
    conditions = {_text(value) for value in item["invalidation"]}
    for ref in item["snapshot_references"]:
        source = {"snapshot_id": ref["snapshot_id"], "as_of": ref.get("as_of")}
        if ref["state"] != "resolved":
            reasons.append({**source, "code": "reference_unavailable", "reference_state": ref["state"]})
            continue
        age = (date.fromisoformat(as_of) - date.fromisoformat(ref["as_of"])).days
        if age >= REVIEW_INTERVAL_DAYS:
            reasons.append({**source, "code": "periodic_review_due", "calendar_age_days": age})
        if ref.get("source_coverage") != "complete":
            reasons.append({**source, "code": "source_incomplete"})
        if ref.get("analysis", {}).get("name") != "instock-stock-research-dossier":
            continue
        research = ref.get("research", {})
        complete = (ref.get("research_details_complete") and bool(_text(research.get("conclusion")))
                    and isinstance(research.get("invalidation_conditions"), list)
                    and bool(research["invalidation_conditions"])
                    and all(isinstance(value, str) and _text(value) for value in research["invalidation_conditions"]))
        if not complete:
            reasons.append({**source, "code": "research_details_incomplete"})
            continue
        missing = [value for value in research["invalidation_conditions"] if _text(value) not in conditions]
        differs = _text(item["thesis"]) != _text(research["conclusion"])
        comparisons.append({**source, "calendar_age_days": age, "source_conclusion": research["conclusion"],
                            "thesis_text_differs": differs, "source_invalidation": research["invalidation_conditions"],
                            "unmatched_invalidation": missing})
        if differs:
            reasons.append({**source, "code": "thesis_text_differs"})
        if missing:
            reasons.append({**source, "code": "invalidation_not_carried", "conditions": missing})
    if not comparisons:
        reasons.append({"code": "no_comparable_dossier"})
    return {"state": "needs_review" if reasons else "text_aligned", "reasons": reasons,
            "comparisons": comparisons, "condition_evaluation": "not_evaluated",
            "review_interval_calendar_days": REVIEW_INTERVAL_DAYS,
            "basis": "explicit_matched_references_only_whitespace_normalized_text_comparison",
            "boundary": "只比较已关联来源的文字，未检索最新资料。改写不等于冲突，遗漏不等于证伪命中；90自然日仅作季度复核提醒，来源不因此失效。所有证伪条件仍需人工验证。"}


def summarize_reviews(items):
    pending = [item for item in items if item["thesis_review"]["state"] == "needs_review"]
    unavailable = [item for item in items if not item["thesis_review"]["comparisons"]]
    return {"items_to_review": len(pending),
            "review_target_weight_pct": round(sum(item["target_weight_pct"] for item in pending), 2),
            "without_comparable_dossier": len(unavailable),
            "uncompared_target_weight_pct": round(sum(item["target_weight_pct"] for item in unavailable), 2),
            "text_aligned_items": len(items) - len(pending),
            "condition_evaluation": "not_evaluated",
            "boundary": "各类按观察项去重计权重，类别间可重叠，不可相加。研究暴露不是损失估计；无文字差异不代表投资逻辑成立。"}
