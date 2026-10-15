from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService
from vibe_visualization_api.capital_flow.service import finite_number


def month_shift(month: str, offset: int) -> str:
    year, number = map(int, month[:7].split("-"))
    index = year * 12 + number - 1 + offset
    return f"{index // 12:04}-{index % 12 + 1:02}"


def difference(left, right, scale=1):
    a, b = finite_number(left), finite_number(right)
    return round((a - b) * scale, 4) if a is not None and b is not None else None


RATE_META = (
    ("dr007", "DR007", "存款类机构质押式回购 · 7天", "dr007"),
    ("r007", "R007", "银行间质押式回购 · 7天", "r007"),
    ("shibor1w", "SHIBOR 1周", "无担保报价利率，不是回购成交利率", "shibor"),
    ("shibor3m", "SHIBOR 3月", "无担保报价利率 · 3个月", "shibor"),
    ("spreadBp", "R007 − DR007", "不同参与者与押品范围的利差，不是纯粹的非银信用利差", "spread"),
)


def rate_analysis(feeds: dict, today: date) -> dict:
    dr = {row["date"]: finite_number(row.get("weight")) for row in feeds["dr007"]["rows"] if row.get("ts_code") == "DR007.IB"}
    repo = {row["date"]: finite_number(row.get("weight")) for row in feeds["r007"]["rows"] if row.get("ts_code") == "R007.IB"}
    shibor = {row["date"]: row for row in feeds["shibor"]["rows"]}
    dates = sorted(set(dr) | set(repo) | set(shibor))
    points = [{"date": day, "dr007": dr.get(day), "r007": repo.get(day),
               "shibor1w": finite_number(shibor.get(day, {}).get("1w")),
               "shibor3m": finite_number(shibor.get(day, {}).get("3m")),
               "spreadBp": difference(repo.get(day), dr.get(day), 100)} for day in dates]
    newest = dates[-1] if dates else None
    series = []
    for key, name, definition, source in RATE_META:
        observed = [i for i, row in enumerate(points) if row.get(key) is not None]
        index = observed[-1] if observed else None
        latest = points[index] if index is not None else {}
        end = (index + 1) if index is not None else 0
        unit_scale = 1 if key == "spreadBp" else 100
        def change(count):
            window = points[max(0, end - count - 1):end]
            return difference(window[-1][key], window[0][key], unit_scale) if len(window) == count + 1 and all(row.get(key) is not None for row in window) else None
        history = [row[key] for row in points[max(0, end - 61):max(0, end - 1)] if row.get(key) is not None]
        age = (today - date.fromisoformat(latest["date"])).days if latest else None
        sources = [feeds["dr007"], feeds["r007"]] if source == "spread" else [feeds[source]]
        current = bool(latest and latest["date"] == newest and age <= 7
                       and all(feed["status"] == "ready" and not feed.get("usingSaved") for feed in sources))
        series.append({"id": key, "name": name, "definition": definition, "unit": "bp" if key == "spreadBp" else "%",
                       "value": latest.get(key), "asOf": latest.get("date"), "ageDays": age,
                       "current": current, "change1Bp": change(1), "change5Bp": change(5), "change20Bp": change(20),
                       "baselineSamples": len(history), "baselineExpected": min(60, max(0, end - 1)),
                       "percentile": round(sum(value <= latest[key] for value in history) / len(history) * 100, 1)
                       if len(history) >= 20 and latest else None})
    return {"asOf": newest, "points": points, "series": series,
            "note": "日频采用源数据观测日，不套用股票交易日历；1/5/20为观测日间隔，已知缺值时停止跨缺口比较。历史分位不是风险概率。7个日历日内且来源更新成功、日期对齐才参与当期解读，节假日仍需核对。"}


def credit_analysis(money: dict, financing: dict, today: date) -> dict:
    m = {row["date"][:7]: row for row in money["rows"]}
    s = {row["date"][:7]: row for row in financing["rows"]}
    points = []
    observed_months = sorted(set(m) | set(s))
    months = []
    month = observed_months[0] if observed_months else None
    while month and month <= observed_months[-1]:
        months.append(month)
        month = month_shift(month, 1)
    for month in months:
        row, previous = s.get(month, {}), s.get(month_shift(month, -12), {})
        value, old = finite_number(row.get("stk_endval")), finite_number(previous.get("stk_endval"))
        # M1 expanded in 2025. Do not splice earlier definitions or recompute its YoY from levels.
        m1 = finite_number(m.get(month, {}).get("m1_yoy")) if month >= "2025-01" else None
        m2 = finite_number(m.get(month, {}).get("m2_yoy"))
        points.append({"month": month, "m1Yoy": m1, "m2Yoy": m2, "m2M1GapPp": difference(m2, m1),
                       "socialFlowYi": finite_number(row.get("inc_month")),
                       "socialPriorYearYi": finite_number(previous.get("inc_month")),
                       "socialYoYDiffYi": difference(row.get("inc_month"), previous.get("inc_month")),
                       "socialStockWanYi": value, "socialStockYoy": round((value / old - 1) * 100, 4) if value is not None and old and old > 0 else None})
    by_month = {row["month"]: row for row in points}
    money_month = max(m, default=None)
    social_month = max(s, default=None)
    money_latest = by_month.get(money_month, {})
    social_latest = by_month.get(social_month, {})
    money_prior = by_month.get(month_shift(money_month, -1), {}) if money_month else {}
    social_prior = by_month.get(month_shift(social_month, -1), {}) if social_month else {}
    def total(month, offset):
        values = [by_month.get(month_shift(month, offset - i), {}).get("socialFlowYi") for i in range(3)]
        return sum(values) if all(value is not None for value in values) else None
    recent = total(social_month, 0) if social_month else None
    old = total(social_month, -12) if social_month else None
    def current(feed, month):
        return bool(month and month >= month_shift(today.strftime("%Y-%m"), -2) and feed["status"] == "ready" and not feed.get("usingSaved"))
    return {"points": points, "money": {**money_latest, "current": current(money, money_month) and all(money_latest.get(key) is not None for key in ("m1Yoy", "m2Yoy")),
                "m1ChangePp": difference(money_latest.get("m1Yoy"), money_prior.get("m1Yoy")),
                "m2ChangePp": difference(money_latest.get("m2Yoy"), money_prior.get("m2Yoy")),
                "gapChangePp": difference(money_latest.get("m2M1GapPp"), money_prior.get("m2M1GapPp"))},
            "social": {**social_latest, "current": current(financing, social_month) and all(social_latest.get(key) is not None for key in ("socialFlowYi", "socialStockWanYi")),
                "stockYoyChangePp": difference(social_latest.get("socialStockYoy"), social_prior.get("socialStockYoy")),
                "flow3mYi": recent, "flow3mPriorYearYi": old, "flow3mYoYDiffYi": difference(recent, old)},
            "note": "月度为所属期，不是发布日期。供应商未返回发布时间、历史版本与修订链，不能据此做无前视回测。近两个月所属期仅作时滞检查，不保证最新已发布；M1只展示2025年起扩围后的公布同比。社融含政府债券，增加不等于私人融资需求或股市流入。"}


def transmission(daily: dict, credit: dict) -> list[dict]:
    rates = {row["id"]: row for row in daily["series"]}
    dr, spread = rates["dr007"], rates["spreadBp"]
    money, social = credit["money"], credit["social"]
    def fmt(value):
        return "--" if value is None else f"{value:,.4f}".rstrip("0").rstrip(".")
    def direction(value, threshold=0):
        return "higher" if value > threshold else "lower" if value < -threshold else "flat"
    def row(key, name, observed, value, evidence, implication, watch, threshold=0):
        return {"id": key, "name": name, "signal": direction(value, threshold) if observed and value is not None else "unknown",
                "evidence": evidence, "implication": implication, "watch": watch}
    rows = [
        row("funding", "短端融资成本", dr["current"], dr["change5Bp"],
            f"DR007 {dr['asOf'] or '无日期'}：{fmt(dr['value'])}%；5观测日变化 {fmt(dr['change5Bp'])} bp" if dr["value"] is not None else "未取得DR007实际加权成交利率",
            "成本下行可缓解短端融资压力，也会压低货币类资产再投资收益；不能单凭短端利率判断长债久期机会。",
            "核对税期、季末、央行操作到期与实际融资条款；摘要按±1bp区分变化，非预测阈值。", 1),
        row("spread", "资金分层", spread["current"], spread["change5Bp"],
            f"同日R007−DR007 {fmt(spread['value'])} bp；5观测日变化 {fmt(spread['change5Bp'])} bp" if spread["value"] is not None else "R007/DR007同日数据不足，不做错日相减",
            "利差走阔提示不同参与者与押品范围的资金价格分化，需核查非银融资可得性；不是纯信用溢价。",
            "同时看绝对资金成本、成交结构与期限；不能把这条利差当成机构净流入。", 1),
        row("money", "货币活化线索", money.get("current"), money.get("gapChangePp"),
            f"{money.get('month', '无所属期')}：M1 {fmt(money.get('m1Yoy'))}%，M2 {fmt(money.get('m2Yoy'))}%，增速差较前月变化 {fmt(money.get('gapChangePp'))} 个百分点",
            "M2−M1增速差收窄可作为活化线索，但不能代替企业收入、订单和盈利验证。",
            "M1口径2025年起扩围；只用公布同比，不跨新旧口径计算增速。"),
        row("credit", "信用扩张验证", social.get("current"), social.get("stockYoyChangePp"),
            f"{social.get('month', '无所属期')}：社融存量同比估算 {fmt(social.get('socialStockYoy'))}%；近3月社融较上年同期多增 {fmt(social.get('flow3mYoYDiffYi'))} 亿元",
            "存量增速回升与季节对齐的增量多增共同支持信用改善观察；若二者背离，不能确认传导。",
            "总社融包含政府融资；还需到宏观/行业/公司模块验证私人需求与盈利。"),
    ]
    if rows[0]["signal"] == "higher":
        rows[0]["implication"] = "短端融资成本上行，杠杆策略与期限错配的利差空间可能承压；核对真实融资成本，不直接据此减仓。"
    if rows[2]["signal"] == "higher":
        rows[2]["implication"] = "M2−M1增速差扩大，尚不能确认货币活化改善；不将货币总量直接解读为股市增量资金。"
    stock_change, flow_change = social.get("stockYoyChangePp"), social.get("flow3mYoYDiffYi")
    if rows[3]["signal"] != "unknown":
        if flow_change is None:
            rows[3]["signal"] = "unknown"
        elif stock_change * flow_change < 0:
            rows[3]["signal"] = "mixed"
            rows[3]["implication"] = "社融存量增速与近3月同比增量背离，信用传导尚未得到共同验证，不能确认宽信用。"
        elif stock_change < 0 and flow_change < 0:
            rows[3]["implication"] = "社融存量同比增速回落，近3个月增量同比少增，尚未形成信用扩张共振；谨慎依赖流动性改善来推导盈利回升。"
    return rows


class LiquidityResearchService(CapitalResearchService):
    async def research(self, *, refresh=False) -> dict:
        self.start = (self.today - timedelta(days=220)).isoformat()
        monthly = CapitalResearchService(self.token, self.store, today=self.today)
        monthly.start = month_shift(self.today.strftime("%Y-%m"), -27) + "-01"
        monthly.end = (self.today.replace(day=1) - timedelta(days=1)).isoformat()
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            async def repo(code):
                return await self._dataset(client, "repo_daily", code, {"ts_code": code},
                    "ts_code,trade_date,weight", refresh=refresh, cache_key="liquidity.repo.v1")
            async def month(api, fields):
                return await monthly._dataset(client, api, "CN", {"start_m": monthly.start[:7].replace("-", ""),
                    "end_m": monthly.end[:7].replace("-", "")}, fields, "month", refresh=refresh, cache_key=f"liquidity.{api}.v1")
            dr, repo_all, shibor, money, financing = await asyncio.gather(
                repo("DR007.IB"), repo("R007.IB"),
                self._dataset(client, "shibor", "CN", {}, "date,1w,3m", "date", refresh=refresh, cache_key="liquidity.shibor.v1"),
                month("cn_m", "month,m1_yoy,m2_yoy"),
                month("sf_month", "month,inc_month,stk_endval"),
            )
            feeds = {"dr007": dr, "r007": repo_all, "shibor": shibor, "money": money, "social": financing}
            daily = rate_analysis(feeds, self.today)
            credit = credit_analysis(money, financing, self.today)
            source_meta = {"dr007": ("Tushare repo_daily · DR007.IB", "https://tushare.pro/document/2?doc_id=256"),
                "r007": ("Tushare repo_daily · R007.IB", "https://tushare.pro/document/2?doc_id=256"),
                "shibor": ("Tushare shibor", "https://tushare.pro/document/2?doc_id=149"),
                "money": ("Tushare cn_m · 人民银行货币供应量", "https://tushare.pro/document/2?doc_id=242"),
                "social": ("Tushare sf_month · 人民银行社会融资规模", "https://tushare.pro/document/2?doc_id=310")}
            return {"schemaVersion": "newma-desk.liquidity.v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "query": {"dailyStart": self.start, "dailyEnd": self.end, "monthlyStart": monthly.start[:7], "monthlyEnd": monthly.end[:7]},
                    "daily": daily, "credit": credit, "transmission": transmission(daily, credit),
                    "feeds": [{"id": key, "name": source_meta[key][0], "url": source_meta[key][1],
                        **{k: v for k, v in feed.items() if k != "rows"},
                        "count": len(feed["rows"]), "asOf": feed["rows"][-1]["date"][:7] if key in {"money", "social"} and feed["rows"] else feed["rows"][-1]["date"] if feed["rows"] else None}
                        for key, feed in feeds.items()],
                    "operations": {"status": "unavailable", "grossYi": None, "maturitiesYi": None, "netYi": None,
                        "url": "https://www.pbc.gov.cn/", "note": "央行操作尚未接入完整的投放、到期与期限明细，不用投放额冒充净投放，不把缺失当零。"},
                    "notes": ["利率值为%，变化为bp，1个百分点=100bp；R007/DR007采用weight加权价，不用收盘或weight_r替代。",
                        "社融增量为亿元、存量为万亿元，两者不相加；存量同比由同月存量估算，可能与官方修订后同比不同。",
                        "月频社融只比较上年同月/相同3个月，不拿月度环比跳变直接判断宽信用。",
                        "更新失败可保留已保存历史，但失败来源不参加当期文字方向判断。没有预测置信度和混频总分。"]}
        finally:
            if owns:
                await client.aclose()
