import { sessionBoardSnapshotSchema, type SessionBoardSnapshot } from "@newma-desk/contracts";
import { newmaHostIdentityFromLocation, type NewmaHostIdentity } from "./hostBridge";

export function readNewmaSessions(options: {
  identity?: NewmaHostIdentity | null; target?: Window; isCurrent?: () => boolean;
} = {}): Promise<SessionBoardSnapshot> {
  const identity = options.identity === undefined ? newmaHostIdentityFromLocation() : options.identity;
  const target = options.target ?? window.parent;
  if (!identity || target === window || identity.parentOrigin === "file://") {
    return Promise.reject(new Error("未连接支持会话看板的 newma Web 宿主；独立 Desk 暂不读取 Hermes 登录凭据。"));
  }
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    const cleanup = () => { window.clearTimeout(timer); window.removeEventListener("message", receive); };
    const receive = (event: MessageEvent) => {
      const data = event.data;
      if (event.source !== target || event.origin !== identity.parentMessageOrigin || !data
        || data.type !== "newma:sessions-result" || data.protocol !== "newma:mod-host:v1"
        || data.requestId !== requestId || data.projectId !== identity.projectId
        || data.workspaceId !== identity.workspaceId || data.modId !== "workflow-sessions") return;
      cleanup();
      if (options.isCurrent && !options.isCurrent()) { reject(new Error("看板已切换，请重新读取会话。")); return; }
      if (data.ok !== true) { reject(new Error("newma 无法读取当前会话，请检查登录或 Profile 后重试。")); return; }
      const parsed = sessionBoardSnapshotSchema.safeParse(data.snapshot);
      if (!parsed.success || parsed.data.sessions.some((row) => {
        const link = new URL(row.url);
        return link.origin !== identity.parentOrigin || Boolean(link.username || link.password);
      })) { reject(new Error("宿主返回的会话数据或跳转地址不符合约定。")); return; }
      resolve(parsed.data);
    };
    const timer = window.setTimeout(() => {
      cleanup(); reject(new Error("宿主未响应会话读取，请确认 newma 和 Desk 均已加载看板接入版本。"));
    }, 10000);
    window.addEventListener("message", receive);
    target.postMessage({ type: "newma:sessions-request", protocol: "newma:mod-host:v1", requestId,
      projectId: identity.projectId, workspaceId: identity.workspaceId, modId: "workflow-sessions" }, identity.parentTargetOrigin);
  });
}
