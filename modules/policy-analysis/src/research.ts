import type { PolicyEvent, PolicySource } from "./types";

export function withinPolicyWindow(event: PolicyEvent, today: string, days: number): boolean {
  if (!days) return true;
  const age = Date.parse(`${today}T00:00:00Z`) - Date.parse(`${event.date}T00:00:00Z`);
  return age >= 0 && age < days * 86400_000;
}

export function sourceCoverage(source: PolicySource, events: PolicyEvent[]) {
  const hostname = new URL(source.url).hostname.replace(/^www\./, "");
  const records = events.filter((event) => {
    if (event.status !== "published") return false;
    const host = new URL(event.sourceUrl).hostname.replace(/^www\./, "");
    return host === hostname || host.endsWith(`.${hostname}`);
  });
  return { discovered: records.length, readable: records.filter((event) => event.documentEvidence?.status === "available").length };
}
