import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Network, Search, Table2 } from "lucide-react";
import type { GraphArtifactInput } from "@/lib/artifacts";
import { evidenceLink, industryTargets, type IndustryEvidence } from "@/lib/industryWorkspace";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";

export interface IndustryGraphSelection {
  tab: "graph" | "data" | "source";
  query: string;
  nodeId: string | null;
}
interface Props {
  spec: GraphArtifactInput;
  viewUrl?: string;
  previewHtml?: string;
  previewError?: string | null;
  references?: IndustryEvidence[];
  onSelectionChange: (selection: IndustryGraphSelection) => void;
}
const THEME_VARIABLES = [
  "--vibe-bg", "--vibe-surface", "--vibe-surface-muted", "--vibe-surface-raised",
  "--vibe-surface-selected", "--vibe-border", "--vibe-border-strong", "--vibe-text",
  "--vibe-text-muted", "--vibe-text-faint", "--vibe-accent", "--vibe-error",
  "--vibe-chart-series-1", "--vibe-chart-series-2", "--vibe-chart-series-3",
  "--vibe-chart-series-4", "--vibe-chart-series-5",
];

export function IndustryArtifactView({ spec, viewUrl, previewHtml, previewError, references = [], onSelectionChange }: Props) {
  const [selection, setSelection] = useState<IndustryGraphSelection>({
    tab: window.matchMedia?.("(max-width: 639px)").matches ? "data" : "graph",
    query: "", nodeId: null,
  });
  const graphFrameRef = useRef<HTMLIFrameElement>(null);
  const syncGraphTheme = useCallback(() => {
    const styles = getComputedStyle(document.documentElement);
    const cssVars = Object.fromEntries(THEME_VARIABLES.map((key) => [key, styles.getPropertyValue(key).trim()]).filter(([, value]) => value));
    const mode = document.documentElement.classList.contains("dark") ? "dark" : "light";
    graphFrameRef.current?.contentWindow?.postMessage({ type: "newma:artifact-theme", mode, cssVars }, "*");
  }, []);
  useEffect(() => {
    const observer = new MutationObserver(syncGraphTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    window.addEventListener("vibedesk:theme", syncGraphTheme);
    return () => { observer.disconnect(); window.removeEventListener("vibedesk:theme", syncGraphTheme); };
  }, [syncGraphTheme]);
  useEffect(() => onSelectionChange(selection), [selection, onSelectionChange]);
  const nodes = spec.nodes.filter((node) => [node.label, node.subtitle, node.group].join(" ").toLocaleLowerCase().includes(selection.query.trim().toLocaleLowerCase()));
  const selectedNode = spec.nodes.find((node) => node.id === selection.nodeId);
  const label = (id: string) => spec.nodes.find((node) => node.id === id)?.label ?? id;
  const relations = selectedNode ? spec.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id) : [];
  const referenceTargets = new Set(industryTargets({ ...spec, nodes: selectedNode ? [selectedNode] : spec.nodes, edges: selectedNode ? relations : spec.edges }).map((target) => target.key));
  const visibleReferences = references.filter((item) => referenceTargets.has(item.target));
  return (
    <GlassCard className="mb-6 overflow-hidden p-0" data-vibe-artifact="industry-graph">
      <div className="border-b border-border px-4 py-4">
        <h2 className="text-base font-semibold">{spec.title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{spec.nodes.length} 个节点 · {spec.edges.length} 条关系 · 结构示意，非企业供货证据</p>
      </div>
      <div className="flex flex-wrap gap-1 border-b border-border px-3 py-2" role="tablist" aria-label="产业链图谱视图">
        {([["graph", "关系图", Network], ["data", "节点与关系", Table2], ["source", "来源与边界", FileText]] as const).map(([value, title, Icon]) => (
          <button key={value} type="button" role="tab" aria-selected={selection.tab === value}
            onClick={() => setSelection((previous) => ({ ...previous, tab: value }))}
            className={cn("inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-xs", selection.tab === value ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}>
            <Icon className="h-3.5 w-3.5" />{title}
          </button>
        ))}
      </div>
      {selection.tab === "graph" && (
        <div className="p-3">
          {viewUrl || previewHtml ? <iframe ref={graphFrameRef} src={viewUrl} srcDoc={viewUrl ? undefined : previewHtml}
            title={spec.title + " Archify 关系图"} className="h-[500px] w-full rounded-xl border border-border bg-background sm:h-[620px]"
            sandbox="allow-scripts allow-downloads" onLoad={syncGraphTheme} />
            : <p role="status" className="py-12 text-center text-sm text-muted-foreground">{previewError || "正在生成只读预览…"}</p>}
          <p className="pt-2 text-xs text-muted-foreground">搜索、缩放可在图内操作。需要向 Agent 指定环节，请在「节点与关系」中选择。</p>
        </div>
      )}
      {selection.tab === "data" && (
        <div className="space-y-4 p-4">
          <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <input aria-label="搜索图谱节点" value={selection.query} placeholder="搜索环节、子环节或分组" className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              onChange={(event) => setSelection((previous) => ({ ...previous, query: event.target.value, nodeId: null }))} />
          </label>
          <p className="text-xs text-muted-foreground">显示 {nodes.length} / {spec.nodes.length} 个节点。点选环节查看直接连接；不推断多跳供货关系。</p>
          {selectedNode && <section aria-label="选中环节" className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
            <h3 className="font-semibold">{selectedNode.label}</h3>
            <p className="my-2 text-xs text-muted-foreground">{selectedNode.subtitle}</p>
            {relations.map((edge, index) => <p key={index} className="py-1 text-xs">{label(edge.source)} → {label(edge.target)} · {edge.label || "未说明关系"}</p>)}
            {!relations.length && <p className="text-xs">没有提供明确关系，不能据此判断其独立或无关联。</p>}
            {references.length > 0 && <button type="button" className="mr-4 mt-2 text-xs text-primary" onClick={() => setSelection((previous) => ({ ...previous, tab: "source" }))}>查看本环节引用（{visibleReferences.length}）</button>}
            <button type="button" className="mt-2 text-xs text-primary" onClick={() => setSelection((previous) => ({ ...previous, nodeId: null }))}>清除选择</button>
          </section>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead><tr className="border-b border-border text-muted-foreground"><th className="p-2">环节 / 分组</th><th className="p-2">范围 / 子环节</th><th className="p-2">直接去向（结构示意）</th></tr></thead>
              <tbody>{nodes.map((node) => <tr key={node.id} className={cn("border-b border-border/50 align-top", selection.nodeId === node.id && "bg-primary/10")}>
                <th className="p-2"><button type="button" aria-pressed={selection.nodeId === node.id} className="text-left text-primary underline-offset-4 hover:underline"
                  onClick={() => setSelection((previous) => ({ ...previous, nodeId: node.id }))}>{node.label}</button><p className="mt-1 font-normal text-muted-foreground">{node.group}</p></th>
                <td className="p-2 text-muted-foreground">{node.subtitle || "未提供"}</td>
                <td className="p-2 text-muted-foreground">{spec.edges.filter((edge) => edge.source === node.id).map((edge) => label(edge.target) + "（" + (edge.label || "关系未说明") + "）").join("、") || "未提供"}</td>
              </tr>)}</tbody>
            </table>
          </div>
          {!nodes.length && <p role="status" className="text-sm text-muted-foreground">没有匹配的节点，请调整关键词。</p>}
        </div>
      )}
      {selection.tab === "source" && <div className="space-y-4 p-4 text-xs leading-6">
        <p className="rounded-lg border border-warning/30 bg-warning/5 p-3">{references.length ? "本主题提供逐条原文引用，但仍是预置阅读记录，不是当前用户的复核结论。厂商技术说明不等于独立行业统计，未引用的节点不自动视为有证据。" : "这些是整理说明或来源线索，尚未逐条对应节点、关系和原文页码。"}保存／固化不等于已核实，也不代表当期景气或投资收益。</p>
        {references.length > 0 && <section aria-label="预置逐条引用" className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{selectedNode ? selectedNode.label + "及直接关系" : "全部关系"} · {visibleReferences.length} 条引用</h3>{selectedNode && <button type="button" className="text-primary" onClick={() => setSelection((previous) => ({ ...previous, nodeId: null }))}>查看全部引用</button>}</div>
          <p className="text-muted-foreground">同一网页的不同摘录不是独立交叉验证。需要复核和保存时，可在上方显式复制结构与待复核引用到工作区。</p>
          {visibleReferences.map((item) => <article key={item.id} className="rounded-lg border border-border bg-background/50 p-3">
            <h4 className="font-semibold">{item.title}</h4><p>{item.reviewRequired?.targetLabel}</p>
            <p className="text-muted-foreground">发布：{item.publishedAt || "未知（滚动产品页）"} · 编纂读取：{item.recordedAt}</p>
            <p className="text-muted-foreground">{item.locator}</p><blockquote className="my-2 border-l-2 border-primary/40 pl-3">{item.excerpt}</blockquote>
            <p>{item.note}</p>{evidenceLink(item.url) && <a className="text-primary underline" href={evidenceLink(item.url)!} target="_blank" rel="noreferrer">打开对应原文</a>}
          </article>)}
        </section>}
        <section><h3 className="font-semibold">来源线索</h3><ul className="list-inside list-disc text-muted-foreground">{spec.sources?.length ? spec.sources.map((source, i) => <li key={i}>{source}</li>) : <li>未提供来源</li>}</ul></section>
        <pre className="max-h-[620px] overflow-auto whitespace-pre-wrap break-words text-muted-foreground">{spec.sourceText || "未提供整理原文。"}</pre>
      </div>}
    </GlassCard>
  );
}
