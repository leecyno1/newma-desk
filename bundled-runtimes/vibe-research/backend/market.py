"""市场总览数据层 —— 市场情绪 + 板块资金流（板块/大盘级公开数据，不涉个股推荐）。

省流量：全站共享一份缓存（TTL 默认 5 分钟），多个用户/多次打开只抓一次；
盘中 5 分钟刷新足够，非交易时段数据本就不变。数据源全免费、无 key。
"""

from __future__ import annotations

import time
import os
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Lock
from collections import Counter
from datetime import datetime, timezone, timedelta

import astock
import gstock

BEIJING = timezone(timedelta(hours=8))
_CACHE: dict = {}
_TTL = 300  # 5 分钟；全站共享，省数据源压力
_OVERVIEW_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-overview")
_OVERVIEW_JOBS = {}
_OVERVIEW_LOCK = Lock()
_OVERVIEW_BUDGET = 10  # 留出时间给15秒的Desk网关；慢来源互不阻塞


def _cached(key: str, fn, valid=bool):
    """TTL 缓存。数据源故障的空结果不缓存（valid 判否），下次请求直接重试。"""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    if valid(val):
        _CACHE[key] = (now, val)
    return val


def _num(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _sentiment() -> dict:
    """市场情绪：涨跌家数/涨停跌停/活跃度 + 大盘宽度、题材投机（客观数据机械分档）。"""
    try:
        # akshare 惰性导入（同 astock 模式）：未装时降级返回空，不挡整个服务启动
        df = astock.akshare_call("stock_market_activity_legu")
        d = {row["item"]: row["value"] for _, row in df.iterrows()}
    except Exception:
        return {}
    counts = {}
    for key, label in (("up", "上涨"), ("down", "下跌"), ("flat", "平盘"),
                       ("zt", "涨停"), ("zt_real", "真实涨停"), ("dt", "跌停"), ("dt_real", "真实跌停")):
        try:
            number = float(d.get(label))
            counts[key] = int(number) if number >= 0 and number.is_integer() else None
        except (ValueError, TypeError):
            counts[key] = None
    up, down, flat = (counts[key] for key in ("up", "down", "flat"))
    zt_real = counts["zt_real"]
    complete = all(value is not None for value in (up, down, flat)) and up + down + flat > 0
    r = up / max(down, 1) if complete else None
    if not complete:
        breadth = None
    elif up < 600:
        breadth = "冰点"
    elif r < 0.7:
        breadth = "偏弱"
    elif r < 1.2:
        breadth = "中性"
    elif r < 2.5:
        breadth = "偏强"
    else:
        breadth = "普涨"
    speculation = None if zt_real is None else "亢奋" if zt_real >= 100 else "活跃" if zt_real >= 60 else "普通" if zt_real >= 30 else "冰点"
    return {
        **counts,
        "missingFields": [key for key, value in counts.items() if value is None],
        "source": "乐咕乐股 · stock_market_activity_legu",
        "scope": "来源返回的A股统计；不保证与其他供应商覆盖一致",
        "active": str(d.get("活跃度", "")),
        "breadth": breadth, "speculation": speculation,
        "date": str(d.get("统计日期", "")),
    }


def _sectors() -> list[dict]:
    """东财行业大额订单净额；旧同花顺接口已失效，不混接两种口径。"""
    params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
              "fid": "f62", "fid0": "f62", "fs": "m:90 t:2", "stat": "1",
              "ut": "b2884a393a59ad64002292a3e90d46a5",
              "fields": "f12,f14,f3,f62,f184,f124"}
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            rows = []
            page = 1
            while True:
                response = astock.em_get(f"https://{host}/api/qt/clist/get", params={**params, "pn": page}, headers={"User-Agent": astock.UA, "Referer": "https://data.eastmoney.com/bkzj/hy.html"}, timeout=8)
                data = response.json().get("data") or {}
                diff = data.get("diff") or []
                batch = list(diff.values()) if isinstance(diff, dict) else diff
                if not batch:
                    if rows:
                        raise ValueError("行业分页不完整，不发布为完整板块样本")
                    break
                rows.extend(batch)
                if len(rows) >= int(data.get("total") or len(rows)):
                    break
                page += 1
            if not rows:
                continue
            out = []
            for row in rows:
                net = astock._numf(row.get("f62"))
                timestamp = astock._numf(row.get("f124"))
                out.append({"name": row.get("f14"), "code": row.get("f12"),
                            "pct": astock._numf(row.get("f3")), "net": net / 1e8 if net is not None else None,
                            "inflow": None, "outflow": None, "netSharePct": astock._numf(row.get("f184")),
                            "asOf": datetime.fromtimestamp(timestamp, BEIJING).isoformat() if timestamp else None,
                            "metric": "large-order-net", "aggregateSafe": False, "source": f"eastmoney-{host.split('.')[0]}"})
            return sorted(out, key=lambda row: row["net"] if row["net"] is not None else float("-inf"), reverse=True)
        except Exception:
            continue
    return []


def get_overview(include_sentiment: bool = True) -> dict:
    """独立缓存两路来源；超时只降级该来源，复用未完成请求，避免刷新堆积。"""
    sources = {"sentiment": _sentiment, "sectors": _sectors} if include_sentiment else {"sectors": _sectors}
    daily_mode = include_sentiment and os.environ.get("VR_CN_SCAN_SOURCE") == "tushare-daily"
    if daily_mode:
        from market_scan_daily import daily_market_breadth
        sources = {"dailyBreadth": daily_market_breadth, "sectors": _sectors}
    result = {"sentiment": {}, "sectors": [], "sources": {}}
    pending = {}
    with _OVERVIEW_LOCK:
        for key, fetch in sources.items():
            cached = _CACHE.get(f"overview-source:{key}")
            if cached and time.time() - cached[0] < _TTL:
                result[key] = cached[1]
                result["sources"][key] = {"status": "ready", "reason": "", "receivedAt": cached[2]}
            else:
                job = _OVERVIEW_JOBS.get(key)
                if job is None:
                    job = _OVERVIEW_POOL.submit(fetch)
                    _OVERVIEW_JOBS[key] = job
                pending[key] = job
    if pending:
        wait(pending.values(), timeout=_OVERVIEW_BUDGET)
    for key, job in pending.items():
        if not job.done():
            result["sources"][key] = {"status": "timeout", "reason": "来源等待超时；不使用旧统计，请稍后刷新", "receivedAt": None}
            continue
        try:
            value = job.result()
            if key == "sentiment" and not any(value.get(field) is not None for field in ("up", "down", "flat", "zt", "dt")):
                value = {}
            received = datetime.now(BEIJING).isoformat()
            result[key] = value
            result["sources"][key] = {"status": "ready" if value else "unavailable",
                "reason": "" if value else "来源未返回有效统计，可能访问受限或数据暂缺；不补零", "receivedAt": received}
            if value:
                with _OVERVIEW_LOCK:
                    _CACHE[f"overview-source:{key}"] = (time.time(), value, received)
        except Exception:
            result["sources"][key] = {"status": "error", "reason": "来源读取失败；不使用旧统计", "receivedAt": None}
        finally:
            with _OVERVIEW_LOCK:
                if _OVERVIEW_JOBS.get(key) is job:
                    del _OVERVIEW_JOBS[key]
    if daily_mode:
        daily = result.pop("dailyBreadth", {})
        result.update(daily)
        result.setdefault("industryBreadth", {"top": [], "bottom": [], "total": 0,
            "data_state": "unavailable", "source": "tushare.daily+index_member_all"})
    result["updated"] = datetime.now(BEIJING).isoformat()
    return result


def _emotion() -> dict:
    """短线情绪（聚合口径，**零个股名**）：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    数据源＝东财涨停板四池（push2ex）。只把池子聚合成计数与比率，
    **不输出任何个股 code/name**——守产品「零标的」红线（个股清单是甩名单，不做）。
    """
    # 定位最近交易日：从今天往前回溯，第一日有涨停池即取（非交易日/盘前返空则继续回溯）。
    today = datetime.now(BEIJING).date()
    resolved, zt = "", []
    for back in range(8):
        d = (today - timedelta(days=back)).strftime("%Y%m%d")
        zt = astock.em_zt_topic_pool("getTopicZTPool", d, "fbt:asc")
        if zt:
            resolved = d
            break
    if not resolved:
        return {}

    zb = astock.em_zt_topic_pool("getTopicZBPool", resolved, "fbt:asc")    # 炸板池
    dt = astock.em_zt_topic_pool("getTopicDTPool", resolved, "fund:asc")   # 跌停池
    yzt = astock.em_zt_topic_pool("getYesterdayZTPool", resolved, "zs:desc")  # 昨涨停池

    boards = [_num(p.get("lbc")) or 1 for p in zt]      # 每只连板数（缺省按 1 板）
    lianban = [b for b in boards if b >= 2]             # 2 板及以上（连板）
    # 连板梯队：2/3/4/5+ 各多少家（5 代表 5 板及以上），只保留有家数的档
    tiers = Counter(min(b, 5) for b in lianban)
    ladder = [{"boards": b, "count": tiers[b], "plus": b >= 5} for b in sorted(tiers)]

    # 连板股清单（2 板+，客观公开榜单数据；按连板数、成交额降序）。
    # 产品定位调整（2026-07-05）：从「零标的」→「展示客观榜单但不推荐/不预测/不评分」。
    lianban_stocks = sorted(
        ({
            "code": str(p.get("c", "")), "name": p.get("n", ""),
            "boards": _num(p.get("lbc")) or 1,
            "price": round((astock._numf(p.get("p")) or 0) / 1000, 2),
            "pct": round(astock._numf(p.get("zdp")) or 0, 2),
            "amount": astock._numf(p.get("amount")),      # 成交额,元（'-' 占位归一为 None，防排序对 str 取负崩溃）
            "float_cap": astock._numf(p.get("ltsz")),     # 流通市值,元
            "industry": p.get("hybk", ""),  # 概念/行业
        } for p in zt if (_num(p.get("lbc")) or 1) >= 2),
        key=lambda x: (-x["boards"], -(x["amount"] or 0)),
    )

    zt_count, zb_count, yzt_count = len(zt), len(zb), len(yzt)
    attempts = zt_count + zb_count                       # 尝试涨停 = 封住 + 炸板
    seal_rate = round(zt_count / attempts, 3) if attempts else None      # 封板率
    break_rate = round(zb_count / attempts, 3) if attempts else None     # 炸板率
    # 晋级率＝今日 2 板+（＝昨涨停今又停）÷ 昨日涨停家数
    promotion_rate = round(len(lianban) / yzt_count, 3) if yzt_count else None

    return {
        "date": f"{resolved[:4]}-{resolved[4:6]}-{resolved[6:]}",
        "zt_count": zt_count,
        "dt_count": len(dt),
        "zb_count": zb_count,
        "max_boards": max(boards) if boards else 0,
        "lianban_count": len(lianban),
        "ladder": ladder,
        "lianban_stocks": lianban_stocks,
        "seal_rate": seal_rate,
        "break_rate": break_rate,
        "promotion_rate": promotion_rate,
        "yzt_count": yzt_count,
    }


def get_short_term_emotion() -> dict:
    """短线情绪（含缓存，5 分钟）。"""
    return _cached("emotion", _emotion)


def get_turnover_top() -> dict:
    """全市场成交额榜 Top20（客观公开榜单，含缓存 5 分钟）。"""
    def build():
        return {
            "stocks": astock.market_turnover_rank(20),
            "updated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        }
    return _cached("turnover_top", build, valid=lambda v: bool(v.get("stocks")))


def get_global_indices() -> list[dict]:
    """全球指数快照（美股 / 港股，含缓存 5 分钟）。空结果不缓存。"""
    return _cached("global_indices", gstock.global_indices, valid=bool)
