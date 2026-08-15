import { modPageContextSchema, type ModPageContext } from "@newma-desk/contracts";

const HOST_PROTOCOL = "newma:mod-host:v1" as const;
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MOD_ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;

export interface NewmaHostIdentity {
  projectId: string;
  workspaceId: string;
  parentOrigin: string;
  parentMessageOrigin: string;
  parentTargetOrigin: string;
}

export interface NewmaHostContextRequest {
  type: "newma:mod-context-request";
  protocol: typeof HOST_PROTOCOL;
  requestId: string;
  projectId: string;
  modId: string;
  workspaceId: string;
  reason: "initial" | "agent" | "refresh";
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  if (normalized === "localhost" || normalized.endsWith(".localhost") || normalized === "[::1]") {
    return true;
  }
  const octets = normalized.split(".");
  return octets.length === 4 && octets[0] === "127" && octets.every((octet) => {
    const value = Number(octet);
    return /^\d{1,3}$/.test(octet) && value >= 0 && value <= 255;
  });
}

export function newmaHostIdentityFromLocation(): NewmaHostIdentity | null {
  const params = new URLSearchParams(window.location.search);
  if (params.get("host") !== "newma") return null;
  const projectId = params.get("project")?.trim() || "";
  const workspaceId = params.get("workspace")?.trim() || "";
  const parentOriginRaw = params.get("parentOrigin")?.trim() || "";
  let parentOrigin: string;
  let parentMessageOrigin: string;
  try {
    const parsed = new URL(parentOriginRaw);
    if (parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
      return null;
    }
    if (parsed.protocol === "https:") {
      parentOrigin = parsed.origin;
      parentMessageOrigin = parsed.origin;
    } else if (parsed.protocol === "http:" && isLoopbackHostname(parsed.hostname)) {
      parentOrigin = parsed.origin;
      parentMessageOrigin = parsed.origin;
    } else if (parsed.protocol === "file:") {
      parentOrigin = "file://";
      parentMessageOrigin = "null";
    } else {
      return null;
    }
  } catch {
    return null;
  }
  return ID_PATTERN.test(projectId) && ID_PATTERN.test(workspaceId)
    ? {
        projectId,
        workspaceId,
        parentOrigin,
        parentMessageOrigin,
        // file: parents have an opaque message Origin. The explicit file://
        // declaration is the only path allowed to use the platform-required
        // wildcard; incoming requests still require source===window.parent and
        // event.origin==="null" plus exact project/mod/workspace identity.
        parentTargetOrigin: parentOrigin === "file://" ? "*" : parentOrigin,
      }
    : null;
}

export function parseNewmaHostContextRequest(
  value: unknown,
): NewmaHostContextRequest | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (
    row.type !== "newma:mod-context-request" ||
    row.protocol !== HOST_PROTOCOL ||
    typeof row.requestId !== "string" ||
    !ID_PATTERN.test(row.requestId) ||
    typeof row.projectId !== "string" ||
    !ID_PATTERN.test(row.projectId) ||
    typeof row.modId !== "string" ||
    !MOD_ID_PATTERN.test(row.modId) ||
    typeof row.workspaceId !== "string" ||
    !ID_PATTERN.test(row.workspaceId) ||
    !["initial", "agent", "refresh"].includes(String(row.reason))
  ) {
    return null;
  }
  return row as unknown as NewmaHostContextRequest;
}

export function postNewmaHostContext(input: {
  context: ModPageContext;
  identity: NewmaHostIdentity;
  modId: string;
  requestId?: string;
  target?: Window;
}): void {
  const context = modPageContextSchema.parse(input.context);
  (input.target ?? window.parent).postMessage(
    {
      type: "newma:mod-context",
      protocol: HOST_PROTOCOL,
      ...(input.requestId ? { requestId: input.requestId } : {}),
      projectId: input.identity.projectId,
      modId: input.modId,
      workspaceId: input.identity.workspaceId,
      context,
      updatedAt: Date.now(),
    },
    input.identity.parentTargetOrigin,
  );
}
