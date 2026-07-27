import type { Quote } from "../types";

export type ScannerField = "changePct" | "volumeRatio" | "amount" | "pe" | "pb";
export type ScannerOperator = "gt" | "gte" | "lt" | "lte" | "eq";

export interface ScannerCondition {
  id: string;
  field: ScannerField;
  operator: ScannerOperator;
  value: number;
}

export interface ScannerExpression {
  logic: "all" | "any";
  conditions: ScannerCondition[];
}

export interface SavedScannerExpression {
  id: string;
  name: string;
  expression: ScannerExpression;
  updatedAt: string;
}

function quoteNumber(quote: Quote, field: ScannerField) {
  const value = quote[field];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function evaluateScannerCondition(quote: Quote, condition: ScannerCondition) {
  const actual = quoteNumber(quote, condition.field);
  if (actual === undefined) return false;
  if (condition.operator === "gt") return actual > condition.value;
  if (condition.operator === "gte") return actual >= condition.value;
  if (condition.operator === "lt") return actual < condition.value;
  if (condition.operator === "lte") return actual <= condition.value;
  return actual === condition.value;
}

export function evaluateScannerExpression(quote: Quote, expression: ScannerExpression) {
  if (!expression.conditions.length) return true;
  const results = expression.conditions.map((condition) => evaluateScannerCondition(quote, condition));
  return expression.logic === "all" ? results.every(Boolean) : results.some(Boolean);
}

export function createScannerCondition(input: Partial<Omit<ScannerCondition, "id">> = {}): ScannerCondition {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `condition-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    field: input.field ?? "changePct",
    operator: input.operator ?? "gte",
    value: input.value ?? 0,
  };
}

export const SCANNER_TEMPLATES = {
  all: { logic: "all", conditions: [] },
  momentum: {
    logic: "all",
    conditions: [
      createScannerCondition({ field: "changePct", operator: "gte", value: 1.5 }),
    ],
  },
  volume: {
    logic: "any",
    conditions: [
      createScannerCondition({ field: "volumeRatio", operator: "gte", value: 1.2 }),
      createScannerCondition({ field: "amount", operator: "gte", value: 5_000_000_000 }),
    ],
  },
  value: {
    logic: "all",
    conditions: [
      createScannerCondition({ field: "pe", operator: "gt", value: 0 }),
      createScannerCondition({ field: "pe", operator: "lte", value: 30 }),
    ],
  },
} satisfies Record<string, ScannerExpression>;

export function cloneScannerExpression(expression: ScannerExpression): ScannerExpression {
  return {
    logic: expression.logic,
    conditions: expression.conditions.map((condition) => ({
      ...condition,
      id: globalThis.crypto?.randomUUID?.() ?? `${condition.id}-${Math.random().toString(16).slice(2)}`,
    })),
  };
}
