"""Read-only first-observation archive; never reconstruct or backfill historical signals."""
from .turnover_candidates import DATASET, RULE

NOTE = "仅浏览已保存的首次观察记录，不受近期6日窗口限制。无记录不等于没有信号；记录可来自页面观察或已启用的收盘采集任务。冻结条件不代表当时可成交，归档不重算收益、不判断策略有效。"


def summary(row):
    eligible = row.get("eligibleCodes")
    return {"signalDate": row["date"], "capturedAt": row.get("capturedAt"),
            "candidateCount": len(row["candidates"]), "eligibleCount": row.get("eligibleCount"),
            "controlCount": len(set(eligible) - {item["code"] for item in row["candidates"]}) if eligible is not None else None,
            "controlStatus": "saved" if eligible is not None else "missing",
            "baselineStart": row.get("baselineStart"), "baselineEnd": row.get("baselineEnd"),
            "rules": row.get("rules"), "marketMedianRatio": row.get("marketMedianRatio"),
            "mode": "recorded", "verification": "not-evaluated", "captureSource": row.get("captureSource", "legacy")}


def archive(store, start, end, page=1):
    result = store.read_page(DATASET, RULE["id"], start, end, page, 20)
    return {**result, "rows": [summary(row) for row in result["rows"]], "start": start, "end": end, "note": NOTE}


def archive_detail(store, signal_date, page=1):
    rows, _ = store.read(DATASET, RULE["id"], signal_date, signal_date)
    if not rows:
        return None
    row = rows[0]
    total = len(row["candidates"])
    page_count = max(1, (total + 49) // 50)
    page = min(page, page_count)
    return {**summary(row), "candidates": row["candidates"][(page - 1) * 50:page * 50],
            "page": page, "pageSize": 50, "pageCount": page_count, "note": NOTE}
