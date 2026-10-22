import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { IndustryArtifactView, type IndustryGraphSelection } from "@/components/industry/IndustryArtifactView";
import { IndustryWorkspace, type IndustryWorkspaceView } from "@/components/industry/IndustryWorkspace";
import { useIndustryConfirm } from "@/components/industry/useIndustryConfirm";
import { evidenceCoverage, industryStructureError } from "@/lib/industryWorkspace";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { listGraphArtifacts, previewGraphArtifact, type GraphArtifactInput, type ModArtifactRecord } from "@/lib/artifacts";
import { getVibeDeskConfig, subscribeVibeDeskConfig, publishVibeDeskContext, registerVibeDeskContextProvider, type VibeDeskPageContext, type VibeDeskWikiSubject } from "@/lib/vibedesk";
import { getBaseIndustryGraph } from "@/data/industry-graphs";
import { HBM_REFERENCES } from "@/data/hbm-research";
import sectorsData from "@/data/sectors.json";
import { industrySubject } from "@/lib/wiki";

function currentScope() {
  const config = getVibeDeskConfig();
  return JSON.stringify([config?.userId, config?.workspaceId, config?.instanceId]);
}

export function SectorDetail() {
  const { key } = useParams();
  const [scope, setScope] = useState(currentScope);
  useEffect(() => subscribeVibeDeskConfig(() => setScope(currentScope())), []);
  return <SectorDetailContent key={key + scope} sectorKey={key} />;
}

function SectorDetailContent({ sectorKey }: { sectorKey?: string }) {
  const navigate = useNavigate();
  const { confirm, confirmation } = useIndustryConfirm();
  const location = useLocation();
  const sector = sectorsData.sectors.find((item) => item.key === sectorKey);
  const routeState = location.state as { wikiSubject?: VibeDeskWikiSubject; scope?: string } | null;
  const linkedSubject = routeState?.scope === currentScope() ? routeState.wikiSubject : undefined;
  const [history, setHistory] = useState<ModArtifactRecord[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [artifactId, setArtifactId] = useState("");
  const [workspaceView, setWorkspaceView] = useState<IndustryWorkspaceView | null>(null);
  const [preview, setPreview] = useState<{ spec: GraphArtifactInput; html?: string; error?: string }>();
  const [selection, setSelection] = useState<IndustryGraphSelection>({ tab: "graph", nodeId: null, query: "" });
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const artifact = history.find((item) => item.id === artifactId);
  const base = sector ? getBaseIndustryGraph(sector.key) : null;
  const sourceSpec = artifact?.spec ?? base;
  const sourceEvidence = !artifact && sectorKey === "hbm" ? HBM_REFERENCES : undefined;
  const publicReferences = !workspaceView ? sourceEvidence : undefined;
  const spec = workspaceView?.version.spec ?? sourceSpec;
  const structureError = spec ? industryStructureError(spec) : null;
  const contextRef = useRef<VibeDeskPageContext>(null!);
  const selectedNode = spec?.nodes.find((node) => node.id === selection.nodeId) ?? null;
  contextRef.current = {
    view: { id: "industry-map", title: sector ? sector.label + "产业结构" : "板块不存在" },
    visibleBlocks: sector ? [{ id: "industry-graph", type: selection.tab, title: "产业结构与来源" }] : [],
    selection: { sectorKey: sector?.key ?? null, selectedNode, linkedSubject: linkedSubject ?? null, artifactId: artifact?.id ?? null },
    filters: { query: selection.query, tab: selection.tab },
    data: {
      source: "vibe-research-industry-map", freshness: "unknown",
      summary: {
        evidenceStatus: "unverified", taxonomy: "curated-topics-not-official-industry-classification",
        origin: workspaceView ? "user-workspace-version" : artifact ? "legacy-shared-artifact" : "bundled-curated-outline",
        version: workspaceView ? workspaceView.version.number : artifact?.id ?? base?.metadata?.baseVersion ?? null,
        savedAt: workspaceView ? workspaceView.version.savedAt || null : artifact?.updatedAt ?? null,
        workspaceEvidence: workspaceView ? { dirty: workspaceView.dirty, revision: workspaceView.revision,
          evidence: workspaceView.version.evidence, pendingEvidence: workspaceView.pendingEvidence, sourceCheck: workspaceView.sourceCheck,
          coverage: evidenceCoverage(workspaceView.version.spec, workspaceView.version.evidence),
          authority: "manual-records-not-system-verification" } : null,
        nodes: spec?.nodes ?? [], edges: spec?.edges ?? [], sources: spec?.sources ?? [],
        previewStatus: !spec ? "unavailable" : structureError ? "invalid" : artifact && !workspaceView ? "saved-artifact"
          : preview?.spec !== spec ? "loading" : preview.error ? "unavailable" : "ready",
        previewError: structureError || (preview?.spec === spec ? preview.error ?? null : null),
        publicReferences: publicReferences ?? [],
        referenceAuthority: publicReferences?.length ? "public-reading-not-user-review-or-independent-verification" : null,
        sourceText: spec?.sourceText ?? null, stages: sector?.nodes ?? [],
        selectedRelations: selectedNode ? spec?.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id) : [],
        limitations: ["静态整理，非实时或逐边核验数据", "主题匹配不证明公司业务暴露或供货关系", "保存时间不是资料发布日期", "图内缩放和选点未回传；节点列表选择已回传"],
      },
    },
    actions: [], tasks: [],
    ...(sector ? { wiki: { primarySubject: industrySubject(sector.key, sector.label), relatedSubjects: [], conceptIds: [], intent: "industry.chain" } } : {}),
  };
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [sectorKey, artifactId, selection, linkedSubject, workspaceView, preview, structureError]);
  useEffect(() => {
    if (!spec || structureError || (artifact && !workspaceView)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => { void previewGraphArtifact(spec, controller.signal).then(
      (html) => { if (!controller.signal.aborted) setPreview({ spec, html }); },
      (error) => { if (!controller.signal.aborted) setPreview({ spec, error: error.message }); },
    ); }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [spec, structureError, artifact, Boolean(workspaceView)]);
  const loadHistory = async () => {
    if (loadingHistory) return;
    setLoadingHistory(true);
    setHistoryError(null);
    try {
      const items = await listGraphArtifacts();
      if (active.current) { setHistory(items.filter((item) => item.spec.metadata?.sectorKey === sectorKey)); setHistoryLoaded(true); }
    } catch (error) {
      if (active.current) setHistoryError(error instanceof Error ? error.message : "历史图谱读取失败");
    } finally {
      if (active.current) setLoadingHistory(false);
    }
  };
  if (!sector) return <p className="py-12 text-center">未找到该板块。<Link className="text-primary" to="/sectors">返回板块中心</Link></p>;
  return (
    <div>
      {confirmation}
      <Link to="/sectors" onClick={async (event) => { if (workspaceView?.dirty) { event.preventDefault(); if (await confirm("离开将放弃未保存的图谱修改，继续？")) navigate("/sectors"); } }} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground"><ArrowLeft className="h-4 w-4" />板块中心</Link>
      <header className="mb-5"><h1 className="text-xl font-semibold">{sector.label}</h1><p className="mt-2 text-xs leading-6 text-muted-foreground">{sector.tagline}</p></header>
      <div className="mb-5 border-l-2 border-warning bg-warning/5 px-4 py-3 text-xs leading-6">
        <b>结构草图 · 待证据核验</b>
        <p>用于理解产业分工，不是实时景气、公司供应链或投资建议。打开页面不会保存或发布图谱。</p>
        <p>{workspaceView ? "当前显示工作区" + (workspaceView.dirty ? "未保存草稿" : "版本 " + workspaceView.version.number) : artifact ? "当前显示历史共享记录；保存时间：" + artifact.updatedAt : base ? "预置整理版本：" + String(base.metadata?.baseVersion) : "当前仅有主题目录或环节清单，尚无关系图。"} · 资料有效期未核实</p>
        {linkedSubject && <p>研究入口：{linkedSubject.displayName}。仅主题关联，不代表该公司的业务或供货关系已确认。</p>}
      </div>
      <details hidden={Boolean(workspaceView)} className="mb-5 rounded-xl border border-border p-3 text-xs">
        <summary className="cursor-pointer font-medium">历史共享图谱（非私人工作区）</summary>
        <p className="my-3 text-muted-foreground">旧图谱库按模块共享，未做账户／工作区隔离。原记录保留；本页只读查看，不在此保存私人研究。</p>
        <button type="button" className="rounded border border-border px-3 py-2" disabled={loadingHistory} onClick={loadHistory}>{loadingHistory ? "读取中…" : "读取历史共享图谱"}</button>
        {historyError && <p role="alert" className="mt-2 text-destructive">{historyError}</p>}
        {historyLoaded && <label className="mt-3 block">选择查看版本<select aria-label="图谱版本" className="mt-2 block w-full rounded border border-border bg-background p-2" value={artifactId}
          onChange={(event) => { setArtifactId(event.target.value); setSelection({ tab: "graph", query: "", nodeId: null }); }}>
          <option value="">预置结构（只读）</option>
          {history.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.updatedAt} · {item.status === "published" ? "已固化，非已核实" : "草稿"}</option>)}
        </select>{!history.length && <p className="mt-2">该主题没有历史共享图谱。</p>}</label>}
      </details>
      <IndustryWorkspace sectorKey={sector.key} sectorLabel={sector.label} sourceSpec={sourceSpec} sourceEvidence={sourceEvidence} provenance={artifact ? "历史共享图谱 " + artifact.id : "预置结构 " + String(base?.metadata?.baseVersion ?? "无版本")} onViewChange={setWorkspaceView} />
      <section aria-label="产业图谱研究交接" className="mb-4 rounded-lg border border-border p-3 text-xs leading-6">
        <button type="button" className="rounded bg-primary/20 px-3 py-2 text-primary disabled:opacity-40"
          disabled={!workspaceView || workspaceView.dirty || !workspaceView.version.number || !selectedNode}
          onClick={() => {
            const config = getVibeDeskConfig();
            if (!config?.instanceId || !workspaceView || workspaceView.dirty || !selectedNode) return;
            const search = new URLSearchParams({ sourceModule: "industry-map", sector: sector.key, node: selectedNode.id,
              version: String(workspaceView.version.number), revision: String(workspaceView.revision),
              sourceUserId: config.userId, sourceWorkspaceId: config.workspaceId, theme: sector.label, market: "GLOBAL" }).toString();
            window.parent.postMessage({ type: "vibedesk:navigate", modId: config.moduleId, instanceId: config.instanceId, targetModId: "instock-industry-chain", search }, config.gatewayOrigin);
          }}>带选中环节进入产业链证据</button>
        <p className="mt-2 text-muted-foreground">先保存工作区版本，再在「节点与关系」选中环节。接收页需显式读取、确认；只传版本与节点标识，不把私人摘录放入网址，也不自动采集或认定企业关系。</p>
      </section>
      {spec ? <IndustryArtifactView key={(workspaceView ? "workspace-" + workspaceView.version.number : artifactId) || sector.key} spec={spec} viewUrl={workspaceView ? undefined : artifact?.viewUrl}
        references={publicReferences} previewHtml={!structureError && preview?.spec === spec ? preview.html : undefined} previewError={structureError || (preview?.spec === spec ? preview.error : null)} onSelectionChange={setSelection} />
        : <div className="mb-6 rounded-xl border border-dashed border-border p-6">
          <h2 className="mb-3 font-semibold">关系图尚未建立</h2>
          <p className="text-sm text-muted-foreground">需要有来源的上下游关系，不能把环节列表自动串成产业链。</p>
          <div className="mt-4 flex flex-wrap gap-2">{sector.nodes.map((node) => <span key={node} className="rounded border border-border px-3 py-1 text-xs">{node}</span>)}</div>
        </div>}
      <p className="mb-4 text-xs leading-6 text-muted-foreground">投资研究下一步：核对需求与订单 → 识别产能、价格和利润传导 → 在产业链证据模块核验公司关系。本页不重复计算景气评分或生成买卖建议。</p>
      <Disclaimer />
    </div>
  );
}
