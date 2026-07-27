import { describe, expect, it } from "vitest";

import type { Quote } from "../types";
import { createScannerCondition, evaluateScannerExpression } from "./scannerExpressions";

const quote: Quote = {
  symbol: "300308",
  name: "中际旭创",
  market: "CN",
  changePct: 3.2,
  volumeRatio: 1.8,
  pe: 28,
};

describe("scanner expressions", () => {
  it("combines conditions with all logic", () => {
    expect(evaluateScannerExpression(quote, {
      logic: "all",
      conditions: [
        createScannerCondition({ field: "changePct", operator: "gte", value: 3 }),
        createScannerCondition({ field: "pe", operator: "lte", value: 30 }),
      ],
    })).toBe(true);
  });

  it("supports any logic and rejects missing quote fields", () => {
    expect(evaluateScannerExpression(quote, {
      logic: "any",
      conditions: [
        createScannerCondition({ field: "pb", operator: "lte", value: 2 }),
        createScannerCondition({ field: "volumeRatio", operator: "gt", value: 1.5 }),
      ],
    })).toBe(true);
  });
});
