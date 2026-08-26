import { ArrowRight, Lightbulb } from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import type { CoverageModId, CoverageStatus, ResearchCoverageSnapshot } from "@/lib/researchCoverage";

const STATUS: Record<CoverageStatus, string> = {
  ready: "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  due: "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  stale: "border-orange-500/25 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  missing: "border-border bg-muted/25 text-muted-foreground",
};
const STAGE = { inbox: "线索箱", triage: "初筛", shortlist: "短名单", "deep-dive": "深度研究", handoff: "已交接", deferred: "暂缓", closed: "关闭", untracked: "未回链" } as const;

export function ResearchCoverageView({ snapshot, onRefresh, onEditIdea, onOpenMod }: {
  snapshot: ResearchCoverageSnapshot;
  onRefresh: () => void;
  onEditIdea: (ideaId: string) => void;
  onOpenMod: (modId: CoverageModId) => void;
}) {
  const metrics = [
    ["研究对象", snapshot.totals.securities, "合并去重"],
    ["复核到期", snapshot.totals.dueReviews, `${snapshot.totals.overdueTasks} 项任务逾期`],
    ["待办任务", snapshot.totals.pendingTasks, "来自机会池"],
    ["覆盖缺口", snapshot.totals.coverageGaps, `${snapshot.totals.staleSources} 个陈旧来源`],
  ] as const;
  return <div className="space-y-5">
    <GlassCard className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="font-bold">研究流程调度</h2><p className="mt-1 text-xs text-muted-foreground">按复核、逾期和档案缺口排序；只读取本地缓存，不复制底层档案。</p></div>
        <button onClick={onRefresh} className="rounded-lg border border-border px-3 py-2 text-xs font-semibold">刷新状态</button>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">{metrics.map(([label, value, detail]) => <div key={label} className="rounded-xl border border-border bg-muted/15 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p><p className="text-[11px] text-muted-foreground">{detail}</p></div>)}</div>
    </GlassCard>

    <div className="space-y-3">{snapshot.items.map((item) => <GlassCard key={item.id} className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="flex flex-wrap items-center gap-2"><h3 className="font-bold">{item.security.name}</h3><span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">{item.security.market}:{item.security.symbol}</span><span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">{STAGE[item.stage]}</span></div><p className="mt-1 text-xs text-muted-foreground">更新 {item.latestAt?.slice(0, 10) || "暂无"} · 复核 {item.nextReviewAt?.slice(0, 10) || "暂无"} · 来源 {item.sourceCount} · 缺口 {item.gapCount} · 待办 {item.pendingTaskCount}</p></div>
        <div className="flex gap-2">{item.ideaId && <button onClick={() => onEditIdea(item.ideaId!)} className="rounded-lg border border-border px-3 py-2 text-xs font-semibold">编辑候选</button>}<button onClick={() => onOpenMod(item.nextModId)} className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground">打开{item.nextModLabel}<ArrowRight className="h-3.5 w-3.5" /></button></div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{item.modules.map((module) => <button key={module.modId} onClick={() => onOpenMod(module.modId)} className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold ${STATUS[module.status]}`}>{module.label}{module.status === "due" ? " · 到期" : module.status === "stale" ? " · 陈旧" : module.status === "missing" ? " · 未覆盖" : ""}</button>)}</div>
      {item.attention.length > 0 && <p className="mt-3 text-xs text-amber-800 dark:text-amber-200">{item.attention.join(" · ")}</p>}
    </GlassCard>)}
    {!snapshot.items.length && <GlassCard className="p-8 text-center"><Lightbulb className="mx-auto h-8 w-8 text-muted-foreground" /><h2 className="mt-3 font-bold">还没有可汇总的研究档案</h2><p className="mt-1 text-sm text-muted-foreground">先建立候选或保存一个深度研究档案。</p></GlassCard>}</div>
    <Disclaimer />
  </div>;
}
