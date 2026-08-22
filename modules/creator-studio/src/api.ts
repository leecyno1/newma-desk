import type {
  CapabilityDetection,
  CreatorMarketplace,
  CreatorMaterial,
  CreatorRegistry,
  CreatorRunSummary,
  CreatorSnapshot,
  Identity,
  MarketplaceCompatibility,
  MarketplaceItem,
  MarketplacePreset,
} from "./types";

export interface DeskAgentPreferences {
  userId: string;
  defaultAdapter: string;
  moduleOverrides: Record<string, string>;
  profileTargets: Record<string, string>;
  moduleProfileOverrides: Record<string, Record<string, string>>;
  updatedAt: string | null;
}

function headers(identity?: Identity, json = false) {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(identity ? {
      "X-User-Id": identity.userId,
      "X-Workspace-Id": identity.workspaceId,
    } : {}),
  };
}

async function payload<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body?.detail === "string"
      ? body.detail
      : body?.detail?.message || body?.error?.message || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export function creatorClient(identity: Identity) {
  return {
    registry: async () => payload<CreatorRegistry>(await fetch("/api/creator-studio/registry")),
    system: async () => payload<Record<string, unknown>>(await fetch("/api/creator-studio/system")),
    agentPreferences: async () => payload<DeskAgentPreferences>(await fetch(
      "/api/agent/preferences",
      { headers: headers(identity) },
    )),
    saveAgentPreferences: async (preferences: Omit<DeskAgentPreferences, "userId" | "updatedAt">) => payload<DeskAgentPreferences>(await fetch(
      "/api/agent/preferences",
      {
        method: "PUT",
        headers: headers(identity, true),
        body: JSON.stringify(preferences),
      },
    )),
    runs: async () => payload<{ runs: CreatorRunSummary[] }>(await fetch(
      "/api/creator-studio/runs",
      { headers: headers(identity) },
    )),
    run: async (runId: string) => payload<CreatorSnapshot>(await fetch(
      `/api/creator-studio/runs/${encodeURIComponent(runId)}`,
      { headers: headers(identity) },
    )),
    createRun: async (input: {
      title: string;
      stageId: string;
      nodeId: string;
      materials: CreatorMaterial[];
    }) => payload<CreatorSnapshot>(await fetch("/api/creator-studio/runs", {
      method: "POST",
      headers: headers(identity, true),
      body: JSON.stringify(input),
    })),
    command: async (runId: string, input: {
      actionId: string;
      stageId?: string;
      nodeId?: string;
      input?: Record<string, unknown>;
      expectedRevision?: number;
    }) => {
      // Auto-inject user's selected agent from localStorage into command input
      const selectedAgent = typeof window !== "undefined"
        ? (localStorage.getItem("newma.creator-studio.selected-agent") || "").trim()
        : "";
      const agentBin = typeof window !== "undefined"
        ? (localStorage.getItem("newma.creator-studio.agent-bin-override") || "").trim()
        : "";
      const enrichedInput = {
        ...input,
        input: {
          ...(input.input || {}),
          ...(selectedAgent ? { agent_cli: selectedAgent } : {}),
          ...(agentBin ? { agent_cli_bin: agentBin } : {}),
        },
      };
      return payload<CreatorSnapshot>(await fetch(
        `/api/creator-studio/runs/${encodeURIComponent(runId)}/commands`,
        {
          method: "POST",
          headers: headers(identity, true),
          body: JSON.stringify(enrichedInput),
        },
      ));
    },
    events: async (runId: string, after: number) => payload<{
      events: Array<Record<string, unknown>>;
      lastSequence: number;
    }>(await fetch(
      `/api/creator-studio/runs/${encodeURIComponent(runId)}/events?after=${after}`,
      { headers: headers(identity) },
    )),
    marketplace: async () => payload<CreatorMarketplace>(await fetch("/api/creator-studio/marketplace")),
    marketplaceCompatibility: async (input: {
      itemId: string;
      itemKind: MarketplaceItem["kind"];
      stageId?: string;
      nodeId?: string;
    }) => payload<MarketplaceCompatibility>(await fetch("/api/creator-studio/marketplace/compatibility", {
      method: "POST",
      headers: headers(identity, true),
      body: JSON.stringify(input),
    })),
    marketplacePresets: async () => payload<{ presets: MarketplacePreset[] }>(await fetch(
      "/api/creator-studio/marketplace/presets",
      { headers: headers(identity) },
    )),
    saveMarketplacePreset: async (input: {
      name: string;
      itemId: string;
      itemKind: MarketplaceItem["kind"];
      stageId?: string;
      nodeId?: string;
      parameters?: Record<string, unknown>;
    }) => payload<MarketplacePreset>(await fetch("/api/creator-studio/marketplace/presets", {
      method: "POST",
      headers: headers(identity, true),
      body: JSON.stringify(input),
    })),
    marketplacePresetVersions: async (presetId: string) => payload<{
      presetId: string;
      versions: MarketplacePreset[];
    }>(await fetch(
      `/api/creator-studio/marketplace/presets/${encodeURIComponent(presetId)}/versions`,
      { headers: headers(identity) },
    )),
    updateMarketplacePreset: async (presetId: string, input: {
      name: string;
      stageId?: string;
      nodeId?: string;
      parameters: Record<string, unknown>;
      expectedVersion: number;
    }) => payload<MarketplacePreset>(await fetch(
      `/api/creator-studio/marketplace/presets/${encodeURIComponent(presetId)}`,
      {
        method: "PUT",
        headers: headers(identity, true),
        body: JSON.stringify(input),
      },
    )),
    detectCapabilities: async () => payload<CapabilityDetection>(await fetch(
      "/api/creator-studio/capabilities/detect",
      { method: "POST" },
    )),
    testAgent: async (agentId: string, binOverride?: string) => payload<{
      status: string;
      agent_id: string;
      stdout?: string;
      stderr?: string;
      exit_code?: number;
      duration_ms?: number;
    }>(await fetch("/api/creator-studio/capabilities/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agentId, binOverride: binOverride || "" }),
    })),
    previewArtifact: async (path: string) => payload<{
      path: string;
      exists: boolean;
      mime?: string;
      encoding?: string;
      content?: string;
      entries?: Array<{ name: string; is_dir: boolean; size: number }>;
      size?: number;
      truncated?: boolean;
      suffix?: string;
      hint?: string;
      error?: string;
    }>(await fetch(
      `/api/creator-studio/artifacts/preview?path=${encodeURIComponent(path)}`,
      { headers: headers(identity) },
    )),
  };
}
