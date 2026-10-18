import { describe, expect, it } from "vitest";
import { policyCalendarEntries, shiftPolicyMonth } from "./calendar";
import type { PolicyEvent } from "./types";

const event = {
  id: "audit", date: "2026-09-24", status: "published", certainty: "official",
  documentEvidence: { status: "available", effectiveAt: "2026-12-01", effectiveDateQuote: "自12月1日起施行" },
} as PolicyEvent;

describe("policy calendar dates", () => {
  it("retains publication and adds separately evidenced commencement", () => {
    const entries = policyCalendarEntries([event]);
    expect(entries.map(({ date, kind }) => ({ date, kind }))).toEqual([
      { date: "2026-09-24", kind: "publication" }, { date: "2026-12-01", kind: "effective" },
    ]);
    expect(event.date).toBe("2026-09-24");
  });
  it("does not invent an effective date from an unquoted field", () => {
    expect(policyCalendarEntries([{ ...event, documentEvidence: { status: "available", effectiveAt: "2026-12-01", note: "" } }])).toHaveLength(1);
  });
  it("labels calendar-rule windows as expectations, not official appointments", () => {
    expect(policyCalendarEntries([{ ...event, status: "scheduled", certainty: "calendar-rule", documentEvidence: null }])[0]).toMatchObject({ kind: "window", label: "预期窗口" });
  });
  it("moves correctly across year boundaries", () => {
    expect(shiftPolicyMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftPolicyMonth("2026-01", -1)).toBe("2025-12");
  });
});
