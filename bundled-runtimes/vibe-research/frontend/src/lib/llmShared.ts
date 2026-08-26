import { ApiError } from "./api";
import type { VibeDeskConfig } from "./vibedesk";

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResult {
  content: string;
  trace: { tool: string; args: Record<string, unknown> }[];
  rounds: number;
}

export interface ChatHandlers {
  onDelta?: (text: string) => void;
  onTool?: (tool: string, args: Record<string, unknown>) => void;
}

export async function chatViaVibeDesk(
  config: VibeDeskConfig,
  messages: ChatMsg[],
  context: string,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<ChatResult> {
  let created: { id: string };
  try {
    const response = await fetch(`${config.gatewayOrigin}/api/agent/tasks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": config.userId,
      },
      body: JSON.stringify({
        moduleId: config.moduleId,
        capability: "module.explain",
        prompt: messages[messages.length - 1]?.content || "请分析当前页面",
        context: {
          page: context,
          conversation: messages,
          source: "vibe-investment",
        },
      }),
      signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(body?.detail || `Agent Gateway HTTP ${response.status}`, response.status);
    }
    created = await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    if (error instanceof ApiError) throw error;
    throw new ApiError("连接不到 VibeDesk Agent Gateway", 0);
  }

  const cancel = () => {
    void fetch(`${config.gatewayOrigin}/api/agent/tasks/${created.id}/cancel`, {
      method: "POST",
      headers: { "X-User-Id": config.userId },
    });
  };
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    const deadline = Date.now() + 300_000;
    while (Date.now() < deadline) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const response = await fetch(
        `${config.gatewayOrigin}/api/agent/tasks/${created.id}`,
        { headers: { "X-User-Id": config.userId }, signal },
      );
      if (!response.ok) throw new ApiError(`Agent Gateway HTTP ${response.status}`, response.status);
      const task = await response.json();
      if (task.status === "completed") {
        const content = String(task.result?.answer || "").trim();
        if (!content) throw new ApiError("Agent 没有返回答案", 502);
        handlers.onDelta?.(content);
        return { content, trace: [], rounds: 1 };
      }
      if (task.status === "failed" || task.status === "cancelled") {
        throw new ApiError(task.error || "Agent 未完成请求", 502);
      }
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
    cancel();
    throw new ApiError("Agent 运行超时", 504);
  } finally {
    signal?.removeEventListener("abort", cancel);
  }
}
