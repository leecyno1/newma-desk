export const CREATOR_STAGE_IDS = [
  "intake",
  "brief",
  "draft",
  "transwrite",
  "publish",
  "postmortem",
] as const;

export type CreatorStageId = (typeof CREATOR_STAGE_IDS)[number];
export type CreatorWorkspace = "dashboard" | CreatorStageId | "marketplace" | "settings";

export function isCreatorStage(value: string): value is CreatorStageId {
  return CREATOR_STAGE_IDS.includes(value as CreatorStageId);
}

export interface Identity {
  userId: string;
  workspaceId: string;
}

export interface MaterialRequirement {
  type: string;
  label: string;
  required?: boolean;
  accepts?: string[];
  sources?: string[];
}

export interface CreatorMaterial {
  type: string;
  path: string;
  source?: "manual" | "upstream";
  label?: string;
  artifactId?: string;
  artifactVersion?: number;
  contentDigest?: string;
  sourceRunId?: string;
  sourceStageId?: string;
  sourceNodeId?: string;
  status?: string;
  staleAt?: string;
  staleReason?: string;
}

export interface CreatorArtifact {
  id: string;
  type: string;
  path: string;
  label?: string;
  status: string;
  version?: number;
  contentDigest?: string;
  parents?: Array<{
    artifactId: string;
    version: number;
    contentDigest?: string;
    runId?: string;
    stageId?: string;
    nodeId?: string;
  }>;
  producerJobId?: string;
  parametersDigest?: string;
  editorSessionId?: string;
  executionId?: string;
  supersededByArtifactId?: string;
  staleAt?: string;
  staleReason?: string;
  createdAt: string;
}

export interface CreatorHandoff {
  id: string;
  source: { stageId: string; nodeId: string };
  target: { stageId: string; nodeId: string };
  materials: CreatorMaterial[];
  artifactRefs?: Array<{
    artifactId: string;
    version: number;
    contentDigest?: string;
  }>;
  status: string;
  createdAt: string;
  staleAt?: string;
  staleReason?: string;
  supersededAt?: string;
}

export interface EditorSessionSummary {
  sessionId: string;
  status: string;
  editors: Array<{
    id: string;
    name: string;
    kind: string;
    status: string;
    launchUrl?: string;
    artifactPath?: string;
    reason?: string;
    missing?: string[];
  }>;
  selectedEditorId?: string;
  outputContract: string[];
  outputArtifacts: Array<Record<string, unknown>>;
  launch?: {
    status?: string;
    editorId?: string;
    kind?: string;
    launchUrl?: string;
    artifactPath?: string;
    error?: string;
  };
  createdAt: string;
  updatedAt: string;
}

export interface PublishIssue {
  kind?: string;
  channel?: string;
  slot?: string;
  taskId?: string;
  status?: string;
}

export interface PublishPhaseState {
  status?: string;
  nodeStatus?: string;
  jobId?: string;
  nodeId?: string;
  finishedAt?: string;
  taskCount?: number;
  blockers?: PublishIssue[];
  warnings?: PublishIssue[];
  accountHealth?: {
    summary?: Record<string, number>;
    accounts?: Array<{
      channel?: string;
      slot?: string;
      label?: string;
      status?: string;
    }>;
  };
  succeeded?: number;
  failed?: number;
  receipts?: string;
  verificationCount?: number;
  failures?: PublishIssue[];
  postmortemHandoff?: string;
  report?: string;
  approvedAt?: string;
  reviewMessage?: string;
}

export interface CreatorPublishState {
  schemaVersion: string;
  confirmation?: {
    confirmed?: boolean;
    confirmedAt?: string;
    confirmedBy?: string;
    consumedByJobId?: string | null;
    consumedAt?: string;
  };
  preflight?: PublishPhaseState;
  execution?: PublishPhaseState;
  verification?: PublishPhaseState;
  updatedAt?: string;
}

export interface RegistryNode {
  id: string;
  name: string;
  description?: string;
  material_requirements: MaterialRequirement[];
  outputs: string[];
  actions: string[];
  capabilities: string[];
  executor?: string;
  editors?: string[];
  gate?: Record<string, unknown>;
}

export interface RegistryStage {
  order: number;
  id: string;
  name: string;
  short_label?: string;
  color?: string;
  nodes: RegistryNode[];
  lane_catalog?: Array<{ id: string; name: string; enabled: boolean }>;
}

export interface CreatorRegistry {
  schema_version: string;
  product: { id: string; name: string; namespace: string };
  navigation: Record<string, unknown>;
  stages: RegistryStage[];
}

export interface MaterialValidation {
  status: "ready" | "needs_material";
  missing: MaterialRequirement[];
  bindings: Array<Record<string, unknown>>;
}

export interface SnapshotNode {
  id: string;
  name: string;
  description?: string;
  status: string;
  progress: number;
  gate?: Record<string, unknown>;
  actions: string[];
  capabilities: string[];
  executor?: string;
  editors: string[];
  materialRequirements: MaterialRequirement[];
  materialValidation: MaterialValidation;
  materials: CreatorMaterial[];
  outputs: string[];
  artifacts: CreatorArtifact[];
  feedback: Array<{ id: string; message: string; createdAt: string }>;
  logs: Array<{ at: string; message: string }>;
  parameters: Record<string, unknown>;
  attempt: number;
  availableActions: string[];
  executionRequest?: {
    jobId?: string;
    status: string;
    executorId?: string;
    capabilities: string[];
    requestedAt: string;
    startedAt?: string;
    cancelRequestedAt?: string;
    completedAt?: string;
  };
  executionResult?: {
    jobId?: string;
    executionId?: string;
    executorId?: string;
    status: string;
    adapterStatus?: string;
    exitCode?: number;
    durationMs?: number;
    resultPath?: string;
    error?: string;
    finishedAt: string;
  };
  editorSession?: EditorSessionSummary;
  staleAt?: string;
  staleReason?: string;
}

export interface SnapshotStage {
  order: number;
  id: string;
  name: string;
  shortLabel?: string;
  color?: string;
  status: string;
  progress: number;
  nodes: SnapshotNode[];
  laneCatalog: Array<{ id: string; name: string; enabled: boolean }>;
}

export interface CreatorRunSummary {
  runId: string;
  title: string;
  status: string;
  activeStageId?: string;
  activeNodeId?: string;
  revision: number;
  updatedAt: string;
}

export interface CreatorSnapshot {
  schemaVersion: string;
  generatedAt: string;
  run: CreatorRunSummary & { progress: number; createdAt: string };
  stages: SnapshotStage[];
  graph: {
    nodes: Array<{ id: string; stageId: string; nodeId: string; label: string; status: string }>;
    edges: Array<{ from: string; to: string }>;
  };
  handoffs: CreatorHandoff[];
  lineageState?: {
    lastInvalidatedAt: string;
    reason: string;
    affectedNodes: Array<{ stageId: string; nodeId: string }>;
  };
  publishState?: CreatorPublishState;
  notifications: Array<{
    id: string;
    kind: "review" | "warning" | "artifact";
    title: string;
    stageId: string;
    nodeId: string;
  }>;
  counters: { waitingReview: number; newArtifacts: number; blockedNodes: number };
  lastEventSequence: number;
}

export interface MarketplaceItem {
  id: string;
  kind: "project" | "skill" | "pipeline" | "template";
  name: string;
  summary?: string;
  category?: string;
  categoryLabel?: string;
  subcategory?: string;
  source?: string;
  sourceProjectId?: string;
  localPath?: string;
  version?: string;
  tier?: string;
  license?: string;
  capabilities?: string[];
  capabilityLabels?: string[];
  stages?: string[];
  stageIds?: string[];
  skillIds?: string[];
  useCases?: string[];
  inputs?: string[];
  outputs?: string[];
  aspectRatios?: string[];
  tags?: string[];
  engine?: string;
  executionMode?: string;
  orchestratorSkill?: string;
  directorId?: string;
  technicalNotes?: string;
  preview?: {
    assetPath: string;
    url: string;
    kind: "image" | "video";
    alt: string;
  };
  flow?: Array<{ id: string; name: string; description?: string }>;
  status: {
    discovery: string;
    registration: string;
    installation: string;
    runtime: string;
    compatibility: string;
    label: string;
    tone: "ready" | "warning" | "danger" | "muted";
    reasons: string[];
  };
}

export interface CreatorMarketplace {
  schema_version: string;
  generated_at: string;
  counts: {
    projects: number;
    repositories: number;
    skills: number;
    pipelines: number;
    supportPipelines?: number;
    templates: number;
    ready: number;
  };
  projects: MarketplaceItem[];
  repositories: MarketplaceItem[];
  skills: MarketplaceItem[];
  pipelines: MarketplaceItem[];
  supportPipelines?: MarketplaceItem[];
  templates: MarketplaceItem[];
}

export interface MarketplaceCompatibility {
  schemaVersion: string;
  status: "compatible" | "ready_for_target" | "incompatible";
  canSave: boolean;
  canApply: boolean;
  item: { id: string; kind: MarketplaceItem["kind"]; name: string; version?: string; sourceProjectId?: string };
  target?: { stageId: string; nodeId: string; name: string };
  checks: Array<{ id: string; status: "pass" | "warning" | "fail"; label: string }>;
  recommendedNodes: Array<{ stageId: string; nodeId: string; label: string }>;
  demo: { mode: "preview" | "source" | "flow"; url?: string; available: boolean };
}

export interface MarketplacePreset {
  schemaVersion: string;
  presetId: string;
  version: number;
  name: string;
  itemId: string;
  itemKind: MarketplaceItem["kind"];
  itemVersion?: string;
  sourceProjectId?: string;
  target?: { stageId: string; nodeId: string };
  parameters: Record<string, unknown>;
  compatibility: MarketplaceCompatibility;
  createdAt: string;
  updatedAt: string;
}

export interface CapabilityDetection {
  available_count: number;
  capabilities: Array<{
    id: string;
    name: string;
    mode: string;
    available: boolean;
    version?: string;
    path?: string;
    stages: string[];
  }>;
}
