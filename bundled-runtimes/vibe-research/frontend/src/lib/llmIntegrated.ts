import { ApiError } from "./api";
import { waitForVibeDeskConfig } from "./vibedesk";
import {
  chatViaVibeDesk,
  type ChatHandlers,
  type ChatMsg,
  type ChatResult,
} from "./llmShared";

export type { ChatHandlers, ChatMsg, ChatResult } from "./llmShared";

export const isIntegratedResearchBuild = true;
export const usesUnifiedDeskAgent = true;

// Compatibility exports keep dead standalone chunks transformable while the
// integrated route graph omits them from the emitted bundle.
export function loadLlm(): null {
  return null;
}

export function saveLlm(): void {}

export function clearLlm(): void {}

export function hasLlm(): boolean {
  return true;
}

export async function chatStream(
  messages: ChatMsg[],
  context: string,
  handlers: ChatHandlers = {},
  signal?: AbortSignal,
): Promise<ChatResult> {
  const config = await waitForVibeDeskConfig();
  if (!config) {
    throw new ApiError(
      "Desk Agent 尚未就绪，请从 Newma-Desk 打开本模块并检查统一 Agent 设置",
      503,
    );
  }
  return chatViaVibeDesk(config, messages, context, handlers, signal);
}

export function chat(messages: ChatMsg[], context: string): Promise<ChatResult> {
  return chatStream(messages, context);
}
