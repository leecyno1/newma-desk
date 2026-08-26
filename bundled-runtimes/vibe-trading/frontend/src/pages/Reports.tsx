import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  GitCompare,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingDown,
  XCircle,
} from "lucide-react";
import {
  api,
  type QuickRunRequest,
  type QuickRunTemplateId,
  type QuickRunStatusResponse,
  type RunListItem,
} from "@/lib/api";
import { formatMetricVal } from "@/lib/formatters";
import { buildStrategyLedgerContext, strategyLedgerForRun } from "@/lib/strategyLedger";
import { cn } from "@/lib/utils";
import { createVibeDeskSnapshotCache, registerVibeDeskContextSummary, subscribeVibeDeskConfig } from "@/lib/vibedesk";

const REPORT_SCAN_LIMIT = 100;
const ACTIVE_RUN_STATUSES = new Set(["queued", "pending", "running", "in_progress"]);
const DEFAULT_INITIAL_CASH = 100_000;
const DEFAULT_COMMISSION = 0;
const DEFAULT_SMA_FAST_WINDOW = 20;
const DEFAULT_SMA_SLOW_WINDOW = 50;
const REFRESH_INTERVAL_MS = 5_000;

type SortMode = "created_desc" | "created_asc" | "return_desc" | "sharpe_desc";
type QuickBacktestFormState = {
  templateId: QuickRunTemplateId;
  symbol: string;
  startDate: string;
  endDate: string;
  initialCash: string;
  commission: string;
  fastWindow: string;
  slowWindow: string;
};

type TrackedQuickRunDraft = {
  run_id: string;
  status: string;
  created_at: string;
  prompt: string;
  codes: string[];
  start_date: string;
  end_date: string;
};

export function Reports() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("created_desc");
  const [error, setError] = useState<string | null>(null);
  const [trackedRunIds, setTrackedRunIds] = useState<string[]>([]);
  const [trackedRunDrafts, setTrackedRunDrafts] = useState<Record<string, TrackedQuickRunDraft>>({});
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createInfo, setCreateInfo] = useState<string | null>(null);
  const [cancelingRunIds, setCancelingRunIds] = useState<Record<string, boolean>>({});
  const [form, setForm] = useState<QuickBacktestFormState>(() => buildInitialFormState());
  const [cacheRevision, setCacheRevision] = useState(0);
  const reportsCache = useMemo(() => createVibeDeskSnapshotCache<RunListItem[]>("reports:completed", 1, 1024 * 1024), [cacheRevision]);
  const runsRef = useRef(runs);
  const cacheRevisionRef = useRef(cacheRevision);
  runsRef.current = runs;

  async function loadReports(mode: "initial" | "refresh" = "refresh") {
    if (mode === "initial") setLoading(true);
    else setRefreshing(true);
    setError(null);
    const cached = reportsCache.read()?.value ?? [];
    if (mode === "initial" && cached.length && runsRef.current.length === 0) setRuns(cached);
    try {
      const list = await api.listRuns(REPORT_SCAN_LIMIT);
      const merged = await mergeRunsWithTrackedStatuses(
        Array.isArray(list) ? list : [],
        trackedRunIds,
        trackedRunDrafts,
      );
      const trackedSet = new Set(trackedRunIds);
      const visibleRuns = merged.filter((run) => shouldDisplayRun(run, trackedSet));
      setRuns(visibleRuns);
      reportsCache.write(visibleRuns.filter((run) => (
        !isActiveRunStatus(run.status) && isBacktestReportRun(run)
      )));
    } catch (err) {
      setError((runsRef.current.length || cached.length)
        ? "Update failed. Showing the last completed reports."
        : err instanceof Error ? err.message : t("reports.loadError"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const cached = reportsCache.read()?.value ?? [];
    const identityChanged = cacheRevisionRef.current !== cacheRevision;
    cacheRevisionRef.current = cacheRevision;
    if (identityChanged || runsRef.current.length === 0) {
      setRuns(cached);
      runsRef.current = cached;
    }
    void loadReports("initial");
  }, [cacheRevision, reportsCache]);
  useEffect(() => subscribeVibeDeskConfig(() => setCacheRevision((value) => value + 1)), []);

  const trackedRunIdsSet = useMemo(() => new Set(trackedRunIds), [trackedRunIds]);
  const statusOptions = useMemo(() => {
    const values = Array.from(new Set(
      runs
        .filter((run) => shouldDisplayRun(run, trackedRunIdsSet))
        .map((run) => run.status || "unknown"),
    )).sort();
    return ["all", ...values];
  }, [runs, trackedRunIdsSet]);

  const activeTrackedRunIds = useMemo(() => {
    const runsById = new Map(runs.map((run) => [run.run_id, run]));
    return trackedRunIds.filter((runId) => {
      const run = runsById.get(runId);
      return run == null || isActiveRunStatus(run.status);
    });
  }, [runs, trackedRunIds]);

  useEffect(() => {
    if (activeTrackedRunIds.length === 0) return;
    const timer = window.setInterval(() => {
      void loadReports("refresh");
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [activeTrackedRunIds]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const startMs = startDate ? Date.parse(startDate) : Number.NEGATIVE_INFINITY;
    const endMs = endDate ? Date.parse(`${endDate}T23:59:59`) : Number.POSITIVE_INFINITY;

    return [...runs]
      .filter((run) => shouldDisplayRun(run, trackedRunIdsSet))
      .filter((run) => {
        if (statusFilter !== "all" && (run.status || "unknown") !== statusFilter) return false;
        const created = Date.parse(run.created_at);
        if (Number.isFinite(created) && (created < startMs || created > endMs)) return false;
        if (!needle) return true;
        const haystack = [
          run.run_id,
          run.status,
          run.prompt,
          ...(run.codes || []),
          run.start_date,
          run.end_date,
          run.strategy_ledger?.strategy.id,
          run.strategy_ledger?.strategy.name,
          run.strategy_ledger?.strategy.version,
          run.strategy_ledger?.strategy.template_id,
        ].filter(Boolean).join(" ").toLowerCase();
        return haystack.includes(needle);
      })
      .sort((left, right) => compareRuns(left, right, sortMode));
  }, [runs, query, statusFilter, startDate, endDate, sortMode, trackedRunIdsSet]);

  const ledgerContext = useMemo(
    () => buildStrategyLedgerContext(filtered, {
      query,
      status: statusFilter,
      startDate,
      endDate,
      sort: sortMode,
    }),
    [filtered, query, statusFilter, startDate, endDate, sortMode],
  );

  useEffect(
    () => registerVibeDeskContextSummary(() => ledgerContext),
    [ledgerContext],
  );

  async function submitQuickRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const symbol = form.symbol.trim().toUpperCase();
    const startDateValue = form.startDate.trim();
    const endDateValue = form.endDate.trim();

    setCreateError(null);
    setCreateInfo(null);

    if (!symbol) {
      setCreateError(t("reports.quickSymbolRequired"));
      return;
    }
    if (!startDateValue || !endDateValue) {
      setCreateError(t("reports.quickDateRequired"));
      return;
    }
    const startDateMs = Date.parse(startDateValue);
    const endDateMs = Date.parse(`${endDateValue}T23:59:59`);
    if (!Number.isFinite(startDateMs) || !Number.isFinite(endDateMs)) {
      setCreateError(t("reports.quickDateRequired"));
      return;
    }
    if (endDateMs < startDateMs) {
      setCreateError(t("reports.quickDateOrder"));
      return;
    }

    const initialCash = Number(form.initialCash);
    if (!Number.isFinite(initialCash) || initialCash <= 0) {
      setCreateError(t("reports.quickInitialCashRequired"));
      return;
    }

    const commission = Number(form.commission);
    if (!Number.isFinite(commission) || commission < 0) {
      setCreateError(t("reports.quickCommissionInvalid"));
      return;
    }

    const body: QuickRunRequest = {
      template_id: form.templateId,
      symbol,
      start_date: startDateValue,
      end_date: endDateValue,
      params: {
        initial_cash: initialCash,
        commission,
      },
    };

    if (form.templateId === "sma_crossover") {
      const fastWindow = Number(form.fastWindow);
      const slowWindow = Number(form.slowWindow);
      if (!Number.isFinite(fastWindow) || !Number.isFinite(slowWindow) || fastWindow <= 0 || slowWindow <= 0) {
        setCreateError(t("reports.quickSmaRequired"));
        return;
      }
      if (fastWindow >= slowWindow) {
        setCreateError(t("reports.quickSmaOrder"));
        return;
      }
      body.params = {
        ...body.params,
        fast_window: fastWindow,
        slow_window: slowWindow,
      };
    }

    setCreating(true);
    try {
      const created = await api.createQuickRun(body);
      const runId = created.run_id;
      setTrackedRunIds((current) => (current.includes(runId) ? current : [runId, ...current]));
      setTrackedRunDrafts((current) => ({
        ...current,
        [runId]: buildTrackedQuickRunDraft(runId, form, symbol, created.status),
      }));
      setCreateInfo(t("reports.quickQueued", { runId }));
      await loadReports("refresh");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t("reports.quickCreateFailed"));
    } finally {
      setCreating(false);
    }
  }

  async function cancelRun(runId: string) {
    setCancelingRunIds((current) => ({ ...current, [runId]: true }));
    setCreateError(null);
    try {
      await api.cancelRun(runId);
      setCreateInfo(t("reports.quickCancelled", { runId }));
      await loadReports("refresh");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t("reports.quickCancelFailed"));
    } finally {
      setCancelingRunIds((current) => {
        const next = { ...current };
        delete next[runId];
        return next;
      });
    }
  }

  return (
    <div className="min-h-screen p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="flex flex-col gap-4 border-b pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium text-muted-foreground">
              <FileText className="h-3.5 w-3.5" />
              {t("reports.badge")}
            </div>
            <div data-mod-page-title>
              <h1 className="text-3xl font-bold tracking-tight">{t("reports.title")}</h1>
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t("reports.subtitle")}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadReports("refresh")}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition hover:bg-muted disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {t("reports.refresh")}
          </button>
        </section>

        <section className="rounded-md border p-5">
          <div className="flex flex-col gap-2 border-b pb-4">
            <h2 className="text-lg font-semibold">{t("reports.quickTitle")}</h2>
            <p className="max-w-3xl text-sm text-muted-foreground">{t("reports.quickSubtitle")}</p>
          </div>

          <form className="mt-4 grid gap-4" onSubmit={submitQuickRun}>
            <div className="grid gap-4 lg:grid-cols-[180px_minmax(180px,1fr)_170px_170px_150px_140px]">
              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickTemplate")}</span>
                <select
                  value={form.templateId}
                  onChange={(event) => setForm((current) => ({ ...current, templateId: event.target.value as QuickRunTemplateId }))}
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                >
                  <option value="buy_and_hold">{t("reports.quickTemplateBuyAndHold")}</option>
                  <option value="sma_crossover">{t("reports.quickTemplateSma")}</option>
                </select>
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickSymbol")}</span>
                <input
                  value={form.symbol}
                  onChange={(event) => setForm((current) => ({ ...current, symbol: event.target.value.toUpperCase() }))}
                  placeholder={t("reports.quickSymbolPlaceholder")}
                  className="rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary"
                />
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.startDate")}</span>
                <input
                  type="date"
                  value={form.startDate}
                  onChange={(event) => setForm((current) => ({ ...current, startDate: event.target.value }))}
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.endDate")}</span>
                <input
                  type="date"
                  value={form.endDate}
                  onChange={(event) => setForm((current) => ({ ...current, endDate: event.target.value }))}
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickInitialCash")}</span>
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={form.initialCash}
                  onChange={(event) => setForm((current) => ({ ...current, initialCash: event.target.value }))}
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>

              <label className="grid gap-1.5">
                <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickCommission")}</span>
                <input
                  type="number"
                  min={0}
                  step={0.0001}
                  value={form.commission}
                  onChange={(event) => setForm((current) => ({ ...current, commission: event.target.value }))}
                  className="rounded-md border bg-background px-3 py-2 text-sm"
                />
              </label>
            </div>

            {form.templateId === "sma_crossover" ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:max-w-md">
                <label className="grid gap-1.5">
                  <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickSmaFast")}</span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={form.fastWindow}
                    onChange={(event) => setForm((current) => ({ ...current, fastWindow: event.target.value }))}
                    className="rounded-md border bg-background px-3 py-2 text-sm"
                  />
                </label>

                <label className="grid gap-1.5">
                  <span className="text-xs font-medium uppercase text-muted-foreground">{t("reports.quickSmaSlow")}</span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={form.slowWindow}
                    onChange={(event) => setForm((current) => ({ ...current, slowWindow: event.target.value }))}
                    className="rounded-md border bg-background px-3 py-2 text-sm"
                  />
                </label>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={creating}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {creating ? t("reports.quickSubmitting") : t("reports.quickSubmit")}
              </button>

              {activeTrackedRunIds.length > 0 ? (
                <span className="text-sm text-muted-foreground">
                  {t("reports.quickActiveCount", { count: activeTrackedRunIds.length })}
                </span>
              ) : null}
            </div>

            {createInfo ? (
              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                {createInfo}
              </div>
            ) : null}

            {createError ? (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                {createError}
              </div>
            ) : null}
          </form>
        </section>

        <StrategyLedgerOverview runs={runs} />

        <section className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_160px_150px_150px_170px]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("reports.searchPlaceholder")}
              className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm outline-none transition focus:border-primary"
            />
          </label>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
          >
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status === "all" ? t("reports.allStatuses") : status}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
            aria-label={t("reports.startDate")}
          />
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
            aria-label={t("reports.endDate")}
          />
          <select
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as SortMode)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
            aria-label={t("reports.sort")}
          >
            <option value="created_desc">{t("reports.sortNewest")}</option>
            <option value="created_asc">{t("reports.sortOldest")}</option>
            <option value="return_desc">{t("reports.sortReturn")}</option>
            <option value="sharpe_desc">{t("reports.sortSharpe")}</option>
          </select>
        </section>

        <div className="text-sm text-muted-foreground">
          {t("reports.count", { shown: filtered.length, total: runs.length })}
        </div>

        {loading && runs.length === 0 ? (
          <div className="grid gap-3">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="h-28 animate-pulse rounded-md border bg-muted/40" />
            ))}
          </div>
        ) : null}

        {error ? (
          <section className="rounded-md border border-amber-500/30 bg-amber-500/5 p-5">
            <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
              {t("reports.unavailable")}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          </section>
        ) : null}

        {!loading && filtered.length === 0 ? (
          <section className="rounded-md border border-dashed p-8 text-center">
            <FileText className="mx-auto h-8 w-8 text-muted-foreground" />
            <h2 className="mt-3 font-medium">{runs.length === 0 ? t("reports.emptyTitle") : t("reports.noMatchesTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {runs.length === 0 ? t("reports.emptyBody") : t("reports.noMatchesBody")}
            </p>
          </section>
        ) : null}

        {filtered.length > 0 ? (
          <section className="grid gap-3">
            {filtered.map((run) => (
              <ReportRow
                key={run.run_id}
                run={run}
                canceling={Boolean(cancelingRunIds[run.run_id])}
                onCancel={isActiveRunStatus(run.status) ? cancelRun : undefined}
              />
            ))}
          </section>
        ) : null}
      </div>
    </div>
  );
}

function ReportRow({
  run,
  canceling,
  onCancel,
}: {
  run: RunListItem;
  canceling: boolean;
  onCancel?: (runId: string) => void;
}) {
  const { t } = useTranslation();
  const active = isActiveRunStatus(run.status);
  const ledger = strategyLedgerForRun(run);
  const metrics = ledger?.metrics;
  return (
    <article className="rounded-md border p-4 transition hover:border-primary/40 hover:bg-muted/30">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            <Link to={`/runs/${run.run_id}`} className="truncate font-mono text-sm font-medium hover:text-primary">
              {run.run_id}
            </Link>
            <span className="text-xs text-muted-foreground">{formatRunDate(run.created_at)}</span>
          </div>
          <p className="line-clamp-2 text-sm text-muted-foreground">{run.prompt || t("reports.noPrompt")}</p>
          {ledger ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-medium text-foreground">{ledger.strategy.name}</span>
              <span className="rounded border px-2 py-0.5 font-mono text-muted-foreground">
                {t("reports.ledgerVersion", { version: ledger.strategy.version })}
              </span>
              <span className="rounded border border-primary/20 bg-primary/5 px-2 py-0.5 text-primary">
                {t("reports.ledgerPaperOnly")}
              </span>
              {ledger.dataset.market ? (
                <span className="rounded border px-2 py-0.5 text-muted-foreground">{ledger.dataset.market}</span>
              ) : null}
              {ledger.dataset.timeframe ? (
                <span className="rounded border px-2 py-0.5 text-muted-foreground">{ledger.dataset.timeframe}</span>
              ) : null}
            </div>
          ) : null}
          {active ? (
            <p className="text-xs text-muted-foreground">{t("reports.quickPendingHint")}</p>
          ) : null}
          <div className="flex flex-wrap gap-1.5">
            {(run.codes || []).slice(0, 6).map((code) => (
              <span key={code} className="rounded border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                {code}
              </span>
            ))}
            {run.start_date || run.end_date ? (
              <span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">
                {run.start_date || "?"} {t("reports.to")} {run.end_date || "?"}
              </span>
            ) : null}
            {ledger?.cost_model.commission_rate != null ? (
              <span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">
                {t("reports.ledgerCostModel", { rate: formatRate(ledger.cost_model.commission_rate) })}
              </span>
            ) : null}
            {ledger?.quality.flags.includes("low_trade_sample") ? (
              <span className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
                {t("reports.ledgerLowSample")}
              </span>
            ) : null}
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="grid grid-cols-2 gap-2 text-right sm:flex sm:flex-wrap sm:justify-end">
            <MetricPill
              label={t("reports.return")}
              value={formatOptionalMetric("total_return", metrics?.total_return ?? run.total_return)}
            />
            <MetricPill
              label={t("reports.ledgerDrawdown")}
              value={formatOptionalMetric("max_drawdown", metrics?.max_drawdown ?? undefined)}
            />
            <MetricPill
              label={t("reports.sharpe")}
              value={formatOptionalMetric("sharpe", metrics?.sharpe ?? run.sharpe)}
            />
            <MetricPill
              label={t("reports.ledgerTrades")}
              value={formatOptionalMetric("trade_count", metrics?.trade_count ?? undefined)}
            />
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <Link
              to={`/runs/${run.run_id}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition hover:opacity-90"
            >
              {active ? t("reports.openRun") : t("reports.fullReport")} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              to="/compare"
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition hover:bg-muted"
            >
              <GitCompare className="h-3.5 w-3.5" />
              {t("reports.compare")}
            </Link>
            {onCancel ? (
              <button
                type="button"
                onClick={() => onCancel(run.run_id)}
                disabled={canceling}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition hover:bg-muted disabled:opacity-50"
              >
                {canceling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                {canceling ? t("reports.quickCancelling") : t("reports.quickCancel")}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function StrategyLedgerOverview({ runs }: { runs: RunListItem[] }) {
  const { t } = useTranslation();
  const ledgers = runs.map(strategyLedgerForRun).filter((ledger) => ledger != null);
  const completed = ledgers.filter((ledger) => ledger.status === "completed").length;
  const comparable = ledgers.filter((ledger) => (
    (ledger.quality.level === "complete" || ledger.quality.level === "usable")
    && !ledger.quality.flags.includes("low_trade_sample")
    && !ledger.quality.flags.includes("zero_cost_assumption")
  )).length;

  return (
    <section className="rounded-md border bg-muted/15 p-5" aria-labelledby="strategy-ledger-heading">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-2xl">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            <h2 id="strategy-ledger-heading" className="text-lg font-semibold">{t("reports.ledgerTitle")}</h2>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{t("reports.ledgerSubtitle")}</p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <LedgerStat icon={<Activity className="h-4 w-4" />} label={t("reports.ledgerExperiments")} value={String(ledgers.length)} />
          <LedgerStat icon={<ShieldCheck className="h-4 w-4" />} label={t("reports.ledgerCompleted")} value={String(completed)} />
          <LedgerStat icon={<TrendingDown className="h-4 w-4" />} label={t("reports.ledgerComparable")} value={String(comparable)} />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="rounded border px-2 py-1">newma-desk.strategy-ledger.v1</span>
        <span className="rounded border px-2 py-1">{t("reports.ledgerPaperOnly")}</span>
        <span className="rounded border px-2 py-1">{t("reports.ledgerNativeRuntime")}</span>
        <span className="rounded border px-2 py-1">{t("reports.ledgerArtifactStorage")}</span>
      </div>
    </section>
  );
}

function LedgerStat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="min-w-24 rounded-md border bg-background px-3 py-2">
      <div className="flex items-center justify-center gap-1.5 text-muted-foreground">{icon}<span className="text-[11px]">{label}</span></div>
      <div className="mt-1 font-mono text-lg font-semibold">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const ok = ["success", "done", "completed", "complete"].includes(normalized);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
        ok ? "bg-success/10 text-success" : "bg-muted text-muted-foreground",
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {status || "unknown"}
    </span>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border px-3 py-1.5">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="font-mono text-sm font-medium">{value}</div>
    </div>
  );
}

function isBacktestReportRun(run: RunListItem): boolean {
  return Number.isFinite(run.total_return) || Number.isFinite(run.sharpe);
}

function shouldDisplayRun(run: RunListItem, trackedRunIds: Set<string>): boolean {
  return isBacktestReportRun(run) || isActiveRunStatus(run.status) || trackedRunIds.has(run.run_id);
}

function isActiveRunStatus(status: string | undefined): boolean {
  return ACTIVE_RUN_STATUSES.has(String(status || "").toLowerCase());
}

function compareRuns(left: RunListItem, right: RunListItem, mode: SortMode): number {
  if (mode === "created_asc") return dateMs(left.created_at) - dateMs(right.created_at);
  if (mode === "return_desc") return metric(right.total_return) - metric(left.total_return);
  if (mode === "sharpe_desc") return metric(right.sharpe) - metric(left.sharpe);
  return dateMs(right.created_at) - dateMs(left.created_at);
}

function metric(value: number | undefined): number {
  return Number.isFinite(value) ? Number(value) : Number.NEGATIVE_INFINITY;
}

function formatOptionalMetric(key: string, value: number | undefined): string {
  return Number.isFinite(value) ? formatMetricVal(key, value as number) : "-";
}

function formatRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function dateMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatRunDate(value: string): string {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return value || "unknown";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function buildInitialFormState(): QuickBacktestFormState {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setFullYear(startDate.getFullYear() - 1);
  return {
    templateId: "buy_and_hold",
    symbol: "",
    startDate: formatDateInput(startDate),
    endDate: formatDateInput(endDate),
    initialCash: String(DEFAULT_INITIAL_CASH),
    commission: String(DEFAULT_COMMISSION),
    fastWindow: String(DEFAULT_SMA_FAST_WINDOW),
    slowWindow: String(DEFAULT_SMA_SLOW_WINDOW),
  };
}

function buildTrackedQuickRunDraft(
  runId: string,
  form: QuickBacktestFormState,
  symbol: string,
  status: string | undefined,
): TrackedQuickRunDraft {
  return {
    run_id: runId,
    status: status || "queued",
    created_at: new Date().toISOString(),
    prompt: form.templateId === "sma_crossover" ? `Quick SMA crossover for ${symbol}` : `Quick buy and hold for ${symbol}`,
    codes: [symbol],
    start_date: form.startDate,
    end_date: form.endDate,
  };
}

async function mergeRunsWithTrackedStatuses(
  list: RunListItem[],
  trackedRunIds: string[],
  trackedRunDrafts: Record<string, TrackedQuickRunDraft>,
): Promise<RunListItem[]> {
  const merged = new Map(list.map((run) => [run.run_id, run]));
  const statusIds = trackedRunIds.filter((runId) => {
    const run = merged.get(runId);
    return run == null || isActiveRunStatus(run.status);
  });

  if (statusIds.length === 0) {
    return Array.from(merged.values());
  }

  const settled = await Promise.all(
    statusIds.map(async (runId) => {
      try {
        const status = await api.getRunStatus(runId);
        return [runId, status] as const;
      } catch {
        return [runId, null] as const;
      }
    }),
  );

  for (const [runId, status] of settled) {
    const current = merged.get(runId);
    const draft = trackedRunDrafts[runId];
    if (!current && !draft && !status) continue;
    merged.set(runId, mergeTrackedRun(current, draft, status, runId));
  }

  return Array.from(merged.values());
}

function mergeTrackedRun(
  current: RunListItem | undefined,
  draft: TrackedQuickRunDraft | undefined,
  status: QuickRunStatusResponse | null,
  runId: string,
): RunListItem {
  return {
    run_id: current?.run_id || draft?.run_id || status?.run_id || runId,
    status: status?.status || current?.status || draft?.status || "queued",
    created_at: current?.created_at || draft?.created_at || new Date().toISOString(),
    prompt: current?.prompt || draft?.prompt,
    total_return: current?.total_return,
    sharpe: current?.sharpe,
    codes: current?.codes || draft?.codes,
    start_date: current?.start_date || draft?.start_date,
    end_date: current?.end_date || draft?.end_date,
  };
}

function formatDateInput(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
