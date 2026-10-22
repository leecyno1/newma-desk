"""Read four consolidated statement amounts, preserving PDF column evidence.

Opt-in comparison only: no financial snapshot, publication date or score writes.
Uses the existing PDF reader and monetary-cell grammar, not an OCR/LLM parser.
"""
import re
from decimal import Decimal
from itertools import chain, islice

from earnings_import import compact
from earnings_capital import AMOUNT, VALUES


FIELDS = {
    "资产总计": ("assets", "合并总资产", "资产负债表"),
    "负债合计": ("liabilities", "合并总负债", "资产负债表"),
    "净利润": ("net_income", "合并净利润", "利润表"),
    "经营活动产生的现金流量净额": ("operating_cash_flow", "合并经营现金流净额", "现金流量表"),
}
HEADING = re.compile(r"(?:[\d一二三四五六七八九十]+[、.．])?(合并|母公司)(资产负债表|利润表|现金流量表|所有者权益变动表)")


def statement_candidates(pages, symbol: str) -> dict:
    pages = iter(pages)
    front = list(islice(pages, 10))
    cover = compact("\n".join(p["text"] for p in front[:3]))
    identity_text = compact("\n".join(p["text"] for p in front))
    report = re.search(r"(20\d{2})年(半年度|年度)报告", cover)
    codes = set(re.findall(r"(?:股票|证券|公司)代码[：:]?(\d{6})", identity_text))
    if not report or codes != {symbol} or "报告摘要" in cover:
        raise ValueError("未确认同一证券的文字版年度/半年度完整财报，不猜测报告期")
    year, kind = report.groups()
    period = f"{year}-{'06-30' if kind == '半年度' else '12-31'}"
    # Annual report titles use 年年度报告, but statement columns commonly
    # use 年度. Match both explicit forms without accepting other periods.
    flow_headers = {f"项目{year}{suffix}{int(year)-1}{suffix}"
                    for suffix in (("年度", "年年度") if kind == "年度" else ("年半年度",))}
    currency_basis = next(({"page": p["page"], "excerpt": line.strip()}
                           for p in front for line in p["text"].splitlines()
                           if re.search(r"元(?:[、，,]万元)?(?:[、，,]亿元)?指人民币元", compact(line))), None)
    found, conflicts, read_pages = {}, set(), []
    active, start_page, header, unit, date_ok, currency_ok = None, 0, None, None, False, False
    header_page = None
    # Keep initial pages available without reading the document a second time.
    for p in chain(front, pages):
        if len(read_pages) >= 200:
            break
        read_pages.append(p["page"])
        for line in p["text"].splitlines():
            text = compact(line)
            heading = HEADING.fullmatch(text)
            if heading:
                active = heading[2] if heading[1] == "合并" else None
                start_page, header_page = p["page"], p["page"]
                header, unit, date_ok, currency_ok = None, None, False, bool(currency_basis)
                continue
            if not active or p["page"] - start_page > 5:
                continue
            if "调整前" in text or "调整后" in text:
                conflicts.update(key for key, _, table in FIELDS.values() if table == active)
                active = None
                continue
            if "单位" in text:
                match = re.fullmatch(r"单位[：:](?:人民币)?(亿元|万元|元)(?:币种[：:]人民币)?", text)
                unit = match[1] if match else None
                currency_ok = bool(unit and (currency_basis or "人民币" in text))
            if text.startswith("项目"):
                header = None
            if active == "资产负债表":
                date = re.fullmatch(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
                if date:
                    date_ok = f"{date[1]}-{int(date[2]):02d}-{int(date[3]):02d}" == period
                dates = re.findall(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
                if len(dates) == 2:
                    date_ok = [f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in dates] == [period, f"{int(year)-1}-12-31"]
                    header = line.strip() if date_ok else None
                elif text == "项目期末余额期初余额":
                    header = line.strip() if date_ok else None
            elif text in flow_headers:
                header = line.strip()
                date_ok = True
            if not (header and date_ok and unit and currency_ok):
                continue
            # Start the numeric part at a monetary-formatted value. A blank
            # current cell cannot promote the single prior-year cell to current.
            number = re.search(AMOUNT, line)
            if not number:
                continue
            name = compact(line[:number.start()])
            name = re.sub(r"^[一二三四五六七八九十]+[、.．]", "", name)
            name = re.sub(r"[（(].*[）)]$", "", name)
            field = FIELDS.get(name)
            values = VALUES.fullmatch(line[number.start():]) if field and field[2] == active else None
            if not values:
                continue
            key, label, _ = field
            scale = {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}[unit]
            amount = Decimal(values["current"].replace(",", "")) * scale
            candidate = {"id": key, "label": label, "value": float(amount), "unit": "CNY", "currency": "CNY",
                         "scope": "consolidated", "asOf": period,
                         "periodStart": None if active == "资产负债表" else f"{year}-01-01",
                         "periodStartBasis": None if active == "资产负债表" else "calendar_report_period",
                         "rawValue": values["current"], "rawUnit": unit, "page": p["page"],
                         "headerPage": header_page, "columnHeader": "合并" + active + " · " + header,
                         "excerpt": line.strip()}
            if key in found and found[key]["value"] != candidate["value"]:
                conflicts.add(key)
            found.setdefault(key, candidate)
        if len(found) == 4:
            break
    return {"symbol": symbol, "periodEnd": period, "basis": "ytd" if kind == "半年度" else "annual",
            "currency": "CNY" if currency_basis or found else None, "currencyEvidence": currency_basis,
            "facts": [v for k, v in found.items() if k not in conflicts], "readPages": read_pages,
            "warnings": ["仅对照四项合并报表金额，不是全文审计；一致不证明供应商历史版本或报告已经审计。",
                         "只接受明确人民币单位、当前/上期双列与合并表；扫描件、空白、重述多列及无法确认的格式不猜值。",
                         "利润及现金流起点按年度/半年度报告口径取1月1日；不适用于非日历财年。",
                         *(["同项冲突或重述多列，已排除：" + "、".join(sorted(conflicts))] if conflicts else [])]}
