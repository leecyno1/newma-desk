import { describe, expect, it } from "vitest";

import { moduleEventNameSchema, moduleEventSchema } from "./event";

describe("moduleEventSchema", () => {
  it("parses a valid module event", () => {
    const event = {
      version: "1.0",
      event: "security.selected",
      source: "market-daily",
      target: "stock-analysis",
      traceId: "trace-1",
      payload: { symbol: "600519", market: "CN" },
    };

    expect(moduleEventSchema.parse(event)).toEqual(event);
  });

  it("rejects an unversioned module event", () => {
    expect(() =>
      moduleEventSchema.parse({ event: "security.selected" }),
    ).toThrow();
  });

  it("exports the namespaced module event name contract", () => {
    expect(moduleEventNameSchema.parse("security.selected")).toBe(
      "security.selected",
    );
    expect(() => moduleEventNameSchema.parse("selected")).toThrow();
  });

  it("rejects unknown envelope fields", () => {
    expect(() =>
      moduleEventSchema.parse({
        version: "1.0",
        event: "security.selected",
        source: "market-daily",
        traceId: "trace-1",
        payload: {},
        timestamp: "2026-07-20T00:00:00Z",
      }),
    ).toThrow();
  });
});
