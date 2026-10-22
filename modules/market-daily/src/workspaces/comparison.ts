import { normalizedStrengthSeries } from "@newma-desk/chart-kit";
import { isOpenFundSecurity, securityKey } from "../data";
import type { Adjustment, OhlcvResult, SecurityRef, Timeframe } from "../types";

export const ADJUSTMENT_LABELS = { none: "不复权", qfq: "前复权", hfq: "后复权" };

export function requestedAdjustment(security: SecurityRef, timeframe: Timeframe, adjustment: Adjustment): Adjustment {
  return security.market !== "CN" || isOpenFundSecurity(security) || timeframe.endsWith("m") ? "none" : adjustment;
}

function tradingDate(timestamp: number, market: SecurityRef["market"]) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: market === "US" ? "America/New_York" : "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(timestamp);
}

function weekStart(date: string) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - (value.getUTCDay() + 6) % 7);
  return value.toISOString().slice(0, 10);
}

export function buildStrengthComparison(
  securities: SecurityRef[], results: Record<string, OhlcvResult>, colors: string[], period: "1d" | "1w",
) {
  const excluded: Array<{ id: string; label: string; reason: string }> = [];
  const eligible = securities.flatMap((security, index) => {
    const id = securityKey(security);
    const result = results[id];
    const bars = (result?.items ?? []).filter((bar) => Number.isFinite(bar.timestamp) && Number.isFinite(bar.close) && bar.close > 0);
    const reason = bars.length < 2 ? "有效日线不足" : result?.adjust !== requestedAdjustment(security, "1d", "qfq") ? "返回复权与请求不一致" : null;
    if (reason) {
      excluded.push({ id, label: security.name, reason });
      return [];
    }
    const byDate = new Map([...bars].sort((a, b) => a.timestamp - b.timestamp).map((bar) => [tradingDate(bar.timestamp, security.market), bar]));
    return [{ id, label: security.name, color: colors[index % colors.length]!, byDate }];
  });
  const commonDates = eligible.length < 2 ? [] : [...eligible[0]!.byDate.keys()].filter((date) => eligible.every((item) => item.byDate.has(date))).sort();
  // Weekly views sample the same daily observations; provider weekly bars can use different closing dates.
  const dates = period === "1w" ? [...new Map(commonDates.map((date) => [weekStart(date), date])).values()] : commonDates;
  const window = dates.length < 2 ? null : { start: dates[0]!, end: dates.at(-1)!, observations: dates.length, commonTradingDays: commonDates.length };
  const series = !window ? [] : eligible.map((item) => normalizedStrengthSeries(item.id, item.label, item.color,
    dates.map((date) => ({ ...item.byDate.get(date)!, timestamp: Date.parse(`${date}T00:00:00Z`) })),
  ));
  return { series, window, excluded };
}
