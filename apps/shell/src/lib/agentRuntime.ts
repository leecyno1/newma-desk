export type AgentRuntimePreference = "auto" | "newma" | "local";
export type AgentRuntimeMode = "newma" | "local";

export interface AgentRuntimeRequest {
  prompt?: string;
  mode?: "ask" | "edit";
}

export interface AgentRuntimeBinding {
  mode: AgentRuntimeMode;
  request(request: AgentRuntimeRequest): void;
}

export interface AgentRuntimeAdapterCandidate {
  id: string;
  kind?: string;
  available?: boolean;
}

export type AgentRuntimeRouteMode = "research" | "batch" | "edit";

export interface AgentRuntimeRouteCandidate
  extends AgentRuntimeAdapterCandidate {
  capabilities: readonly string[];
}

const RUNTIME_PREFERENCE_KEY = "newma-desk.agent-runtime.v1";

export function loadAgentRuntimePreference(): AgentRuntimePreference {
  try {
    const value = window.localStorage.getItem(RUNTIME_PREFERENCE_KEY);
    if (value === "numa") {
      window.localStorage.setItem(RUNTIME_PREFERENCE_KEY, "newma");
      return "newma";
    }
    return value === "newma" || value === "local" ? value : "auto";
  } catch {
    return "auto";
  }
}

export function saveAgentRuntimePreference(
  preference: AgentRuntimePreference,
): void {
  try {
    window.localStorage.setItem(RUNTIME_PREFERENCE_KEY, preference);
  } catch {
    // Runtime selection still applies for the current page when storage is blocked.
  }
}

export function adapterRuntimeLabel(
  adapter: AgentRuntimeAdapterCandidate,
): string {
  if (adapter.kind === "agent-gateway") return "Newma / Hermes Runtime";
  if (adapter.kind === "local-cli") return "本地 Agent CLI";
  return "Desk Gateway";
}

export function adapterMatchesRuntimePreference(
  adapter: AgentRuntimeAdapterCandidate,
  preference: AgentRuntimePreference,
): boolean {
  if (preference === "newma") return adapter.kind === "agent-gateway";
  if (preference === "local") return adapter.kind === "local-cli";
  return true;
}

export function preferredAdapterForRuntime<T extends AgentRuntimeAdapterCandidate>(
  adapters: T[],
  preference: AgentRuntimePreference,
  currentId?: string,
): T | undefined {
  const candidates = adapters.filter(
    (adapter) =>
      adapter.available !== false &&
      adapterMatchesRuntimePreference(adapter, preference),
  );
  return (
    candidates.find((adapter) => adapter.id === currentId) ??
    candidates[0] ??
    adapters.find(
      (adapter) =>
        adapter.id === currentId &&
        adapterMatchesRuntimePreference(adapter, preference),
    ) ??
    adapters.find((adapter) =>
      adapterMatchesRuntimePreference(adapter, preference),
    )
  );
}

const ROUTE_CAPABILITY: Record<AgentRuntimeRouteMode, string> = {
  research: "module.explain",
  batch: "module.analyze",
  edit: "module.edit",
};

/**
 * Selects the concrete Adapter for one Copilot route.
 *
 * Runtime ownership is applied before saved preferences so an old module or
 * profile override can never escape the selected Agent Runtime Seam.
 */
export function routeAgentAdapter<T extends AgentRuntimeRouteCandidate>(
  adapters: readonly T[],
  input: {
    mode: AgentRuntimeRouteMode;
    preference: AgentRuntimePreference;
    preferredId?: string;
  },
): T | undefined {
  const capability = ROUTE_CAPABILITY[input.mode];
  const candidates = adapters.filter(
    (adapter) =>
      adapter.available !== false &&
      adapter.capabilities.includes(capability) &&
      adapterMatchesRuntimePreference(adapter, input.preference),
  );
  const preferred = candidates.find(
    (adapter) => adapter.id === input.preferredId,
  );
  if (preferred) return preferred;

  const preferredKind =
    input.preference === "newma"
      ? "agent-gateway"
      : input.preference === "local"
        ? "local-cli"
        : input.mode === "research"
          ? "agent-gateway"
          : "local-cli";
  return (
    candidates.find((adapter) => adapter.kind === preferredKind) ??
    candidates[0]
  );
}
