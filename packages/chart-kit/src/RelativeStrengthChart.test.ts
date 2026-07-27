import { describe, expect, it } from "vitest";

import { normalizedStrengthSeries } from "./RelativeStrengthChart";

describe("normalizedStrengthSeries", () => {
  it("normalizes the first close to zero and subsequent closes to percentage returns", () => {
    const result = normalizedStrengthSeries("CN:600519", "贵州茅台", "#2563eb", [
      { timestamp: 1, open: 10, high: 10, low: 10, close: 10 },
      { timestamp: 2, open: 11, high: 11, low: 11, close: 11 },
    ]);

    expect(result.points).toEqual([
      { timestamp: 1, value: 0 },
      { timestamp: 2, value: 10.000000000000009 },
    ]);
  });

  it("returns an empty series when there is no usable base close", () => {
    expect(normalizedStrengthSeries("empty", "空", "#000", []).points).toEqual([]);
  });
});
