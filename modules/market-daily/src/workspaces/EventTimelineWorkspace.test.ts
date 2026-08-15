import { describe, expect, it } from "vitest";

import {
  deriveMarketEvents,
  selectChartTimelineEvents,
  selectFundChartTimelineEvents,
} from "./EventTimelineWorkspace";

describe("deriveMarketEvents", () => {
  it("derives only evidence-backed price, volume and breakout events", () => {
    const bars = Array.from({ length: 24 }, (_, index) => ({
      timestamp: 1_700_000_000_000 + index * 86_400_000,
      open: 100 + index,
      high: 101 + index,
      low: 99 + index,
      close: index === 22 ? 140 : 100 + index,
      volume: index === 22 ? 20_000 : 1_000,
    }));

    const events = deriveMarketEvents(bars);
    expect(events.some((event) => event.type === "price")).toBe(true);
    expect(events.some((event) => event.type === "volume")).toBe(true);
    expect(events.some((event) => event.type === "breakout")).toBe(true);
    expect(events.every((event) => ["price", "volume", "breakout"].includes(event.type))).toBe(true);
  });

  it("uses a lower daily move threshold for ETF timelines", () => {
    const bars = [
      { timestamp: 1_700_000_000_000, open: 100, high: 101, low: 99, close: 100, volume: 1_000 },
      { timestamp: 1_700_086_400_000, open: 100, high: 103, low: 100, close: 102, volume: 1_000 },
    ];

    expect(deriveMarketEvents(bars).some((event) => event.type === "price")).toBe(false);
    expect(deriveMarketEvents(bars, 1.5).some((event) => event.type === "price")).toBe(true);
  });

  it("derives fund NAV and distribution events without volume signals", () => {
    const bars = [
      { timestamp: 1_700_000_000_000, open: 1, high: 1, low: 1, close: 1, volume: 0 },
      { timestamp: 1_700_086_400_000, open: 1.02, high: 1.02, low: 1.02, close: 1.02, volume: 99_000, navEvent: "每份派现金0.10元" },
    ];

    const events = deriveMarketEvents(bars, 1, { includeVolume: false, priceLabel: "单位净值" });

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "price", title: "单位净值快速上行" }),
      expect.objectContaining({ type: "distribution", detail: "每份派现金0.10元" }),
    ]));
    expect(events.some((event) => event.type === "volume")).toBe(false);
  });
});

describe("selectChartTimelineEvents", () => {
  it("deduplicates dense evidence by date while retaining the selection", () => {
    const day = Date.UTC(2026, 6, 23);
    const events = [
      { id: "news-1", timestamp: day + 3_000, type: "news" },
      { id: "news-2", timestamp: day + 2_000, type: "news" },
      { id: "report-1", timestamp: day + 1_000, type: "research" },
      { id: "announcement-1", timestamp: day - 86_400_000, type: "announcement" },
    ];

    expect(selectChartTimelineEvents(events).map((event) => event.id)).toEqual([
      "news-1",
      "announcement-1",
    ]);
    expect(selectChartTimelineEvents(events, "news-2", 3).map((event) => event.id)).toEqual([
      "news-2",
      "announcement-1",
    ]);
  });

  it("keeps fund annotations focused on distributions, announcements and major NAV moves", () => {
    const day = Date.UTC(2026, 7, 14);
    const events = [
      { id: "distribution", timestamp: day, type: "distribution", origin: "derived", score: 8 },
      { id: "announcement-1", timestamp: day - 86_400_000, type: "announcement", origin: "evidence", score: 10 },
      { id: "announcement-2", timestamp: day - 2 * 86_400_000, type: "announcement", origin: "evidence", score: 10 },
      { id: "announcement-3", timestamp: day - 3 * 86_400_000, type: "announcement", origin: "evidence", score: 10 },
      { id: "nav-large", timestamp: day - 4 * 86_400_000, type: "price", origin: "derived", score: 4.2 },
      { id: "nav-small", timestamp: day - 5 * 86_400_000, type: "price", origin: "derived", score: 1.1 },
    ];

    const selected = selectFundChartTimelineEvents(events);

    expect(selected).toHaveLength(5);
    expect(selected.map((event) => event.id)).toEqual(expect.arrayContaining([
      "distribution",
      "announcement-1",
      "announcement-2",
      "nav-large",
    ]));
  });
});
