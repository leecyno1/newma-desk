export type PolicyStatus = "published" | "scheduled" | "awaiting-verification";
export type PolicyCertainty = "official" | "calendar-rule" | "expected-window";
export type PolicyDocumentType = "formal-policy" | "policy-interpretation" | "meeting-speech" | "implementation-update" | "macro-data";
export type PolicyLifecycleStage = "scheduled" | "solicitation" | "published" | "effective" | "amended" | "adjusted" | "repealed" | "expired";
export type PolicyEntityType = "security" | "etf" | "industry" | "concept";

export interface PolicyEntity {
  type: PolicyEntityType; canonicalId: string; displayName: string; confidence: number;
  evidence: string; source: "rule"; market?: "CN"; symbol?: string; assetType?: "stock" | "etf";
}

export interface PolicyComparison {
  basePolicyId: string; basis: "title-summary"; added: string[]; removed: string[]; shared: string[]; note: string;
}

export interface PolicyInterpretation {
  policyId: string; title: string; sourceUrl: string; mode: "ai" | "rule-fallback";
  model?: string; adapter?: string;
  impactAnalysis: { facts: string[]; inferences: string[]; uncertainties: string[] };
  historicalComparison: {
    matchedPolicies: Array<{ id: string; title: string; date: string }>;
    added: string[]; removed: string[]; shared: string[]; note: string;
  };
  transcriptComparison: { status: "available" | "unavailable"; basis: string; note: string };
}

export interface PolicyEvent {
  id: string; title: string; date: string; institution: string; category: string;
  level: 1 | 2 | 3; status: PolicyStatus; certainty: PolicyCertainty; summary: string;
  rationale: string[]; sourceUrl: string; marketScope: string[];
  assessmentConfidence: number; assessmentStatus: "machine" | "reviewed";
  documentType: PolicyDocumentType;
  lifecycleStage: PolicyLifecycleStage; policySeriesKey: string;
  relatedPolicyIds: string[];
  entities: PolicyEntity[]; comparison: PolicyComparison | null;
  firstSeenAt?: string; lastSeenAt?: string; discoveredBy?: string;
}

export interface PolicySource {
  id: string; name: string; url: string; categories: string[]; rssHubPath: string | null;
}

export interface PolicyDashboard {
  schemaVersion: string; generatedAt: string; today: string; events: PolicyEvent[]; sources: PolicySource[];
  summary: { total: number; level3: number; upcoming: number; nextDate: string | null; lifecycle: Record<PolicyLifecycleStage, number> };
  assessment: Array<{ level: 1 | 2 | 3; label: string; definition: string }>;
  collector: {
    foundation: string; revision: string; mode: string; status: string; note: string;
    feeds: Array<{ sourceId: string; status: string; items: number; reason?: string; lastAttemptAt?: string; lastSuccessAt?: string | null }>;
    collectedAt?: string;
  };
}
