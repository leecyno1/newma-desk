import { waitForVibeDeskConfig } from "@/lib/vibedesk";

export type ArtifactNodeKind =
  | "source"
  | "material"
  | "component"
  | "infrastructure"
  | "market"
  | "company"
  | "risk"
  | "external";

export interface GraphArtifactNode {
  id: string;
  label: string;
  subtitle?: string;
  kind?: ArtifactNodeKind;
  group?: string;
}

export interface GraphArtifactEdge {
  source: string;
  target: string;
  label?: string;
  kind?: "flow" | "dependency" | "supply" | "risk";
}

export interface GraphArtifactInput {
  moduleId: string;
  title: string;
  subtitle?: string;
  nodes: GraphArtifactNode[];
  edges: GraphArtifactEdge[];
  sourceText?: string;
  sources?: string[];
  metadata?: Record<string, unknown>;
}

export interface ModArtifactRecord {
  id: string;
  moduleId: string;
  kind: "graph";
  renderer: "archify";
  title: string;
  status: "draft" | "published";
  createdAt: string;
  updatedAt: string;
  viewUrl: string;
  spec: GraphArtifactInput;
  archifyIr: Record<string, unknown>;
}

function absoluteViewUrl(record: ModArtifactRecord, gatewayOrigin: string): ModArtifactRecord {
  return {
    ...record,
    viewUrl: new URL(record.viewUrl, gatewayOrigin).toString(),
  };
}

export async function createGraphArtifact(
  input: GraphArtifactInput,
): Promise<ModArtifactRecord> {
  const config = await waitForVibeDeskConfig();
  if (!config) throw new Error("图谱固化需要从 VibeDesk 中打开当前 Mod");
  const response = await fetch(`${config.gatewayOrigin}/api/artifacts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": config.userId,
    },
    body: JSON.stringify({ ...input, moduleId: config.moduleId }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `图谱生成失败（HTTP ${response.status}）`);
  return absoluteViewUrl(body as ModArtifactRecord, config.gatewayOrigin);
}

export async function loadLatestGraphArtifact(): Promise<ModArtifactRecord | null> {
  const config = await waitForVibeDeskConfig();
  if (!config) return null;
  const query = new URLSearchParams({ module_id: config.moduleId });
  const response = await fetch(`${config.gatewayOrigin}/api/artifacts/latest?${query}`, {
    headers: { "X-User-Id": config.userId },
  });
  if (response.status === 404) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `读取图谱失败（HTTP ${response.status}）`);
  return absoluteViewUrl(body as ModArtifactRecord, config.gatewayOrigin);
}

export async function listGraphArtifacts(): Promise<ModArtifactRecord[]> {
  const config = await waitForVibeDeskConfig();
  if (!config) return [];
  const query = new URLSearchParams({ module_id: config.moduleId });
  const response = await fetch(`${config.gatewayOrigin}/api/artifacts?${query}`, {
    headers: { "X-User-Id": config.userId },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `读取图谱列表失败（HTTP ${response.status}）`);
  return (body as ModArtifactRecord[]).map((record) =>
    absoluteViewUrl(record, config.gatewayOrigin));
}

export async function publishGraphArtifact(
  artifact: ModArtifactRecord,
): Promise<ModArtifactRecord> {
  const config = await waitForVibeDeskConfig();
  if (!config) throw new Error("图谱发布需要从 VibeDesk 中打开当前 Mod");
  const response = await fetch(
    `${config.gatewayOrigin}/api/artifacts/${artifact.id}/publish`,
    {
      method: "POST",
      headers: { "X-User-Id": config.userId },
    },
  );
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `图谱发布失败（HTTP ${response.status}）`);
  return absoluteViewUrl(body as ModArtifactRecord, config.gatewayOrigin);
}
