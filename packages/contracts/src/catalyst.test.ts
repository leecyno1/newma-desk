import { describe, expect, it } from "vitest";

import { catalystEventSchema, catalystFeedSchema } from "./catalyst";

const event = {
  id: "cycle:C7:2026-07:1",
  type: "macro",
  date: "2026-08-31",
  windowStart: "2026-07-31",
  windowEnd: "2026-08-31",
  timePrecision: "window",
  status: "monitoring",
  title: "C7 1个月状态观察窗",
  summary: "风险偏好概率 80%",
  source: { id: "seven-cycle", label: "七周期研究", url: "http://127.0.0.1:4174/cycles?cycle=C7" },
  evidenceIds: ["seven-cycle:C7:2026-07:1m"],
  asOf: "2026-07",
  freshness: { status: "fresh", ageDays: 3 },
  confidence: { level: "high", score: 0.79, rationale: "通过样本外门槛" },
  impactedAssets: [],
  expectedDirection: "positive",
  confirmationConditions: ["方向保持一致"],
  invalidationConditions: ["验证门槛失效"],
  importance: "high",
};

describe("catalyst calendar contract", () => {
  it("accepts an evidence-gated monitoring window", () => {
    expect(catalystEventSchema.parse(event).cycleContext).toBeUndefined();
    expect(catalystFeedSchema.parse({
      schemaVersion: "newma-desk.catalyst-calendar.v1",
      generatedAt: "2026-08-03T00:00:00Z",
      horizon: { start: "2026-08-03", end: "2026-12-31", days: 150 },
      coverage: { markets: ["CN"], symbols: ["600519"] },
      items: [event],
      sources: [{ id: "seven-cycle", label: "七周期研究", status: "ok", count: 1, asOf: "2026-08-03" }],
      gaps: [],
      disclaimer: "仅供研究",
    }).items).toHaveLength(1);
  });

  it("rejects a window without boundaries", () => {
    expect(() => catalystEventSchema.parse({ ...event, windowStart: undefined })).toThrow();
  });
});
