import { describe, expect, it } from "vitest";
import type { OhlcvResult, SecurityRef } from "../types";
import { buildStrengthComparison, requestedAdjustment } from "./comparison";

const cn: SecurityRef = { symbol: "600519", name: "A", market: "CN" };
const us: SecurityRef = { symbol: "AAPL", name: "B", market: "US" };
function result(security: SecurityRef, days: string[], closes: number[]): OhlcvResult {
  return { symbol: security.symbol, market: security.market, timeframe: "1d", adjust: security.market === "CN" ? "qfq" : "none", source: "fixture", asOf: "2026-10-22", hasMore: false,
    items: days.map((day, index) => ({ timestamp: Date.parse(`${day}T00:00:00${security.market === "CN" ? "+08:00" : "-04:00"}`), open: 10, high: 20, low: 10, close: closes[index]! })) };
}
const compare = (a: OhlcvResult, b: OhlcvResult, period: "1d" | "1w" = "1d") => buildStrengthComparison([cn, us], { "CN:600519": a, "US:AAPL": b }, ["red", "blue"], period);

describe("common-window relative strength", () => {
  it("normalizes unequal histories over common local trading dates across timezones", () => {
    const value = compare(result(cn, ["2026-10-19", "2026-10-20", "2026-10-21"], [1, 10, 12]), result(us, ["2026-10-20", "2026-10-21", "2026-10-22"], [20, 22, 100]));
    expect(value.window).toMatchObject({ start: "2026-10-20", end: "2026-10-21", observations: 2 });
    expect(value.series[0]!.points.at(-1)!.value).toBeCloseTo(20);
    expect(value.series[1]!.points.at(-1)!.value).toBeCloseTo(10);
    expect(value.series[0]!.points.map((point) => point.timestamp)).toEqual(value.series[1]!.points.map((point) => point.timestamp));
  });
  it("does not rank empty, invalid or adjustment-degraded series as zero returns", () => {
    const a = result(cn, ["2026-10-20", "2026-10-21"], [10, 12]);
    const b = result(us, ["2026-10-20", "2026-10-21"], [0, NaN]);
    expect(compare(a, b).series).toEqual([]);
    expect(compare(a, b).excluded[0]!.reason).toBe("有效日线不足");
    expect(compare({ ...a, adjust: "none" }, b).excluded).toHaveLength(2);
  });
  it("does not interpolate across nonoverlapping histories", () => {
    expect(compare(result(cn, ["2026-10-19", "2026-10-20"], [10, 12]), result(us, ["2026-10-21", "2026-10-22"], [10, 12])).window).toBeNull();
  });
  it("samples weekly views at the last shared day, including a disclosed partial week", () => {
    const dates = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"];
    const value = compare(result(cn, dates, [9, 10, 11, 12]), result(us, dates, [18, 20, 22, 24]), "1w");
    expect(value.window).toEqual({ start: "2026-10-16", end: "2026-10-20", observations: 2, commonTradingDays: 4 });
    expect(value.series[0]!.points.at(-1)!.value).toBeCloseTo(20);
  });
  it("never requests minute, overseas or fund adjusted prices", () => {
    expect(requestedAdjustment(cn, "1d", "hfq")).toBe("hfq");
    expect(requestedAdjustment(cn, "15m", "hfq")).toBe("none");
    expect(requestedAdjustment(us, "1d", "hfq")).toBe("none");
    expect(requestedAdjustment({ ...cn, assetType: "fund" }, "1d", "hfq")).toBe("none");
  });
});
