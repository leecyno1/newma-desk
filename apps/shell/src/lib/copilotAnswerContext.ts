import type { ModPageContext } from "@newma-desk/contracts";

const sources = ["structured", "dom-html", "visual", "manifest"] as const;
const fields = ["viewTitle", "subject", "symbol", "market", "currency", "fiscalPeriod", "periodEnd", "basis", "workbookId"] as const;
export type CopilotAnswerContext = {
  capturedAt: string;
  source: typeof sources[number];
} & Partial<Record<typeof fields[number], string>>;

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, 300) : undefined;
}

/** Keep identity only, not another copy of financial data or document contents. */
export function captureAnswerContext(page: ModPageContext, source: CopilotAnswerContext["source"]): CopilotAnswerContext {
  const record: CopilotAnswerContext = {
    capturedAt: new Date().toISOString(), source, viewTitle: text(page.view.title),
  };
  // DOM/screenshots may identify a page, but do not establish workbook identity.
  if (source === "structured") {
    const selection = page.selection;
    const filters = page.filters;
    record.subject = text([selection.name, selection.symbol, selection.market].map(text).filter(Boolean).join(" · "));
    record.symbol = text(selection.symbol);
    record.market = text(selection.market);
    record.currency = text(filters.currency);
    record.fiscalPeriod = text(selection.fiscalPeriod);
    record.periodEnd = text(filters.periodEnd);
    record.basis = text(filters.basis);
    record.workbookId = text(selection.workbookId);
  }
  return record;
}

const identityFields = ["workbookId", "symbol", "market", "currency", "periodEnd", "basis"] as const;
export const FOLLOWUP_MAX_CHARS = 16000;

export function canFollowup(record?: CopilotAnswerContext): boolean {
  return record?.source === "structured" && identityFields.every(key => Boolean(record[key])) &&
    ["annual", "quarter", "ytd", "ttm"].includes(record.basis!);
}

export function matchesFollowup(selected: CopilotAnswerContext | undefined, current: CopilotAnswerContext): boolean {
  const comparedFields = [...identityFields, "subject", "fiscalPeriod"] as const;
  return canFollowup(selected) && canFollowup(current) &&
    comparedFields.every(key => selected![key] === current[key]);
}

export function readAnswerContext(value: unknown): CopilotAnswerContext | undefined {
  if (!value || typeof value !== "object") return undefined;
  const item = value as Record<string, unknown>;
  if (typeof item.capturedAt !== "string" || item.capturedAt.length > 40 || !Number.isFinite(Date.parse(item.capturedAt)) ||
      !sources.includes(item.source as CopilotAnswerContext["source"])) return undefined;
  const record: CopilotAnswerContext = {capturedAt: item.capturedAt, source: item.source as CopilotAnswerContext["source"]};
  for (const key of fields) {
    if (typeof item[key] === "string" && item[key].length <= 300) record[key] = text(item[key]);
  }
  return record;
}
