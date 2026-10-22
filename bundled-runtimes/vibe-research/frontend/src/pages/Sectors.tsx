import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import sectorsData from "@/data/sectors.json";
import { getBaseIndustryGraph } from "@/data/industry-graphs";
import { api } from "@/lib/api";
import { getVibeDeskConfig, subscribeVibeDeskConfig, publishVibeDeskContext, registerVibeDeskContextProvider, registerVibeDeskHandoffHandler, type VibeDeskPageContext, type VibeDeskWikiSubject } from "@/lib/vibedesk";
import { sectorKeyFromWikiHandoff, sectorKeysForLabels } from "@/lib/wiki";

const sectors = sectorsData.sectors;
const coverage = (key: string, count: number) => getBaseIndustryGraph(key) ? "结构图谱" : count ? "环节清单" : "待建立";
function scopeKey() {
  const config = getVibeDeskConfig();
  return JSON.stringify([config?.userId, config?.workspaceId, config?.instanceId]);
}

export function Sectors() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("全部");
  const [linkedSubject, setLinkedSubject] = useState<VibeDeskWikiSubject>();
  const [candidates, setCandidates] = useState<string[]>([]);
  const [mappingStatus, setMappingStatus] = useState("");
  const generation = useRef(0);
  const contextRef = useRef<VibeDeskPageContext>(null!);
  const visible = sectors.filter((sector) => (filter === "全部" || coverage(sector.key, sector.nodes.length) === filter)
    && [sector.label, sector.key, sector.tagline, ...sector.nodes].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  contextRef.current = {
    view: { id: "industry-map", title: "产业图谱 · 板块中心" },
    visibleBlocks: [{ id: "industry-sectors", type: "industry-list", title: "主题目录与覆盖情况" }],
    selection: { linkedSubject: linkedSubject ?? null, candidateSectorKeys: candidates },
    filters: { query, coverage: filter },
    data: {
      source: "vibe-research-industry-map", freshness: "unknown",
      summary: {
        sectorCount: sectors.length, visibleCount: visible.length, graphCount: sectors.filter((sector) => getBaseIndustryGraph(sector.key)).length,
        evidenceStatus: "unverified", taxonomy: "curated-topics-not-official-industry-classification",
        sectors: visible.map((sector) => ({ key: sector.key, label: sector.label, description: sector.tagline, stages: sector.nodes, coverage: coverage(sector.key, sector.nodes.length) })),
        mappingStatus, limitation: "静态主题目录，不代表市场热度；概念名称匹配不能证明企业业务暴露。",
      },
    },
    actions: [], tasks: [],
  };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => {
    let previousScope = scopeKey();
    const unsubscribe = subscribeVibeDeskConfig(() => {
      if (scopeKey() === previousScope) return;
      previousScope = scopeKey();
      generation.current++;
      setLinkedSubject(undefined); setCandidates([]); setMappingStatus(""); setQuery(""); setFilter("全部");
    });
    return () => { generation.current++; unsubscribe(); };
  }, []);
  useEffect(() => registerVibeDeskHandoffHandler(async (handoff) => {
    if (!["security", "industry", "concept"].includes(handoff.subject.type)) throw new Error("产业图谱不支持该对象");
    const requestGeneration = ++generation.current;
    const scope = scopeKey();
    setLinkedSubject(handoff.subject); setCandidates([]); setQuery(""); setFilter("全部"); setMappingStatus("");
    const sectorKey = sectorKeyFromWikiHandoff(handoff);
    if (handoff.subject.type !== "security" && sectorKey) {
      navigate("/sectors/" + sectorKey, { state: { wikiSubject: handoff.subject, scope } });
      return { selected: handoff.subject.canonicalId, sectorKey };
    }
    let matches = sectorKeysForLabels([...handoff.conceptIds.map((id) => id.split(":").pop() || ""), ...handoff.relatedSubjects.map((item) => item.displayName)]);
    if (handoff.subject.type === "security" && handoff.subject.market === "CN" && handoff.subject.symbol) {
      setMappingStatus("正在查找概念线索，不自动确认行业归属…");
      const [blocks, hotConcepts] = await Promise.all([
        api.blocks(handoff.subject.symbol).catch(() => null),
        api.hotConcepts(handoff.subject.symbol).catch(() => null),
      ]);
      if (requestGeneration !== generation.current || scope !== scopeKey()) return { discarded: true };
      matches = [...new Set([...matches, ...sectorKeysForLabels([...(blocks?.concept_tags ?? []), ...(hotConcepts ?? []).map((item) => item.concept)])])];
    }
    if (requestGeneration !== generation.current || scope !== scopeKey()) return { discarded: true };
    setCandidates(matches);
    setMappingStatus(matches.length ? "以下仅为概念匹配候选，请自行选择；不证明收入、供货或客户关系。" : "没有可用的匹配线索，请手动选择主题；未匹配不代表没有相关业务。");
    return { selected: handoff.subject.canonicalId, candidateSectorKeys: matches, confirmed: false };
  }), [navigate]);
  useEffect(() => { void publishVibeDeskContext(); }, [linkedSubject, candidates, mappingStatus, query, filter]);

  return (
    <div>
      <PageHeader title="板块中心" subtitle="产业结构导航 · 先看分工，再核验证据" />
      <div className="mb-5 grid grid-cols-3 divide-x divide-border rounded-xl border border-border bg-card py-4 text-center">
        {[[sectors.length, "研究主题"], [sectors.filter((s) => getBaseIndustryGraph(s.key)).length, "结构图谱"], [sectors.filter((s) => !getBaseIndustryGraph(s.key) && !s.nodes.length).length, "待建立主题"]].map(([value, label]) => <div key={label}><p className="font-mono text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{label}</p></div>)}
      </div>
      <p className="mb-5 text-xs leading-6 text-muted-foreground">预置内容是研究骨架，不是官方行业分类、实时热度或已核实的企业供应链。来源与证据不足之处会保留空白。</p>
      {linkedSubject && <section className="mb-5 rounded-xl border border-primary/30 bg-primary/5 p-4 text-xs">
        <b>研究入口：{linkedSubject.displayName}</b><p className="my-2">{mappingStatus}</p>
        <div className="flex flex-wrap gap-2">{candidates.map((key) => <Link key={key} className="rounded border border-border px-3 py-2 text-primary" to={"/sectors/" + key} state={{ wikiSubject: linkedSubject, scope: scopeKey() }}>{sectors.find((s) => s.key === key)?.label}</Link>)}</div>
      </section>}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row">
        <label className="flex flex-1 items-center gap-2 rounded-lg border border-border px-3 py-2"><Search className="h-4 w-4 text-muted-foreground" /><input aria-label="搜索产业主题" className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="搜索产业、环节或关键词" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <select aria-label="覆盖情况" value={filter} onChange={(event) => setFilter(event.target.value)} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">{["全部", "结构图谱", "环节清单", "待建立"].map((value) => <option key={value}>{value}</option>)}</select>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visible.map((sector) => <Link key={sector.key} to={"/sectors/" + sector.key}>
          <GlassCard className="flex h-full flex-col justify-between transition-colors hover:border-primary/50">
            <div><h2 className="mb-2 text-base font-bold">{sector.label}</h2><p className="text-xs leading-relaxed text-muted-foreground">{sector.tagline}</p></div>
            <div className="mt-4 flex items-center justify-between border-t border-border/50 pt-3 text-xs"><span className={sector.nodes.length ? "text-primary" : "text-muted-foreground"}>{coverage(sector.key, sector.nodes.length)}{sector.nodes.length ? " · " + sector.nodes.length + " 个环节" : ""}</span><ChevronRight className="h-4 w-4" /></div>
          </GlassCard>
        </Link>)}
      </div>
      {!visible.length && <p role="status" className="py-10 text-center text-sm text-muted-foreground">没有匹配的主题，请调整关键词或覆盖筛选。</p>}
      <p className="mt-4 text-center text-xs text-muted-foreground">共 {sectors.length} 个板块 · 当前显示 {visible.length} 个 · 静态整理，资料有效期未核实</p>
      <Disclaimer />
    </div>
  );
}
