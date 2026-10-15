"""Exchange disclosures only: exact yuan, explicit dates, no derived repayment."""
from __future__ import annotations

import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from .research import iso_date
from .service import finite_number


SOURCES = {
    "SH": {"name": "上交所", "url": "https://www.sse.com.cn/market/othersdata/margin/detail/", "missingFields": []},
    "SZ": {"name": "深交所", "url": "https://www.szse.cn/disclosure/margin/margin/index.html", "missingFields": ["融资偿还额"]},
    "BJ": {"name": "北交所", "url": "https://www.bse.cn/disclosure/rzrq_trans_list.html", "missingFields": ["融资偿还额"]},
}
HEADERS = {"User-Agent": "Mozilla/5.0"}


def yuan(value):
    return finite_number(value.replace(",", "").strip() if isinstance(value, str) else value)


def szse_xlsx(content, code, day, report):
    metadata = report.get("metadata") or {}
    if metadata.get("subname") != day or metadata.get("tabkey") != "tab2":
        raise ValueError("官方披露日期或表格不匹配")
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if archive.getinfo("xl/worksheets/sheet1.xml").file_size > 5_000_000:
            raise ValueError("官方表格超过有界查询范围")
        strings = ET.fromstring(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in archive.namelist() else None
        shared = ["".join(node.itertext()) for node in strings] if strings is not None else []
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    parsed = []
    for row in sheet.findall("s:sheetData/s:row", ns):
        cells = {}
        for cell in row:
            value = cell.findtext("s:v", default="", namespaces=ns)
            if cell.get("t") == "s":
                value = shared[int(value)]
            elif cell.get("t") == "inlineStr":
                value = "".join(cell.find("s:is", ns).itertext())
            cells[re.sub(r"\d", "", cell.get("r", ""))] = value.strip()
        parsed.append(cells)
    if not parsed:
        raise ValueError("官方表格无表头")
    headers = parsed[0]
    columns = {label: next((column for column, name in headers.items() if name == label), None)
               for label in ("证券代码", "融资买入额(元)", "融资余额(元)")}
    if any(column is None for column in columns.values()):
        raise ValueError("官方表格单位或字段不匹配")
    selected = [row for row in parsed[1:] if row.get(columns["证券代码"]) == code]
    if len(selected) > 1:
        raise ValueError("官方目标证券重复")
    result = []
    for row in selected:
        values = {"rzmre": yuan(row.get(columns["融资买入额(元)"])), "rzye": yuan(row.get(columns["融资余额(元)"]))}
        grid = next((item for item in report["data"] if item.get("zqdm") == code), None)
        if not grid or any(value is None for value in values.values()):
            raise ValueError("官方元金额或日期证据不完整")
        # The date-labelled JSON only displays 0.01 billion yuan (some values truncate).
        # Use it solely to cross-check the dated download, never as an exact amount.
        for field, key in (("rzmre", "jrrzmr"), ("rzye", "jrrzye")):
            rounded = yuan(grid.get(key))
            if "亿元" not in metadata["cols"].get(key, "") or rounded is None or abs(values[field] - rounded * 1e8) > 1_000_001:
                raise ValueError("官方下载表与同日网页口径冲突")
        result.append({"date": day, "code": code, **values, "rzche": None,
                       "raw": {headers[column]: value for column, value in row.items()},
                       "dateEvidence": {"reportDate": metadata["subname"], "roundedRow": grid}, "unit": "元", "dateBasis": "同参数官方报表日期及下载表核对"})
    return result


def bse_page(text, day):
    match = re.fullmatch(r"\s*cb\((.*)\)\s*;?\s*", text, flags=re.S)
    if not match:
        raise ValueError("官方响应不是目标JSONP")
    payload = re.sub(r",\s*'(\d{4}-\d{2}-\d{2})'\s*\]$", lambda item: "," + json.dumps(item[1]) + "]", match[1])
    data = json.loads(payload)
    if len(data) != 2 or data[1] != day:
        raise ValueError("官方返回日期不匹配")
    return data[0][0]


async def fetch_official_rows(client, exchange, code, day):
    headers = {**HEADERS, "Referer": SOURCES[exchange]["url"]}
    if exchange == "SH":
        response = await client.get("https://query.sse.com.cn/marketdata/tradedata/queryMargin.do",
            params={"isPagination": "true", "tabType": "mxtype", "detailsDate": day.replace("-", ""), "stockCode": code,
                    "beginDate": "", "endDate": "", "pageHelp.pageSize": "50", "pageHelp.pageNo": "1"}, headers=headers)
        response.raise_for_status()
        rows = response.json().get("result")
        if not isinstance(rows, list):
            raise ValueError("官方记录结构异常")
        return [{"date": day, "code": code, **{field: yuan(row.get(field)) for field in ("rzye", "rzmre", "rzche")}, "raw": row, "unit": "元", "dateBasis": "原始opDate"}
                for row in rows if str(row.get("stockCode")) == code and iso_date(row.get("opDate")) == day]
    if exchange == "SZ":
        params = {"CATALOGID": "1837_xxpl", "txtDate": day, "tab2PAGENO": "1", "TABKEY": "tab2", "txtZqdm": code}
        report = await client.get("https://www.szse.cn/api/report/ShowReport/data", params={**params, "SHOWTYPE": "JSON"}, headers=headers)
        report.raise_for_status()
        data = report.json()
        if not isinstance(data, list) or len(data) != 1 or (data[0].get("metadata") or {}).get("subname") != day:
            raise ValueError("官方返回日期不匹配")
        if int(data[0]["metadata"].get("pagecount") or 0) > 1:
            raise ValueError("官方证券筛选未生效，不截取第一页")
        download = await client.get("https://www.szse.cn/api/report/ShowReport", params={**params, "SHOWTYPE": "xlsx"}, headers=headers)
        download.raise_for_status()
        return szse_xlsx(download.content, code, day, data[0])
    # BSE ignores zqdm on this report. Scan bounded pages, stopping as soon as the exact code is found.
    page, pages = 0, 1
    while page < min(pages, 16):
        response = await client.post("https://www.bse.cn/rzrqjyyexxController/detailInfoResult.do", params={"callback": "cb"},
                                    data={"transDate": day, "page": str(page)}, headers=headers, follow_redirects=True)
        response.raise_for_status()
        report = bse_page(response.text, day)
        pages = int(report["totalPages"])
        selected = [row for row in report["content"] if str(row.get("zqdm")) == code]
        if len(selected) > 1:
            raise ValueError("官方目标证券重复")
        for row in selected:
            stamp = row.get("sxrq") or {}
            actual = f'{stamp["year"] + 1900:04d}-{stamp["month"] + 1:02d}-{stamp["date"]:02d}'
            if actual != day:
                raise ValueError("官方证券行日期不匹配")
            return [{"date": actual, "code": code, "rzye": yuan(row.get("rzye")), "rzmre": yuan(row.get("rzmre")), "rzche": None,
                     "raw": row, "unit": "元", "dateBasis": "响应日期及原始sxrq", "page": page}]
        page += 1
    if page < pages:
        raise ValueError("官方分页超过16页，尚未完整查询目标证券")
    return []
