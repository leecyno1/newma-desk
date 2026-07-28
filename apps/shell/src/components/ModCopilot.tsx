import type { ModPageContext } from "@newma-desk/contracts";
import {
  Bot,
  CircleAlert,
  Code2,
  LoaderCircle,
  MessageSquareText,
  Send,
  Settings2,
  Square,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  cancelAgentTask,
  createAgentTask,
  getAgentTask,
  loadAgentSettings,
  type AgentTask,
} from "../api/agents";
import type { StoredMod } from "../api/modules";

type CopilotMode = "ask" | "edit";
type ContextState = "idle" | "syncing" | "ready" | "fallback";

interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  mode?: CopilotMode;
}

interface ModCopilotProps {
  module: StoredMod;
  open: boolean;
  userId: string;
  workspaceId: string;
  onClose: () => void;
  onEditCompleted?: () => void | Promise<void>;
  onOpenAgentSettings?: () => void;
  requestContext: () => Promise<ModPageContext | undefined>;
  invokeUiAction?: (
    actionId: string,
    input?: Record<string, unknown>,
  ) => Promise<unknown>;
}

interface AgentRuntimeState {
  label: string;
  available: boolean;
  loading: boolean;
}

const MESSAGE_STORAGE_PREFIX = "vibedesk.mod-copilot.messages.";

function loadMessages(moduleId: string): ConversationMessage[] {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(`${MESSAGE_STORAGE_PREFIX}${moduleId}`) || "[]",
    );
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (item): item is ConversationMessage =>
          typeof item === "object" &&
          item !== null &&
          typeof item.id === "string" &&
          ["user", "assistant", "system"].includes(item.role) &&
          typeof item.content === "string",
      )
      .slice(-40);
  } catch {
    return [];
  }
}

function saveMessages(moduleId: string, messages: ConversationMessage[]) {
  try {
    window.localStorage.setItem(
      `${MESSAGE_STORAGE_PREFIX}${moduleId}`,
      JSON.stringify(messages.slice(-40)),
    );
  } catch {
    // Blocked storage must not prevent the shared Agent drawer from working.
  }
}

function messageId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `message-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function taskAnswer(task: AgentTask): string {
  if (task.result?.answer) return task.result.answer;
  if (task.result?.message) return task.result.message;
  if (task.result) return JSON.stringify(task.result, null, 2);
  return "Agent 已完成任务，但没有返回文本结果。";
}

function fallbackPageContext(module: StoredMod): Record<string, unknown> {
  return {
    view: {
      id: module.moduleId,
      title: module.manifest.name,
    },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: {
      freshness: "unknown",
      summary: {
        note: "当前 Mod 尚未提供结构化页面上下文，以下信息来自 Manifest。",
        entry: module.manifest.entry,
        category: module.manifest.category,
      },
    },
    actions: [],
    tasks: [],
  };
}

function contextLabel(state: ContextState): string {
  if (state === "syncing") return "正在同步页面";
  if (state === "ready") return "已同步当前页面";
  if (state === "fallback") return "使用 Mod 基础信息";
  return "发送时同步页面";
}

export function ModCopilot({
  module,
  open,
  userId,
  workspaceId,
  onClose,
  onEditCompleted,
  onOpenAgentSettings,
  requestContext,
  invokeUiAction,
}: ModCopilotProps) {
  const [messagesByModule, setMessagesByModule] = useState<
    Record<string, ConversationMessage[]>
  >({});
  const [modeByModule, setModeByModule] = useState<Record<string, CopilotMode>>(
    {},
  );
  const [inputByModule, setInputByModule] = useState<Record<string, string>>({});
  const [taskByModule, setTaskByModule] = useState<Record<string, string>>({});
  const [contextByModule, setContextByModule] = useState<
    Record<string, ContextState>
  >({});
  const [agentByModule, setAgentByModule] = useState<
    Record<string, AgentRuntimeState>
  >({});
  const mountedRef = useRef(true);
  const handledTasksRef = useRef(new Set<string>());
  const taskModesRef = useRef(new Map<string, CopilotMode>());
  const messageListRef = useRef<HTMLDivElement>(null);
  const moduleId = module.moduleId;
  const messages = messagesByModule[moduleId] ?? [];
  const mode = modeByModule[moduleId] ?? "ask";
  const input = inputByModule[moduleId] ?? "";
  const activeTaskId = taskByModule[moduleId];
  const contextState = contextByModule[moduleId] ?? "idle";
  const busy = Boolean(activeTaskId) || contextState === "syncing";

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, activeTaskId, open]);

  useEffect(() => {
    if (!open) return;
    setMessagesByModule((current) =>
      current[moduleId] === undefined
        ? { ...current, [moduleId]: loadMessages(moduleId) }
        : current,
    );
    setAgentByModule((current) => ({
      ...current,
      [moduleId]: current[moduleId] ?? {
        label: "正在读取 Agent…",
        available: false,
        loading: true,
      },
    }));
    let active = true;
    void loadAgentSettings(userId).then(
      ({ adapters, preferences }) => {
        if (!active) return;
        const selectedId =
          preferences.moduleOverrides[moduleId] || preferences.defaultAdapter;
        const selected = adapters.find((adapter) => adapter.id === selectedId);
        setAgentByModule((current) => ({
          ...current,
          [moduleId]: {
            label: selected?.name || selected?.id || selectedId,
            available: selected ? selected.available !== false : false,
            loading: false,
          },
        }));
      },
      () => {
        if (!active) return;
        setAgentByModule((current) => ({
          ...current,
          [moduleId]: {
            label: "Agent 配置不可用",
            available: false,
            loading: false,
          },
        }));
      },
    );
    return () => {
      active = false;
    };
  }, [moduleId, open, userId]);

  const appendMessage = (targetModuleId: string, message: ConversationMessage) => {
    if (!mountedRef.current) return;
    setMessagesByModule((current) => {
      const nextMessages = [...(current[targetModuleId] ?? []), message].slice(-40);
      saveMessages(targetModuleId, nextMessages);
      return { ...current, [targetModuleId]: nextMessages };
    });
  };

  const finishTask = (
    targetModuleId: string,
    taskId: string,
    message?: ConversationMessage,
    editCompleted = false,
  ) => {
    if (handledTasksRef.current.has(taskId)) return;
    handledTasksRef.current.add(taskId);
    taskModesRef.current.delete(taskId);
    if (message) appendMessage(targetModuleId, message);
    if (editCompleted) {
      void Promise.resolve(onEditCompleted?.()).then(
        () =>
          appendMessage(targetModuleId, {
            id: messageId(),
            role: "system",
            content: "修改任务已完成，当前 Mod 已重新加载。",
          }),
        () =>
          appendMessage(targetModuleId, {
            id: messageId(),
            role: "system",
            content: "修改已完成，但自动重新加载失败，请手动刷新当前 Mod。",
          }),
      );
    }
    if (!mountedRef.current) return;
    setTaskByModule((current) => {
      if (current[targetModuleId] !== taskId) return current;
      const next = { ...current };
      delete next[targetModuleId];
      return next;
    });
  };

  const pollTask = async (targetModuleId: string, taskId: string) => {
    try {
      while (mountedRef.current && !handledTasksRef.current.has(taskId)) {
        const task = await getAgentTask(taskId);
        if (task.status === "completed") {
          const actionResults: string[] = [];
          for (const action of task.result?.actions ?? []) {
            if (!action || typeof action.actionId !== "string") continue;
            try {
              await invokeUiAction?.(action.actionId, action.input ?? {});
              actionResults.push(`已执行 ${action.actionId}`);
            } catch (reason) {
              actionResults.push(`${action.actionId} 执行失败：${reason instanceof Error ? reason.message : "未知错误"}`);
            }
          }
          const answer = taskAnswer(task);
          finishTask(targetModuleId, taskId, {
            id: messageId(),
            role: "assistant",
            content: actionResults.length ? `${answer}\n\n${actionResults.join("\n")}` : answer,
          }, taskModesRef.current.get(taskId) === "edit");
          return;
        }
        if (task.status === "failed") {
          finishTask(targetModuleId, taskId, {
            id: messageId(),
            role: "system",
            content: task.error || "Agent 任务失败。",
          });
          return;
        }
        if (task.status === "cancelled") {
          finishTask(targetModuleId, taskId, {
            id: messageId(),
            role: "system",
            content: "任务已停止。",
          });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (reason) {
      finishTask(targetModuleId, taskId, {
        id: messageId(),
        role: "system",
        content: reason instanceof Error ? reason.message : "读取 Agent 状态失败。",
      });
    }
  };

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || busy) return;
    const targetModule = module;
    const targetModuleId = targetModule.moduleId;
    const targetMode = mode;
    setInputByModule((current) => ({ ...current, [targetModuleId]: "" }));
    appendMessage(targetModuleId, {
      id: messageId(),
      role: "user",
      content: prompt,
      mode: targetMode,
    });
    setContextByModule((current) => ({
      ...current,
      [targetModuleId]: "syncing",
    }));

    try {
      const pageContext = await requestContext();
      if (!mountedRef.current) return;
      setContextByModule((current) => ({
        ...current,
        [targetModuleId]: pageContext ? "ready" : "fallback",
      }));
      const task = await createAgentTask(
        { userId, workspaceId },
        {
          moduleId: targetModuleId,
          capability: targetMode === "edit" ? "module.edit" : "module.explain",
          memoryScope: "user-agent-mod",
          prompt,
          context: {
            vibedesk: {
              mode: targetMode,
              source: pageContext ? "mod-bridge" : "manifest-fallback",
              mod: {
                id: targetModuleId,
                name: targetModule.manifest.name,
                version: targetModule.manifest.version,
                revision: targetModule.revision,
                manifest: targetModule.manifest,
              },
              page: pageContext ?? fallbackPageContext(targetModule),
            },
          },
        },
      );
      if (!mountedRef.current) return;
      setTaskByModule((current) => ({
        ...current,
        [targetModuleId]: task.id,
      }));
      taskModesRef.current.set(task.id, targetMode);
      void pollTask(targetModuleId, task.id);
    } catch (reason) {
      setContextByModule((current) => ({
        ...current,
        [targetModuleId]: "fallback",
      }));
      appendMessage(targetModuleId, {
        id: messageId(),
        role: "system",
        content: reason instanceof Error ? reason.message : "Agent 请求失败。",
      });
    }
  };

  const stop = async () => {
    if (!activeTaskId) return;
    const taskId = activeTaskId;
    try {
      await cancelAgentTask(taskId);
      finishTask(moduleId, taskId, {
        id: messageId(),
        role: "system",
        content: "任务已停止。",
      });
    } catch (reason) {
      appendMessage(moduleId, {
        id: messageId(),
        role: "system",
        content: reason instanceof Error ? reason.message : "停止任务失败。",
      });
    }
  };

  const agentState = agentByModule[moduleId] ?? {
    label: "发送时选择 Agent",
    available: true,
    loading: true,
  };
  const suggestions =
    mode === "edit"
      ? ["修复当前页面的异常状态", "优化当前页面布局并验证", "检查并修复当前 Mod 的数据链路"]
      : ["总结当前页面的关键信息", "解释当前页面的数据与风险", "检查当前页面是否存在异常或缺失"];

  return (
    <aside
      className={`mod-copilot${open ? " is-open" : ""}`}
      aria-label={`${module.manifest.name} Agent`}
      aria-hidden={!open}
      inert={!open}
    >
      <header className="mod-copilot-header">
        <div>
          <span>当前 Mod</span>
          <strong>{module.manifest.name}</strong>
          <small data-context-state={contextState}>
            {contextLabel(contextState)} · {agentState.label}
          </small>
        </div>
        <div className="mod-copilot-header-actions">
          {onOpenAgentSettings ? (
            <button
              type="button"
              aria-label="打开 Agent 设置"
              onClick={onOpenAgentSettings}
            >
              <Settings2 size={15} aria-hidden="true" />
            </button>
          ) : null}
          <button type="button" aria-label="关闭 Agent 侧栏" onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="mod-copilot-modes" aria-label="Agent 模式">
        <button
          type="button"
          aria-pressed={mode === "ask"}
          onClick={() =>
            setModeByModule((current) => ({ ...current, [moduleId]: "ask" }))
          }
        >
          <MessageSquareText size={14} aria-hidden="true" />
          提问
        </button>
        <button
          type="button"
          aria-pressed={mode === "edit"}
          onClick={() =>
            setModeByModule((current) => ({ ...current, [moduleId]: "edit" }))
          }
        >
          <Code2 size={14} aria-hidden="true" />
          修改
        </button>
      </div>

      {mode === "edit" ? (
        <div className="mod-copilot-warning">
          <CircleAlert size={14} aria-hidden="true" />
          Agent 可修改当前 Mod 所属工程，并会返回改动文件与验证结果。
        </div>
      ) : null}

      {!agentState.loading && !agentState.available ? (
        <div className="mod-copilot-warning">
          <CircleAlert size={14} aria-hidden="true" />
          当前 Agent 不可用，请先在 Newma-Desk 的 Agent 设置中完成安装或登录。
        </div>
      ) : null}

      <div className="mod-copilot-messages" ref={messageListRef}>
        {messages.length === 0 ? (
          <div className="mod-copilot-empty">
            <Bot size={22} aria-hidden="true" />
            <strong>针对当前 Mod 提问</strong>
            <span>发送时会先同步当前页面、选择项和筛选条件。</span>
            <div className="mod-copilot-suggestions">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() =>
                    setInputByModule((current) => ({
                      ...current,
                      [moduleId]: suggestion,
                    }))
                  }
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`copilot-message ${message.role}`}
            >
              <span>
                {message.role === "user"
                  ? message.mode === "edit"
                    ? "修改请求"
                    : "你"
                  : message.role === "assistant"
                    ? "Agent"
                    : "系统"}
              </span>
              <p>{message.content}</p>
            </article>
          ))
        )}
        {busy ? (
          <div className="mod-copilot-running" role="status">
            <LoaderCircle className="spin" size={15} aria-hidden="true" />
            {activeTaskId ? "Agent 正在处理当前 Mod…" : "正在同步当前页面…"}
          </div>
        ) : null}
      </div>

      <footer className="mod-copilot-composer">
        <textarea
          rows={3}
          value={input}
          onChange={(event) =>
            setInputByModule((current) => ({
              ...current,
              [moduleId]: event.target.value,
            }))
          }
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder={
            mode === "edit"
              ? "描述要修改的功能或问题…"
              : "就当前页面提问…"
          }
          disabled={busy}
        />
        <div>
          <span>Enter 发送 · Shift+Enter 换行</span>
          {activeTaskId ? (
            <button type="button" className="copilot-stop" onClick={() => void stop()}>
              <Square size={13} aria-hidden="true" />
              停止
            </button>
          ) : (
            <button
              type="button"
              className="copilot-send"
              onClick={() => void send()}
              disabled={!input.trim() || busy || !agentState.available}
            >
              <Send size={14} aria-hidden="true" />
              发送
            </button>
          )}
        </div>
      </footer>
    </aside>
  );
}
