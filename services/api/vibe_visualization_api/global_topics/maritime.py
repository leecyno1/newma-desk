"""Topic relevance is a search clue, never a route-closure assessment."""
from datetime import UTC, datetime
import re

NGA_URL = "https://msi.nga.mil/api/publications/broadcast-warn?output=json"
_SCOPE = {
    "hormuz-mentioned": "明确提及霍尔木兹",
    "nearby-coordinate": "附近坐标线索",
    "regional": "区域性公告",
}


def _instant(value: str | None) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
        return result.astimezone(UTC) if result and result.tzinfo else None
    except ValueError:
        return None


def maritime_evidence(source: dict, now: datetime) -> tuple[dict, dict]:
    payload = source["data"] or {}
    source = {**source, "collectedAt": payload.get("collected_at"), "cacheExpiresAt": payload.get("cache_expires_at")}
    collected, expires = _instant(source["collectedAt"]), _instant(source["cacheExpiresAt"])
    if payload and (payload.get("freshness") != "fresh" or not collected or collected > now or not expires or expires <= now):
        source.update(status="stale", reason="来源缓存已过期或采集时间未核实，当前有效性待核验")
    warnings, seen = [], set()
    for row in payload.get("warnings", []):
        if row.get("status") != "active" or row.get("cancel_date") or not row.get("id"):
            continue
        text = row.get("text") or ""
        points = [point for point in row.get("coordinates", [])
                  if 25.5 <= point["lat"] <= 27.5 and 55 <= point["lon"] <= 57.5]
        if re.search(r"\bhorm[ou]z\b|霍尔木兹", text, re.I):
            scope = "hormuz-mentioned"
        elif points:
            scope = "nearby-coordinate"
        elif row.get("origin_navarea") == "IX" or row.get("navarea") == "IX" or re.search(r"persian gulf|arabian gulf|gulf of oman|波斯湾|阿曼湾", text, re.I):
            scope = "regional"
        else:
            continue
        identifier = f"{row.get('navarea', '')}:{row['id']}"
        if identifier in seen:
            continue
        seen.add(identifier)
        published = _instant(row.get("issue_date"))
        warnings.append({
            "id": identifier, "reference": f"{row.get('broadcast_label') or row.get('navarea', '')} {row['id']}",
            "title": " ".join(text.split())[:180] or "航行警告正文缺失",
            "text": text[:6000], "textTruncated": len(text) > 6000,
            "publishedAt": published.isoformat() if published and published <= now else None,
            "publicationDateRaw": row.get("issue_date_raw"),
            "scope": scope, "scopeLabel": _SCOPE[scope], "nearbyCoordinates": points,
            "broadcastArea": row.get("broadcast_area", row.get("navarea")), "originNavarea": row.get("origin_navarea"),
            "authority": row.get("authority"), "sourceUrl": NGA_URL,
            "status": "not-cancelled-in-snapshot", "currentValidity": "unverified",
        })
    warnings.sort(key=lambda row: row["publishedAt"] or "", reverse=True)
    warnings.sort(key=lambda row: list(_SCOPE).index(row["scope"]))
    return source, {
        "status": source["status"], "reason": source["reason"], "source": source["label"], "sourceUrl": NGA_URL,
        "collectedAt": source["collectedAt"], "cacheExpiresAt": source["cacheExpiresAt"],
        "scannedCount": len(payload.get("warnings", [])) if payload else None,
        "matchedCount": len(warnings) if payload else None,
        "counts": {key: sum(row["scope"] == key for row in warnings) for key in _SCOPE} if payload else None,
        "warnings": warnings[:20],
        "selectionRule": "扫描 NGA 本次广播快照中未取消记录的完整正文；优先匹配 Hormuz / Hormoz，其次筛选 25.5–27.5°N、55–57.5°E 内任一已解析坐标，再纳入波斯湾、阿曼湾或 NAVAREA IX 区域公告。最多展示 20 条，先按相关性、再按发布日期排序。",
        "limitations": "坐标框仅为附近线索，不是航道边界；未匹配记录不代表海峡安全。源记录未取消不等于当前仍有效，公告中的生效、到期和取消条款需核验。警告数量不是风险分数，也不能证明航道中断或战事升级。",
    }
