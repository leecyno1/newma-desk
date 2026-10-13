import { ApiError } from "./api";
import {
  requestVibeDeskAgent,
  type VibeDeskConfig,
} from "./vibedesk";

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
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (!config.runtimeAvailable) {
    throw new ApiError("Agent Runtime 尚未连接", 503);
  }
  const conversation = messages.slice(-6).map((message) =>
    `${message.role === "user" ? "用户" : "Agent"}：${message.content}`
  ).join("\n");
  const prompt = [
    messages[messages.length - 1]?.content || "请分析当前页面",
    context ? `当前研究页面补充文本：\n${context.slice(0, 4_000)}` : "",
    conversation ? `最近对话：\n${conversation}` : "",
  ].filter(Boolean).join("\n\n");
  try {
    await requestVibeDeskAgent({ prompt, mode: "ask" });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : "Agent Runtime 请求失败",
      503,
    );
  }
  const content = "已把当前页面上下文和问题交给当前 Agent Runtime，请在统一 Copilot 中继续查看。";
  handlers.onDelta?.(content);
  return { content, trace: [], rounds: 1 };
}
