import type { PolicyEvent } from "./types";

export type CalendarBasis = "all" | "publication" | "effective" | "window";
export interface PolicyCalendarEntry {
  id: string;
  date: string;
  kind: Exclude<CalendarBasis, "all">;
  label: string;
  event: PolicyEvent;
}

// One document may have several dates. Never replace publication with commencement.
export function policyCalendarEntries(events: PolicyEvent[]): PolicyCalendarEntry[] {
  return events.flatMap((event): PolicyCalendarEntry[] => {
    const kind = event.status === "published" ? "publication" : "window";
    const entries: PolicyCalendarEntry[] = [{
      id: `${event.id}:${kind}`, date: event.date, kind, event,
      label: kind === "publication" ? "发布记录" : event.certainty === "official" ? "官方日程" : "预期窗口",
    }];
    const document = event.documentEvidence;
    if (document?.status === "available" && document.effectiveAt && document.effectiveDateQuote) {
      entries.push({ id: `${event.id}:effective`, date: document.effectiveAt, kind: "effective", label: "明确施行", event });
    }
    return entries;
  }).filter((entry) => /^\d{4}-\d{2}-\d{2}$/.test(entry.date))
    .sort((a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id));
}

export function shiftPolicyMonth(month: string, offset: number): string {
  const date = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1 + offset, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}
