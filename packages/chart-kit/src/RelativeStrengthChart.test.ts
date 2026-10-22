import { describe, expect, it } from "vitest";

import { normalizedStrengthSeries, strengthPath } from "./RelativeStrengthChart";

describe("normalizedStrengthSeries", () => {
  it("normalizes the first close to zero and subsequent closes to percentage returns", () => {
    const result = normalizedStrengthSeries("CN:600519", "贵州茅台", "#a87432", [
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

  it("uses elapsed time, not point index, for the shared horizontal axis", () => {
    const series = { id: "a", label: "a", color: "red", points: [{ timestamp: 100, value: 0 }, { timestamp: 200, value: 1 }, { timestamp: 1000, value: 2 }] };
    expect(strengthPath(series, 0, 2, 100, 1000)).toBe("M48.00,326.00 L149.11,180.00 L958.00,34.00");
    expect(strengthPath({ ...series, points: series.points.slice(1) }, 0, 2, 100, 1000)).toBe("M149.11,180.00 L958.00,34.00");
  });

  it("sorts valid observations and removes invalid closes", () => {
    const bars = [20, 0, NaN, 10].map((close, index) => ({ timestamp: 4 - index, open: close, high: close, low: close, close }));
    expect(normalizedStrengthSeries("a", "a", "red", bars).points).toEqual([{ timestamp: 1, value: 0 }, { timestamp: 4, value: 100 }]);
  });
});
