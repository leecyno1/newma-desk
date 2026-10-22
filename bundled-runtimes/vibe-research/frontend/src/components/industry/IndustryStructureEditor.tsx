import { useState } from "react";
import type { GraphArtifactInput, GraphArtifactNode, GraphArtifactEdge } from "@/lib/artifacts";

const field = "mt-1 w-full min-w-0 rounded border border-border bg-background px-2 py-2 text-xs";
const button = "rounded border border-border px-3 py-2 text-xs disabled:opacity-40";
const nodeKinds = { source: "来源", material: "材料", component: "部件／环节", infrastructure: "基础设施", market: "需求市场", company: "企业", risk: "风险", external: "外部因素" };
const edgeKinds = { flow: "流程", dependency: "依赖", supply: "供应", risk: "风险传导" };

export function IndustryStructureEditor({ spec, disabled, onChange, confirm }: {
  spec: GraphArtifactInput; disabled: boolean; onChange: (spec: GraphArtifactInput) => void; confirm: (message: string) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(spec.nodes.length < 2);
  const node = (id: string, patch: Partial<GraphArtifactNode>) => onChange({ ...spec, nodes: spec.nodes.map((item) => item.id === id ? { ...item, ...patch } : item) });
  const edge = (index: number, patch: Partial<GraphArtifactEdge>) => onChange({ ...spec, edges: spec.edges.map((item, i) => i === index ? { ...item, ...patch } : item) });
  return <details className="my-4 rounded-lg border border-border bg-background/50" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer px-3 py-3 text-sm font-semibold">编辑产业结构 · {spec.nodes.length} 个节点 / {spec.edges.length} 条关系</summary>
    <fieldset aria-label="产业结构编辑" disabled={disabled} className="space-y-4 border-t border-border p-3 disabled:opacity-60">
      <p className="text-xs leading-6 text-muted-foreground">修改立即进入未保存草稿，保存新版本才会落库。节点含义或关系改变后，相关证据保留但需重新复核。新增关系不代表真实供货。</p>
      <label className="block text-xs">图谱标题<input aria-label="图谱标题" className={field} maxLength={160} value={spec.title} onChange={(e) => onChange({ ...spec, title: e.target.value })} /></label>
      <div className="space-y-2" aria-label="结构节点">
        {spec.nodes.map((item, index) => <section key={item.id} aria-label={"结构节点 " + (index + 1)} className="rounded border border-border p-3">
          <div className="mb-2 flex items-center justify-between gap-2"><span className="text-xs font-semibold">节点 {index + 1}</span><button type="button" className="text-xs text-destructive" onClick={async () => {
            const connected = spec.edges.filter((entry) => entry.source === item.id || entry.target === item.id).length;
            if (await confirm("移除此节点及 " + connected + " 条直接关系？相关证据转为待复核，已保存版本不变。")) onChange({ ...spec, nodes: spec.nodes.filter((entry) => entry.id !== item.id), edges: spec.edges.filter((entry) => entry.source !== item.id && entry.target !== item.id) });
          }}>移除节点</button></div>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="text-xs">节点名称<input aria-label="节点名称" className={field} maxLength={120} value={item.label} onChange={(e) => node(item.id, { label: e.target.value })} /></label>
            <label className="text-xs">分组<input aria-label="节点分组" className={field} maxLength={80} value={item.group || ""} onChange={(e) => node(item.id, { group: e.target.value })} /></label>
            <label className="text-xs">类型<select aria-label="节点类型" className={field} value={item.kind || "component"} onChange={(e) => node(item.id, { kind: e.target.value as GraphArtifactNode["kind"] })}>{Object.entries(nodeKinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          </div>
          <label className="mt-2 block text-xs">范围／说明<input aria-label="节点说明" className={field} maxLength={600} value={item.subtitle || ""} onChange={(e) => node(item.id, { subtitle: e.target.value })} /></label>
        </section>)}
        <button type="button" className={button} disabled={spec.nodes.length >= 80} onClick={() => {
          const id = "n-" + Array.from(crypto.getRandomValues(new Uint8Array(8)), (part) => part.toString(16).padStart(2, "0")).join("");
          onChange({ ...spec, nodes: [...spec.nodes, { id, label: "", kind: "component" }] });
        }}>添加节点</button>
      </div>
      <div className="space-y-2" aria-label="结构关系">
        {spec.edges.map((item, index) => <section key={index} aria-label={"结构关系 " + (index + 1)} className="rounded border border-border p-3">
          <div className="mb-2 flex items-center justify-between gap-2"><span className="text-xs font-semibold">关系 {index + 1} · 有向连接</span><button type="button" className="text-xs text-destructive" onClick={async () => {
            if (await confirm("移除此关系？原证据保留为待复核，已保存版本不变。")) onChange({ ...spec, edges: spec.edges.filter((_, i) => i !== index) });
          }}>移除关系</button></div>
          <div className="grid gap-2 sm:grid-cols-2">
            {(["source", "target"] as const).map((side) => <label key={side} className="text-xs">{side === "source" ? "起点" : "终点"}<select aria-label={side === "source" ? "关系起点" : "关系终点"} className={field} value={item[side]} onChange={(e) => edge(index, { [side]: e.target.value })}><option value="">请选择节点</option>{spec.nodes.map((entry, i) => <option key={entry.id} value={entry.id}>{entry.label || "未命名节点 " + (i + 1)}</option>)}</select></label>)}
            <label className="text-xs">关系说明<input aria-label="关系说明" className={field} maxLength={120} value={item.label || ""} onChange={(e) => edge(index, { label: e.target.value })} /></label>
            <label className="text-xs">关系类型<select aria-label="关系类型" className={field} value={item.kind || "flow"} onChange={(e) => edge(index, { kind: e.target.value as GraphArtifactEdge["kind"] })}>{Object.entries(edgeKinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          </div>
        </section>)}
        <button type="button" className={button} disabled={spec.nodes.length < 2 || spec.edges.length >= 160} onClick={() => onChange({ ...spec, edges: [...spec.edges, { source: "", target: "", label: "", kind: "flow" }] })}>添加关系</button>
      </div>
    </fieldset>
  </details>;
}
