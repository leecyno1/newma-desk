import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MarketOverview } from "../types";
import { sentimentEvidence, SentimentWorkspace } from "./SentimentWorkspace";

const overview = (): MarketOverview => ({ sentiment: { up: 40, down: 40, flat: 20, zt: 4, dt: 1, date: "2026-10-15", source: "测试来源" },
  sectors: [{ name: "测试行业", pct: 1.2, net: 2.5, metric: "large-order-net", asOf: "2026-10-15" }], updated: "2026-10-16 13:00" });
const source = (load: () => Promise<MarketOverview>) => ({ sentiment: load, sentimentHistory: () => new Promise<never>(() => {}), limitBoards: () => new Promise<never>(() => {}) });

describe("sentiment evidence", () => {
  it("uses a verified daily session without pretending it is live", () => {
    const data = overview();
    data.session = { expectedDate: "2026-10-15", current: true, calendarStatus: "ready", cached: true, usingSaved: false };
    expect(sentimentEvidence({ status: "loaded", data }).freshness).toBe("fresh");
    data.session.expectedDate = "2026-10-16";
    expect(sentimentEvidence({ status: "loaded", data }).freshness).not.toBe("fresh");
    data.session.expectedDate = "2026-10-15";
    data.session.usingSaved = true;
    expect(sentimentEvidence({ status: "loaded", data }).freshness).not.toBe("fresh");
  });
  it("includes flat stocks, separates limit share and preserves source date and units", () => {
    const result = sentimentEvidence({ status: "loaded", data: overview() });
    expect(result.breadth.upRatioPct).toBe(40);
    expect(result.limitBoard.upSharePct).toBe(80);
    expect(result.asOf).toBe("2026-10-15");
    expect(result.retrievedAt).toBe("2026-10-16 13:00");
    expect(result.freshness).not.toBe("live");
    expect(result.sectors[0]!.netYi).toBe(2.5);
    expect(result).not.toHaveProperty("score");
  });
  it("does not replace missing or invalid counts with neutral values", () => {
    const data = overview();
    data.sentiment = { up: 40, down: 40, flat: null, zt: null, dt: 1 };
    const result = sentimentEvidence({ status: "loaded", data });
    expect(result.breadth.upRatioPct).toBeNull();
    expect(result.limitBoard.upSharePct).toBeNull();
    expect(result.asOf).toBeNull();
    expect(result.status).toBe("partial");
    for (const value of [-1, NaN, Infinity, 1.5]) {
      data.sentiment.up = value;
      expect(sentimentEvidence({ status: "loaded", data }).breadth.up).toBeNull();
    }
  });
  it("keeps legitimate zero counts but does not calculate zero-denominator ratios", () => {
    const data = overview();
    data.sentiment = { up: 0, down: 0, flat: 100, zt: 0, dt: 0 };
    let result = sentimentEvidence({ status: "loaded", data });
    expect(result.breadth.upRatioPct).toBe(0);
    expect(result.limitBoard.upSharePct).toBeNull();
    data.sentiment.flat = 0;
    result = sentimentEvidence({ status: "loaded", data });
    expect(result.breadth.total).toBe(0);
    expect(result.breadth.upRatioPct).toBeNull();
  });
  it("withdraws ratios when counts contradict and does not assume unknown flow units", () => {
    const data = overview(); data.sentiment!.zt = 90; delete data.sectors![0]!.metric;
    const result = sentimentEvidence({ status: "loaded", data });
    expect(result.breadth.upRatioPct).toBeNull();
    expect(result.limitBoard.upSharePct).toBeNull();
    expect(result.sectors[0]!.netYi).toBeNull();
    expect(result.reasons.join()).toContain("统计口径待核验");
  });
  it("rejects impossible and future dates without substituting retrieval date", () => {
    for (const date of ["2026-02-30", "2999-01-01", "missing"]) {
      const data = overview(); data.sentiment!.date = date;
      expect(sentimentEvidence({ status: "loaded", data }).asOf).toBeNull();
    }
  });
  it("clears both visible evidence and context while refreshing and after failure, then recovers", async () => {
    let reject!: (error: Error) => void;
    const load = vi.fn().mockResolvedValueOnce(overview()).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; })).mockResolvedValueOnce(overview());
    const dataSource = source(load), onContextChange = vi.fn();
    const { rerender } = render(<SentimentWorkspace dataSource={dataSource} refreshNonce={0} onContextChange={onContextChange} />);
    expect(await screen.findByText("40%")).toBeVisible();
    rerender(<SentimentWorkspace dataSource={dataSource} refreshNonce={1} onContextChange={onContextChange} />);
    await waitFor(() => expect(onContextChange.mock.lastCall?.[0].status).toBe("loading"));
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
    expect(onContextChange.mock.lastCall?.[0].breadth.up).toBeNull();
    await act(async () => reject(new Error("来源暂不可用")));
    expect(screen.getByRole("alert")).toHaveTextContent("旧数据与旧判断已撤下");
    expect(onContextChange.mock.lastCall?.[0].status).toBe("error");
    expect(onContextChange.mock.lastCall?.[0].sectors).toEqual([]);
    rerender(<SentimentWorkspace dataSource={dataSource} refreshNonce={2} onContextChange={onContextChange} />);
    expect(await screen.findByText("40%")).toBeVisible();
  });
  it("ignores an older response after data source changes", async () => {
    let finish!: (data: MarketOverview) => void;
    const old = source(() => new Promise(resolve => { finish = resolve; })), nextData = overview();
    nextData.sentiment!.up = 140;
    const next = source(async () => nextData), onContextChange = vi.fn();
    const { rerender } = render(<SentimentWorkspace dataSource={old} refreshNonce={0} onContextChange={onContextChange} />);
    rerender(<SentimentWorkspace dataSource={next} refreshNonce={0} onContextChange={onContextChange} />);
    expect(await screen.findByText("70%")).toBeVisible();
    await act(async () => finish(overview()));
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
    expect(onContextChange.mock.lastCall?.[0].breadth.up).toBe(140);
  });
});
