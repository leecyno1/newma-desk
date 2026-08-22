import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { portfolioClient, type PortfolioIdentity } from "./api";
import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
} from "./icons";
import type {
  PortfolioWorkspace,
  StrategicAllocationInput,
  StrategicAllocationModel,
  StrategicAllocationResult,
} from "./types";

const PAGE_META: Partial<Record<PortfolioWorkspace, { title: string; english: string; description: string }>> = {
  "portfolio-brief": {
    title: "配置总览",
    english: "Asset Allocation Overview",
    description: "汇总跨资产目标权重、前瞻风险收益和周期证据。",
  },
  "portfolio-allocation": {
    title: "配置模型",
    english: "Allocation Models",
    description: "使用 Black-Litterman、风险平价或最低波动生成目标配置。",
  },
  "portfolio-scenarios": {
    title: "情景推演",
    english: "Scenario Analysis",
    description: "观察增长、通胀、流动性和风险冲击下的组合变化。",
  },
  "portfolio-performance": {
    title: "配置评估",
    english: "Allocation Review",
    description: "拆解风险贡献、预期收益和周期信号可信度。",
  },
  "portfolio-settings": {
    title: "模型说明",
    english: "Model Methodology",
    description: "查看模型假设、数据来源与证据边界。",
  },
};

const MODEL_META: Record<StrategicAllocationModel, { name: string; note: string }> = {
  "black-litterman": { name: "Black-Litterman", note: "长期均衡先验与周期观点融合" },
  "risk-parity": { name: "风险平价", note: "降低高波动资产对组合的支配" },
  "minimum-volatility": { name: "最低波动", note: "在相关性约束下寻找更稳结构" },
};

const CATEGORY_COLORS: Record<string, string> = {
  权益: "#df6b57",
  固收: "#56a4c7",
  商品: "#c7a34b",
  现金: "#7d8794",
};

function workspaceFromSearch(): PortfolioWorkspace {
  const value = new URLSearchParams(window.location.search).get("workspace") as PortfolioWorkspace | null;
  return value && PAGE_META[value] ? value : "portfolio-brief";
}

function parentOrigin() {
  if (document.referrer) {
    try { return new URL(document.referrer).origin; } catch { /* noop */ }
  }
  return "http://127.0.0.1:5888";
}

function pct(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function plainPct(value: number | null | undefined, digits = 1) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${value.toFixed(digits)}%`;
}

function statusLabel(status: StrategicAllocationResult["status"]) {
  if (status === "ready") return "证据完整";
  if (status === "partial") return "研究参考";
  return "长期先验";
}

function buildContext(workspace: PortfolioWorkspace, input: StrategicAllocationInput, result?: StrategicAllocationResult): ModPageContext {
  const meta = PAGE_META[workspace] || PAGE_META["portfolio-brief"]!;
  return {
    view: { id: workspace, title: meta.title },
    visibleBlocks: [
      { id: "allocation-summary", type: "portfolio-summary", title: "资产配置结论" },
      { id: "allocation-assets", type: "portfolio-allocation", title: "资产风险收益与目标权重" },
    ],
    selection: {},
    filters: { ...input },
    data: {
      asOf: result?.cycleAsOf || result?.generatedAt,
      source: "newma-seven-cycle + strategic-allocation",
      freshness: result ? "fresh" : "unknown",
      summary: result ? { ...result } : {},
    },
    actions: [
      { id: "portfolio.refresh", label: "刷新配置", available: true },
      { id: "portfolio.optimize", label: "生成目标配置", available: true },
    ],
    tasks: [],
  };
}

function SummaryMetrics({ result }: { result: StrategicAllocationResult }) {
  return <section className="saa-metrics" aria-label="配置关键指标">
    <article><span>组合预期收益</span><strong className={result.expectedReturnPct >= 0 ? "up" : "down"}>{pct(result.expectedReturnPct)}</strong><small>年化 · 周期观点融合</small></article>
    <article><span>目标 / 实际波动</span><strong>{plainPct(result.targetVolatilityPct)} <i>/</i> {plainPct(result.achievedVolatilityPct)}</strong><small>不使用杠杆</small></article>
    <article><span>风险调整收益</span><strong>{result.sharpe?.toFixed(2) ?? "—"}</strong><small>预期 Sharpe</small></article>
    <article><span>现金缓冲</span><strong>{plainPct(result.cashWeightPct)}</strong><small>目标波动率自动控制</small></article>
  </section>;
}

function AllocationStrip({ result }: { result: StrategicAllocationResult }) {
  return <div className="saa-allocation-strip" aria-label="目标配置比例">
    {result.assets.filter((asset) => asset.targetWeightPct > 0).map((asset) => (
      <div
        key={asset.id}
        style={{ width: `${asset.targetWeightPct}%`, background: CATEGORY_COLORS[asset.category] || "#7d8794" }}
        title={`${asset.name} ${plainPct(asset.targetWeightPct)}`}
      >
        {asset.targetWeightPct >= 7 ? <span>{asset.name} {asset.targetWeightPct.toFixed(0)}%</span> : null}
      </div>
    ))}
  </div>;
}

function AssetTable({ result, compact = false }: { result: StrategicAllocationResult; compact?: boolean }) {
  return <div className="saa-table-wrap">
    <table className="saa-table">
      <thead><tr>
        <th>资产</th><th>目标权重</th><th>预期收益</th><th>预期波动</th>
        {!compact && <th>风险贡献</th>}<th>上涨概率</th><th>周期置信度</th>
      </tr></thead>
      <tbody>{result.assets.map((asset) => (
        <tr key={asset.id}>
          <td><div className="saa-asset-name"><i style={{ background: CATEGORY_COLORS[asset.category] }} /><span><b>{asset.name}</b><small>{asset.category}</small></span></div></td>
          <td><div className="saa-weight"><span><i style={{ width: `${Math.min(100, asset.targetWeightPct * 2.5)}%` }} /></span><b>{plainPct(asset.targetWeightPct)}</b></div></td>
          <td className={asset.expectedReturnPct >= 0 ? "up" : "down"}>{pct(asset.expectedReturnPct)}</td>
          <td>{plainPct(asset.volatilityPct)}</td>
          {!compact && <td>{plainPct(asset.riskContributionPct)}</td>}
          <td>{plainPct(asset.upProbabilityPct, 0)}</td>
          <td><span className={`saa-evidence evidence-${asset.publicationStatus}`}>{asset.id === "cash" ? "模型输入" : `${asset.confidencePct.toFixed(0)}%`}</span></td>
        </tr>
      ))}</tbody>
    </table>
  </div>;
}

function Overview({ result }: { result: StrategicAllocationResult }) {
  return <>
    <SummaryMetrics result={result} />
    <section className="saa-section saa-overview-grid">
      <div className="saa-main-pane">
        <div className="saa-section-head"><div><span>TARGET MIX</span><h2>目标资产配置</h2></div><b>{MODEL_META[result.model].name}</b></div>
        <AllocationStrip result={result} />
        <AssetTable result={result} />
      </div>
      <aside className="saa-insight-pane">
        <div className="saa-section-head"><div><span>FORWARD VIEW</span><h2>前沿结论</h2></div><Activity size={17} /></div>
        <ol>{result.insights.map((insight) => <li key={insight}>{insight}</li>)}</ol>
        <div className="saa-source-line"><Database size={14} /><span>周期数据 {result.cycleAsOf || "暂不可用"}</span></div>
      </aside>
    </section>
  </>;
}

function ModelControls({ input, setInput, run, loading }: {
  input: StrategicAllocationInput;
  setInput: Dispatch<SetStateAction<StrategicAllocationInput>>;
  run(): void;
  loading: boolean;
}) {
  return <aside className="saa-controls">
    <div className="saa-section-head"><div><span>MODEL INPUT</span><h2>配置参数</h2></div><SlidersHorizontal size={17} /></div>
    <div className="saa-model-options">
      {(Object.entries(MODEL_META) as Array<[StrategicAllocationModel, { name: string; note: string }]>).map(([id, meta]) => (
        <button key={id} className={input.model === id ? "active" : ""} onClick={() => setInput((current) => ({ ...current, model: id }))}>
          <strong>{meta.name}</strong><span>{meta.note}</span>
        </button>
      ))}
    </div>
    <label><span>目标年化波动率 <b>{plainPct(input.targetVolatilityPct)}</b></span><input type="range" min="3" max="20" step="0.5" value={input.targetVolatilityPct} onChange={(event) => setInput((current) => ({ ...current, targetVolatilityPct: Number(event.target.value) }))} /></label>
    <div className="saa-two-fields">
      <label><span>预测周期</span><select value={input.horizonMonths} onChange={(event) => setInput((current) => ({ ...current, horizonMonths: Number(event.target.value) as 1 | 3 | 6 }))}><option value="1">1 个月</option><option value="3">3 个月</option><option value="6">6 个月</option></select></label>
      <label><span>单资产上限</span><select value={input.maxWeight} onChange={(event) => setInput((current) => ({ ...current, maxWeight: Number(event.target.value) }))}><option value="0.25">25%</option><option value="0.35">35%</option><option value="0.45">45%</option></select></label>
    </div>
    <label><span>无风险收益率</span><input type="number" min="-2" max="15" step="0.1" value={input.riskFreeRatePct} onChange={(event) => setInput((current) => ({ ...current, riskFreeRatePct: Number(event.target.value) }))} /></label>
    <button className="saa-primary" onClick={run} disabled={loading}>{loading ? <LoaderCircle className="spin" size={16} /> : <Gauge size={16} />}生成目标配置</button>
  </aside>;
}

function ModelWorkbench(props: Parameters<typeof ModelControls>[0] & { result: StrategicAllocationResult }) {
  return <section className="saa-workbench">
    <ModelControls {...props} />
    <div className="saa-result-pane">
      <SummaryMetrics result={props.result} />
      <div className="saa-section">
        <div className="saa-section-head"><div><span>MODEL OUTPUT</span><h2>资产风险收益与目标权重</h2></div><span className={`saa-status status-${props.result.status}`}>{statusLabel(props.result.status)}</span></div>
        <AssetTable result={props.result} />
      </div>
    </div>
  </section>;
}

function ScenarioView({ result }: { result: StrategicAllocationResult }) {
  const assetRows = result.assets.filter((asset) => asset.id !== "cash");
  return <section className="saa-section">
    <div className="saa-section-head"><div><span>STRESS MATRIX</span><h2>宏观情景冲击</h2></div><BarChart3 size={17} /></div>
    <div className="saa-scenario-grid">{result.scenarios.map((scenario) => (
      <article key={scenario.id}>
        <header><div><strong>{scenario.name}</strong><span>{scenario.description}</span></div><b className={scenario.portfolioImpactPct >= 0 ? "up" : "down"}>{pct(scenario.portfolioImpactPct)}</b></header>
        <div>{assetRows.map((asset) => <span key={asset.id}><i>{asset.name}</i><b className={(scenario.assetImpactsPct[asset.id] || 0) >= 0 ? "up" : "down"}>{pct(scenario.assetImpactsPct[asset.id])}</b></span>)}</div>
      </article>
    ))}</div>
  </section>;
}

function ReviewView({ result }: { result: StrategicAllocationResult }) {
  return <section className="saa-review-grid">
    <div className="saa-section">
      <div className="saa-section-head"><div><span>RISK BUDGET</span><h2>风险贡献</h2></div><ShieldCheck size={17} /></div>
      <div className="saa-risk-list">{result.assets.filter((asset) => asset.id !== "cash").sort((a, b) => b.riskContributionPct - a.riskContributionPct).map((asset) => (
        <div key={asset.id}><span><b>{asset.name}</b><i>{plainPct(asset.targetWeightPct)} 权重</i></span><div><i style={{ width: `${Math.max(0, asset.riskContributionPct)}%` }} /></div><strong>{plainPct(asset.riskContributionPct)}</strong></div>
      ))}</div>
    </div>
    <div className="saa-section">
      <div className="saa-section-head"><div><span>EVIDENCE</span><h2>周期观点可信度</h2></div><Database size={17} /></div>
      <AssetTable result={result} compact />
      {result.warnings.map((warning) => <p className="saa-warning" key={warning}><TriangleAlert size={13} />{warning}</p>)}
    </div>
  </section>;
}

function Methodology({ result }: { result: StrategicAllocationResult }) {
  return <section className="saa-methodology">
    <div className="saa-section">
      <div className="saa-section-head"><div><span>MODEL PIPELINE</span><h2>计算链路</h2></div><Gauge size={17} /></div>
      <ol><li><b>长期均衡先验</b><span>使用战略基准权重、长期波动率和资产类别相关性构建均衡收益。</span></li><li><b>周期观点融合</b><span>从周期叠加提取下阶段收益、波动与上涨概率，按证据等级收缩。</span></li><li><b>目标权重求解</b><span>根据所选模型与单资产上限生成跨资产权重。</span></li><li><b>目标波动控制</b><span>不使用杠杆；风险超标时提高现金比例，直到接近目标波动率。</span></li></ol>
    </div>
    <div className="saa-section">
      <div className="saa-section-head"><div><span>DATA CONTRACT</span><h2>数据与边界</h2></div><Database size={17} /></div>
      <dl><div><dt>周期数据</dt><dd>{result.cycleAsOf || "不可用"}</dd></div><div><dt>模型</dt><dd>{result.method}</dd></div><div><dt>资产层级</dt><dd>资产类别，不下钻单只股票</dd></div><div><dt>刷新方式</dt><dd>打开页面及手动刷新</dd></div></dl>
      {result.warnings.map((warning) => <p className="saa-warning" key={warning}><TriangleAlert size={13} />{warning}</p>)}
    </div>
  </section>;
}

export function StrategicAllocationApp() {
  const workspace = workspaceFromSearch();
  const meta = PAGE_META[workspace] || PAGE_META["portfolio-brief"]!;
  const embedded = window.self !== window.top;
  if (!embedded && !document.documentElement.dataset.theme) {
    document.documentElement.dataset.theme = "dark";
  }
  const [identity, setIdentity] = useState<PortfolioIdentity | undefined>(() => embedded ? undefined : { userId: "local-user", workspaceId: "local-workspace" });
  const [input, setInput] = useState<StrategicAllocationInput>({ model: "black-litterman", targetVolatilityPct: 10, horizonMonths: 6, maxWeight: 0.35, riskFreeRatePct: 1.5 });
  const [result, setResult] = useState<StrategicAllocationResult>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [host, setHost] = useState<Extract<ModHostConnection, { embedded: true }>>();
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const inputRef = useRef(input);
  const loadRef = useRef<() => Promise<StrategicAllocationResult | undefined>>(async () => undefined);
  const contextRef = useRef<ModPageContext>(buildContext(workspace, input));
  inputRef.current = input;

  const load = useCallback(async () => {
    if (!identity) return undefined;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const next = await portfolioClient(identity).strategicAllocation(inputRef.current, { signal: controller.signal });
      if (!controller.signal.aborted) setResult(next);
      return next;
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "资产配置暂时不可用");
      return undefined;
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [identity]);
  loadRef.current = load;

  useEffect(() => { if (identity) void load(); }, [identity, load]);
  useEffect(() => {
    let active = true;
    let connection: ModHostConnection | undefined;
    void connectModHost({ modId: workspace, parentOrigin: parentOrigin(), capabilities: ["actions", "agent", "context", "theme"] }).then((next) => {
      if (!active) { next.close(); return; }
      connection = next;
      if (!next.embedded) return;
      setHost(next);
      setIdentity({ userId: next.config.user.id, workspaceId: next.config.workspace.id });
      document.documentElement.dataset.theme = next.config.environment.theme;
      next.subscribe((desk) => {
        document.documentElement.dataset.theme = desk.environment.theme;
        setIdentity({ userId: desk.user.id, workspaceId: desk.workspace.id });
      });
      next.setContextProvider(() => contextRef.current);
      next.setUiActionHandler(async (actionId) => {
        if (actionId !== "portfolio.refresh" && actionId !== "portfolio.optimize") throw new Error(`Unsupported action: ${actionId}`);
        return await loadRef.current() || { ok: false };
      });
    }).catch(() => undefined);
    return () => { active = false; connection?.close(); };
  }, [workspace]);
  useEffect(() => () => controllerRef.current?.abort(), []);

  contextRef.current = buildContext(workspace, input, result);
  useEffect(() => { if (host) host.publishContext(contextRef.current); }, [host, input, result, workspace]);

  const view = useMemo(() => {
    if (!result) return null;
    if (workspace === "portfolio-allocation") return <ModelWorkbench input={input} setInput={setInput} run={() => void load()} loading={loading} result={result} />;
    if (workspace === "portfolio-scenarios") return <ScenarioView result={result} />;
    if (workspace === "portfolio-performance") return <ReviewView result={result} />;
    if (workspace === "portfolio-settings") return <Methodology result={result} />;
    return <Overview result={result} />;
  }, [input, loading, result, workspace]);

  return <main className="saa-root" data-embedded={embedded || undefined}>
    <header className="saa-toolbar">
      {!embedded && <div data-mod-page-title><span>{meta.english}</span><h1>{meta.title}</h1><p>{meta.description}</p></div>}
      <div className="saa-toolbar-actions">
        {result && <span className={`saa-status status-${result.status}`}>{statusLabel(result.status)}</span>}
        <span className="saa-asof">周期数据 {result?.cycleAsOf || "—"}</span>
        <button onClick={() => void load()} disabled={loading} title="刷新配置数据">{loading ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}<span>刷新</span></button>
      </div>
    </header>
    {error && <div className="saa-error">{error}</div>}
    {loading && !result ? <div className="saa-loading"><LoaderCircle className="spin" size={20} /><span>正在读取周期数据并生成配置</span></div> : view}
  </main>;
}
