import {
  Activity,
  AlertTriangle,
  BookOpenCheck,
  Calculator,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  History,
  Route,
  ShieldCheck,
} from "lucide-react";

import { GlassCard } from "@/components/ui/GlassCard";
import type {
  EquityResearchAxisScore,
  EquityResearchEvidence,
  EquityResearchMetric,
  EquityResearchSnapshot,
} from "@/lib/api";

function evidenceValue(item: EquityResearchEvidence) {
  const value = typeof item.value === "number"
    ? item.value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
    : String(item.value);
  return `${value}${item.unit ? ` ${item.unit}` : ""}`;
}

function metricValue(item: EquityResearchMetric) {
  return `${item.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${
    item.unit === "%" ? "%" : ` ${item.unit}`
  }`;
}

const SCORE_STYLE: Record<string, string> = {
  strong: "border-primary/35 bg-primary/10 text-primary",
  balanced: "border-border/80 bg-muted/40 text-foreground",
  watch: "border-warning/35 bg-warning/10 text-warning",
  weak: "border-destructive/35 bg-destructive/10 text-destructive",
  unavailable: "border-border/50 bg-muted/20 text-muted-foreground",
};

const SCORE_LABEL: Record<string, string> = {
  strong: "较强",
  balanced: "中性",
  watch: "观察",
  weak: "承压",
  unavailable: "待补证据",
};

const BLOCK_STYLE: Record<string, string> = {
  available: "border-primary/30 bg-primary/10 text-primary",
  fallback: "border-warning/35 bg-warning/10 text-warning",
  partial: "border-warning/35 bg-warning/10 text-warning",
  estimated: "border-warning/35 bg-warning/10 text-warning",
  missing: "border-border/60 bg-muted/25 text-muted-foreground",
  not_supported: "border-border/60 bg-muted/25 text-muted-foreground",
  fetch_failed: "border-destructive/30 bg-destructive/10 text-destructive",
};

const BLOCK_LABEL: Record<string, string> = {
  available: "可用",
  fallback: "已降级",
  partial: "部分可用",
  estimated: "估算",
  missing: "缺失",
  not_supported: "未启用",
  fetch_failed: "获取失败",
};

const QUALITY_LABEL: Record<string, string> = {
  good: "良好",
  usable: "可用",
  limited: "受限",
  poor: "不足",
};

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false });
}

function ResearchWorkflow({ snapshot }: { snapshot: EquityResearchSnapshot }) {
  const workflow = snapshot.workflow;
  if (!workflow) return null;
  const quality = workflow.dataQuality;
  const failed = workflow.sourceStatus.filter((item) => item.status === "fetch_failed");
  const fallback = workflow.sourceStatus.filter((item) => item.status === "fallback");
  const history = snapshot.reportHistory || [];
  const persisted = workflow.history.state === "saved";

  return (
    <section className="mt-4 rounded-xl border border-border/60 bg-muted/15 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="flex items-center gap-1.5 text-xs font-semibold">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" /> 研究流程与数据质量
          </h4>
          <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
            记录每个数据块的完成情况、来源降级和失败原因；缺失项不会被静默当成零值。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-2 py-1 font-mono text-[10px] ${
            quality.level === "good" || quality.level === "usable"
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-warning/35 bg-warning/10 text-warning"
          }`}>
            质量 {quality.score}/100 · {QUALITY_LABEL[quality.level] || quality.level}
          </span>
          <span className="rounded-full border border-border/60 bg-background/50 px-2 py-1 text-[10px] text-muted-foreground">
            {workflow.task.status === "completed" ? "流程完成" : "部分完成"}
          </span>
        </div>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {workflow.stages.map((stage, index) => (
          <div key={stage.id} className="rounded-lg border border-border/50 bg-background/45 px-2.5 py-2">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 font-mono text-[9px] text-primary">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-[10px] font-medium">{stage.title}</span>
              <span className="font-mono text-[9px] text-muted-foreground">{stage.durationMs}ms</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-3">
        {workflow.blocks.map((block) => (
          <div key={block.id} className={`rounded-lg border px-2.5 py-2 ${BLOCK_STYLE[block.status] || BLOCK_STYLE.missing}`}>
            <div className="flex items-center gap-2">
              <span className="truncate text-[11px] font-medium">{block.title}</span>
              <span className="ml-auto font-mono text-[10px]">{block.qualityScore}</span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2 text-[9px] opacity-75">
              <span>{BLOCK_LABEL[block.status] || block.status}</span>
              <span>{block.evidenceCount} 条证据</span>
            </div>
            {block.sources.length > 0 && (
              <p className="mt-1 truncate text-[9px] opacity-65" title={block.sources.join(" / ")}>
                {block.sources.join(" / ")}
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="mt-3 grid gap-2 lg:grid-cols-2">
        <details className="rounded-lg border border-border/50 bg-background/40 open:bg-background/65">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[10px] font-medium">
            <Route className="h-3.5 w-3.5 text-primary" /> 来源与降级诊断
            <span className="ml-auto text-muted-foreground">失败 {failed.length} · 降级 {fallback.length}</span>
          </summary>
          <div className="space-y-1.5 border-t border-border/40 px-3 py-2">
            {workflow.sourceStatus.map((item) => (
              <div key={item.id} className="flex items-start gap-2 text-[10px] leading-4">
                <span className={`mt-0.5 rounded border px-1 py-0.5 text-[8px] ${BLOCK_STYLE[item.status] || BLOCK_STYLE.missing}`}>
                  {BLOCK_LABEL[item.status] || item.status}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{item.title} · {item.source}</p>
                  {item.message && <p className="text-muted-foreground">{item.message}</p>}
                </div>
              </div>
            ))}
          </div>
        </details>

        <details className="rounded-lg border border-border/50 bg-background/40 open:bg-background/65">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[10px] font-medium">
            <History className="h-3.5 w-3.5 text-primary" /> 最近研究记录
            <span className="ml-auto text-muted-foreground">
              {persisted ? "Desk 已保存" : "仅当前会话"} · {history.length} 条
            </span>
          </summary>
          <div className="space-y-1.5 border-t border-border/40 px-3 py-2">
            {history.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">研究记录将在当前结果写入 Desk 后显示。</p>
            ) : history.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-center gap-2 text-[10px]">
                <Clock3 className="h-3 w-3 text-muted-foreground" />
                <span className="font-mono text-muted-foreground">{formatTime(item.createdAt)}</span>
                <span className="ml-auto">质量 {item.qualityScore} · 覆盖 {Math.round(item.coverageRatio * 100)}%</span>
              </div>
            ))}
            {workflow.history.lastGoodAt && (
              <p className="border-t border-border/40 pt-1.5 text-[9px] text-muted-foreground">
                最近可用结果：{formatTime(workflow.history.lastGoodAt)}
              </p>
            )}
          </div>
        </details>
      </div>
    </section>
  );
}

function ScoreCard({ axis }: { axis: EquityResearchAxisScore }) {
  const score = axis.score == null ? null : Math.max(0, Math.min(100, axis.score));
  return (
    <div className={`relative overflow-hidden rounded-xl border p-3 ${SCORE_STYLE[axis.status] || SCORE_STYLE.unavailable}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] opacity-70">{axis.id}</p>
          <p className="mt-1 text-sm font-semibold">{axis.title}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-xl font-bold leading-none">{score == null ? "—" : score.toFixed(0)}</p>
          <p className="mt-1 text-[10px] opacity-75">{SCORE_LABEL[axis.status] || axis.status}</p>
        </div>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-background/50">
        <div className="h-full rounded-full bg-current transition-[width] duration-500" style={{ width: `${score || 0}%` }} />
      </div>
      <p className="mt-2 text-[10px] leading-4 opacity-80">{axis.summary}</p>
      <p className="mt-1 font-mono text-[9px] opacity-55">{axis.signalCount} 个有效信号</p>
    </div>
  );
}

export function EquityResearchFramework({
  snapshot,
}: {
  snapshot: EquityResearchSnapshot;
}) {
  const coverage = Math.round(snapshot.coverage.ratio * 100);
  const hasEdgar = snapshot.evidenceLedger.some((item) => item.sourceType === "filing");
  const scorecard = snapshot.scorecard || [];
  const derivedMetrics = snapshot.analytics?.metrics || [];

  return (
    <GlassCard glow className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <BookOpenCheck className="h-4 w-4 text-primary" />
            跨市场研究框架
          </h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-muted-foreground/70">
            A/H/US 共用研究维度，数据由市场 Adapter 标准化；所有数字保留来源、字段、日期与置信度，缺失项不会被静默补写。
          </p>
        </div>
        <div className="min-w-36 rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-right">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Evidence coverage</p>
          <p className="font-mono text-xl font-bold">{coverage}%</p>
          <p className="text-[10px] text-muted-foreground">
            {snapshot.coverage.coveredDimensions}/{snapshot.coverage.totalDimensions} 个维度
          </p>
        </div>
      </div>

      <ResearchWorkflow snapshot={snapshot} />

      {scorecard.length > 0 && (
        <section className="mt-4 rounded-xl border border-border/60 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.10),transparent_48%)] p-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h4 className="flex items-center gap-1.5 text-xs font-semibold">
                <Activity className="h-3.5 w-3.5 text-primary" /> 财务结构画像
              </h4>
              <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                质量、增长、估值、韧性统一为可追溯结构信号；不是评级，也不输出目标价。
              </p>
            </div>
            <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">FinanceToolkit method layer</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-4">
            {scorecard.map((axis) => <ScoreCard key={axis.id} axis={axis} />)}
          </div>
        </section>
      )}

      {derivedMetrics.length > 0 && (
        <section className="mt-4">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold">
            <Calculator className="h-3.5 w-3.5 text-primary" /> 标准化派生指标
          </h4>
          <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {derivedMetrics.map((metric) => (
              <div key={metric.id} className="rounded-xl border border-border/60 bg-muted/20 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-medium">{metric.label}</p>
                    <p className="mt-0.5 font-mono text-[9px] text-muted-foreground">{metric.id}</p>
                  </div>
                  <p className="font-mono text-base font-bold text-primary">{metricValue(metric)}</p>
                </div>
                <p className="mt-2 text-[10px] leading-4 text-muted-foreground">{metric.interpretation}</p>
                <p className="mt-2 border-t border-border/40 pt-2 font-mono text-[9px] text-muted-foreground/70">
                  {metric.method}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {metric.dependsOn.map((evidenceId) => (
                    <span key={evidenceId} className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[8px] text-primary/80">
                      {evidenceId}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-3">
        {snapshot.sections.map((section) => (
          <div
            key={section.id}
            className={`rounded-lg border px-3 py-2 ${
              section.status === "covered"
                ? "border-primary/25 bg-primary/5"
                : "border-warning/25 bg-warning/5"
            }`}
          >
            <div className="flex items-center gap-2">
              {section.status === "covered" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
              ) : (
                <AlertTriangle className="h-3.5 w-3.5 text-warning" />
              )}
              <span className="text-xs font-medium">{section.title}</span>
              <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                {section.evidenceIds.length}
              </span>
            </div>
          </div>
        ))}
      </div>

      <details className="mt-4 rounded-lg border border-border/60 bg-muted/20 open:bg-muted/35">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs font-medium">
          <Database className="h-3.5 w-3.5 text-primary" />
          Evidence Ledger
          <span className="font-normal text-muted-foreground">{snapshot.evidenceLedger.length} 条可追溯证据</span>
        </summary>
        <div className="overflow-x-auto border-t border-border/50">
          <table className="min-w-[760px] w-full text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">指标</th>
                <th className="px-3 py-2 font-medium">值</th>
                <th className="px-3 py-2 font-medium">来源 / 字段</th>
                <th className="px-3 py-2 font-medium">截止日</th>
                <th className="px-3 py-2 font-medium">置信度</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.evidenceLedger.map((item) => (
                <tr key={item.id} className="border-t border-border/40 align-top">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <strong className="font-medium">{item.label}</strong>
                      {item.sourceType === "derived" && (
                        <span className="rounded bg-primary/10 px-1 py-0.5 text-[8px] text-primary">派生</span>
                      )}
                    </div>
                    <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">{item.id}</span>
                  </td>
                  <td className="px-3 py-2.5 font-mono font-medium">{evidenceValue(item)}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      {item.url ? (
                        <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-primary">
                          {item.source}
                        </a>
                      ) : item.source}
                      {item.url && <ExternalLink className="h-3 w-3" />}
                    </span>
                    <span className="mt-0.5 block font-mono text-[10px] opacity-70">{item.field}</span>
                    {item.method && <span className="mt-1 block text-[10px] opacity-70">{item.method}</span>}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-muted-foreground">{item.asOf || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{item.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {snapshot.gaps.length > 0 && (
        <div className="mt-3 rounded-lg border border-warning/25 bg-warning/5 px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-xs font-medium text-warning">
            <AlertTriangle className="h-3.5 w-3.5" /> 数据缺口
          </p>
          <ul className="mt-1.5 space-y-1 text-[11px] leading-5 text-muted-foreground">
            {snapshot.gaps.map((gap) => <li key={gap}>• {gap}</li>)}
          </ul>
        </div>
      )}

      {snapshot.identity.market === "US" && !hasEdgar && (
        <p className="mt-3 text-[10px] text-muted-foreground/60">
          SEC EDGAR 为可选披露 Adapter；配置 VR_SEC_USER_AGENT 后才会加入原始申报证据，不影响通用研究框架。
        </p>
      )}
    </GlassCard>
  );
}
