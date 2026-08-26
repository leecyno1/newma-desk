"""Conservative item-level industry classification for the news radar."""

from __future__ import annotations

import re


_RULES: dict[str, tuple[tuple[str, int], ...]] = {
    "ai": (
        ("openai", 3), ("anthropic", 3), ("gemini", 3), ("claude", 3),
        ("large language model", 3), ("generative ai", 3),
        ("ai model", 3), ("llm", 3), ("chatbot", 2), ("inference model", 3),
        ("大模型", 3), ("生成式ai", 3), ("人工智能", 2), ("智能体", 2),
    ),
    "semi": (
        ("semiconductor", 3), ("chip", 3), ("gpu", 3), ("cpu", 3), ("wafer", 3),
        ("foundry", 3), ("tsmc", 3), ("nand", 3), ("dram", 3), ("hbm", 3),
        ("npu", 3), ("npus", 3),
        ("lithography", 3), ("半导体", 3), ("芯片", 3), ("晶圆", 3), ("光刻", 3),
        ("台积电", 3), ("中芯国际", 3), ("存储器", 2),
    ),
    "robot": (
        ("humanoid robot", 3), ("industrial robot", 3), ("robotics", 3), ("automation", 2),
        ("robot", 2), ("人形机器人", 3), ("工业机器人", 3), ("机器人", 2),
        ("自动化", 2), ("具身智能", 3),
    ),
    "auto": (
        ("electric vehicle", 3), ("robotaxi", 3), ("automaker", 3), ("automakers", 3),
        ("carmaker", 3), ("carmakers", 3),
        ("automotive", 3), ("tesla", 2), ("byd", 2),
        ("vehicle", 2), ("suv", 2),
        ("sedan", 2), ("新能源汽车", 3), ("电动汽车", 3), ("新能源车", 3),
        ("机器人出租车", 3), ("汽车", 2), ("车企", 3), ("车型", 2),
        ("特斯拉", 2), ("比亚迪", 2),
    ),
    "energy": (
        ("photovoltaic", 3), ("solar power", 3), ("solar wafer", 4), ("wind power", 3), ("power grid", 3),
        ("energy storage", 3), ("battery storage", 3), ("bess", 3), ("crude oil", 3),
        ("natural gas", 3), ("nuclear power", 3), ("renewable energy", 3),
        ("光伏", 3), ("风电", 3), ("电网", 3), ("储能", 3), ("原油", 3),
        ("天然气", 3), ("核电", 3), ("电力", 2), ("煤炭", 2),
    ),
    "bio": (
        ("clinical trial", 3), ("phase i", 3), ("phase ii", 3), ("phase iii", 3),
        ("phase 1", 3), ("phase 2", 3), ("phase 3", 3),
        ("fda", 3), ("biotech", 3), ("biopharma", 3),
        ("medical", 3), ("healthcare", 3), ("cancer", 3), ("vaccine", 3),
        ("therapy", 2), ("patient", 2), ("hospital", 2), ("disease", 2),
        ("hearing loss", 3), ("deafness", 3), ("医药", 3), ("医疗", 3),
        ("临床", 3), ("癌症", 3), ("疫苗", 3), ("药物", 2), ("疾病", 2),
        ("患者", 2), ("医院", 2), ("耳聋", 3), ("生物科技", 3),
    ),
    "space": (
        ("spacex", 3), ("starlink", 3), ("nasa", 3), ("cesiumastro", 4),
        ("constellation", 2), ("rocket", 3),
        ("satellite", 3), ("spacecraft", 3), ("astronaut", 3), ("lunar", 3),
        ("moon mission", 3), ("orbit", 2), ("航天", 3), ("火箭", 3),
        ("卫星", 3), ("宇航员", 3), ("月球", 3), ("太空", 2),
    ),
    "security": (
        ("ransomware", 3), ("data breach", 3), ("cyberattack", 3), ("cyberattacks", 3), ("cyber attack", 3),
        ("vulnerability", 3), ("malware", 3), ("zero-day", 3), ("spyware", 3),
        ("phishing", 3), ("botnet", 3), ("hacker", 2), ("exploit", 2),
        ("数据泄露", 3), ("网络攻击", 3), ("勒索软件", 3), ("恶意软件", 3),
        ("零日", 3), ("间谍软件", 3), ("漏洞", 3), ("黑客", 2),
    ),
    "tech": (
        ("cloud computing", 3), ("e-commerce", 3), ("social media", 3),
        ("software", 2), ("internet", 2), ("app store", 2), ("云计算", 3),
        ("电子商务", 3), ("社交媒体", 3), ("互联网", 2), ("软件", 2),
    ),
    "consumer": (
        ("smartphone", 3), ("iphone", 3), ("galaxy", 2), ("pixel", 3),
        ("galaxy phone", 3), ("pixel phone", 3),
        ("laptop", 3), ("tablet", 3), ("earbuds", 3), ("smartwatch", 3),
        ("headset", 2), ("camera", 2), ("display", 2), ("手机", 3),
        ("笔记本电脑", 3), ("平板电脑", 3), ("耳机", 3), ("智能手表", 3),
        ("相机", 2), ("显示器", 2), ("消费电子", 3),
    ),
    "macro": (
        ("federal reserve", 3), ("interest rate", 3), ("inflation", 3), ("gdp", 3),
        ("treasury yield", 3), ("foreign exchange", 3), ("tariff", 2), ("bond market", 2),
        ("央行", 3), ("美联储", 3), ("利率", 3), ("通胀", 3), ("国内生产总值", 3),
        ("汇率", 3), ("国债", 3), ("关税", 2), ("财报", 2),
    ),
    "science": (
        ("quantum physics", 3), ("particle physics", 3), ("archaeology", 3),
        ("fossil", 3), ("evolution", 2), ("scientists discover", 3),
        ("研究发现", 3), ("量子物理", 3), ("粒子物理", 3), ("考古", 3),
        ("化石", 3), ("进化", 2),
    ),
}


def _contains(text: str, term: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", term):
        return term.casefold() in text
    return re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", text) is not None


def classify_news_industry(title: str, summary: str = "", translated_title: str = "", fallback: str = "tech") -> tuple[str, dict[str, int]]:
    headline = (title or translated_title).casefold()
    detail = summary.casefold()
    headline_scores = {
        key: sum(weight for term, weight in terms if _contains(headline, term))
        for key, terms in _RULES.items()
    }
    if re.search(r"\btesla\b.*\b(?:production|deliveries|vehicle|car)\b|特斯拉.*(?:生产|交付|车型|汽车)", headline):
        headline_scores["auto"] += 2
    if re.search(r"\b(?:pixel|iphone|galaxy)\b.*\b(?:phone|series|pro|ultra|camera|display|chip)\b|"
                 r"(?:pixel|iphone|galaxy).*(?:系列|手机|相机|屏幕|芯片)", headline):
        headline_scores["consumer"] += 2
    scores = {
        key: headline_scores[key] + sum(1 for term, weight in terms if weight >= 2 and _contains(detail, term) and not _contains(headline, term))
        for key, terms in _RULES.items()
    }
    scores[fallback] = scores.get(fallback, 0) + 2
    winner = max(scores, key=scores.get)
    strong_headline = headline_scores[winner] >= 3
    strong_summary = scores[winner] >= 4 and scores[winner] >= scores.get(fallback, 0) + 2
    if winner == fallback or (not strong_headline and not strong_summary) or scores[winner] < scores.get(fallback, 0) + 1:
        return fallback, scores
    return winner, scores


def classify_industries(industries: list[dict]) -> dict[str, int]:
    by_key = {industry["key"]: {**industry, "items": []} for industry in industries}
    moved = 0
    total = 0
    for industry in industries:
        for item in industry.get("items") or []:
            total += 1
            fallback = str(item.get("source_industry_key") or industry["key"])
            assigned, scores = classify_news_industry(
                str(item.get("title") or ""),
                str(item.get("summary") or ""),
                str(item.get("zh") or ""),
                fallback,
            )
            item["source_industry_key"] = fallback
            item["industry_key"] = assigned
            item["industry_classified"] = assigned != fallback
            item["industry_score"] = scores.get(assigned, 0)
            if assigned != fallback:
                moved += 1
            by_key.get(assigned, by_key[fallback])["items"].append(item)
    for industry in industries:
        industry["items"] = by_key[industry["key"]]["items"]
        industry["items"].sort(key=lambda item: item.get("ts", 0), reverse=True)
    return {"classified_items": total, "reclassified_items": moved}
