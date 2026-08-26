import { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  Download,
  ExternalLink,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, ApiError, downloadReport, type MyReport } from "@/lib/api";
import {
  ARCHIVE_KIND_LABELS,
  loadResearchArchive,
  researchArchiveSourceUrl,
  type ResearchArchiveEntry,
  type ResearchArchiveKind,
} from "@/lib/researchArchive";
import { cn } from "@/lib/utils";
import {
  createVibeDeskSnapshotCache,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const fmtSize = (bytes: number) =>
  bytes < 1024 ? `${bytes}B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(0)}KB` : `${(bytes / 1048576).toFixed(1)}MB`;
const fmtDate = (value: string | number) =>
  new Date(value).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });

const STATUS_LABEL: Record<ResearchArchiveEntry["status"], string> = {
  active: "有效",
  draft: "草稿",
  archived: "已归档",
  invalidated: "已失效",
  stale: "待更新",
  unknown: "未标记",
};

const fileToB64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

export function MyReports() {
  const [cacheRevision, setCacheRevision] = useState(0);
  const archiveCache = useMemo(
    () => createVibeDeskSnapshotCache<{ reports: MyReport[]; entries: ResearchArchiveEntry[] }>("research-archive:index", 1, 2 * 1024 * 1024),
    [cacheRevision],
  );
  const cachedArchive = archiveCache.read()?.value;
  const [reports, setReports] = useState<MyReport[]>(() => cachedArchive?.reports ?? []);
  const [entries, setEntries] = useState<ResearchArchiveEntry[]>(() => cachedArchive?.entries ?? []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<ResearchArchiveKind | "all">("all");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cacheRevisionRef = useRef(cacheRevision);

  const load = async () => {
    setLoading(true);
    setErr(null);
    const cached = archiveCache.read()?.value;
    const identityChanged = cacheRevisionRef.current !== cacheRevision;
    cacheRevisionRef.current = cacheRevision;
    const visibleReports = identityChanged ? cached?.reports ?? [] : reports;
    const visibleEntries = identityChanged ? cached?.entries ?? [] : entries;
    if (identityChanged || (!entries.length && cached)) {
      setReports(visibleReports);
      setEntries(visibleEntries);
    }
    let files: MyReport[] = cached?.reports ?? visibleReports;
    try {
      files = await api.myReports();
      setReports(files);
    } catch (error) {
      setErr((files.length || visibleEntries.length)
        ? "上传研报列表暂时不可用，正在显示上次索引"
        : error instanceof ApiError ? error.message : "上传研报列表暂时不可用");
    }
    try {
      const index = await loadResearchArchive(files);
      setEntries(index.entries);
      archiveCache.write({ reports: files, entries: index.entries }, index.generatedAt);
    } catch {
      setErr((current) => current ?? ((visibleEntries.length || cached?.entries.length)
        ? "研究档案索引更新失败，正在显示上次索引"
        : "研究档案索引加载失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [archiveCache]);
  useEffect(() => subscribeVibeDeskConfig(() => setCacheRevision((value) => value + 1)), []);

  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    setErr(null);
    try {
      for (const file of Array.from(files)) {
        await api.uploadReport(file.name, await fileToB64(file));
      }
      await load();
    } catch (error) {
      setErr(error instanceof ApiError ? error.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: ResearchArchiveEntry) => {
    const report = reports.find((candidate) => candidate.id === item.artifactId);
    if (!report || !confirm(`删除「${report.name}」？（同时从本地归档目录移除）`)) return;
    try {
      await api.deleteReport(report.id);
      if (selectedId === item.id) setSelectedId(null);
      await load();
    } catch (error) {
      setErr(error instanceof ApiError ? error.message : "删除失败");
    }
  };

  const download = async (item: ResearchArchiveEntry) => {
    const report = reports.find((candidate) => candidate.id === item.artifactId);
    if (!report) return;
    try {
      await downloadReport(report.id, report.name);
    } catch (error) {
      setErr(error instanceof ApiError ? error.message : "下载失败");
    }
  };

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return entries.filter((item) => {
      if (kind !== "all" && item.kind !== kind) return false;
      if (!keyword) return true;
      return [item.title, item.security?.name, item.security?.symbol, ...item.tags]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [entries, kind, query]);
  const grouped = useMemo(() => Object.entries(
    visible.reduce<Record<string, ResearchArchiveEntry[]>>((groups, item) => {
      (groups[item.kind] ||= []).push(item);
      return groups;
    }, {}),
  ) as Array<[ResearchArchiveKind, ResearchArchiveEntry[]]>, [visible]);
  const selected = entries.find((item) => item.id === selectedId) ?? null;
  const structuredCount = entries.filter((item) => item.kind !== "uploaded-report" && item.kind !== "research-record").length;
  const attentionCount = entries.filter((item) => ["draft", "stale", "invalidated"].includes(item.status)).length;

  const contextRef = useRef<VibeDeskPageContext>({
    view: { id: "research-library", title: "研究档案" },
    visibleBlocks: [], selection: {}, filters: {}, data: {}, actions: [], tasks: [],
  });
  contextRef.current = {
    view: { id: "research-library", title: "研究档案" },
    visibleBlocks: grouped.map(([groupKind, items]) => ({
      id: `archive-${groupKind}`,
      type: "research-archive-group",
      title: `${ARCHIVE_KIND_LABELS[groupKind]} · ${items.length}`,
    })),
    selection: selected ? {
      archiveId: selected.id,
      kind: selected.kind,
      sourceModId: selected.sourceModId,
      artifactId: selected.artifactId,
      title: selected.title,
    } : {},
    filters: { query, kind },
    data: {
      asOf: new Date().toISOString(),
      source: "newma-desk.research-archive.v1",
      freshness: loading ? "unknown" : "fresh",
      summary: {
        entryCount: entries.length,
        visibleCount: visible.length,
        structuredCount,
        attentionCount,
        countsByKind: Object.fromEntries(grouped.map(([groupKind, items]) => [groupKind, items.length])),
        selectedReference: selected,
        note: "统一索引只包含引用与最小元数据，不复制研究正文、财务明细或上传文件。",
      },
    },
    actions: [
      { id: "archive.summarize", label: "总结研究覆盖", available: entries.length > 0 },
      { id: "archive.find-gaps", label: "识别研究缺口", available: entries.length > 0 },
      { id: "archive.open-source", label: "打开来源档案", available: Boolean(selected) },
    ],
    tasks: [],
  };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [attentionCount, entries.length, kind, loading, query, selectedId, visible.length]);

  return (
    <div>
      <PageHeader
        title="研究档案"
        subtitle="统一索引上传文件、研究记录与结构化研究档案；这里只保存引用，正文和底层数据仍由来源 Mod 维护。"
        actions={(
          <button onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-primary disabled:opacity-50">
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> 刷新索引
          </button>
        )}
      />

      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        {[
          { label: "全部档案", value: entries.length, Icon: Archive },
          { label: "结构化档案", value: structuredCount, Icon: FileText },
          { label: "需要关注", value: attentionCount, Icon: FolderOpen },
        ].map(({ label, value, Icon }) => (
          <GlassCard key={label} className="!p-3">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2 text-primary"><Icon className="h-4 w-4" /></div>
              <div><div className="text-lg font-semibold">{value}</div><div className="text-[11px] text-muted-foreground">{label}</div></div>
            </div>
          </GlassCard>
        ))}
      </div>

      <GlassCard className="mb-4 !p-3">
        <div
          onDragOver={(event) => { event.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(event) => { event.preventDefault(); setDrag(false); if (event.dataTransfer.files.length) void upload(event.dataTransfer.files); }}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex cursor-pointer items-center justify-center gap-3 rounded-xl border border-dashed px-4 py-5 text-center transition-colors",
            drag ? "border-primary bg-primary/10" : "border-border hover:border-primary/50 hover:bg-primary/5",
          )}
        >
          {busy ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : <Upload className="h-5 w-5 text-primary" />}
          <div className="text-left">
            <p className="text-sm font-medium">{busy ? "上传中…" : "添加本地研报文件"}</p>
            <p className="text-[11px] text-muted-foreground">PDF / Word / txt / md / 表格 / 图片，单个 ≤ 25MB</p>
          </div>
          <input ref={inputRef} type="file" multiple accept=".pdf,.doc,.docx,.txt,.md,.markdown,.csv,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.webp" className="hidden" onChange={(event) => { if (event.target.files?.length) void upload(event.target.files); event.target.value = ""; }} />
        </div>
      </GlassCard>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-card/50 px-3">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、证券或标签" className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/60" />
        </label>
        <select value={kind} onChange={(event) => setKind(event.target.value as ResearchArchiveKind | "all")} className="h-9 rounded-lg border border-border bg-card/50 px-3 text-sm">
          <option value="all">全部类型</option>
          {Object.entries(ARCHIVE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>

      {err && <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{err}</div>}

      {loading && entries.length === 0 ? (
        <GlassCard><div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在汇总研究档案…</div></GlassCard>
      ) : visible.length === 0 ? (
        <GlassCard><div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground"><FolderOpen className="h-8 w-8 text-muted-foreground/40" />没有符合条件的研究档案。</div></GlassCard>
      ) : (
        <div className="space-y-4">
          {grouped.map(([groupKind, items]) => (
            <GlassCard key={groupKind}>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <span className="rounded bg-primary/15 px-2 py-0.5 text-xs text-primary">{ARCHIVE_KIND_LABELS[groupKind]}</span>
                <span className="text-xs font-normal text-muted-foreground">{items.length} 条引用</span>
              </h3>
              <div className="divide-y divide-border/30">
                {items.map((item) => {
                  const report = item.kind === "uploaded-report" ? reports.find((candidate) => candidate.id === item.artifactId) : undefined;
                  return (
                    <div key={item.id} onClick={() => setSelectedId(item.id)} className={cn("flex items-center gap-3 py-3", selectedId === item.id && "rounded-lg bg-primary/5 px-2")}>
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <p className="truncate text-sm font-medium">{item.title}</p>
                          <span className="rounded bg-muted/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">{STATUS_LABEL[item.status]}</span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-muted-foreground/70">
                          {item.security ? `${item.security.name} · ${item.security.market}:${item.security.symbol} · ` : ""}
                          {item.asOf ? `截至 ${item.asOf} · ` : ""}{fmtDate(item.updatedAt)}
                          {report ? ` · ${fmtSize(report.size)}` : ""}
                        </p>
                        {item.tags.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{item.tags.slice(0, 4).map((tag) => <span key={tag} className="rounded bg-muted/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">{tag}</span>)}</div>}
                      </div>
                      {item.kind === "uploaded-report" ? (
                        <>
                          <button onClick={(event) => { event.stopPropagation(); void download(item); }} className="text-muted-foreground/60 hover:text-primary" title="下载"><Download className="h-4 w-4" /></button>
                          <button onClick={(event) => { event.stopPropagation(); void remove(item); }} className="text-muted-foreground/50 hover:text-destructive" title="删除"><Trash2 className="h-3.5 w-3.5" /></button>
                        </>
                      ) : (
                        <a href={researchArchiveSourceUrl(item)} target="_top" onClick={(event) => event.stopPropagation()} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary">打开来源<ExternalLink className="h-3.5 w-3.5" /></a>
                      )}
                    </div>
                  );
                })}
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
