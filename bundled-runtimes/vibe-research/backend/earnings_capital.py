"""Bounded, opt-in extraction of consolidated balance-sheet reference facts.

These are accounting facts, never ready-to-use DCF capital inputs. Blank cells
are not zero; share capital is money, not diluted shares.
"""
import re
from decimal import Decimal

from earnings_import import compact

CAPITAL_ROWS = {
    "存货": "inventory",
    "应收账款": "accounts-receivable",
    "货币资金": "cash-funds",
    "短期借款": "short-borrowings",
    "长期借款": "long-borrowings",
    "应付债券": "bonds-payable",
    "一年内到期的非流动负债": "current-noncurrent-liabilities",
    "租赁负债": "lease-liabilities",
    "实收资本（或股本）": "share-capital",
    "股本": "share-capital",
    "吸收存款及同业存放": "customer-deposits",
}
# Require monetary formatting so an integer note number cannot become a value.
# Integer-only or wrapped cells are intentionally left for manual review.
AMOUNT = r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2,})"
VALUES = re.compile(rf"\s*(?:\d{{1,3}}\s+)?(?P<current>{AMOUNT})\s+(?P<prior>{AMOUNT})\s*")


def capital_candidates(pages, period_end: str) -> dict:
    found, conflicts, read_pages = {}, set(), []
    active, started, header, unit = False, None, None, None
    year = int(period_end[:4])
    for page in pages:
        read_pages.append(page["page"])
        if started is not None and page["page"] - started > 5:
            break
        for line in page["text"].splitlines():
            label = compact(line)
            if label == "合并资产负债表":
                if not active:
                    started = page["page"]
                active, header, unit = True, None, None
                continue
            if active and re.fullmatch(r"(?:母公司|合并)(?:资产负债表|利润表|现金流量表|所有者权益变动表)", label):
                return _result(found, conflicts, read_pages)
            if not active:
                continue
            if "调整前" in label or "调整后" in label:
                # Multi-column restatement tables require a separate parser.
                return _result({}, set(), read_pages)
            if "单位" in label:
                match = re.search(r"单位[：:](亿元|万元|元).*币种[：:]人民币", label)
                unit = match[1] if match else None
            dates = re.findall(r"(20\d{2})年12月31日", label)
            if len(dates) >= 2:
                header = line.strip() if dates == [str(year), str(year - 1)] else None
            if not header or not unit:
                continue
            # Retain label/value boundaries; compact only the Chinese row label.
            prefix = re.match(r"^\s*([^\d]+?)\s+(?=[\d+\-—（(])", line)
            if not prefix:
                continue
            name = compact(prefix[1])
            key = CAPITAL_ROWS.get(name)
            values = VALUES.fullmatch(line[prefix.end():]) if key else None
            if not values:
                continue
            raw = values["current"]
            scale = {"元": Decimal("0.000001"), "万元": Decimal("0.01"), "亿元": Decimal(100)}[unit]
            value = float(Decimal(raw.replace(",", "")) * scale)
            row = {"id": f"capital-{key}", "label": name, "value": value, "unit": "百万元",
                   "basis": "instant", "periodEnd": period_end, "scope": "consolidated",
                   "rawValue": raw, "rawUnit": unit, "page": page["page"], "excerpt": line.strip(),
                   "columnHeader": "合并资产负债表 · " + header}
            if key in found and found[key]["value"] != value:
                conflicts.add(key)
            found.setdefault(key, row)
    return _result(found, conflicts, read_pages)


def _result(found, conflicts, read_pages):
    return {"capitalCandidates": [row for key, row in found.items() if key not in conflicts],
            "capitalReadPages": read_pages,
            "capitalWarnings": [
                f"已扫描 {len(read_pages)} 页定位合并资产负债表（最多前 200 页、表内连续 6 页）。只接受本年/上年列序、人民币单位及金额格式明确的原始项目；空白、整数无格式、重述多列不猜值。",
                "仅作资本核验参考：股本金额不是稀释股数；货币资金不是可归属现金；一年内到期负债须看附注拆分，不能与其明细重复相加；未提取借款不等于无债务。",
                "财务公司客户存款、受限资金、少数股东权益和非经营性资产等仍需另行核验；本次不自动计算净债务或每股价值。",
                "存货、应收账款为合并报表期末账面价值，不是年度发生额；应收账款不包含应收票据、应收款项融资及其他应收款，不据此直接计算周转天数。",
                *(["同项存在冲突，已排除：" + "、".join(sorted(conflicts))] if conflicts else []),
            ]}
