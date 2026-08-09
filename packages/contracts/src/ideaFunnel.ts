import { z } from "zod";

export const ideaStageSchema = z.enum([
  "inbox",
  "triage",
  "shortlist",
  "deep-dive",
  "handoff",
  "deferred",
  "closed",
]);

export const ideaPrioritySchema = z.enum(["high", "medium", "low"]);
export const ideaResearchStyleSchema = z.enum([
  "value",
  "growth",
  "quality",
  "event",
  "special-situation",
  "risk",
  "other",
]);

const sourceReferenceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.enum(["market", "filing", "company", "consensus", "research", "news", "derived", "user"]),
  asOf: z.string().min(1),
  status: z.enum(["verified", "available", "stale", "unavailable"]),
  url: z.string().url().optional(),
}).strict();

const artifactReferenceSchema = z.object({
  id: z.string().min(1),
  sourceModId: z.string().min(1),
  artifactId: z.string().min(1),
  title: z.string().min(1),
  asOf: z.string().min(1).optional(),
  status: z.enum(["linked", "stale", "missing"]),
}).strict();

const screenRuleSchema = z.object({
  id: z.string().min(1),
  metric: z.string().min(1),
  operator: z.enum(["gt", "gte", "lt", "lte", "eq", "between", "trend"]),
  value: z.string().min(1),
  rationale: z.string().min(1),
}).strict();

const screenMetricSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  value: z.string().min(1),
  peerReference: z.string(),
  asOf: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(20),
}).strict();

const ideaSignalSchema = z.object({
  id: z.string().min(1),
  type: z.enum(["quantitative", "thematic", "quality", "catalyst", "risk", "pattern"]),
  direction: z.enum(["supports", "challenges", "neutral"]),
  summary: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(20),
}).strict();

const scorecardSchema = z.object({
  relevance: z.number().min(0).max(100),
  evidenceQuality: z.number().min(0).max(100),
  novelty: z.number().min(0).max(100),
  catalystClarity: z.number().min(0).max(100),
  falsifiability: z.number().min(0).max(100),
  researchEffort: z.number().min(0).max(100),
  total: z.number().min(0).max(100),
}).strict();

const ideaCatalystSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  window: z.string().min(1),
  confirmationCondition: z.string().min(1),
  invalidationCondition: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(20),
}).strict();

const ideaRiskSchema = z.object({
  id: z.string().min(1),
  statement: z.string().min(1),
  earlyWarning: z.string().min(1),
  falsificationCondition: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(20),
}).strict();

const nextActionSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["data-check", "filing", "model", "peer", "industry", "catalyst", "expert", "other"]),
  label: z.string().min(1),
  status: z.enum(["pending", "done", "skipped"]),
  dueAt: z.string().date().optional(),
  completionStandard: z.string().min(1),
}).strict();

export const researchIdeaSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  security: z.object({
    market: z.string().min(1),
    symbol: z.string().min(1),
    name: z.string().min(1),
    currency: z.string().min(1),
  }).strict(),
  stage: ideaStageSchema,
  priority: ideaPrioritySchema,
  researchStyle: ideaResearchStyleSchema,
  origin: z.object({
    type: z.enum(["screener", "theme", "news", "catalyst", "industry", "watchlist", "agent", "manual"]),
    label: z.string().min(1),
    sourceModId: z.string().min(1).optional(),
    artifactId: z.string().min(1).optional(),
    asOf: z.string().min(1),
    discoveredAt: z.string().datetime(),
  }).strict(),
  searchCriteria: z.object({
    markets: z.array(z.string().min(1)).max(20),
    sectors: z.array(z.string().min(1)).max(30),
    styles: z.array(ideaResearchStyleSchema).max(10),
    themes: z.array(z.string().min(1)).max(30),
    marketCapRange: z.string(),
    rules: z.array(screenRuleSchema).max(30),
  }).strict(),
  researchQuestion: z.string().min(1),
  initialHypothesis: z.string().min(1),
  opposingHypothesis: z.string().min(1),
  whyNow: z.string().min(1),
  marketMayMiss: z.string().min(1),
  metrics: z.array(screenMetricSchema).max(30),
  signals: z.array(ideaSignalSchema).min(2).max(30),
  scorecard: scorecardSchema,
  catalysts: z.array(ideaCatalystSchema).max(20),
  risks: z.array(ideaRiskSchema).min(1).max(20),
  linkedArtifacts: z.array(artifactReferenceSchema).max(40),
  sources: z.array(sourceReferenceSchema).max(100),
  gaps: z.array(z.string().min(1)).max(30),
  nextActions: z.array(nextActionSchema).min(1).max(30),
  handoff: z.object({
    targetModId: z.enum([
      "thesis-tracker",
      "earnings-workbench",
      "peer-comparison",
      "valuation-workbench",
      "research-memo",
      "other",
    ]),
    status: z.enum(["none", "ready", "created"]),
    artifactId: z.string().min(1).optional(),
    note: z.string(),
  }).strict(),
  reviewLog: z.array(z.object({
    id: z.string().min(1),
    createdAt: z.string().datetime(),
    stage: ideaStageSchema,
    summary: z.string().min(1),
  }).strict()).max(100),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict();

export const ideaFunnelWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.idea-funnel.v1"),
  updatedAt: z.string().datetime(),
  ideas: z.array(researchIdeaSchema).max(300),
}).strict();

export type IdeaStage = z.infer<typeof ideaStageSchema>;
export type IdeaPriority = z.infer<typeof ideaPrioritySchema>;
export type IdeaResearchStyle = z.infer<typeof ideaResearchStyleSchema>;
export type ResearchIdea = z.infer<typeof researchIdeaSchema>;
export type IdeaFunnelWorkspace = z.infer<typeof ideaFunnelWorkspaceSchema>;
