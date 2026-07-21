import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { viewSchema } from "@vibedesk/contracts";
import {
  createGatewayClient,
  createModBridge,
  requestGatewayJson,
  type AgentTask,
  type GatewayClient,
  type GatewayFetch,
  type ModelResponse,
  type ModBridge,
} from "@vibedesk/mod-sdk";
import { StructuredView } from "@vibedesk/view-renderer";

import rawView from "./view.json";

const MOD_ID = "market-daily";
const view = viewSchema.parse(rawView);

interface MarketSnapshot {
  id: string;
  moduleId: string;
  createdAt: string;
  data: Record<string, unknown> & { asOf: string };
}

type AiGatewayMode = "model" | "agent";

export interface MarketPulseAppProps {
  bridge?: ModBridge;
  fetch?: GatewayFetch;
  gatewayBaseUrl?: string;
}

function configuredOrigin(name: "gateway" | "parent"): string {
  const configured =
    name === "gateway"
      ? import.meta.env.VITE_GATEWAY_BASE_URL
      : import.meta.env.VITE_PARENT_ORIGIN;
  return configured?.trim() || window.location.origin;
}

function parseSnapshot(value: unknown): MarketSnapshot {
  if (typeof value !== "object" || value === null) {
    throw new Error("行情快照格式无效");
  }
  const row = value as Record<string, unknown>;
  if (
    typeof row.id !== "string" ||
    row.moduleId !== MOD_ID ||
    typeof row.createdAt !== "string" ||
    typeof row.data !== "object" ||
    row.data === null ||
    typeof (row.data as Record<string, unknown>).asOf !== "string"
  ) {
    throw new Error("行情快照格式无效");
  }
  return row as unknown as MarketSnapshot;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

function staleSnapshot(snapshot: MarketSnapshot): boolean {
  const timestamp = new Date(snapshot.data.asOf).getTime();
  return Number.isNaN(timestamp) || Date.now() - timestamp > 24 * 60 * 60 * 1000;
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "行情 Mod 操作失败";
}

function taskAnswer(task: AgentTask): string | undefined {
  const result = task.result;
  if (!result) return undefined;
  for (const key of ["answer", "output", "text"]) {
    if (typeof result[key] === "string") return result[key];
  }
  return JSON.stringify(result, null, 2);
}

function parseModelResponse(value: unknown): ModelResponse {
  if (typeof value !== "object" || value === null) {
    throw new Error("模型返回格式无效");
  }
  const row = value as Record<string, unknown>;
  if (
    typeof row.answer !== "string" ||
    typeof row.adapter !== "string" ||
    typeof row.model !== "string"
  ) {
    throw new Error("模型返回格式无效");
  }
  return row as unknown as ModelResponse;
}

export function MarketPulseApp({
  bridge: providedBridge,
  fetch: providedFetch,
  gatewayBaseUrl,
}: MarketPulseAppProps) {
  const fetcher = useMemo(
    () => providedFetch ?? globalThis.fetch.bind(globalThis),
    [providedFetch],
  );
  const gatewayOrigin = gatewayBaseUrl || configuredOrigin("gateway");
  const gateway = useMemo<GatewayClient>(
    () => createGatewayClient({ baseUrl: gatewayOrigin, fetch: fetcher }),
    [fetcher, gatewayOrigin],
  );
  const [bridge] = useState(
    () =>
      providedBridge ??
      createModBridge({
        modId: MOD_ID,
        parentOrigin: configuredOrigin("parent"),
      }),
  );
  const ownsBridge = providedBridge === undefined;
  const pollTimer = useRef<number | undefined>(undefined);
  const bridgeCloseTimer = useRef<number | undefined>(undefined);
  const [snapshot, setSnapshot] = useState<MarketSnapshot>();
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"refresh" | "explain">();
  const [error, setError] = useState<string>();
  const [task, setTask] = useState<AgentTask>();
  const [modelResponse, setModelResponse] = useState<ModelResponse>();
  const [aiMode, setAiMode] = useState<AiGatewayMode>("agent");

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const value = await requestGatewayJson<unknown>(
        fetcher,
        `${gatewayOrigin}/api/mods/${MOD_ID}/snapshot`,
      );
      setSnapshot(parseSnapshot(value));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [fetcher, gatewayOrigin]);

  const pollTask = useCallback(
    async (taskId: string) => {
      try {
        const next = await gateway.getTask(taskId);
        setTask(next);
        if (next.status === "queued" || next.status === "running") {
          pollTimer.current = window.setTimeout(
            () => void pollTask(taskId),
            500,
          );
        } else {
          setAction(undefined);
        }
      } catch (reason) {
        setError(errorMessage(reason));
        setAction(undefined);
      }
    },
    [gateway],
  );

  useEffect(() => {
    if (bridgeCloseTimer.current !== undefined) {
      window.clearTimeout(bridgeCloseTimer.current);
      bridgeCloseTimer.current = undefined;
    }
    void loadSnapshot();
    const unsubscribe = bridge.subscribe((event) => {
      if (event.event === "date.changed") void loadSnapshot();
    });
    return () => {
      unsubscribe();
      if (pollTimer.current !== undefined) window.clearTimeout(pollTimer.current);
      if (ownsBridge) {
        bridgeCloseTimer.current = window.setTimeout(() => bridge.close(), 0);
      }
    };
  }, [bridge, loadSnapshot, ownsBridge]);

  const handleAction = useCallback(
    async (capability: string) => {
      if (action !== undefined) return;
      setError(undefined);
      if (capability === "market.refresh") {
        setAction("refresh");
        try {
          const value = await gateway.invokeModAction<unknown>(
            MOD_ID,
            capability,
            {},
          );
          setSnapshot(parseSnapshot(value));
        } catch (reason) {
          setError(errorMessage(reason));
        } finally {
          setAction(undefined);
        }
        return;
      }
      if (capability === "market.explain") {
        setAction("explain");
        setTask(undefined);
        setModelResponse(undefined);
        try {
          const next = await gateway.invokeModAction<unknown>(
            MOD_ID,
            capability,
            {
              gatewayMode: aiMode,
              prompt: "解释当前市场行情",
            },
          );
          if (aiMode === "model") {
            setModelResponse(parseModelResponse(next));
            setAction(undefined);
          } else {
            const agentTask = next as AgentTask;
            setTask(agentTask);
            if (
              agentTask.status === "queued" ||
              agentTask.status === "running"
            ) {
              await pollTask(agentTask.id);
            } else {
              setAction(undefined);
            }
          }
        } catch (reason) {
          setError(errorMessage(reason));
          setAction(undefined);
        }
      }
    },
    [action, aiMode, gateway, pollTask],
  );

  const asOf = snapshot ? formatTimestamp(snapshot.data.asOf) : "—";
  const answer = task ? taskAnswer(task) : undefined;

  return (
    <div className="market-root">
      <header className="market-header">
        <div>
          <h1>市场行情</h1>
          <p>市场宽度、主要指数与成交额榜的最后成功快照</p>
        </div>
        <div className="market-header-controls">
          <div>
            <span className="control-label">AI 调用方式</span>
            <div className="ai-mode-switch" role="group" aria-label="AI 调用方式">
              <button
                type="button"
                aria-pressed={aiMode === "model"}
                disabled={action === "explain"}
                onClick={() => {
                  setAiMode("model");
                  setTask(undefined);
                  setModelResponse(undefined);
                }}
              >
                模型
              </button>
              <button
                type="button"
                aria-pressed={aiMode === "agent"}
                disabled={action === "explain"}
                onClick={() => {
                  setAiMode("agent");
                  setTask(undefined);
                  setModelResponse(undefined);
                }}
              >
                Agent
              </button>
            </div>
            <span className="ai-mode-note">
              {aiMode === "agent" ? "保留当前 Mod 的长期上下文" : "一次性模型调用"}
            </span>
          </div>
          <div className="snapshot-time">
            <span>数据时间</span>
            <strong>{asOf}</strong>
          </div>
        </div>
      </header>

      {snapshot && staleSnapshot(snapshot) ? (
        <div className="stale-banner" role="status">
          当前展示的是超过 24 小时的最后成功数据；刷新失败不会清空页面。
        </div>
      ) : null}
      {error ? <div className="module-error" role="alert">{error}</div> : null}
      <div className="module-status" aria-live="polite">
        {loading ? "正在读取最后成功快照…" : null}
        {action === "refresh" ? "正在刷新行情…" : null}
        {action === "explain"
          ? aiMode === "agent"
            ? "Agent 正在解释行情…"
            : "模型正在解释行情…"
          : null}
      </div>

      <StructuredView
        schema={view}
        data={snapshot?.data ?? {}}
        onAction={(capability) => void handleAction(capability)}
        onRowSelect={(blockId, row) => {
          if (blockId !== "leaders" || typeof row.symbol !== "string") return;
          bridge.emit("security.selected", {
            symbol: row.symbol,
            market: typeof row.market === "string" ? row.market : "CN",
          });
        }}
      />

      {task ? (
        <section className="agent-result" aria-live="polite">
          <h2>Agent 行情解释</h2>
          <p className="agent-task-state">任务状态：{task.status}</p>
          {answer ? <pre>{answer}</pre> : null}
          {task.error ? <p className="agent-task-error">{task.error}</p> : null}
        </section>
      ) : null}
      {modelResponse ? (
        <section className="agent-result" aria-live="polite">
          <h2>模型行情解释</h2>
          <p className="agent-task-state">
            {modelResponse.adapter} · {modelResponse.model}
          </p>
          <pre>{modelResponse.answer}</pre>
        </section>
      ) : null}
    </div>
  );
}

export const MarketDailyApp = MarketPulseApp;
export type MarketDailyAppProps = MarketPulseAppProps;
