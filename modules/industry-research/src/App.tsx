import { useEffect, useMemo, useRef, useState } from "react";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";
import { contextFor, fmt, METRICS, migrationFor, publicationsFor, researchQuestions, rowsFor, STATES, type History, type Industry, type Metric, type Snapshot } from "./research";
import { HistoryPanel } from "./HistoryPanel";
import { MigrationPanel } from "./MigrationPanel";
import { ProductionPanel } from "./ProductionPanel";
import { productionFor, type Production } from "./production";
import { usePeriodEvidence } from "./usePeriodEvidence";
import { pricesFor, type Prices } from "./prices";
import { PricePanel } from "./PricePanel";
import { diagnosisFor } from "./diagnosis";
import { DiagnosisPanel } from "./DiagnosisPanel";
import { Scatter } from "./ScatterPlot";
import { OperationsPanel } from "./OperationsPanel";
import { capacityFor, capacityPeriodEnd, type Capacity } from "./capacity";
import { CapacityPanel } from "./CapacityPanel";
import { useCompanyEvidence } from "./useCompanyEvidence";
import { CompanyPanel } from "./CompanyPanel";
import { TrackingPanel } from "./TrackingPanel";
import { useIndustryTracking } from "./useIndustryTracking";
import { TrackingOverview } from "./TrackingOverview";
import { resolveDeskOrigin } from "./deskOrigin";

type Host = Extract<ModHostConnection, {embedded: true}>;
const DEFAULTS = ["煤炭开采和洗选业", "计算机、通信和其他电子设备制造业"];
function deskOrigin() {
  return resolveDeskOrigin(location.href, import.meta.env.VITE_PARENT_ORIGIN);
}
const deskHref = (mod: string) => {
  const configured = import.meta.env.VITE_DESK_URL;
  if (!configured && import.meta.env.MODE === "standalone" && window.parent === window) return undefined;
  return `${configured ? new URL(configured).origin : deskOrigin()}/?mod=${mod}`;
};

export function App() {
  const embedded = window.parent !== window;
  const [host, setHost] = useState<Host>();
  const [latest, setData] = useState<Snapshot | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [historyStatus, setHistoryStatus] = useState("idle");
  const [historyError, setHistoryError] = useState("");
  const [historyRequest, setHistoryRequest] = useState(0);
  const [publicationUrl, setPublicationUrl] = useState("");
  const publications = useMemo(() => publicationsFor(latest, history), [latest, history]);
  const data = latest ? publications.find(item => item.sourceUrl === (publicationUrl || latest.sourceUrl)) ?? latest : null;
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [sort, setSort] = useState<Metric>("profitYoy");
  const [selectedName, setSelectedName] = useState(DEFAULTS[0]);
  const [compare, setCompare] = useState<string[]>(DEFAULTS);
  const scopeRows = useMemo(() => rowsFor(data, query, "all", sort), [data, query, sort]);
  const rows = useMemo(() => scopeRows.filter(row => state === "all" || row.quadrant === state), [scopeRows, state]);
  const migration = useMemo(() => data && history && historyStatus === "ready" ? migrationFor(data, publications, scopeRows) : null, [data, history, historyStatus, publications, scopeRows]);
  const selected = rows.find(r => r.name === selectedName) ?? rows[0];
  const company = useCompanyEvidence(host, data, selected);
  const tracker = useIndustryTracking(host, selected?.name);
  const comparison = useMemo(() => compare.flatMap(name => data?.rows.filter(r => r.name === name) ?? []), [data, compare]);
  const sourceKey = data ? `${data.sourceUrl}|${data.fetchedAt}` : undefined;
  const production = usePeriodEvidence<Production>("production", data?.periodEnd, sourceKey);
  const prices = usePeriodEvidence<Prices>("prices", data?.periodEnd, sourceKey);
  const capacity = usePeriodEvidence<Capacity>("capacity", capacityPeriodEnd(data?.periodEnd), sourceKey);
  const capacityEvidence = useMemo(() => capacityFor(data, selected, capacity.data, capacity.status, capacity.error), [data, selected, capacity.data, capacity.status, capacity.error]);
  const productionEvidence = useMemo(() => productionFor(data, selected, production.data, production.status, production.error), [data, selected, production.data, production.status, production.error]);
  const priceEvidence = useMemo(() => pricesFor(data, selected, prices.data, prices.status, prices.error, productionEvidence), [data, selected, prices.data, prices.status, prices.error, productionEvidence]);
  const diagnosis = useMemo(() => diagnosisFor(data, selected, productionEvidence, priceEvidence, publications, historyStatus, capacityEvidence), [data, selected, productionEvidence, priceEvidence, publications, historyStatus, capacityEvidence]);
  const context = useMemo(() => contextFor(data, rows, selected, comparison, {query, quadrant: state, sort, publicationUrl: data?.sourceUrl, historicalReport: data?.sourceUrl !== latest?.sourceUrl}, status, error,
    history, historyStatus, historyError, publications, productionEvidence, priceEvidence, diagnosis, capacityEvidence, company.context, tracker.context), [data, latest, rows, selected, comparison, query, state, sort, status, error, history, historyStatus, historyError, publications, productionEvidence, priceEvidence, diagnosis, capacityEvidence, company.context, tracker.context]);
  const ref = useRef(context); ref.current = context;

  useEffect(() => {
    const controller = new AbortController();
    setData(null); setStatus("loading"); setError("");
    void fetch(`/api/industry-research${refresh ? "?refresh=true" : ""}`, {signal: controller.signal})
      .then(async res => {const body = await res.json(); if (!res.ok) throw new Error(body.detail || "行业数据读取失败"); return body as Snapshot;})
      .then(body => {if (!controller.signal.aborted) {setData(body); setStatus("ready");}})
      .catch(reason => {if (!controller.signal.aborted) {setError(reason instanceof Error ? reason.message : "读取失败"); setStatus("failed");}});
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => {
    if (!historyRequest) return;
    const controller = new AbortController();
    void fetch(`/api/industry-research/history${historyRequest > 1 ? "?refresh=true" : ""}`, {signal: controller.signal})
      .then(async res => {const body = await res.json(); if (!res.ok) throw new Error(body.detail || "历史读取失败"); return body as History;})
      .then(body => {if (!controller.signal.aborted) {setHistory(body); setHistoryStatus("ready");}})
      .catch(reason => {if (!controller.signal.aborted) {setHistoryError(reason instanceof Error ? reason.message : "历史读取失败"); setHistoryStatus("failed");}});
    return () => controller.abort();
  }, [historyRequest]);
  useEffect(() => {
    const controller = new AbortController(); let close = () => {};
    const parentOrigin = deskOrigin();
    void connectModHost({modId: "industry-prosperity", parentOrigin, sdkVersion: "0.1.0", capabilities: ["context", "agent", "theme", "storage"], signal: controller.signal})
      .then(connection => {close = connection.close; if (controller.signal.aborted) return close(); if (connection.embedded) setHost(connection);})
      .catch(() => undefined);
    return () => {controller.abort(); close();};
  }, []);
  useEffect(() => host?.setContextProvider(() => ref.current), [host]);
  useEffect(() => {host?.publishContext(context);}, [host, context]);
  function reload() {setData(null); setStatus("loading"); setError(""); setRefresh(v => v + 1);
    setHistory(null); setHistoryStatus("idle"); setHistoryError(""); setHistoryRequest(0); setPublicationUrl("");}
  function loadHistory() {setHistory(null); setPublicationUrl(""); setHistoryError(""); setHistoryStatus("loading"); setHistoryRequest(v => v + 1);}
  function toggle(name: string) {setCompare(current => current.includes(name) ? current.filter(x => x !== name) : current.length < 4 ? [...current, name] : current);}
  function exportEvidence() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({snapshot: data, history, migration, production: productionEvidence, prices: priceEvidence, capacity: capacityEvidence, company: company.context, tracking: tracker.context, diagnosis, growthStructure: context.data.summary?.growthStructure, selection: selected?.name, comparison: compare, filters: {query, state, sort}}, null, 2)], {type: "application/json"}));
    const a = document.createElement("a"); a.href = url; a.download = `industry-evidence-${data.periodEnd}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const evidencePrompt = "先核对diagnosis中的规则判断、证据覆盖和原文来源，不把规则诊断当作独立事实。基于当前页面selection、comparison、publication、history、production和prices，比较营收、利润、生产与行业价格，区分事实与推断。prices仅在已加载且行业和期间匹配时使用；环比、同比、年内平均同比必须分开，年内平均同比不是累计涨幅，PPI不是现货/长协或公司售价，不以全国购进价格代替行业成本，不计算未经验证的价格贡献。production中的产量不是销量或需求，不用增速差推算价格，不从集成电路数量推断整个半导体盈利。历史报告不能冒充最新，现时读取的历史网页不是当时存档。说明样本、累计口径和缺口，给出三项验证问题；不把方向一致当作拐点，不补造库存、订单或估值。";
  return <main className="industry-root">
    <header className="toolbar">{!embedded && <h1>行业景气</h1>}<span className="edition">INDUSTRY / FUNDAMENTALS</span>
      <button onClick={reload} disabled={status === "loading"}>{status === "loading" ? "读取官方原表…" : "刷新原文"}</button>
      <button onClick={exportEvidence} disabled={!data}>导出证据快照</button>
      {host ? <button disabled={!data} onClick={() => host.requestAgent({prompt: evidencePrompt + " 同时核对capacity季度证据及其timingNote：不把滞后季度作为当前月需求，不以利用率确认订单增长。production.nationalSales仅是全国产销背景，不可赋值给所选行业；同比变化是百分点。", mode: "ask"})}>问当前行业</button>
        : !embedded && (deskHref("industry-prosperity")
          ? <a href={deskHref("industry-prosperity") + "&copilot=1"}>在 Desk 中研究</a>
          : <span>独立模式 · 未配置 Desk 入口</span>)}
    </header>
    <div className="boundary">基本面证据层 · 与行业资金、量价轮动分工；不使用热度代替景气，不自动映射成分或推送交易。</div>
    {error && <div role="alert" className="error">{error}。旧数据与 Agent 旧证据已撤下。<button onClick={reload}>重试</button></div>}
    {status === "loading" && <div role="status" className="loading">正在从国家统计局最近发布列表读取行业财务原表，不加载模拟数据。</div>}
    {data && <>
      {data.sourceUrl !== latest?.sourceUrl && <div className="history-notice" role="status">正在查看历史报告：{data.period}（不是最新报告）。<button onClick={() => setPublicationUrl("")}>返回最新报告</button></div>}
      <section className="release"><div><small>统计期 · 累计值</small><strong>{data.period}</strong><span>发布 {data.publishedAt} · {data.cached ? "15分钟内采集缓存" : "本次采集"}</span></div>
        <div><small>行业覆盖</small><strong>{data.coverage.industries} / {data.coverage.expectedIndustries}</strong><span>{data.coverage.comparable} 个具有完整增长坐标</span></div>
        <div><small>全体规上工业营收同比</small><strong>{fmt(data.total.revenueYoy, "%")}</strong><span>不是当前筛选行业均值</span></div>
        <div><small>全体规上工业利润同比</small><strong>{fmt(data.total.profitYoy, "%")}</strong><span>沿用官方可比口径</span></div>
        <div><small>资料日期</small><a href={data.sourceUrl} target="_blank" rel="noreferrer">统计局原文 ↗</a><span>{data.freshness === "stale" ? "发布已超过45天，需核验更新" : "月度滞后指标，非实时景气"}</span></div>
      </section>
      <DiagnosisPanel diagnosis={diagnosis} rows={rows} select={setSelectedName} loading={production.status === "loading" || prices.status === "loading"} load={() => {production.load(); prices.load();}}/>
      <TrackingOverview key={tracker.scope} tracker={tracker} industries={data.rows.map(row => row.name)} open={(industry, id) => {
        setQuery(""); setState("all"); setSelectedName(industry); tracker.select(id, industry);
        requestAnimationFrame(() => document.querySelector('[aria-label="行业研究跟踪"]')?.scrollIntoView({block: "start"}));
      }}/>
      <div className="research-grid"><section className="plot-panel"><div className="section-title"><h2>增长结构</h2><span>等大圆点 · 非市值权重</span></div>
        <Scatter rows={rows} scopeRows={scopeRows} selected={selected?.name} select={setSelectedName} growthFilter={state} filter={setState}
          query={query} period={data.period} clearFilters={() => {setQuery(""); setState("all");}}/><p>{rows.length} 个筛选结果；同比缺失或不可比的行业不进入象限，但保留在下表。</p></section>
        <section className="detail-panel" aria-label="当前行业证据"><small>SELECTED INDUSTRY</small><h2>{selected?.name ?? "无匹配行业"}</h2>
          {selected && <><span className={"state " + selected.quadrant}>{STATES[selected.quadrant]}</span><div className="facts">
            <div><span>营业收入 / 亿元</span><b>{fmt(selected.revenue)}</b></div><div><span>利润总额 / 亿元</span><b>{fmt(selected.profit)}</b></div>
            <div><span>利润率 / 计算值</span><b>{fmt(selected.profitMargin, "%", 2)}</b></div><div><span>成本率 / 计算值</span><b>{fmt(selected.costRatio, "%", 2)}</b></div>
          </div><h3>下一步应核验什么</h3><ol>{researchQuestions(selected.name).map(question => <li key={question}>{question}</li>)}</ol>
          <p className="caution">这是累计增长分类，不是买入信号；未取得行业库存、订单和估值证据。</p></>}
        </section></div>
      <HistoryPanel data={data} publications={publications} history={history} status={historyStatus} error={historyError} selected={selected?.name} load={loadHistory} select={setPublicationUrl}/>
      {migration && <MigrationPanel evidence={migration} select={name => {setState("all"); setSelectedName(name); document.querySelector('[aria-label="当前行业证据"]')?.scrollIntoView({block: "start"});}}/>}
      <CapacityPanel evidence={capacityEvidence} load={capacity.load}/>
      <ProductionPanel evidence={productionEvidence} load={production.load}/>
      <PricePanel evidence={priceEvidence} load={prices.load}/>
      <OperationsPanel data={data} industry={selected?.name}/>
      <CompanyPanel company={company} href={deskHref("earnings-workbench")} chainHref={deskHref("instock-industry-chain")}/>
      {selected && <TrackingPanel key={JSON.stringify([tracker.scope, selected.name, data.sourceUrl, data.fetchedAt])} tracker={tracker} report={data} industry={selected.name}/>}
      <section className="comparison" aria-label="行业对比"><div className="section-title"><h2>研究对照组</h2><span>最多 4 个 · 从下表勾选 · 非同类估值排名</span></div>
        <div className="comparison-grid">{comparison.map(row => <article key={row.name}><button className="remove" aria-label={`移除对照 ${row.name}`} onClick={() => toggle(row.name)}>×</button><h3>{row.name}</h3>
          <span className={"state " + row.quadrant}>{STATES[row.quadrant]}</span><dl>{(["revenueYoy", "profitYoy", "profitMargin", "costRatio"] as const).map(key => <div key={key}><dt>{METRICS[key]}</dt><dd>{fmt(row[key], "%", 2)}</dd></div>)}</dl></article>)}</div>
        {!comparison.length && <p>从下表选择行业加入对照；没有默认投资建议。</p>}</section>
      <section className="matrix"><div className="filters"><h2>行业比较矩阵</h2><input aria-label="搜索行业" value={query} placeholder="搜索统计局行业名称" onChange={e => setQuery(e.target.value)}/>
        <select aria-label="增长结构筛选" value={state} onChange={e => setState(e.target.value)}><option value="all">全部增长结构</option>{Object.entries(STATES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <select aria-label="排序指标" value={sort} onChange={e => setSort(e.target.value as Metric)}>{Object.entries(METRICS).map(([value, label]) => <option key={value} value={value}>{label} ↓</option>)}</select></div>
        <div className="table-scroll"><table><thead><tr><th>对照</th><th>统计局行业</th><th>增长结构</th><th>营收 / 亿元</th><th>营收同比 %</th><th>利润 / 亿元</th><th>利润同比 %</th><th>利润率 %</th><th>成本率 %</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.name} className={row.name === selected?.name ? "selected" : ""}>
            <td><input type="checkbox" aria-label={`对照 ${row.name}`} checked={compare.includes(row.name)} disabled={compare.length >= 4 && !compare.includes(row.name)} onChange={() => toggle(row.name)}/></td>
            <th><button onClick={() => setSelectedName(row.name)}>{row.name}</button></th><td><span className={"state " + row.quadrant}>{STATES[row.quadrant]}</span></td>
            {(["revenue", "revenueYoy", "profit", "profitYoy", "profitMargin", "costRatio"] as const).map(key => <td key={key} title={row.raw[key] ? `官方原值：${row.raw[key]}` : "根据本期官方金额计算"}>{fmt(row[key], "", 2)}</td>)}</tr>)}</tbody></table>
          {!rows.length && <p className="empty">没有符合条件的行业，请调整搜索或增长结构。</p>}</div></section>
      <section className="method"><h2>证据边界与计算口径</h2><ul>{data.limitations.map(line => <li key={line}>{line}</li>)}</ul>
        <p>采集时间 {new Date(data.fetchedAt).toLocaleString("zh-CN")} · {data.discovery}。快照导出到本机，不等于服务器已保存历史序列。</p>
        {deskHref("capital-sectors") && <nav><a href={deskHref("capital-sectors")} target="_blank" rel="noreferrer">行业资金 ↗</a><a href={deskHref("instock-rotation")} target="_blank" rel="noreferrer">行业与 ETF 轮动 ↗</a><a href={deskHref("instock-industry-chain")} target="_blank" rel="noreferrer">产业链证据 ↗</a><span>仅打开相关工作区；分类未核验，不自动传递当前行业。</span></nav>}
      </section>
    </>}
  </main>;
}
