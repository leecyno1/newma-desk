import i18n from "@/i18n";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ArrowRight, GitCompare, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type EquityPoint, type RunListItem, type RunData } from "@/lib/api";
import { SkeletonChart, SkeletonMetrics } from "@/components/common/Skeleton";
import {
  assessStrategyLedgerComparison,
  buildStrategyComparisonContext,
  type StrategyComparisonAssessment,
} from "@/lib/strategyLedger";
import { createVibeDeskSnapshotCache, registerVibeDeskContextSummary, subscribeVibeDeskConfig } from "@/lib/vibedesk";

const EquityChartOverlay = lazy(() =>
  import("@/components/charts/EquityChartOverlay").then((module) => ({
    default: module.EquityChartOverlay,
  })),
);

interface MetricDef {
  key: string;
  label: string;
  type: "pct" | "num" | "int" | "days";
  higherIsBetter: boolean;
}

interface CompareRunSnapshot {
  metrics: Record<string, number> | null;
  curve: EquityPoint[];
}

function isActiveRun(status: string | undefined) {
  return ["queued", "pending", "running", "in_progress"].includes(String(status || "").toLowerCase());
}

function fmt(v: unknown, type: "pct" | "num" | "int" | "days" = "num"): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "\u2014";
  if (type === "pct") return (n * 100).toFixed(2) + "%";
  if (type === "int") return n.toFixed(0);
  if (type === "days") return n.toFixed(1);
  return n.toFixed(3);
}

function diffClass(a: unknown, b: unknown, higherIsBetter: boolean): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "";
  const better = higherIsBetter ? nb > na : nb < na;
  const worse = higherIsBetter ? nb < na : nb > na;
  return better ? "text-green-600 dark:text-green-400" : worse ? "text-red-600 dark:text-red-400" : "";
}

function diffStr(a: unknown, b: unknown, type: "pct" | "num" | "int" | "days"): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "\u2014";
  const d = nb - na;
  return (d > 0 ? "+" : "") + fmt(d, type);
}

function truncatePrompt(prompt: string | undefined, maxLen = 40): string {
  if (!prompt) return "";
  const trimmed = prompt.replace(/\n/g, " ").trim();
  return trimmed.length > maxLen ? trimmed.slice(0, maxLen) + "\u2026" : trimmed;
}

function runLabel(r: RunListItem): string {
  const summary = truncatePrompt(r.prompt);
  if (summary) return summary;
  return r.run_id;
}

const METRICS: MetricDef[] = [
  { key: "total_return",           label: i18n.t("compare.totalReturn"),         type: "pct", higherIsBetter: true },
  { key: "annualized_return",      label: i18n.t("compare.annualizedReturn"),    type: "pct", higherIsBetter: true },
  { key: "sharpe",                 label: i18n.t("compare.sharpeRatio"),         type: "num", higherIsBetter: true },
  { key: "calmar_ratio",           label: i18n.t("compare.calmarRatio"),         type: "num", higherIsBetter: true },
  { key: "sortino_ratio",          label: i18n.t("compare.sortinoRatio"),        type: "num", higherIsBetter: true },
  { key: "max_drawdown",           label: i18n.t("compare.maxDrawdown"),         type: "pct", higherIsBetter: false },
  { key: "volatility",             label: i18n.t("compare.volatility"),           type: "pct", higherIsBetter: false },
  { key: "win_rate",               label: i18n.t("compare.winRate"),             type: "pct", higherIsBetter: true },
  { key: "profit_factor",          label: i18n.t("compare.profitFactor"),        type: "num", higherIsBetter: true },
  { key: "avg_win",                label: i18n.t("compare.avgWin"),              type: "pct", higherIsBetter: true },
  { key: "avg_loss",               label: i18n.t("compare.avgLoss"),             type: "pct", higherIsBetter: false },
  { key: "trade_count",            label: i18n.t("compare.trades"),               type: "int", higherIsBetter: true },
  { key: "max_consecutive_losses", label: i18n.t("compare.maxConsecLosses"),   type: "int", higherIsBetter: false },
  { key: "exposure_time",          label: i18n.t("compare.exposureTime"),        type: "pct", higherIsBetter: true },
  { key: "avg_holding_period",     label: i18n.t("compare.avgHoldingPeriod"),   type: "days", higherIsBetter: false },
];

// Also accept backend aliases
const METRIC_ALIASES: Record<string, string> = {
  annual_return: "annualized_return",
  calmar: "calmar_ratio",
  sortino: "sortino_ratio",
  profit_loss_ratio: "profit_factor",
  max_consec_loss: "max_consecutive_losses",
  max_consecutive_loss: "max_consecutive_losses",
  avg_hold_days: "avg_holding_period",
  avg_holding_days: "avg_holding_period",
};

const COMPARISON_FIELD_KEYS = {
  symbols: "compare.comparisonFields.symbols",
  market: "compare.comparisonFields.market",
  datasetWindow: "compare.comparisonFields.datasetWindow",
  timeframe: "compare.comparisonFields.timeframe",
  dataSources: "compare.comparisonFields.dataSources",
  commission: "compare.comparisonFields.commission",
} as const;

const READINESS_REASON_KEYS = {
  missingLedger: "compare.readinessReasons.missingLedger",
  missingDatasetIdentity: "compare.readinessReasons.missingDatasetIdentity",
  differentSymbols: "compare.readinessReasons.differentSymbols",
  differentMarket: "compare.readinessReasons.differentMarket",
  differentWindow: "compare.readinessReasons.differentWindow",
  differentTimeframe: "compare.readinessReasons.differentTimeframe",
  missingDataSources: "compare.readinessReasons.missingDataSources",
  differentDataSources: "compare.readinessReasons.differentDataSources",
  differentCommission: "compare.readinessReasons.differentCommission",
  missingCommission: "compare.readinessReasons.missingCommission",
  unfinishedExperiment: "compare.readinessReasons.unfinishedExperiment",
  lowTradeSample: "compare.readinessReasons.lowTradeSample",
  zeroCostAssumption: "compare.readinessReasons.zeroCostAssumption",
  missingRiskMetrics: "compare.readinessReasons.missingRiskMetrics",
  limitedQuality: "compare.readinessReasons.limitedQuality",
} as const;

function comparisonFieldLabel(field: string): string {
  const key = COMPARISON_FIELD_KEYS[field as keyof typeof COMPARISON_FIELD_KEYS];
  return key ? i18n.t(key) : field;
}

function readinessReasonLabel(code: string): string {
  const key = READINESS_REASON_KEYS[code as keyof typeof READINESS_REASON_KEYS];
  return key ? i18n.t(key) : code;
}

function resolveMetric(metrics: Record<string, number> | null, key: string): number | undefined {
  if (!metrics) return undefined;
  if (metrics[key] !== undefined) return metrics[key];
  // Check if any alias maps to this key
  for (const [alias, canonical] of Object.entries(METRIC_ALIASES)) {
    if (canonical === key && metrics[alias] !== undefined) return metrics[alias];
  }
  return undefined;
}

export function Compare() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [leftData, setLeftData] = useState<Record<string, number> | null>(null);
  const [rightData, setRightData] = useState<Record<string, number> | null>(null);
  const [leftCurve, setLeftCurve] = useState<EquityPoint[]>([]);
  const [rightCurve, setRightCurve] = useState<EquityPoint[]>([]);
  const [leftLoading, setLeftLoading] = useState(false);
  const [rightLoading, setRightLoading] = useState(false);
  const [cacheRevision, setCacheRevision] = useState(0);
  const runsCache = useMemo(
    () => createVibeDeskSnapshotCache<RunListItem[]>("compare:runs", 1, 1024 * 1024),
    [cacheRevision],
  );
  const leftCache = useMemo(
    () => createVibeDeskSnapshotCache<CompareRunSnapshot>(`compare:run:${leftId || "none"}`, 1, 1024 * 1024),
    [cacheRevision, leftId],
  );
  const rightCache = useMemo(
    () => createVibeDeskSnapshotCache<CompareRunSnapshot>(`compare:run:${rightId || "none"}`, 1, 1024 * 1024),
    [cacheRevision, rightId],
  );
  const runsIdentityRef = useRef(cacheRevision);
  const leftResourceRef = useRef("");
  const rightResourceRef = useRef("");

  useEffect(() => {
    const cached = runsCache.read()?.value ?? [];
    const identityChanged = runsIdentityRef.current !== cacheRevision;
    runsIdentityRef.current = cacheRevision;
    if (identityChanged || runs.length === 0) {
      setRuns(cached);
      setLeftId(cached.length >= 2 ? cached[1]!.run_id : cached[0]?.run_id || "");
      setRightId(cached.length >= 2 ? cached[0]!.run_id : "");
    }
    api.listRuns().then((items) => {
      const nextRuns = Array.isArray(items) ? items : [];
      setRuns(nextRuns);
      runsCache.write(nextRuns.filter((run) => !isActiveRun(run.status)));
      setLeftId((current) => current || (nextRuns.length >= 2 ? nextRuns[1]!.run_id : nextRuns[0]?.run_id || ""));
      setRightId((current) => current || (nextRuns.length >= 2 ? nextRuns[0]!.run_id : ""));
    }).catch((error) => {
      toast.error(error instanceof Error ? error.message : i18n.t("compare.loadError"));
    });
  }, [cacheRevision, runsCache]);
  useEffect(() => subscribeVibeDeskConfig(() => setCacheRevision((value) => value + 1)), []);

  useEffect(() => {
    if (leftId) {
      const resource = `${cacheRevision}:${leftId}`;
      const resourceChanged = leftResourceRef.current !== resource;
      leftResourceRef.current = resource;
      const cached = leftCache.read()?.value;
      if (resourceChanged) {
        setLeftData(cached?.metrics ?? null);
        setLeftCurve(cached?.curve ?? []);
      }
      setLeftLoading(true);
      api.getRun(leftId).then((d: RunData) => {
        const next = { metrics: d.metrics || null, curve: d.equity_curve || [] };
        setLeftData(next.metrics);
        setLeftCurve(next.curve);
        if (!isActiveRun(d.status)) leftCache.write(next);
      }).catch((error) => {
        toast.error(error instanceof Error ? error.message : i18n.t("compare.loadError"));
      })
        .finally(() => setLeftLoading(false));
    } else {
      setLeftData(null);
      setLeftCurve([]);
    }
  }, [cacheRevision, leftCache, leftId]);

  useEffect(() => {
    if (rightId) {
      const resource = `${cacheRevision}:${rightId}`;
      const resourceChanged = rightResourceRef.current !== resource;
      rightResourceRef.current = resource;
      const cached = rightCache.read()?.value;
      if (resourceChanged) {
        setRightData(cached?.metrics ?? null);
        setRightCurve(cached?.curve ?? []);
      }
      setRightLoading(true);
      api.getRun(rightId).then((d: RunData) => {
        const next = { metrics: d.metrics || null, curve: d.equity_curve || [] };
        setRightData(next.metrics);
        setRightCurve(next.curve);
        if (!isActiveRun(d.status)) rightCache.write(next);
      }).catch((error) => {
        toast.error(error instanceof Error ? error.message : i18n.t("compare.loadError"));
      })
        .finally(() => setRightLoading(false));
    } else {
      setRightData(null);
      setRightCurve([]);
    }
  }, [cacheRevision, rightCache, rightId]);

  const leftRun = runs.find((r) => r.run_id === leftId);
  const rightRun = runs.find((r) => r.run_id === rightId);
  const loading = leftLoading || rightLoading;
  const hasData = Boolean(leftData || rightData);
  const comparison = useMemo(
    () => assessStrategyLedgerComparison(leftRun, rightRun),
    [leftRun, rightRun],
  );
  const comparisonContext = useMemo(
    () => buildStrategyComparisonContext(leftRun, rightRun),
    [leftRun, rightRun],
  );

  useEffect(
    () => registerVibeDeskContextSummary(() => comparisonContext),
    [comparisonContext],
  );

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2" data-mod-page-title>
        <GitCompare className="h-5 w-5" /> {i18n.t("compare.title")}
      </h1>

      {/* Selectors */}
      <div className="flex gap-4 items-end">
        <div className="flex-1">
          <label className="text-xs text-muted-foreground block mb-1">{i18n.t("compare.baseline")}</label>
          <select value={leftId} onChange={(e) => setLeftId(e.target.value)} className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" title={leftRun?.prompt || leftId}>
            <option value="">{i18n.t("compare.select")}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
        <ArrowRight className="h-5 w-5 text-muted-foreground mb-2 shrink-0" />
        <div className="flex-1">
          <label className="text-xs text-muted-foreground block mb-1">{i18n.t("compare.compare")}</label>
          <select value={rightId} onChange={(e) => setRightId(e.target.value)} className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" title={rightRun?.prompt || rightId}>
            <option value="">{i18n.t("compare.select")}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
      </div>

      {comparison ? <ComparisonReadiness assessment={comparison} /> : null}

      {/* Loading state — show skeletons while a selected run's data is in flight */}
      {loading && !hasData && (
        <div className="space-y-6">
          <div className="border rounded-xl p-4">
            <h2 className="text-sm font-medium text-muted-foreground mb-2">{i18n.t("compare.equityDrawdown")}</h2>
            <SkeletonChart height={320} />
          </div>
          <div className="border rounded-xl overflow-hidden">
            <SkeletonMetrics />
          </div>
        </div>
      )}

      {/* Equity curve overlay */}
      {(leftCurve.length > 0 || rightCurve.length > 0) && (
        <div className="border rounded-xl p-4">
          <h2 className="text-sm font-medium text-muted-foreground mb-2">{i18n.t("compare.equityDrawdown")}</h2>
          <Suspense fallback={<SkeletonChart height={320} />}>
            <EquityChartOverlay
              leftCurve={leftCurve}
              rightCurve={rightCurve}
              leftLabel={leftRun ? truncatePrompt(leftRun.prompt, 20) || "Baseline" : "Baseline"}
              rightLabel={rightRun ? truncatePrompt(rightRun.prompt, 20) || "Compare" : "Compare"}
            />
          </Suspense>
        </div>
      )}

      {/* Metrics table */}
      {(leftData || rightData) && (
        <div className="border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">{i18n.t("compare.metric")}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{i18n.t("compare.baselineCol")}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{i18n.t("compare.compareCol")}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{i18n.t("compare.delta")}</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map(({ key, label, type, higherIsBetter }) => {
                const lv = resolveMetric(leftData, key);
                const rv = resolveMetric(rightData, key);
                return (
                  <tr key={key} className="border-b last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium">{label}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmt(lv, type)}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmt(rv, type)}</td>
                    <td className={cn("px-4 py-2.5 text-right font-mono tabular-nums font-semibold", diffClass(lv, rv, higherIsBetter))}>{diffStr(lv, rv, type)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!hasData && !loading && (
        <div className="text-center py-16 text-muted-foreground">
          <GitCompare className="h-12 w-12 mx-auto mb-3 opacity-20" />
          <p className="text-sm">{i18n.t("compare.selectTwoRuns")}</p>
        </div>
      )}
    </div>
  );
}

function ComparisonReadiness({ assessment }: { assessment: StrategyComparisonAssessment }) {
  const ready = assessment.level === "ready";
  const notComparable = assessment.level === "not_comparable" || assessment.level === "legacy";
  const translatedFields = assessment.matchedFields.map(comparisonFieldLabel);

  return (
    <section
      className={cn(
        "rounded-xl border p-4",
        ready && "border-success/30 bg-success/5",
        assessment.level === "caution" && "border-amber-500/30 bg-amber-500/5",
        notComparable && "border-destructive/30 bg-destructive/5",
      )}
      aria-labelledby="comparison-readiness-heading"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            {ready ? (
              <ShieldCheck className="h-5 w-5 text-success" />
            ) : (
              <AlertTriangle className={cn(
                "h-5 w-5",
                assessment.level === "caution" ? "text-amber-600" : "text-destructive",
              )} />
            )}
            <h2 id="comparison-readiness-heading" className="font-semibold">
              {i18n.t("compare.readinessTitle")}
            </h2>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {i18n.t(`compare.readinessLevels.${assessment.level}`)}
          </p>
        </div>
        <span className="rounded border bg-background/70 px-2.5 py-1 text-xs font-medium">
          {i18n.t(`compare.comparisonModes.${assessment.mode}`)}
        </span>
      </div>

      {assessment.reasonCodes.length > 0 ? (
        <ul className="mt-3 grid gap-1.5 text-sm">
          {assessment.reasonCodes.map((code) => (
            <li key={code} className="flex items-start gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
              <span>{readinessReasonLabel(code)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm">{i18n.t("compare.readinessReadyBody")}</p>
      )}

      {translatedFields.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{i18n.t("compare.matchedEvidence")}</span>
          {translatedFields.map((field) => (
            <span key={field} className="rounded border bg-background/70 px-2 py-0.5">{field}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
