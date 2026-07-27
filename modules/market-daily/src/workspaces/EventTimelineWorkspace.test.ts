import { describe, expect, it } from "vitest";

import {
  deriveMarketEvents,
  selectChartTimelineEvents,
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
});
