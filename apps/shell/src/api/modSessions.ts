import type { ModPageContext } from "@newma-desk/contracts";

export interface ModSession {
  sessionId: string;
  instanceId: string;
  accessToken: string;
  tokenType: "Bearer";
  expiresAt: string;
  userId: string;
  workspaceId: string;
  moduleId: string;
  revision: number;
  grants: { permissions: string[]; actions: string[] };
}

export interface ModSessionIssuerInput {
  modId: string;
  instanceId: string;
  userId: string;
  workspaceId: string;
}

export class ModSessionRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ModSessionRequestError";
    this.status = status;
  }
}

async function responseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function errorDetail(body: unknown, fallback: string): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  if (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof body.error === "object" &&
    body.error !== null &&
    "message" in body.error &&
    typeof body.error.message === "string"
  ) {
    return body.error.message;
  }
  return fallback;
}

function parseSession(value: unknown): ModSession {
  if (typeof value !== "object" || value === null) {
    throw new Error("Mod session response is malformed");
  }
  const row = value as Record<string, unknown>;
  const grants = row.grants as Record<string, unknown> | undefined;
  if (
    typeof row.sessionId !== "string" ||
    typeof row.instanceId !== "string" ||
    typeof row.accessToken !== "string" ||
    row.tokenType !== "Bearer" ||
    typeof row.expiresAt !== "string" ||
    typeof row.userId !== "string" ||
    typeof row.workspaceId !== "string" ||
    typeof row.moduleId !== "string" ||
    !Number.isInteger(row.revision) ||
    !grants ||
    !Array.isArray(grants.permissions) ||
    !grants.permissions.every((item) => typeof item === "string") ||
    !Array.isArray(grants.actions) ||
    !grants.actions.every((item) => typeof item === "string")
  ) {
    throw new Error("Mod session response is malformed");
  }
  return row as unknown as ModSession;
}

export async function issueModSession(
  input: ModSessionIssuerInput,
): Promise<ModSession> {
  const response = await fetch(
    `/api/mods/${encodeURIComponent(input.modId)}/sessions`,
    {
      method: "POST",
      credentials: "omit",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-User-Id": input.userId,
      },
      body: JSON.stringify({
        instanceId: input.instanceId,
        workspaceId: input.workspaceId,
      }),
    },
  );
  const body = await responseJson(response);
  if (!response.ok) {
    throw new Error(errorDetail(body, `Mod session returned ${response.status}`));
  }
  return parseSession(body);
}

export async function invokeModSessionAction(
  session: ModSession,
  actionId: string,
  input: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const response = await fetch(
    `/api/mods/${encodeURIComponent(session.moduleId)}/actions/${encodeURIComponent(actionId)}`,
    {
      method: "POST",
      credentials: "omit",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        "Content-Type": "application/json",
        "X-Newma-Desk-Instance-Id": session.instanceId,
      },
      body: JSON.stringify(input),
    },
  );
  const body = await responseJson(response);
  if (!response.ok) {
    throw new ModSessionRequestError(
      response.status,
      errorDetail(body, `Mod action returned ${response.status}`),
    );
  }
  return { status: response.status, body };
}

export async function saveModContext(
  session: ModSession,
  context: ModPageContext,
): Promise<void> {
  const response = await fetch(
    `/api/mods/${encodeURIComponent(session.moduleId)}/context`,
    {
      method: "PUT",
      credentials: "omit",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        "Content-Type": "application/json",
        "X-Newma-Desk-Instance-Id": session.instanceId,
      },
      body: JSON.stringify({ context }),
    },
  );
  if (!response.ok) {
    const body = await responseJson(response);
    throw new ModSessionRequestError(
      response.status,
      errorDetail(body, `Mod context returned ${response.status}`),
    );
  }
}
