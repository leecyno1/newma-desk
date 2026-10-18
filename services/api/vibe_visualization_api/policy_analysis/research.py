from difflib import SequenceMatcher


# These are research hypotheses, not price predictions or asserted policy outcomes.
TRANSMISSION_RULES = [
    ("rates", "融资成本与利率", ("降准", "降息", "贷款利率", "政策利率", "降低利率"),
     "资金价格变化 → 融资成本与折现率 → 债券、银行及利率敏感资产；方向取决于曲线、信用与预期。",
     ["国债收益率曲线", "贷款加权平均利率", "信用利差"], "若资金价格或信用利差没有改善，不能认定宽松已传导到企业。"),
    ("fiscal", "财政与项目现金流", ("专项债", "一般债", "财政补贴", "政府采购", "运营补贴"),
     "预算或融资安排 → 资金拨付与项目落地 → 基建、设备及相关企业现金流；获批不等于到账。",
     ["实际发行与资金拨付", "项目开工及采购订单", "应收账款与经营现金流"], "若配套预算未落实、回款滞后或订单未兑现，应下调受益假设。"),
    ("capital", "资本市场与融资结构", ("并购重组", "上市", "股票", "股权投资", "债券融资"),
     "发行、并购或融资制度 → 企业融资与资本配置 → 相关公司和金融机构；融资支持不等于盈利改善。",
     ["发行或审批落地", "融资成本与规模", "并购后盈利及股东回报"], "若融资无法落地、摊薄超过收益或盈利未改善，原假设可能失效。"),
    ("technology", "技术投入与产业需求", ("人工智能", "算力", "芯片", "数据供给", "科技创新"),
     "技术、资源与应用支持 → 企业投入和采购 → 算力、软件及设备需求；需验证订单、产能与利润率。",
     ["实际资本开支与订单", "商业化收入", "产能利用率与利润率"], "若投入未转化为收入、竞争压低利润或估值已充分反映利好，应重新评估。"),
    ("green", "绿色转型与资本开支", ("绿色", "新能源", "节能", "碳排放", "环境保护"),
     "转型融资或约束 → 合规成本及设备更新 → 能源、设备与工业企业；支持和成本压力可能同时存在。",
     ["转型项目融资", "设备更新订单", "企业能耗、成本与现金流"], "若补贴或融资不足以覆盖投入成本，不应只按绿色主题推定受益。"),
    ("trade", "外贸与供给约束", ("关税", "出口管制", "出口", "进口"),
     "贸易规则或准入变化 → 订单、采购成本与供应链 → 出口企业及替代供应；需区分国家和产品范围。",
     ["适用产品与执行清单", "进出口量价及订单", "汇率与企业毛利率"], "若实际覆盖范围不同、豁免或转移采购抵消影响，应修正传导假设。"),
]


def transmission_hypotheses(document: dict | None) -> list[dict]:
    if not document or document.get("status") != "available":
        return []
    rows = []
    for key, label, terms, mechanism, indicators, invalidation in TRANSMISSION_RULES:
        evidence = [
            {"paragraph": index + 1, "quote": paragraph[:900], "excerpted": len(paragraph) > 900}
            for index, paragraph in enumerate(document["paragraphs"])
            if any(term in paragraph for term in terms)
        ][:2]
        if evidence:
            rows.append({
                "id": key, "label": label, "status": "hypothesis", "evidence": evidence,
                "sourceUrl": document["sourceUrl"], "documentRevision": document.get("revision"),
                "mechanism": mechanism, "indicators": indicators, "invalidation": invalidation,
                "reviewStatus": "unreviewed",
            })
    return rows


def compare_documents(current: dict | None, previous: dict | None, *, relation: str = "same-series-reference") -> dict:
    if not current or not previous or current.get("truncated") or previous.get("truncated"):
        return {
            "status": "unavailable", "basis": "official-text", "changes": [],
            "note": "需要两份未截断的已保存官方正文；摘要差异不能冒充条款变化。",
        }
    before, after = previous["paragraphs"], current["paragraphs"]
    changes = []
    quote_budget = 12_000
    change_count = 0
    for tag, start, end, new_start, new_end in SequenceMatcher(None, before, after).get_opcodes():
        if tag != "equal":
            change_count += 1
            if quote_budget > 0 and len(changes) < 30:
                old, new = "\n".join(before[start:end]), "\n".join(after[new_start:new_end])
                limit = min(1800, quote_budget // 2)
                changes.append({
                    "type": tag, "before": [old[:limit]] if old else [], "after": [new[:limit]] if new else [],
                    "beforeParagraph": start + 1, "afterParagraph": new_start + 1,
                    "excerpted": len(old) > limit or len(new) > limit,
                })
                quote_budget -= len(old[:limit]) + len(new[:limit])
    return {
        "status": "available", "basis": "official-text", "relation": relation,
        "baseRevision": previous.get("revision"), "currentRevision": current.get("revision"),
        "baseTitle": previous.get("title"), "baseSourceUrl": previous["sourceUrl"],
        "baseFetchedAt": previous["fetchedAt"], "currentFetchedAt": current["fetchedAt"],
        "changeCount": change_count, "changes": changes,
        "displayLimited": change_count > len(changes) or any(item["excerpted"] for item in changes),
        "note": "同一官方页面两次保存的正文差异；不等同于法律效力或实施效果变化。" if relation == "same-page-revision"
                else "同系列更早正式文件的正文参考差异；自动关联尚未经人工确认，不代表正式修订或废止。",
    }
