export const NUMA_HANDOFF_PROTOCOL = "newma-desk.v1";

// v0.1 continuity contract for a trusted Desk ↔ Numa deployment. Session
// identifiers stay in URL fragments so they are not sent in HTTP requests or
// referrers. Public deployments should replace them with short-lived,
// single-use handoff tokens issued by a shared backend.

export type ModCopilotSessionStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "handed-off";

export interface ModCopilotSessionMetadata {
  schemaVersion: 1;
  moduleId: string;
  moduleName: string;
  workspaceId: string;
  projectId?: string;
  mode: "ask" | "edit";
  status: ModCopilotSessionStatus;
  updatedAt: string;
  taskId?: string;
  adapterId?: string;
  upstreamSessionId?: string;
  deskReturnUrl?: string;
  lastPrompt?: string;
}

interface DeskReturnUrlInput {
  deskUrl: string;
  moduleId: string;
  projectId?: string;
  workspaceId: string;
  upstreamSessionId: string;
}

interface NumaHandoffUrlInput extends DeskReturnUrlInput {
  numaAgentUrl?: string;
  numaAllowedOrigins?: readonly string[];
  deskReturnUrl?: string;
}

export interface DeskReturnHandoff {
  moduleId: string;
  projectId: string;
  workspaceId: string;
  upstreamSessionId: string;
}

export interface NumaHandoffPayload extends DeskReturnHandoff {
  protocol: typeof NUMA_HANDOFF_PROTOCOL;
  source: "newma-desk";
  returnTo: string;
}

const SESSION_STORAGE_PREFIX = "newma-desk.mod-copilot.session.v1";
const HANDOFF_FRAGMENT_KEY = "newma-handoff";
const SESSION_STATUSES = new Set<ModCopilotSessionStatus>([
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
  "handed-off",
]);

function boundedString(value: unknown, maxLength: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > maxLength) return undefined;
  return trimmed;
}

function handoffIdentifier(value: unknown): string | undefined {
  const candidate = boundedString(value, 128);
  return candidate && /^[a-z][a-z0-9-]{1,127}$/.test(candidate)
    ? candidate
    : undefined;
}

function httpUrl(value: unknown, base?: string): URL | undefined {
  const candidate = boundedString(value, 4096);
  if (!candidate) return undefined;
  try {
    const parsed = new URL(candidate, base);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password
    ) {
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

function writeFragmentPayload(
  url: URL,
  payload: Record<string, string>,
): void {
  const encoded = encodeURIComponent(JSON.stringify(payload));
  const existing = url.hash.slice(1);
  const entry = `${HANDOFF_FRAGMENT_KEY}=${encoded}`;
  if (!existing) {
    url.hash = entry;
    return;
  }
  const existingPattern = new RegExp(
    `(^|[?&])${HANDOFF_FRAGMENT_KEY}=[^&]*`,
  );
  if (existingPattern.test(existing)) {
    url.hash = existing.replace(
      existingPattern,
      (_matched, prefix: string) => `${prefix}${entry}`,
    );
    return;
  }
  const separator = existing.includes("?") ? "&" : "?";
  url.hash = `${existing}${separator}${entry}`;
}

function readFragmentPayload(url: URL): Record<string, unknown> | undefined {
  const match = url.hash
    .slice(1)
    .match(new RegExp(`(?:^|[?&])${HANDOFF_FRAGMENT_KEY}=([^&]+)`));
  if (!match?.[1]) return undefined;
  try {
    const value = JSON.parse(decodeURIComponent(match[1])) as unknown;
    return typeof value === "object" && value !== null
      ? (value as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

function browserStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function stringList(value: unknown): string[] {
  const rows = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(",")
      : [];
  return rows
    .map((item) => boundedString(item, 4096))
    .filter((item): item is string => Boolean(item));
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  if (
    normalized === "localhost" ||
    normalized.endsWith(".localhost") ||
    normalized === "::1" ||
    normalized === "[::1]"
  ) {
    return true;
  }
  const octets = normalized.split(".");
  return (
    octets.length === 4 &&
    octets[0] === "127" &&
    octets.every((octet) => /^\d{1,3}$/.test(octet) && Number(octet) <= 255)
  );
}

function runtimeNumaUrl(): string | undefined {
  const runtime = globalThis as typeof globalThis & {
    __NEWMA_DESK_CONFIG__?: {
      numaAgentUrl?: unknown;
      numaAllowedOrigins?: unknown;
    };
  };
  const configured = boundedString(
    runtime.__NEWMA_DESK_CONFIG__?.numaAgentUrl,
    4096,
  );
  if (configured) return configured;

  if (typeof document !== "undefined") {
    const meta = document
      .querySelector('meta[name="newma-desk:numa-agent-url"]')
      ?.getAttribute("content");
    const metaUrl = boundedString(meta, 4096);
    if (metaUrl) return metaUrl;
  }

  return (
    boundedString(import.meta.env.VITE_NUMA_AGENT_URL, 4096) ??
    boundedString(import.meta.env.VITE_NUMA_URL, 4096)
  );
}

function runtimeNumaAllowedOrigins(): string[] {
  const runtime = globalThis as typeof globalThis & {
    __NEWMA_DESK_CONFIG__?: { numaAllowedOrigins?: unknown };
  };
  const runtimeOrigins = stringList(
    runtime.__NEWMA_DESK_CONFIG__?.numaAllowedOrigins,
  );
  if (runtimeOrigins.length) return runtimeOrigins;

  if (typeof document !== "undefined") {
    const metaOrigins = stringList(
      document
        .querySelector('meta[name="newma-desk:numa-allowed-origins"]')
        ?.getAttribute("content"),
    );
    if (metaOrigins.length) return metaOrigins;
  }

  return stringList(
    import.meta.env.VITE_NUMA_ALLOWED_ORIGINS ??
      import.meta.env.VITE_NUMA_AGENT_ALLOWED_ORIGINS,
  );
}

function isAllowedNumaOrigin(
  target: URL,
  desk: URL,
  configuredOrigins: readonly string[],
): boolean {
  if (target.origin === desk.origin) return true;
  if (
    isLoopbackHostname(desk.hostname) &&
    isLoopbackHostname(target.hostname)
  ) {
    return true;
  }
  return configuredOrigins.some((candidate) => {
    const allowed = httpUrl(candidate, desk.toString());
    return allowed?.origin === target.origin;
  });
}

export function resolveNumaAgentUrl(
  explicitUrl?: string,
  browserUrl = typeof window === "undefined" ? undefined : window.location.href,
  explicitAllowedOrigins?: readonly string[],
): string | undefined {
  const desk = httpUrl(browserUrl);
  if (!desk) return undefined;
  const raw = boundedString(explicitUrl, 4096) ?? runtimeNumaUrl();
  const parsed = httpUrl(raw, desk.toString());
  if (
    !parsed ||
    !isAllowedNumaOrigin(
      parsed,
      desk,
      explicitAllowedOrigins ?? runtimeNumaAllowedOrigins(),
    )
  ) {
    return undefined;
  }
  return parsed.toString();
}

export function buildDeskReturnUrl({
  deskUrl,
  moduleId,
  projectId,
  workspaceId,
  upstreamSessionId,
}: DeskReturnUrlInput): string | undefined {
  const parsed = httpUrl(deskUrl);
  const mod = handoffIdentifier(moduleId);
  const project = handoffIdentifier(projectId) ?? mod;
  const workspace = boundedString(workspaceId, 256);
  const session = boundedString(upstreamSessionId, 1024);
  if (!parsed || !mod || !project || !workspace || !session) return undefined;

  parsed.search = "";
  parsed.searchParams.set("mod", mod);
  parsed.searchParams.set("copilot", "1");
  writeFragmentPayload(parsed, {
    protocol: NUMA_HANDOFF_PROTOCOL,
    source: "numa-agent",
    moduleId: mod,
    projectId: project,
    workspaceId: workspace,
    upstreamSessionId: session,
  });
  return parsed.toString();
}

export function buildNumaHandoffUrl({
  numaAgentUrl,
  numaAllowedOrigins,
  deskUrl,
  deskReturnUrl,
  moduleId,
  projectId,
  workspaceId,
  upstreamSessionId,
}: NumaHandoffUrlInput): string | undefined {
  const desk = httpUrl(deskUrl);
  if (!desk) return undefined;
  const configured = resolveNumaAgentUrl(
    numaAgentUrl,
    desk.toString(),
    numaAllowedOrigins,
  );
  const numa = httpUrl(configured);
  const mod = handoffIdentifier(moduleId);
  const project = handoffIdentifier(projectId) ?? mod;
  const workspace = boundedString(workspaceId, 256);
  const session = boundedString(upstreamSessionId, 1024);
  const returnCandidate = httpUrl(deskReturnUrl, desk.toString());
  const returnBase =
    returnCandidate?.origin === desk.origin
      ? returnCandidate.toString()
      : desk.toString();
  const returnTo = buildDeskReturnUrl({
    deskUrl: returnBase,
    moduleId,
    projectId,
    workspaceId,
    upstreamSessionId,
  });
  if (!numa || !mod || !project || !workspace || !session || !returnTo) {
    return undefined;
  }

  writeFragmentPayload(numa, {
    protocol: NUMA_HANDOFF_PROTOCOL,
    source: "newma-desk",
    moduleId: mod,
    projectId: project,
    workspaceId: workspace,
    upstreamSessionId: session,
    returnTo,
  });
  return numa.toString();
}

export function readNumaHandoffPayload(
  handoffUrl: string,
): NumaHandoffPayload | undefined {
  const parsed = httpUrl(handoffUrl);
  if (!parsed) return undefined;
  const payload = readFragmentPayload(parsed);
  const moduleId = handoffIdentifier(payload?.moduleId);
  const projectId = handoffIdentifier(payload?.projectId);
  const workspaceId = boundedString(payload?.workspaceId, 256);
  const upstreamSessionId = boundedString(payload?.upstreamSessionId, 1024);
  const returnTo = httpUrl(payload?.returnTo)?.toString();
  const returnHandoff =
    returnTo && moduleId && projectId && workspaceId
      ? readDeskReturnHandoff(
          returnTo,
          moduleId,
          workspaceId,
          projectId,
        )
      : undefined;
  if (
    payload?.protocol !== NUMA_HANDOFF_PROTOCOL ||
    payload.source !== "newma-desk" ||
    !moduleId ||
    !projectId ||
    !workspaceId ||
    !upstreamSessionId ||
    !returnTo ||
    returnHandoff?.upstreamSessionId !== upstreamSessionId
  ) {
    return undefined;
  }
  return {
    protocol: NUMA_HANDOFF_PROTOCOL,
    source: "newma-desk",
    moduleId,
    projectId,
    workspaceId,
    upstreamSessionId,
    returnTo,
  };
}

export function readDeskReturnHandoff(
  deskUrl: string,
  expectedModuleId: string,
  expectedWorkspaceId: string,
  expectedProjectId = expectedModuleId,
): DeskReturnHandoff | undefined {
  const parsed = httpUrl(deskUrl);
  if (!parsed) return undefined;
  const copilot = parsed.searchParams.get("copilot");
  const payload = readFragmentPayload(parsed);
  const moduleId = handoffIdentifier(payload?.moduleId);
  const projectId = handoffIdentifier(payload?.projectId);
  const workspaceId = boundedString(payload?.workspaceId, 256);
  const upstreamSessionId = boundedString(payload?.upstreamSessionId, 1024);
  if (
    !["1", "true", "open"].includes(copilot ?? "") ||
    parsed.searchParams.get("mod") !== expectedModuleId ||
    payload?.protocol !== NUMA_HANDOFF_PROTOCOL ||
    payload.source !== "numa-agent" ||
    moduleId !== expectedModuleId ||
    projectId !== expectedProjectId ||
    workspaceId !== expectedWorkspaceId ||
    !upstreamSessionId
  ) {
    return undefined;
  }
  return { moduleId, projectId, workspaceId, upstreamSessionId };
}

export function stripDeskReturnHandoffFragment(
  deskUrl: string,
): string | undefined {
  const parsed = httpUrl(deskUrl);
  if (!parsed) return undefined;
  const fragment = parsed.hash.slice(1);
  if (!fragment) return undefined;
  const queryIndex = fragment.indexOf("?");
  const route = queryIndex >= 0 ? fragment.slice(0, queryIndex) : "";
  const serializedParams =
    queryIndex >= 0 ? fragment.slice(queryIndex + 1) : fragment;
  const params = new URLSearchParams(serializedParams);
  if (!params.has(HANDOFF_FRAGMENT_KEY)) return undefined;
  params.delete(HANDOFF_FRAGMENT_KEY);
  const remaining = params.toString();
  parsed.hash = route
    ? remaining
      ? `${route}?${remaining}`
      : route
    : remaining;
  return parsed.toString();
}

export function modCopilotSessionStorageKey(
  moduleId: string,
  workspaceId: string,
): string {
  return `${SESSION_STORAGE_PREFIX}.${encodeURIComponent(workspaceId)}.${encodeURIComponent(moduleId)}`;
}

function parseSessionMetadata(value: unknown): ModCopilotSessionMetadata | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const row = value as Record<string, unknown>;
  const moduleId = boundedString(row.moduleId, 128);
  const moduleName = boundedString(row.moduleName, 160);
  const workspaceId = boundedString(row.workspaceId, 256);
  const updatedAt = boundedString(row.updatedAt, 64);
  const mode = row.mode === "ask" || row.mode === "edit" ? row.mode : undefined;
  const status = SESSION_STATUSES.has(row.status as ModCopilotSessionStatus)
    ? (row.status as ModCopilotSessionStatus)
    : undefined;
  if (
    row.schemaVersion !== 1 ||
    !moduleId ||
    !moduleName ||
    !workspaceId ||
    !updatedAt ||
    !mode ||
    !status
  ) {
    return undefined;
  }

  const metadata: ModCopilotSessionMetadata = {
    schemaVersion: 1,
    moduleId,
    moduleName,
    workspaceId,
    mode,
    status,
    updatedAt,
  };
  const taskId = boundedString(row.taskId, 256);
  const adapterId = boundedString(row.adapterId, 128);
  const projectId = handoffIdentifier(row.projectId);
  const upstreamSessionId = boundedString(row.upstreamSessionId, 1024);
  const deskReturnUrl = httpUrl(row.deskReturnUrl)?.toString();
  const lastPrompt = boundedString(row.lastPrompt, 8000);
  if (taskId) metadata.taskId = taskId;
  if (adapterId) metadata.adapterId = adapterId;
  if (projectId) metadata.projectId = projectId;
  if (upstreamSessionId) metadata.upstreamSessionId = upstreamSessionId;
  if (deskReturnUrl) metadata.deskReturnUrl = deskReturnUrl;
  if (lastPrompt) metadata.lastPrompt = lastPrompt;
  return metadata;
}

export function loadModCopilotSessionMetadata(
  moduleId: string,
  workspaceId: string,
  storage = browserStorage(),
): ModCopilotSessionMetadata | undefined {
  if (!storage) return undefined;
  try {
    const raw = storage.getItem(
      modCopilotSessionStorageKey(moduleId, workspaceId),
    );
    const parsed = raw ? parseSessionMetadata(JSON.parse(raw)) : undefined;
    if (
      parsed?.moduleId !== moduleId ||
      parsed?.workspaceId !== workspaceId
    ) {
      return undefined;
    }
    return parsed;
  } catch {
    return undefined;
  }
}

export function saveModCopilotSessionMetadata(
  metadata: ModCopilotSessionMetadata,
  storage = browserStorage(),
): boolean {
  const parsed = parseSessionMetadata(metadata);
  if (!storage || !parsed) return false;
  try {
    storage.setItem(
      modCopilotSessionStorageKey(parsed.moduleId, parsed.workspaceId),
      JSON.stringify(parsed),
    );
    return true;
  } catch {
    return false;
  }
}
