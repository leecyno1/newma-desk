export interface WorkspaceIdentity {
  userId: string;
  workspaceId: string;
}

const USER_KEY = "vibedesk.userId.v1";
const WORKSPACE_KEY = "vibedesk.workspaceId.v1";

function randomId(prefix: string): string {
  const value =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value}`;
}

export function loadWorkspaceIdentity(): WorkspaceIdentity {
  try {
    const storedUser = window.localStorage.getItem(USER_KEY);
    const storedWorkspace = window.localStorage.getItem(WORKSPACE_KEY);
    const userId = storedUser || randomId("user");
    const workspaceId = storedWorkspace || randomId("workspace");
    if (!storedUser) window.localStorage.setItem(USER_KEY, userId);
    if (!storedWorkspace) {
      window.localStorage.setItem(WORKSPACE_KEY, workspaceId);
    }
    return { userId, workspaceId };
  } catch {
    return {
      userId: randomId("user"),
      workspaceId: randomId("workspace"),
    };
  }
}
