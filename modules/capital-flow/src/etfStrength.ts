import type { ETFResearch } from "./types";

export type ETFStrengthDays = 1 | 5 | 20;
export type ETFStrengthSort = "pool" | "inflow" | "outflow";

export function etfPoolCoverage(rows: ETFResearch[], days: ETFStrengthDays) {
  const confirmed = rows.flatMap(row => {
    const window = row.summary.strength?.[days];
    return window?.current && window.strengthPct != null ? [window.strengthPct] : [];
  });
  return { total: rows.length, confirmed: confirmed.length, unconfirmed: rows.length - confirmed.length,
    inflow: confirmed.filter(strength => strength > 0).length,
    outflow: confirmed.filter(strength => strength < 0).length };
}

export function withETFStrengthState(row: ETFResearch, confirmed: boolean): ETFResearch {
  return { ...row, summary: { ...row.summary, strength: row.summary.strength ? Object.fromEntries(
    Object.entries(row.summary.strength).map(([key, window]) => [key, { ...window,
      current: confirmed && window.current,
      reason: confirmed ? window.reason : [window.reason, "正在更新或更新失败，不能作为本次确认强度"].filter(Boolean).join("；"),
    }])) : undefined } };
}

export function sortedETFs(rows: ETFResearch[], days: ETFStrengthDays, order: ETFStrengthSort): ETFResearch[] {
  if (order === "pool") return rows;
  return [...rows].sort((a, b) => {
    const aw = a.summary.strength?.[days], bw = b.summary.strength?.[days];
    const av = aw?.current ? aw.strengthPct : null, bv = bw?.current ? bw.strengthPct : null;
    if (av == null || bv == null) return av == null && bv == null ? 0 : av == null ? 1 : -1;
    return order === "inflow" ? bv - av : av - bv;
  });
}
