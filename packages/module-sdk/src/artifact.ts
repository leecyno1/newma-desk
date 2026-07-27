import {
  normalizeGatewayBaseUrl,
  requestGatewayJson,
  type GatewayClientConfig,
} from "./agent";


export type GraphNodeKind =
  | "source"
  | "material"
  | "component"
  | "infrastructure"
  | "market"
  | "company"
  | "risk"
  | "external";


export interface GraphArtifactInput {
  moduleId: string;
  title: string;
  subtitle?: string;
  nodes: Array<{
    id: string;
    label: string;
    subtitle?: string;
    kind?: GraphNodeKind;
    group?: string;
  }>;
  edges: Array<{
    source: string;
    target: string;
    label?: string;
    kind?: "flow" | "dependency" | "supply" | "risk";
  }>;
  sourceText?: string;
  sources?: string[];
  metadata?: Record<string, unknown>;
}


export interface GraphArtifactRecord {
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

export interface ReplayArtifactInput {
  moduleId: string;
  title: string;
  security: {
    symbol: string;
    name: string;
    market: "CN" | "HK" | "US";
    exchange?: string;
  };
  timeframe: "1m" | "5m" | "15m" | "30m" | "60m" | "1d" | "1w" | "1M";
  cursor: number;
  totalBars: number;
  replayTimestamp?: number;
  orders: Array<{
    id: string;
    side: "buy" | "sell";
    index: number;
    timestamp: number;
    price: number;
  }>;
  metrics?: Record<string, unknown>;
  notes?: string;
  metadata?: Record<string, unknown>;
}

export interface ReplayArtifactRecord {
  id: string;
  moduleId: string;
  kind: "replay";
  renderer: "replay-html";
  title: string;
  status: "draft" | "published";
  createdAt: string;
  updatedAt: string;
  viewUrl: string;
  spec: ReplayArtifactInput;
}


export interface ArtifactClient {
  createGraph(input: GraphArtifactInput): Promise<GraphArtifactRecord>;
  listGraphs(moduleId: string, status?: "draft" | "published"): Promise<GraphArtifactRecord[]>;
  latestGraph(moduleId: string, status?: "draft" | "published"): Promise<GraphArtifactRecord>;
  publish(artifactId: string): Promise<GraphArtifactRecord>;
  createReplay(input: ReplayArtifactInput): Promise<ReplayArtifactRecord>;
  listReplays(moduleId: string, status?: "draft" | "published"): Promise<ReplayArtifactRecord[]>;
  latestReplay(moduleId: string, status?: "draft" | "published"): Promise<ReplayArtifactRecord>;
  publishReplay(artifactId: string): Promise<ReplayArtifactRecord>;
  viewUrl(artifact: Pick<GraphArtifactRecord | ReplayArtifactRecord, "viewUrl">): string;
}


function resourceId(value: string): string {
  if (!value) throw new Error("Artifact resource ID cannot be empty");
  return encodeURIComponent(value);
}


export function createArtifactClient(config: GatewayClientConfig): ArtifactClient {
  const baseUrl = normalizeGatewayBaseUrl(config.baseUrl);
  const fetcher = config.fetch ?? globalThis.fetch.bind(globalThis);

  const withStatus = (moduleId: string, status?: "draft" | "published") => {
    const query = new URLSearchParams({ module_id: moduleId });
    if (status) query.set("status", status);
    return query.toString();
  };

  return {
    createGraph(input) {
      return requestGatewayJson<GraphArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    listGraphs(moduleId, status) {
      return requestGatewayJson<GraphArtifactRecord[]>(
        fetcher,
        `${baseUrl}/api/artifacts?${withStatus(moduleId, status)}`,
      );
    },
    latestGraph(moduleId, status) {
      return requestGatewayJson<GraphArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts/latest?${withStatus(moduleId, status)}`,
      );
    },
    publish(artifactId) {
      return requestGatewayJson<GraphArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts/${resourceId(artifactId)}/publish`,
        { method: "POST" },
      );
    },
    createReplay(input) {
      return requestGatewayJson<ReplayArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts/replays`,
        { method: "POST", body: JSON.stringify(input) },
      );
    },
    listReplays(moduleId, status) {
      return requestGatewayJson<ReplayArtifactRecord[]>(
        fetcher,
        `${baseUrl}/api/artifacts/replays?${withStatus(moduleId, status)}`,
      );
    },
    latestReplay(moduleId, status) {
      return requestGatewayJson<ReplayArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts/replays/latest?${withStatus(moduleId, status)}`,
      );
    },
    publishReplay(artifactId) {
      return requestGatewayJson<ReplayArtifactRecord>(
        fetcher,
        `${baseUrl}/api/artifacts/replays/${resourceId(artifactId)}/publish`,
        { method: "POST" },
      );
    },
    viewUrl(artifact) {
      return new URL(artifact.viewUrl, baseUrl).toString();
    },
  };
}
