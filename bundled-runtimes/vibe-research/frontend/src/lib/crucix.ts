import { waitForVibeDeskConfig } from "@/lib/vibedesk";

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

  const headers: Record<string, string> = { "X-User-Id": config.userId };
  if (config.accessToken) headers.Authorization = `Bearer ${config.accessToken}`;
  const response = await fetch(`${config.gatewayOrigin}/api/crucix/snapshot`, { headers });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof body?.detail === "string" ? body.detail : "Crucix 数据暂未就绪");
  }
  if (body?.contract !== "newma-desk.crucix-intelligence.v1") {
    throw new Error("Crucix 数据格式不兼容");
  }
  return body as CrucixSnapshot;
}
