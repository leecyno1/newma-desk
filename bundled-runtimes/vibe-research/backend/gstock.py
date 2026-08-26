"""美股 / 港股数据层。

数据源顺序直接遵循仓库内 ``global-stock-data/SKILL.md``：

* 美股行情：新浪 -> 腾讯 -> 东财 push2。
* 港股行情：腾讯 -> 新浪 -> 东财 push2。
* 中文关键财务指标：东财 GMAININDICATOR。
* 韩股保留原有东财行情兼容路由。

这一层不再把 yfinance 作为美股/港股默认数据源。

工程要点：
- 东财调用全部复用 `astock.em_get`（直连优先、避开用户 Clash 代理挂国内站）+
  `astock.eastmoney_datacenter`（datacenter 三表/指标已封装）。
- push2 stock/get 直连偶发掉连 → **push2 优先、失败降级 push2delay**（延时行情，研究场景足够），
  latch 到可用主机整进程复用（同成交额榜的做法）。
- 行情源会按 Skill 约定自动回退，单一来源失败不会让整个个股页失效。

合规：只做客观数据整理，不预置标的、不推荐、不预测。
"""

from __future__ import annotations

import re

import astock

_UA_H = {"User-Agent": astock.UA}
_GS_HOSTS = ("push2.eastmoney.com", "push2delay.eastmoney.com")
_gs_host = [0]  # 当前可用主机下标；首次 push2 掉连后 latch 到 push2delay

# 全球指数（东财 push2 secid）—— A 股看隔夜外围脸色的核心几个，均已实测。
_INDICES = (
    {"key": "dji", "name": "道琼斯", "secid": "100.DJIA", "region": "美股"},
    {"key": "spx", "name": "标普500", "secid": "100.SPX", "region": "美股"},
    {"key": "ndx", "name": "纳斯达克", "secid": "100.NDX", "region": "美股"},
    {"key": "hsi", "name": "恒生指数", "secid": "100.HSI", "region": "港股"},
    {"key": "hstech", "name": "恒生科技", "secid": "124.HSTECH", "region": "港股"},
)

# 搜索返回的 MktNum → (secucode 后缀, 市场名)
_MKT = {105: (".O", "NASDAQ"), 106: (".N", "NYSE"), 107: (".O", "US"), 116: (".HK", "HK"),
        177: (".KS", "KR")}  # 177=韩股（Kospi/Kosdaq，含三星/SK海力士等半导体龙头）；东财仅行情、无 F10 财务

_QUOTE_FIELDS = "f43,f44,f45,f46,f47,f48,f55,f57,f58,f59,f60,f116,f170"


def _push2_stock_get(secid: str, fields: str) -> dict | None:
    """东财 push2 stock/get：push2 优先、失败降级 push2delay；latch 可用主机。空数据返回 None。"""
    params = {"secid": secid, "fields": fields}
    for i in range(_gs_host[0], len(_GS_HOSTS)):
        try:
            r = astock.em_get(f"https://{_GS_HOSTS[i]}/api/qt/stock/get",
                              params=params, headers=_UA_H, timeout=10)
            d = r.json().get("data")
        except Exception:
            continue
        if d:
            _gs_host[0] = i
            return d
    return None


def _price(d: dict, key: str):
    """f43 等价格字段：除以 10^f59 还原。'-' / None → None。"""
    v = d.get(key)
    if not isinstance(v, (int, float)):
        return None
    dec = d.get("f59")
    if not isinstance(dec, int):  # 注意：不能用 `or 2`——韩元等 f59=0 会被误判成 2，价格被多除 100 倍
        dec = 2
    return round(v / (10 ** dec), dec)


def _quote_from(d: dict) -> dict:
    chg = d.get("f170")
    return {
        "code": d.get("f57"), "name": d.get("f58"),
        "price": _price(d, "f43"), "open": _price(d, "f46"),
        "high": _price(d, "f44"), "low": _price(d, "f45"),
        "prev_close": _price(d, "f60"),
        "volume": d.get("f47") if isinstance(d.get("f47"), (int, float)) else None,
        "amount": d.get("f48") if isinstance(d.get("f48"), (int, float)) else None,
        "turnover_rate": d.get("f55") if isinstance(d.get("f55"), (int, float)) else None,
        "mcap": d.get("f116") if isinstance(d.get("f116"), (int, float)) and d.get("f116") else None,
        "change_pct": round(chg / 100, 2) if isinstance(chg, (int, float)) else None,
        "pe": None,
        "pb": None,
        "source": "eastmoney" if d else None,
    }


def _number(value):
    """将公开行情源的字符串数值转为 float，空值返回 None。"""
    try:
        return float(value) if value not in (None, "", "-") else None
    except (TypeError, ValueError):
        return None


def _quoted_fields(text: str, separator: str) -> list[str]:
    match = re.search(r'"(.+)"', text)
    return match.group(1).split(separator) if match else []


def _get_text(url: str, *, referer: str | None = None) -> str:
    headers = {"User-Agent": astock.UA}
    if referer:
        headers["Referer"] = referer
    response = astock.em_get(url, headers=headers, timeout=10)
    response.encoding = "gbk"
    return response.text


def _us_quote_sina(ticker: str) -> dict:
    fields = _quoted_fields(
        _get_text(
            f"https://hq.sinajs.cn/list=gb_{ticker.lower()}",
            referer="https://finance.sina.com.cn/",
        ),
        ",",
    )
    if len(fields) < 30:
        return {}
    return {
        "name": fields[0],
        "price": _number(fields[1]),
        "change_pct": _number(fields[2]),
        "prev_close": _number(fields[26]),
        "open": _number(fields[5]),
        "high": _number(fields[6]),
        "low": _number(fields[7]),
        "volume": _number(fields[10]),
        "amount": None,
        "turnover_rate": None,
        "mcap": _number(fields[12]),
        "pe": _number(fields[14]),
        "pb": None,
        "source": "sina",
    }


def _us_quote_tencent(ticker: str) -> dict:
    fields = _quoted_fields(_get_text(f"https://qt.gtimg.cn/q=us{ticker.upper()}"), "~")
    if len(fields) < 57:
        return {}
    market_cap_yi = _number(fields[44])
    return {
        "name": fields[1],
        "price": _number(fields[3]),
        "change_pct": _number(fields[32]),
        "prev_close": _number(fields[4]),
        "open": _number(fields[5]),
        "high": _number(fields[33]),
        "low": _number(fields[34]),
        "volume": _number(fields[6]),
        "amount": None,
        "turnover_rate": None,
        "mcap": market_cap_yi * 100_000_000 if market_cap_yi is not None else None,
        "pe": _number(fields[53]),
        "pb": _number(fields[56]),
        "source": "tencent",
    }


def _hk_quote_tencent(code: str) -> dict:
    fields = _quoted_fields(_get_text(f"https://qt.gtimg.cn/q=r_hk{code}"), "~")
    if len(fields) < 57:
        return {}
    market_cap_yi = _number(fields[44])
    return {
        "name": fields[1],
        "price": _number(fields[3]),
        "change_pct": _number(fields[32]),
        "prev_close": _number(fields[4]),
        "open": _number(fields[5]),
        "high": _number(fields[33]),
        "low": _number(fields[34]),
        "volume": _number(fields[6]),
        "amount": _number(fields[37]),
        "turnover_rate": None,
        "mcap": market_cap_yi * 100_000_000 if market_cap_yi is not None else None,
        "pe": _number(fields[39]),
        "pb": _number(fields[56]),
        "source": "tencent",
    }


def _hk_quote_sina(code: str) -> dict:
    fields = _quoted_fields(
        _get_text(
            f"https://hq.sinajs.cn/list=rt_hk{code}",
            referer="https://finance.sina.com.cn/",
        ),
        ",",
    )
    if len(fields) < 15:
        return {}
    return {
        "name": fields[1],
        "price": _number(fields[6]),
        "change_pct": _number(fields[8]),
        "prev_close": _number(fields[3]),
        "open": _number(fields[2]),
        "high": _number(fields[4]),
        "low": _number(fields[5]),
        "volume": _number(fields[12]),
        "amount": _number(fields[11]),
        "turnover_rate": None,
        "mcap": None,
        "pe": None,
        "pb": None,
        "source": "sina",
    }


def _merge_quotes(*quotes: dict) -> dict:
    """以前面的数据源为主，只用后续来源填充空字段。"""
    merged: dict = {}
    sources: list[str] = []
    for quote in quotes:
        if not quote:
            continue
        source = quote.get("source")
        if source and source not in sources:
            sources.append(source)
        for key, value in quote.items():
            if key == "source":
                continue
            if key not in merged or merged[key] in (None, ""):
                merged[key] = value
    merged["source"] = sources[0] if sources else None
    merged["sources"] = sources
    return merged


def _safe_quote(fetcher) -> dict:
    try:
        return fetcher()
    except Exception:
        return {}


def _best_quote(info: dict) -> dict:
    code = info["code"]
    if info["market"] == "HK":
        primary = _safe_quote(lambda: _hk_quote_tencent(code))
        secondary = _safe_quote(lambda: _hk_quote_sina(code))
    elif info["market"] != "KR":
        primary = _safe_quote(lambda: _us_quote_sina(code))
        secondary = _safe_quote(lambda: _us_quote_tencent(code))
    else:
        primary, secondary = {}, {}
    eastmoney = _safe_quote(
        lambda: _quote_from(
            _push2_stock_get(f"{info['secid_prefix']}.{code}", _QUOTE_FIELDS) or {}
        )
    )
    return _merge_quotes(primary, secondary, eastmoney)


def global_indices() -> list[dict]:
    """全球指数快照（道指 / 标普500 / 纳斯达克 / 恒生 / 恒生科技）。源无的档跳过。"""
    out = []
    for idx in _INDICES:
        d = _push2_stock_get(idx["secid"], "f43,f57,f58,f59,f60,f170")
        if not d:
            continue
        chg = d.get("f170")
        out.append({
            "key": idx["key"], "name": idx["name"], "region": idx["region"],
            "price": _price(d, "f43"),
            "change_pct": round(chg / 100, 2) if isinstance(chg, (int, float)) else None,
        })
    return out


def _search(q: str) -> dict | None:
    """东财搜索一次：市场过滤 + **精确代码匹配优先**，退而取第一条。

    只按 MktNum 过滤挑不出正股——东财搜 AAPL 会混入 AAPL22(票据)/AAPB(2倍做多ETF)，
    搜 BABA 混入 05593(窝轮)，且 SecurityType 分不开(正股与 ETF 同为 Type7、正股港股与窝轮同为 Type6)。
    正股的 Code 恰好等于查询词，故精确匹配 Code==q 最稳；无精确匹配(名称查询)才退回第一条。
    """
    url = "https://searchapi.eastmoney.com/api/suggest/get"
    params = {"input": q, "type": 14,
              "token": "D43BF722C8E33BDC906FB84D85E326E8", "count": 10}
    try:
        r = astock.em_get(url, params=params, headers=_UA_H, timeout=10)
        rows = (r.json().get("QuotationCodeTable") or {}).get("Data") or []
    except Exception:
        return None
    matches = []
    for s in rows:
        try:
            mkt = int(s.get("MktNum"))
        except (TypeError, ValueError):
            continue
        if mkt in _MKT:
            matches.append((mkt, s))
    if not matches:
        return None
    mkt, s = next(((m, x) for m, x in matches if str(x.get("Code", "")).upper() == q), matches[0])
    suffix, market = _MKT[mkt]
    code = s.get("Code", "")
    return {"code": code, "name": s.get("Name", ""), "secid_prefix": mkt,
            "secucode": f"{code}{suffix}", "market": market}


def resolve_symbol(query: str) -> dict | None:
    """代码/名称 → {code, name, secid_prefix, secucode, market}。认美股/港股/韩股。
    数字型港股短代码（如 `700`）补零到 5 位再试一次（东财按 `00700` 收）。
    韩股用国际后缀 `.KS`/`.KQ`/`.KR`（如三星 `005930.KS`）——韩股代码与 A 股同为 6 位数字，
    需显式后缀区分，否则前端会按 A 股处理、后端也搜不到韩股。"""
    q = query.strip().upper()
    if not q:
        return None
    explicit_us = q.endswith(".US")
    explicit_hk = q.endswith(".HK")
    if explicit_us or explicit_hk:
        q = q[:-3]
    for suf in (".KS", ".KQ", ".KR"):  # 剥掉韩股后缀，按裸代码搜（东财 177=韩股）
        if q.endswith(suf):
            q = q[: -len(suf)]
            break
    hit = _search(q)
    if hit is None and q.isdigit() and len(q) < 5:
        hit = _search(q.zfill(5))
    if hit is not None:
        return hit

    # 行情源本身可直接按代码查询，不能让可选的东财搜索成为单点故障。
    # 这里的 secid/secucode 仅供东财财务与末级行情回退；主行情仍按 Skill
    # 约定走新浪/腾讯，因此即使未知美股交易所也能返回实时价格。
    if (explicit_hk or q.isdigit()) and q.isdigit() and len(q) <= 5:
        code = q.zfill(5)
        return {
            "code": code,
            "name": "",
            "secid_prefix": 116,
            "secucode": f"{code}.HK",
            "market": "HK",
        }
    if (explicit_us or re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", q)) and not q.isdigit():
        return {
            "code": q,
            "name": "",
            "secid_prefix": 105,
            "secucode": f"{q}.O",
            "market": "US",
        }
    return hit


def _key_metrics(secucode: str) -> dict | None:
    """东财 GMAININDICATOR 最新一期关键财务指标（美股/港股中文字段）。"""
    market = "HK" if secucode.endswith(".HK") else "US"
    rows = astock.eastmoney_datacenter(
        f"RPT_{market}F10_FN_GMAININDICATOR",
        filter_str=f'(SECUCODE="{secucode}")',
        page_size=1, sort_columns="REPORT_DATE", sort_types="-1")
    if not rows:
        return None
    m = rows[0]
    return {
        "report_date": str(m.get("REPORT_DATE") or "")[:10],
        "revenue": m.get("OPERATE_INCOME"),
        "revenue_yoy": m.get("OPERATE_INCOME_YOY"),
        "net_profit": m.get("PARENT_HOLDER_NETPROFIT") or m.get("HOLDER_PROFIT"),
        "eps": m.get("BASIC_EPS"),
        "roe": m.get("ROE_AVG"),
        "gross_margin": m.get("GROSS_PROFIT_RATIO"),
        "net_margin": m.get("NET_PROFIT_RATIO"),
        "debt_ratio": m.get("DEBT_ASSET_RATIO"),
    }


def us_hk_stock(query: str) -> dict:
    """个股聚合（美/港）：解析代码 → 行情 + 关键财务指标。查不到返回 {}。"""
    info = resolve_symbol(query)
    if not info:
        return {}
    quote = _best_quote(info)
    metrics = None
    if info["market"] != "KR":
        try:
            metrics = _key_metrics(info["secucode"])
        except Exception:
            metrics = None
    return {
        "code": info["code"],
        "name": info["name"] or quote.get("name") or info["code"],
        "market": info["market"],
        "quote": quote,
        "metrics": metrics,
        "data_sources": quote.get("sources", []),
    }
