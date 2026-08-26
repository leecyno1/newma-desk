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
    items: Array<{ source: string; status: "ok" | "stale" | "error" }>;
  };
  news: CrucixNewsItem[];
  macro: {
    gscpi: {
      value: number | null;
      date: string | null;
      interpretation: string;
    } | null;
    energy: {
      wti: number | null;
      brent: number | null;
      naturalGas: number | null;
      crudeStocks: number | null;
      wtiRecent: Array<number | { value: number; date?: string }>;
      signals: string[];
    };
  };
  provenance: {
    project: string;
    license: string;
    mode: string;
  };
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
