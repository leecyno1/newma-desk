export type DimensionStatus = "ready" | "degraded" | "on-demand" | "planned";

export interface SectorFlow {
  name?: string; sector?: string; industry?: string;
  inflow?: number; outflow?: number; net?: number; pct?: number; firms?: number;
}

export interface TurnoverLeader {
  code?: string; name?: string; price?: number; pct?: number; amount?: number; industry?: string;
}

export interface CapitalFlowDimension {
  id: string; name: string; status: DimensionStatus; frequency: string;
  lag: string; source: string; note?: string;
}

export interface CapitalFlowDashboard {
  schemaVersion: string; generatedAt: string; marketDate: string | null;
  summary: {
    sectorNetYi: number; sectorInflowYi: number; sectorOutflowYi: number;
    top20TurnoverYi: number; active: number | string | null;
  };
  sectors: SectorFlow[];
  turnoverLeaders: TurnoverLeader[];
  security: { code: string; fundFlow: unknown; margin: unknown } | null;
  dimensions: CapitalFlowDimension[];
  sources: Array<{ name: string; url: string }>;
  upstream: { status: "ready" | "degraded"; base: string };
}
