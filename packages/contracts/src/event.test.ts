import { describe, expect, it } from "vitest";

import { moduleEventSchema } from "./event";

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
});
