"""Local PDF annual-report candidates. No model, network call, or workbook writes."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

NUMBER = re.compile(r"(?<![\d.,])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.,])")
RULES = (
    ("revenue", "营业收入", "亿元", r"^营业收入(?:[（(]元[）)])?$"),
    ("net-profit", "归母净利润", "亿元", r"^归属于(?:上市公司股东|母公司(?:所有者|股东))的净利润(?:[（(]元[）)])?$"),
    ("operating-cash-flow", "经营现金流净额", "亿元", r"^经营活动产生的现金流量净额(?:[（(]元[）)])?$"),
    ("eps", "基本每股收益", "元", r"^基本每股收益[（(]元[／/]股[）)]$"),
    ("roe", "加权平均 ROE", "%", r"^加权平均净资产收益率[（(][%％][）)]$"),
)


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


DISCUSSION_TOPICS = (
    ("现金流", ("现金流量净额变动原因", "现金流量分析", "客户存款和同业存放", "经营活动现金流")),
    ("业务与渠道", ("分销售模式", "渠道类型", "线上销售", "分产品", "分部信息")),
    ("营运资金", ("合同负债", "应收账款", "存货", "预收款")),
    ("经营计划", ("经营计划", "主要目标", "经营目标")),
    ("风险披露", ("可能面对的风险", "风险因素", "面临的风险")),
)


def discussion_candidates(pages: list[dict]) -> tuple[list[dict], list[int]]:
    """Select bounded MD&A pages, retaining tables and surrounding explanations.

    Topic matches are navigation hints, not conclusions. Ignore TOC entries and
    stop at the next numbered section; never infer absent disclosures.
    """
    section, active = [], False
    for page in pages:
        lines = []
        for line in page["text"].splitlines():
            heading = compact(line)
            if re.fullmatch(r"第[一二三四五六七八九十\d]+节(?:管理层讨论与分析|经营情况讨论与分析|董事会报告)", heading):
                active = True
            elif active and re.fullmatch(r"第[一二三四五六七八九十\d]+节[\u4e00-\u9fff]+", heading):
                active = False
            if active:
                lines.append(re.sub(r"[ \t]{3,}", "  ", line.strip()))
        if lines:
            section.append({"page": page["page"], "text": "\n".join(lines).strip()})
    ranked = []
    for topic, terms in DISCUSSION_TOPICS:
        matches = [(sum((len(terms) - i) for i, term in enumerate(terms) if term in compact(p["text"])), p) for p in section]
        ranked.append((topic, [p for score, p in sorted(matches, key=lambda pair: (-pair[0], pair[1]["page"])) if score][:2]))
    # Round-robin gives each topic a first page before taking second matches.
    chosen: dict[int, dict] = {}
    budget = 18000
    for rank in range(2):
        for topic, matches in ranked:
            if rank >= len(matches):
                continue
            page = matches[rank]
            if page["page"] in chosen:
                chosen[page["page"]]["topics"].append(topic)
                continue
            if len(chosen) >= 8 or budget <= 0:
                continue
            text = page["text"][:min(6000, budget)]
            chosen[page["page"]] = {"id": f"discussion:{page['page']}", "page": page["page"], "topics": [topic],
                                    "text": text, "truncated": len(text) < len(page["text"])}
            budget -= len(text)
    return sorted(chosen.values(), key=lambda p: p["page"]), [p["page"] for p in section]


def annual_candidates(pages: list[dict], page_count: int, report_id: str, name: str) -> dict:
    cover = "\n".join(page["text"] for page in pages[:3])
    year_match = re.search(r"(20\d{2})\s*年\s*年度报告", cover)
    symbol_match = re.search(r"(?:公司|证券|股票)代码\s*[：:]\s*(\d{6})", cover)
    name_match = re.search(r"(?:公司|证券|股票)简称\s*[：:]\s*([^\s\n]+)", cover)
    year = int(year_match[1]) if year_match else None
    result = {
        "reportId": report_id, "name": name, "pageCount": page_count,
        "readPages": [p["page"] for p in pages],
        "security": {"market": "CN", "symbol": symbol_match[1] if symbol_match else "", "name": name_match[1] if name_match else "", "currency": "CNY"},
        "periodEnd": f"{year}-12-31" if year else None, "basis": "annual",
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
        "candidates": [], "discussion": [], "discussionPages": [], "warnings": [],
    }
    if not year or not symbol_match or not name_match:
        result["warnings"].append("尚不能确认 A 股年度报告身份；请使用含公司代码、简称和年份的文字版年报。未猜测期间或证券。")
        return result
    if year >= datetime.now().year:
        result["warnings"].append("年度尚未结束，不能作为已披露全年实际值导入。")
        return result
    found: dict[str, dict] = {}
    ambiguous: set[str] = set()
    for page in pages:
        text = page["text"]
        if not re.search(r"主要(?:会计数据|财务指标)", compact(text)):
            continue
        lines = text.splitlines()
        header = None
        unit = None
        for i, line in enumerate(lines):
            unit_match = re.search(r"单位[：:]\s*(亿元|万元|元)", line)
            if unit_match:
                unit = unit_match[1] if "人民币" in compact(text) else None
            # Only accept an unambiguous current-year / previous-year column order.
            years = re.findall(r"(?<!\d)(20\d{2})\s*年(?!度)", line)
            if len(years) >= 2:
                header = line if years[:2] == [str(year), str(year - 1)] and len(years) == len(set(years)) else None
            if not header or "调整后" in compact(text) or "调整前" in compact(text):
                continue
            numbers = list(NUMBER.finditer(line))
            if len(numbers) < 2:
                continue
            prefix = line[:numbers[0].start()]
            # A missing current-period cell must not shift last year's value into it.
            if re.search(r"[—–－]|(?:^|\s)--?(?:\s|$)|不适用|[（(]\s*$", prefix):
                continue
            next_line = next((s.strip() for s in lines[i + 1:i + 3] if s.strip()), "")
            suffix = next_line if not NUMBER.search(next_line) else ""
            label = compact(prefix + suffix)
            for metric_id, metric_label, target_unit, pattern in RULES:
                # Most unwrapped rows need no suffix from the following line.
                if not (re.fullmatch(pattern, label) or re.fullmatch(pattern, compact(prefix))):
                    continue
                if target_unit == "亿元" and not unit:
                    continue
                raw = numbers[0].group()
                scale = {"元": Decimal("0.00000001"), "万元": Decimal("0.0001"), "亿元": Decimal(1)}[unit] if target_unit == "亿元" else Decimal(1)
                value = float(Decimal(raw.replace(",", "")) * scale)
                excerpt = line.strip() + ("\n" + suffix if suffix else "")
                row = {"id": metric_id, "label": metric_label, "value": value, "unit": target_unit,
                       "rawValue": raw, "rawUnit": unit if target_unit == "亿元" else target_unit,
                       "page": page["page"], "excerpt": excerpt, "columnHeader": header.strip()}
                if metric_id in found and found[metric_id]["value"] != value:
                    ambiguous.add(metric_id)
                found.setdefault(metric_id, row)
                # The summary explicitly labels its third numeric column as YoY.
                if metric_id in ("revenue", "net-profit") and len(numbers) >= 3 and re.search(r"本期比.*上年.*增减", compact(text)):
                    yoy_id = metric_id + "-yoy"
                    yoy = float(Decimal(numbers[2].group().replace(",", "")))
                    previous = Decimal(numbers[1].group().replace(",", ""))
                    computed = (Decimal(raw.replace(",", "")) / previous - 1) * 100 if previous > 0 else None
                    if computed is not None and abs(float(computed) - yoy) <= 0.02:
                        growth = {**row, "id": yoy_id, "label": metric_label + "同比", "value": yoy, "unit": "%", "rawValue": numbers[2].group(), "rawUnit": "%"}
                        if yoy_id in found and found[yoy_id]["value"] != yoy:
                            ambiguous.add(yoy_id)
                        found.setdefault(yoy_id, growth)
    result["candidates"] = [row for key, row in found.items() if key not in ambiguous]
    if ambiguous:
        result["warnings"].append("同一指标存在不同数值，未自动选择：" + "、".join(sorted(ambiguous)))
    if not result["candidates"]:
        result["warnings"].append("未识别到列序和单位明确的主要财务指标表。扫描页、重述多列或其他版式请人工核对，缺失不填零。")
    result["discussion"], result["discussionPages"] = discussion_candidates(pages)
    result["warnings"].append(f"仅读取前 {len(pages)} / {page_count} 页：提取主要指标，并在识别到的管理层讨论章节中按主题选页；不是全文审计，未自动回填利润率和每股经营现金流，不提供一致预期。")
    if result["discussion"]:
        result["warnings"].append(f"经营讨论候选 {len(result['discussion'])} 页 / 识别章节 {len(result['discussionPages'])} 页；最多 8 页、每页 6000 字符、合计 18000 字符。主题仅是检索线索，未选中或截断内容不进入分析。")
    else:
        result["warnings"].append("读取范围内未定位到经营讨论候选，不代表公司未披露；请从原报另行核验。")
    return result


def extract_report(path: Path, report_id: str, name: str, *, include_capital: bool = False, include_notes: bool = False, include_revenue: bool = False) -> dict:
    if path.suffix.lower() != ".pdf":
        raise ValueError("财报提取目前只支持 PDF")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("请上传未加密的 PDF")
        pages = [{"page": i + 1, "text": page.extract_text(extraction_mode="layout") or ""}
                 for i, page in enumerate(reader.pages[:30])]
        if not any(p["text"].strip() for p in pages):
            raise ValueError("此 PDF 未提取到文字，可能是扫描件；暂不支持 OCR，未生成任何零值")
        result = annual_candidates(pages, len(reader.pages), report_id, name)
        if include_revenue and result["periodEnd"] and result["security"]["symbol"] and result["security"]["name"] and int(result["periodEnd"][:4]) < datetime.now().year:
            from earnings_revenue import revenue_candidates
            result.update(revenue_candidates(pages))
        if include_capital and result["periodEnd"] and result["security"]["symbol"] and result["security"]["name"] and int(result["periodEnd"][:4]) < datetime.now().year:
            from earnings_capital import capital_candidates
            scan = (pages[i] if i < len(pages) else {"page": i + 1, "text": reader.pages[i].extract_text(extraction_mode="layout") or ""}
                    for i in range(min(200, len(reader.pages))))
            result.update(capital_candidates(scan, result["periodEnd"]))
        if include_notes and result["periodEnd"] and result["security"]["symbol"] and result["security"]["name"] and int(result["periodEnd"][:4]) < datetime.now().year:
            from earnings_capital_notes import capital_note_candidates
            scan = (pages[i] if i < len(pages) else {"page": i + 1, "text": reader.pages[i].extract_text(extraction_mode="layout") or ""}
                    for i in range(min(200, len(reader.pages))))
            result.update(capital_note_candidates(scan))
        return result
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF 读取失败，请确认文件完整且可复制文字") from error
