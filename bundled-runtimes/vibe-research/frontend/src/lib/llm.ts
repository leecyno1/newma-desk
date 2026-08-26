// 独立版的本地 LLM 配置 + Desk 集成版的统一 Agent 调用。

import { ApiError, authHeaders, researchApiUrl } from "./api";
import { isCliProvider, type ProviderId } from "./ai-models";
import {
  isVibeDeskEmbedded,
  waitForVibeDeskConfig,
} from "./vibedesk";
import {
  chatViaVibeDesk,
  type ChatHandlers,
  type ChatMsg,
  type ChatResult,
} from "./llmShared";

export type { ChatHandlers, ChatMsg, ChatResult } from "./llmShared";

export interface LlmConfig {
  provider: ProviderId;
  baseURL: string; // CLI 订阅时留空
  apiKey: string;  // CLI 订阅时留空
  model: string;
}

const KEY = "vr-llm";
export const isIntegratedResearchBuild =
  import.meta.env.VITE_NEWMA_DESK_INTEGRATED === "1";
export const usesUnifiedDeskAgent =
  isIntegratedResearchBuild || isVibeDeskEmbedded;

export function loadLlm(): LlmConfig | null {
  if (isIntegratedResearchBuild) return null;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const c = JSON.parse(raw) as LlmConfig;
    // 订阅(CLI)：有 model 即可，免 key；API：需 baseURL + key + model。
    const ok = c.model && (isCliProvider(c.provider) || (c.baseURL && c.apiKey));
    return ok ? c : null;
  } catch {
    return null;
  }
}

export function saveLlm(cfg: LlmConfig) {
  if (isIntegratedResearchBuild) return;
  localStorage.setItem(KEY, JSON.stringify(cfg));
}

export function clearLlm() {
  if (isIntegratedResearchBuild) return;
  localStorage.removeItem(KEY);
}

export function hasLlm(): boolean {
  return usesUnifiedDeskAgent || loadLlm() !== null;
}

// 流式调后端 /api/chat（NDJSON：每行一个事件 {type: tool|delta|done|error}）。
// 边流边回调 onDelta/onTool；返回累积的最终 {content, trace, rounds}。
// signal：调用方可传 AbortController.signal，用户关面板/换问题时中止请求（省订阅/API 额度）。
export async function chatStream(messages: ChatMsg[], context: string, handlers: ChatHandlers = {}, signal?: AbortSignal): Promise<ChatResult> {
  const vibeDesk = await waitForVibeDeskConfig();
  if (vibeDesk) {
    return chatViaVibeDesk(vibeDesk, messages, context, handlers, signal);
  }

  // 集成构建与 iframe 运行时不得回退到 Research 自带模型配置。
  // Desk 握手未就绪时直接报错，避免意外调用已退役的 /api/chat。
  if (usesUnifiedDeskAgent) {
    throw new ApiError(
      "Desk Agent 尚未就绪，请从 Newma-Desk 打开本模块并检查统一 Agent 设置",
      503,
    );
  }

  return chatViaResearchApi(messages, context, handlers, signal);
}

async function chatViaResearchApi(
  messages: ChatMsg[],
  context: string,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<ChatResult> {
  const llm = loadLlm();
  if (!llm) throw new ApiError("尚未接入 AI，请先在「接入 AI」里配置", 400);

  let resp: Response;
  try {
    resp = await fetch(researchApiUrl("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ messages, context, llm }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e; // 主动中止，原样抛给调用方
    throw new ApiError("连接不到 VibeDesk Research 领域 API", 0);
  }
  // 配置错误（缺 key / 未装 CLI）在流开始前以 HTTP 400 返回
  if (!resp.ok) {
    let body: any = null;
    try { body = await resp.json(); } catch { /* ignore */ }
    if (resp.status === 401) {
      throw new ApiError("后端开启了访问鉴权（VR_API_KEY）：请在「接入 AI」页底部填写后端访问密钥", 401);
    }
    throw new ApiError(body?.detail || `HTTP ${resp.status}`, resp.status);
  }
  if (!resp.body) throw new ApiError("后端无响应流", 502);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let content = "";
  let trace: ChatResult["trace"] = [];
  let rounds = 0;
  let errMsg: string | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      let ev: any;
      try { ev = JSON.parse(t); } catch { continue; }
      if (ev.type === "delta") { content += ev.text; handlers.onDelta?.(ev.text); }
      else if (ev.type === "tool") { handlers.onTool?.(ev.tool, ev.args || {}); }
      else if (ev.type === "done") { trace = ev.trace || []; rounds = ev.rounds || 0; }
      else if (ev.type === "error") { errMsg = ev.message; }
    }
  }
  if (errMsg) throw new ApiError(errMsg, 502);
  return { content, trace, rounds };
}

// 非流式便捷包装（不需要逐字 UI 的调用方用它）。
export function chat(messages: ChatMsg[], context: string): Promise<ChatResult> {
  return chatStream(messages, context);
}
