import type {
  DelegationGrant,
  Identity,
  Principal,
  WorkflowArtifact,
  WorkflowEvent,
  WorkflowNodeDefinition,
  WorkflowLaneDefinition,
  WorkflowOverview,
  WorkflowRun,
  WorkflowRunSnapshot,
  WorkflowScope,
  WorkflowStageDefinition,
  WorkflowTemplate,
  WorkflowTemplateVersion,
} from "./types";

async function payload<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : body?.detail?.message || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

function requestHeaders(identity: Identity, actingPrincipalId: string, json = false) {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    "X-User-Id": identity.userId,
    "X-Workspace-Id": identity.workspaceId,
    ...(actingPrincipalId ? { "X-Workflow-Principal-Id": actingPrincipalId } : {}),
  };
}

export function workflowClient(identity: Identity, actingPrincipalId: string) {
  const headers = (json = false) => requestHeaders(identity, actingPrincipalId, json);
  const json = (method: string, body: unknown) => ({ method, headers: headers(true), body: JSON.stringify(body) });
  return {
    overview: async () => payload<WorkflowOverview>(await fetch("/api/workflows/overview", { headers: headers() })),
    run: async (runId: string) => payload<WorkflowRunSnapshot>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}`, { headers: headers() })),
    createPrincipal: async (input: { kind: "human" | "server_agent"; name: string; role: string; endpoint?: string; externalRef?: string; capabilities?: string[] }) => payload<Principal>(await fetch("/api/workflows/principals", json("POST", input))),
    createTemplate: async (input: { name: string; description: string; nodes: WorkflowNodeDefinition[]; edges: Array<{ source: string; target: string }>; lanes: WorkflowLaneDefinition[]; stages: WorkflowStageDefinition[] }) => payload<WorkflowTemplate>(await fetch("/api/workflows/templates", json("POST", input))),
    createTemplateVersion: async (templateId: string, input: { name: string; description: string; nodes: WorkflowNodeDefinition[]; edges: Array<{ source: string; target: string }>; lanes: WorkflowLaneDefinition[]; stages: WorkflowStageDefinition[]; expectedVersion: number; changeNote: string }) => payload<WorkflowTemplate>(await fetch(`/api/workflows/templates/${encodeURIComponent(templateId)}/versions`, json("POST", input))),
    templateVersions: async (templateId: string) => payload<{ versions: WorkflowTemplateVersion[] }>(await fetch(`/api/workflows/templates/${encodeURIComponent(templateId)}/versions`, { headers: headers() })),
    restoreTemplateVersion: async (templateId: string, sourceVersion: number, expectedVersion: number, changeNote: string) => payload<WorkflowTemplate>(await fetch(`/api/workflows/templates/${encodeURIComponent(templateId)}/versions/${sourceVersion}/restore`, json("POST", { expectedVersion, changeNote }))),
    createRun: async (input: { templateId: string; title: string; assignments: Record<string, string>; reviewers: Record<string, string>; roleAssignments?: Record<string, string> }) => payload<WorkflowRun>(await fetch("/api/workflows/runs", json("POST", input))),
    claimNode: async (runId: string, nodeId: string, expectedRevision: number) => payload<WorkflowRun>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/claim`, json("POST", { expectedRevision, leaseSeconds: 900 }))),
    releaseNode: async (runId: string, nodeId: string, expectedRevision: number) => payload<WorkflowRun>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/release`, json("POST", { expectedRevision }))),
    submitNode: async (runId: string, nodeId: string, expectedRevision: number, note = "") => payload<WorkflowRun>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/submit`, json("POST", { expectedRevision, note }))),
    reviewNode: async (runId: string, nodeId: string, expectedRevision: number, decision: "approve" | "request_changes", note = "") => payload<WorkflowRun>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/review`, json("POST", { expectedRevision, decision, note }))),
    saveNodeData: async (runId: string, nodeId: string, expectedRevision: number, slotKey: string, data: unknown) => payload<{ run: WorkflowRun }>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/data`, json("POST", { expectedRevision, slotKey, payload: data }))),
    saveArtifact: async (runId: string, nodeId: string, input: { expectedRevision: number; artifactKey: string; label: string; kind: string; uri?: string; content?: unknown; inputArtifactIds?: string[] }) => payload<{ run: WorkflowRun; artifact: WorkflowArtifact; staleNodeIds: string[] }>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/artifacts`, json("POST", input))),
    assignNode: async (runId: string, nodeId: string, input: { expectedRevision: number; accountablePrincipalId: string; reviewerPrincipalId?: string | null }) => payload<WorkflowRun>(await fetch(`/api/workflows/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}/assignment`, json("PUT", input))),
    createGrant: async (input: { delegatePrincipalId: string; scope: WorkflowScope; actions: string[]; allowRedelegate: boolean; maxRedelegationDepth: number; expiresAt?: string }) => payload<DelegationGrant>(await fetch("/api/workflows/grants", json("POST", input))),
    revokeGrant: async (grantId: string) => payload<{ grantId: string; revokedGrantIds: string[] }>(await fetch(`/api/workflows/grants/${encodeURIComponent(grantId)}`, { method: "DELETE", headers: headers() })),
    artifacts: async () => payload<{ artifacts: WorkflowArtifact[] }>(await fetch("/api/workflows/artifacts", { headers: headers() })),
    events: async () => payload<{ events: WorkflowEvent[] }>(await fetch("/api/workflows/events?limit=500", { headers: headers() })),
  };
}
