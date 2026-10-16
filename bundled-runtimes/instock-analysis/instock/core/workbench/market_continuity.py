"""A small evidence view over the existing rotation replay, not another score."""
from __future__ import annotations


def build_continuity(payload: dict) -> dict:
    history = payload.get("rotation_history", [])[-20:]
    dates = [point["date"] for point in history]
    latest = history[-1].get("rankings", []) if history else []
    codes = {row["code"] for row in latest}
    reasons = []
    if len(history) < 6:
        reasons.append("不足6期排名，不能比较5期变化")
    if (dates != sorted(set(dates)) or not dates or dates[-1] != payload.get("requested_as_of")
            or payload.get("as_of") != payload.get("requested_as_of")):
        reasons.append("复盘日与排名日期未对齐")
    if len(codes) < 5 or len(codes) != payload.get("universe_size"):
        reasons.append("候选池不完整，不能确认前五成员变化")
    indexed = [{row["code"]: row for row in point.get("rankings", [])} for point in history]
    if any(set(point) != codes or len(point) != len(history[i].get("rankings", [])) for i, point in enumerate(indexed)):
        reasons.append("历史候选池发生变化，名次不可直接比较")
    if any(row.get("data_lag_sessions") != 0 or row.get("signal_lag_sessions") != 0
           for point in indexed for row in point.values()):
        reasons.append("存在滞后或未核验的行情日期")
    if any(len({point[code].get("signal_mode") for point in indexed if code in point}) != 1 for code in codes):
        reasons.append("历史信号在行业指数与ETF代理间切换，口径未统一")
    comparable = not reasons
    previous = indexed[-6] if len(indexed) >= 6 else {}
    current_top = {row["code"] for row in latest if row["rank"] <= 5}
    previous_top = {code for code, row in previous.items() if row["rank"] <= 5}
    details = {row["code"]: row for row in payload.get("etfs", [])}
    rows = []
    for row in sorted(latest, key=lambda item: item["rank"]):
        code = row["code"]
        ranks = [point.get(code, {}).get("rank") for point in indexed]
        detail = details.get(code, {})
        retained = code in current_top and code in previous_top
        phase = ("留在前五" if retained else "新进前五" if code in current_top else
                 "退出前五" if code in previous_top else "前五之外") if comparable else "待核验"
        rows.append({"code": code, "name": row["name"], "industry": row["industry"],
                     "rank": row["rank"], "ranks": ranks, "phase": phase,
                     "rankChange": previous[code]["rank"] - row["rank"] if comparable else None,
                     "top5Periods": sum(rank is not None and rank <= 5 for rank in ranks) if comparable else None,
                     "observedPeriods": sum(rank is not None for rank in ranks),
                     "signalMode": row.get("signal_mode"), "proxyNote": detail.get("proxy_note", ""),
                     "proxyType": detail.get("proxy_type"),
                     "price20dPct": detail.get("momentum_20d"), "relative20dPp": detail.get("relative_20d"),
                     "current": comparable})
    leaders = [min(point.values(), key=lambda row: row["rank"])["code"] for point in indexed if point]
    streak = 0
    for code in reversed(leaders):
        if code != leaders[-1]:
            break
        streak += 1
    retained_count = len(current_top & previous_top) if comparable else None
    return {"schemaVersion": "newma-desk.market-continuity.v1", "asOf": payload.get("as_of"),
            "requestedDate": payload.get("requested_as_of"), "current": comparable, "reasons": reasons,
            "dates": dates, "comparisonDate": dates[-6] if len(dates) >= 6 else None,
            "universeSize": payload.get("universe_size"), "rows": rows,
            "summary": {"retained": retained_count, "entered": 5 - retained_count if comparable else None,
                        "leaderPeriods": streak if comparable else None,
                        "leaderChanges": sum(a != b for a, b in zip(leaders, leaders[1:])) if comparable else None},
            "notes": ["复用行业与ETF轮动的价格成交回放排名；不另造评分。排名领先不等于绝对上涨。",
                      "5期变化比较末期与向前5个观测期；前五留榜次数以本表实际观测日期为分母，不把缺失补为零。",
                      "历史排名使用当前配置代理池，含非直接行业代理；不是当时可投资全集，也不是策略回测。",
                      "留在前五只表示两端均在前五，不保证中间每期都在；完整轨迹列展示中间变化。",
                      "政策与行业资金未作为本区确认依据；不把实时政策、零散资金账本套入历史复盘。",
                      "ETF相对涨幅来自轮动信号（行业指数优先、ETF可回退）；不是ETF申赎流量，也不是资金扩散。"],
            "source": f"InStock RotationEngine · {payload.get('window', 60)}日模型 / 基准{payload.get('benchmark', {}).get('code', '510300')}"}
