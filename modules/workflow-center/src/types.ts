export type WorkflowWorkspace = "overview" | "designer" | "runs" | "delegations" | "artifacts" | "audit" | "settings";

export interface Identity {
  userId: string;
  workspaceId: string;
}

export interface Principal {
  id: string;
  organizationId: string;
  kind: "human" | "server_agent";
  name: string;
  role: "owner" | "admin" | "member";
  status: string;
  externalRef?: string | null;
  endpoint?: string | null;
  capabilities: string[];
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowLaneDefinition {
  id: string;
  name: string;
  description: string;
}

export interface WorkflowStageDefinition {
  id: string;
  name: string;
  description: string;
}

export interface WorkflowNodeDefinition {
  id: string;
  name: string;
  description: string;
  roleKey: string;
  kind: "task" | "review" | "gate" | "automation";
  requiresReview: boolean;
  outputs: string[];
  laneId: string;
  stageId: string;
  promotedToMenu: boolean;
}

export interface WorkflowEdge {
  source: string;
  target: string;
}

export interface WorkflowTemplate {
  id: string;
  organizationId: string;
  name: string;
  description: string;
  ownerPrincipalId: string;
  currentVersion: number;
  status: string;
  nodes: WorkflowNodeDefinition[];
  edges: WorkflowEdge[];
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowTemplateVersion {
  templateId: string;
  version: number;
  name: string;
  description: string;
  nodes: WorkflowNodeDefinition[];
  edges: WorkflowEdge[];
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  changeNote: string;
  createdBy: string;
  createdAt: string;
}

export interface WorkflowClaim {
  id: string;
  principalId: string;
  leaseExpiresAt: string;
}

export interface WorkflowNodeRun extends WorkflowNodeDefinition {
  status: string;
  accountablePrincipalId: string;
  reviewerPrincipalId?: string | null;
  claim?: WorkflowClaim | null;
  dataRevision: number;
  artifactCount: number;
  updatedAt: string;
}

export interface WorkflowRun {
  id: string;
  organizationId: string;
  templateId: string;
  templateVersion: number;
  title: string;
  status: string;
  ownerPrincipalId: string;
  nodes: WorkflowNodeRun[];
  edges: WorkflowEdge[];
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowScope {
  type: "organization" | "template" | "run" | "node" | "role";
  templateId?: string;
  runId?: string;
  nodeId?: string;
  roleKey?: string;
}

export interface DelegationGrant {
  id: string;
  organizationId: string;
  delegatorPrincipalId: string;
  delegatePrincipalId: string;
  scope: WorkflowScope;
  actions: string[];
  startsAt: string;
  expiresAt?: string | null;
  allowRedelegate: boolean;
  maxRedelegationDepth: number;
  parentGrantId?: string | null;
  status: string;
  revokedAt?: string | null;
  revokedBy?: string | null;
  createdAt: string;
}

export interface WorkflowEvent {
  sequence: number;
  runId?: string | null;
  type: string;
  actorPrincipalId: string;
  accountablePrincipalId?: string | null;
  delegationGrantId?: string | null;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface WorkflowArtifact {
  id: string;
  runId: string;
  nodeId: string;
  artifactKey: string;
  version: number;
  label: string;
  kind: string;
  uri?: string | null;
  content?: unknown;
  metadata: Record<string, unknown>;
  inputArtifactIds: string[];
  isCurrent: boolean;
  stale: boolean;
  createdBy: string;
  createdAt: string;
}

export interface WorkflowOverview {
  organization: { id: string; name: string; createdAt: string; updatedAt: string };
  currentPrincipal: Principal;
  principals: Principal[];
  templates: WorkflowTemplate[];
  runs: WorkflowRun[];
  grants: DelegationGrant[];
  recentEvents: WorkflowEvent[];
  metrics: {
    templates: number;
    activeRuns: number;
    readyNodes: number;
    waitingReview: number;
    activeGrants: number;
    serverAgents: number;
  };
}

export interface WorkflowRunSnapshot {
  run: WorkflowRun;
  nodeData: Array<{ runId: string; nodeId: string; slotKey: string; version: number; payload: unknown; createdBy: string; createdAt: string }>;
  artifacts: WorkflowArtifact[];
  events: WorkflowEvent[];
}
