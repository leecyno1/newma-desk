export type PolicyStatus = "published" | "scheduled" | "awaiting-verification";
export type PolicyCertainty = "official" | "calendar-rule" | "expected-window";

export interface PolicyEvent {
  id: string; title: string; date: string; institution: string; category: string;
  level: 1 | 2 | 3; status: PolicyStatus; certainty: PolicyCertainty; summary: string;
  rationale: string[]; sourceUrl: string; marketScope: string[];
}

export interface PolicySource {
  id: string; name: string; url: string; categories: string[]; rssHubPath: string | null;
}

export interface PolicyDashboard {
  schemaVersion: string; generatedAt: string; today: string; events: PolicyEvent[]; sources: PolicySource[];
  summary: { total: number; level3: number; upcoming: number; nextDate: string | null };
  assessment: Array<{ level: 1 | 2 | 3; label: string; definition: string }>;
  collector: {
    foundation: string; revision: string; mode: string; status: string; note: string;
    feeds: Array<{ sourceId: string; status: string; items: number; reason?: string }>;
    collectedAt?: string;
  };
}
