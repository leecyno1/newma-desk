import { createGatewayClient, GatewayError } from "@newma-desk/mod-sdk";
import { getVibeDeskConfig, waitForVibeDeskConfig } from "@/lib/vibedesk";

export interface CrucixNewsItem {
  title: string;
  source: string;
  type: string;
  publishedAt: string | null;
  region: string;
  urgent: boolean;
  url?: string;
}

export interface CrucixObservation {
  id: string;
  label: string;
  value: number | null;
  kind: "spot" | "futures" | "inventory" | "unknown";
  unit: string | null;
  frequency: string;
  period: string | null;
  observedAt: string | null;
  source: {
    id: string; label: string; seriesId: string; url: string | null;
    collectorId?: string; originalSource?: string; originalSeriesId?: string;
    originalUrl?: string | null; fallbackReason?: string;
  } | null;
  note: string;
  freshness: CrucixSnapshot["freshness"];
}

export interface CrucixSnapshot {
  contract: "newma-desk.crucix-intelligence.v1";
  asOf: string | null;
  freshness: {
    status: "fresh" | "stale" | "unknown";
    ageSeconds: number | null;
    staleAfterSeconds: number;
  };
  sourceHealth: {
    queried: number;
    ok: number;
    failed: number;
    partial?: number;
    stale?: number;
    unknown?: number;
    items: Array<{ source: string; status: "ok" | "stale" | "error" | "partial" | "unknown"; reason?: string }>;
  };
  news: CrucixNewsItem[];
  macro: {
    gscpi: {
      value: number | null;
      date: string | null;
      interpretation: string;
      period?: string | null;
      dateBasis?: "period";
      unit?: string;
      source?: { id: string; label: string; seriesId: string; url: string };
      freshness?: CrucixSnapshot["freshness"];
    } | null;
    energy: {
      wti: number | null;
      brent: number | null;
      naturalGas: number | null;
      crudeStocks: number | null;
      wtiRecent: Array<number | { value: number; date?: string }>;
      signals: string[];
      observations?: CrucixObservation[];
      note?: string;
    };
  };
  provenance: {
    project: string;
    license: string;
    mode: string;
  };
}

export function crucixSourcesDegraded(snapshot: CrucixSnapshot): boolean {
  const health = snapshot.sourceHealth;
  return health.queried === 0 || health.ok !== health.queried || health.items.some(item => item.status !== "ok");
}

export function crucixEnergyObservations(energy: CrucixSnapshot["macro"]["energy"]): CrucixObservation[] {
  return energy.observations ?? ([
    ["wti", "WTI", energy.wti], ["brent", "Brent", energy.brent],
    ["naturalGas", "天然气", energy.naturalGas], ["crudeStocks", "原油库存", energy.crudeStocks],
  ] as const).map(([id, label, value]) => ({
    id, label: `${label}（口径待核验）`, value, kind: "unknown", frequency: "unknown", unit: null,
    period: null, observedAt: null, source: null,
    note: "旧快照未保留来源、报价类型与数据时间，不能视为 EIA 现货或实时价格。",
    freshness: { status: "unknown", ageSeconds: null, staleAfterSeconds: 0 },
  }));
}

export async function loadCrucixSnapshot(): Promise<CrucixSnapshot | null> {
  const config = await waitForVibeDeskConfig();
  if (!config) return null;
  if (!config.accessToken || !config.instanceId || !config.permissions?.includes("market.read")) {
    throw new Error("Crucix 读取授权不完整，请从 Desk 重新打开页面。");
  }
  const scopeOf = (value: typeof config | null) => JSON.stringify(value && [
    value.apiOrigin, value.userId, value.workspaceId, value.moduleId,
    value.instanceId, value.accessToken, value.permissions,
  ]);
  const scope = scopeOf(config);
  const client = createGatewayClient({
    baseUrl: config.apiOrigin, accessToken: config.accessToken, instanceId: config.instanceId,
    fetch: (url, init) => fetch(url, { ...init, cache: "no-store", signal: AbortSignal.timeout(15000) }),
  });
  let body: CrucixSnapshot;
  try {
    body = await client.invokeModAction<CrucixSnapshot>(config.moduleId, "crucix.snapshot", {});
  } catch (error) {
    const status = error instanceof GatewayError ? error.status : undefined;
    throw new Error(status === 401 || status === 403
      ? "Crucix 读取授权已失效或不足，请重新打开页面核对权限。"
      : `Crucix 数据暂未就绪${status ? `（HTTP ${status}）` : ""}；未自动重试。`);
  }
  if (scope !== scopeOf(getVibeDeskConfig())) {
    throw new Error("工作区或授权已变化，旧 Crucix 结果未采用。");
  }
  if (body?.contract !== "newma-desk.crucix-intelligence.v1") {
    throw new Error("Crucix 数据格式不兼容");
  }
  return body as CrucixSnapshot;
}
