"""Main-business revenue tables in MD&A, not IFRS/CAS reportable segments.

Keep each page/dimension separate. A parsed row sum is never consolidated revenue.
Only accept layouts with explicit RMB units and revenue-before-cost headers.
"""
import re
from collections import Counter
from decimal import Decimal

from earnings_import import compact

DIMENSIONS = {"行业": "industry", "产品": "product", "地区": "region", "销售模式": "channel"}
HEADING = re.compile(r"主营业务分(行业|产品|地区|销售模式)情况")
SECTION = re.compile(r"第[一二三四五六七八九十\d]+节(.+)")
STOP = re.compile(r"^(?:[（(]\d+[）)]|\d+[、．]|[（(][一二三四五六七八九十]+[）)])")
AMOUNT = re.compile(r"(?<!\S)[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2,})(?=\s|$)")


def _table(lines, page, dimension, title, unit):
    if any("调整前" in line or "调整后" in line for line in lines):
        return None
    header, cost_column, rows, totals, skipped = [], None, [], [], 0
    consumed = set()
    for index, line in enumerate(lines):
        if index in consumed or not line.strip():
            continue
        if "营业收入" in line and "营业成本" in line:
            if line.count("营业收入") == line.count("营业成本") == 1 and line.index("营业收入") < line.index("营业成本"):
                cost_column = line.index("营业成本")
                header = [line.strip()]
            else:
                cost_column = None
            continue
        if cost_column is None:
            continue
        numbers = list(AMOUNT.finditer(line))
        # The revenue cell must end before the cost header. A missing revenue
        # cell must not shift cost, margin or last-period values into revenue.
        first = numbers[0] if numbers else None
        if not first:
            if re.search(r"[—–]|不适用|--", line):
                skipped += 1
            if not rows and any(word in line for word in ("增减", "（%）", "比上年")):
                header.append(line.strip())
            continue
        label = compact(line[:first.start()])
        if not label or any(word in label for word in ("年度报告", "单位", "营业", "增减")):
            continue
        if first.end() > cost_column + 1 or re.search(r"[—–－(（]|不适用", label):
            skipped += 1
            continue
        # A wrapped row label can continue on the next line, with the margin
        # change unit at the far right (e.g. 其他系列 / 酒 ... 个百分点).
        excerpt = line.strip()
        if index + 1 < len(lines):
            following = lines[index + 1]
            continuation = compact(following[:first.start()])
            tail = compact(following[first.start():])
            if re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{1,12}", continuation) and tail in ("", "个百分点"):
                label += continuation
                excerpt += "\n" + following.strip()
                consumed.add(index + 1)
        raw = first.group()
        scale = {"元": Decimal("0.00000001"), "万元": Decimal("0.0001"), "亿元": Decimal(1)}[unit]
        row = {"label": label, "value": float(Decimal(raw.replace(",", "")) * scale),
               "rawValue": raw, "rawUnit": unit, "excerpt": excerpt}
        if label in ("合计", "小计", "总计"):
            totals.append(row)
        else:
            rows.append(row)
    # Duplicate labels can be subtables or restatements; do not merge or pick.
    if not rows or len(rows) > 40 or len({row["label"] for row in rows}) != len(rows):
        return None
    return {"id": f"business-revenue:{page}:{dimension}", "dimension": dimension,
            "title": title, "scope": "main-business", "currency": "CNY", "unit": "亿元",
            "page": page, "columnHeader": "\n".join(header), "rows": rows,
            "total": totals[0] if len(totals) == 1 else None, "skippedRows": skipped + (len(totals) if len(totals) > 1 else 0)}


def revenue_candidates(pages):
    groups, active = [], False
    headings = Counter()
    for page in pages:
        unit, current, lines = None, None, []

        def flush():
            if current and unit:
                group = _table(lines, page["page"], current[0], current[1], unit)
                if group:
                    groups.append(group)

        for line in page["text"].splitlines():
            label = compact(line)
            section = SECTION.fullmatch(label)
            if section:
                flush(); current, lines = None, []
                active = section[1] in ("管理层讨论与分析", "经营情况讨论与分析", "董事会报告")
                continue
            if not active:
                continue
            heading = HEADING.fullmatch(label)
            if heading:
                flush(); current, lines = (DIMENSIONS[heading[1]], label), []
                headings[f"business-revenue:{page['page']}:{current[0]}"] += 1
                continue
            if "单位" in label:
                # A new unit/header ends the old table, including non-RMB ones.
                if any(part.strip() for part in lines):
                    flush(); current, lines = None, []
                match = re.search(r"单位[：:](亿元|万元|元).*币种[：:]人民币", label)
                unit = match[1] if match else None
                continue
            if current and STOP.match(label):
                flush(); current, lines = None, []
            elif current:
                lines.append(line)
        flush()
    duplicates = {key for key, count in headings.items() if count > 1}
    groups = [group for group in groups if group["id"] not in duplicates]
    return {"revenueGroups": groups[:12], "revenueWarnings": [
        "仅读取前30页管理层讨论中列头与人民币单位明确的主营业务表；跨页续表、其他版式及会计报告分部未覆盖，须核对原报。",
        "行业、产品、地区、销售模式是不同划分，不能相加；组内合计不是公司总收入，缺失不填零。",
        *(["同页出现重复分类标题，相关候选已排除；请核对原报，不自动选择或合并。"] if duplicates else []),
        *(["超过12张候选表，仅返回前12张。"] if len(groups) > 12 else []),
    ]}
