import { useCallback, useEffect, useState } from 'react';
import type { PortfolioIdentity } from './api';
import { callPortfolioImport as call } from './api';
import { RiskTable } from './RiskAnalytics';
import { IssuerExposure, type IssuerExposureData } from './IssuerExposure';
import { LiquidityPlan, type LiquidityPlanData } from './LiquidityPlan';
import { PortfolioConclusion, type Conclusion } from './PortfolioConclusion';
import { SnapshotHoldingEditor } from './SnapshotHoldingEditor';
import { SnapshotChanges } from './SnapshotChanges';
import { SnapshotScenarios, type AdditionalScenario } from './SnapshotScenarios';
import { ScenarioContributions, type Contribution } from './ScenarioContributions';
import { OutflowAllocations, type OutflowAllocation } from './OutflowAllocations';
import { SnapshotRiskActions } from './SnapshotRiskActions';
import type { ReviewEvidence } from './RiskReviewComparison';
import type { PortfolioRiskAction } from './types';
import { NavThresholds, type NavThresholdData } from './NavThresholds';
import { ProductRiskOverview } from './ProductRiskOverview';
import type { RiskViewId } from './riskNavigation';

export type Holding = {issuer?:string;proceedsAmount?:number|null;proceedsDate?:string|null;proceedsAccount?:string;proceedsSource?:string;assetType:string; market:string; symbol:string; name:string; account:string; currency:string; bookValue:number|null; fxToBase:number|null; availableCash:number|null; equityBeta:number|null; equityBenchmark:string; ratePnlPerBp:number|null; direction:string|null; notional:number|null; source:string; modifiedDuration?:number|null;contracts?:number|null;contractDv01?:number|null;rateAsOf?:string|null;expiryDate?:string|null;resolvedRatePnlPerBp?:number|null;ratePnlPerBpBase?:number|null;rateInputBasis?:string};
export type Snapshot = {navWarningFloor?:number|null;productId?:string;outflowAllocations?:OutflowAllocation[];additionalScenarios?:AdditionalScenario[];name:string; asOf:string; baseCurrency:string; navFloor:number|null; nearTermOutflow:number; cashNeedDate?:string|null; holdings:Holding[]};
type Cash = {reservedOutflow?:number;account:string; available:number|null; futuresLossDemand:number|null; remaining:number|null};
type ResearchEvidence = {market:string;symbol:string;name:string;status:string;note:string;asOf?:string|null;estimatedDuration?:number|null;rSquared?:number|null;source?:string;method?:string|null};
type Scenario = {contributions?:Contribution[];equityShockPct?:number;rateShockBp?:number;label:string; knownAssetPnl:number; knownFuturesPnl:number; totalPnl:number|null; stressNav:number|null; floorHeadroom:number|null; cashByAccount:Cash[]; cashAfterKnownNeeds:number|null};
export type ImportDiagnosis = {riskActions?:PortfolioRiskAction[];draftPending?:boolean;id?:string; savedAt?:string; snapshot:Snapshot; report:{navThresholds?:NavThresholdData;unallocatedOutflow?:number;researchEvidence?:ResearchEvidence[];method:string; status:string; asOf:string; baseCurrency:string; nav:number|null; knownBookValue:number; navHeadroom:number|null; nearTermOutflow:number; coverage:{total:number;valued:number;sensitivity:number}; alerts:string[]; gaps:string[]; rows:Array<Holding & {baseValue:number|null;gaps:string[];references:Array<{title:string;sourceModId:string;status:string}>}>; equityHedges:Array<{benchmark:string;assets:number;futures:number;net:number}>; concentrations:Array<{name:string;symbol:string;baseValue:number|null;weightPct:number|null}>; scenarios:Scenario[]; limitations:string[]}};
const labels:Record<string,string>={stock:'股票',fund:'基金',bond:'债券',equity_future:'股指期货',bond_future:'国债期货',cash:'现金',liability:'负债',other:'其他'};
const number=(v:number|null|undefined)=>v==null?'未评估':v.toLocaleString('zh-CN',{maximumFractionDigits:2});
const columns='资产类型,市场,代码,名称,账户,币种,账面金额,折算汇率,可用现金,权益Beta,对冲基准,利率每基点损益,方向,名义金额,发行人,依据,修正久期,持仓手数,每手DV01,利率参数日期,合约到期日,预计到账金额,预计到账日,收款账户,到账依据';
export const IMPORT_TEMPLATE = columns+'\n股票,CN,600519,示例股票（请替换）,证券账户,CNY,,,,,,,,,,\n基金,CN,000001,示例基金（请替换）,证券账户,CNY,,,,,,,,,,\n债券,CN,示例债券代码,示例债券（请替换）,证券账户,CNY,,,,,,,,,,\n股指期货,CN,示例股指合约,示例期货（请替换）,期货账户,CNY,,,,,,,空,,,\n国债期货,CN,示例国债合约,示例期货（请替换）,期货账户,CNY,,,,,,,空,,,\n现金,,CNY-CASH,可用及受限现金,期货账户,CNY,,,,,,,,,,\n';

function researchLink(modId:string, workspaceId:string) {
  const url=new URL(window.self!==window.top&&document.referrer?document.referrer:(import.meta.env.VITE_PARENT_ORIGIN||'http://127.0.0.1:5888'));
  url.pathname='/';url.search='';url.searchParams.set('mod',modId);url.searchParams.set('workspace',workspaceId);return url.href;
}

type DiagnosisProps={identity:PortfolioIdentity;onContext(value:(ImportDiagnosis & {reviewComparisons?:Record<string,ReviewEvidence>})|undefined):void;view?:RiskViewId};
export function PortfolioDiagnosis({identity,onContext,view='overview'}:DiagnosisProps) {
  return <ScopedPortfolioDiagnosis key={JSON.stringify([identity.userId,identity.workspaceId])} identity={identity} onContext={onContext} view={view}/>;
}

function ScopedPortfolioDiagnosis({identity,onContext,view='overview'}:DiagnosisProps) {
  const selectionKey=`desk:risk:snapshot:${JSON.stringify([identity.userId,identity.workspaceId])}`;
  const [records,setRecords]=useState<ImportDiagnosis[]>([]);
  const [selected,setSelectedState]=useState<ImportDiagnosis>();
  const [selectionNotice,setSelectionNotice]=useState('');
  const setSelected=(value:ImportDiagnosis|undefined)=>{
    setSelectedState(value);
    setSelectionNotice('');
    try {
      if(value?.id)localStorage.setItem(selectionKey,value.id);
      else localStorage.removeItem(selectionKey);
    } catch {setSelectionNotice('浏览器未允许保存选择；本次仍可正常查看，重新打开后需重新选择。')}
  };
  const [preview,setPreview]=useState<ImportDiagnosis>();
  const [text,setText]=useState('');
  const [name,setName]=useState('我的组合');
  const [productId,setProductId]=useState('');
  const [asOf,setAsOf]=useState(new Date().toLocaleDateString('en-CA'));
  const [currency,setCurrency]=useState('CNY');
  const [floor,setFloor]=useState('');
  const [warningFloor,setWarningFloor]=useState('');
  const [outflow,setOutflow]=useState('0');
  const [cashNeedDate,setCashNeedDate]=useState('');
  const [additionalScenarios,setAdditionalScenarios]=useState<AdditionalScenario[]>([]);
  const [outflowAllocations,setOutflowAllocations]=useState<OutflowAllocation[]>([]);
  const [busy,setBusy]=useState(true);
  const [loaded,setLoaded]=useState(false);
  const [error,setError]=useState('');
  const [editing,setEditing]=useState(false);
  const [draftHoldings,setDraftHoldings]=useState<Holding[]|null>(null);
  const editSnapshot=()=>{
    if(!selected)return;
    const s=selected.snapshot;
    setProductId(s.productId||'');
    setAdditionalScenarios((s.additionalScenarios||[]).map(item=>({...item})));
    setOutflowAllocations((s.outflowAllocations||[]).map(item=>({...item})));
    setName(s.name);setAsOf(s.asOf);setCurrency(s.baseCurrency);
    setFloor(s.navFloor==null?'':String(s.navFloor));setWarningFloor(s.navWarningFloor==null?'':String(s.navWarningFloor));setOutflow(String(s.nearTermOutflow));setCashNeedDate(s.cashNeedDate||'');
    setDraftHoldings(s.holdings.map(p=>({...p})));setPreview(undefined);setError('');setEditing(true);
  };
  const current=preview||selected;
  const [actionScope,setActionScope]=useState<{snapshotId?:string;items?:PortfolioRiskAction[]}>({});
  const onActions=useCallback((items:PortfolioRiskAction[]|undefined)=>setActionScope({snapshotId:current?.id,items}),[current?.id]);
  const [reviewScope,setReviewScope]=useState<{snapshotId?:string;items:Record<string,ReviewEvidence>}>({items:{}});
  const onEvidence=useCallback((key:string,value:ReviewEvidence|undefined)=>setReviewScope(previous=>{
    const items=previous.snapshotId===current?.id?{...previous.items}:{};
    if(value)items[key]=value;else delete items[key];
    return {snapshotId:current?.id,items};
  }),[current?.id]);
  const openSource=async(id:string)=>{setBusy(true);setError('');try{const item=await call<ImportDiagnosis>(identity,`import-snapshots/${encodeURIComponent(id)}`);setRecords(items=>[item,...items.filter(r=>r.id!==id)]);setSelected(item);setPreview(undefined)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
  useEffect(()=>{
    let active=true;
    void call<ImportDiagnosis[]>(identity,'import-snapshots').then(async items=>{
      if(!active)return;
      setRecords(items);
      try {
        const id=localStorage.getItem(selectionKey);
        if(id){
          let saved=items.find(item=>item.id===id);
          if(!saved){
            try {saved=await call<ImportDiagnosis>(identity,`import-snapshots/${encodeURIComponent(id)}`)}
            catch {if(active)setSelectionNotice('上次版本暂无法读取，未替换为其他版本。请重试或重新选择。')}
            if(!active)return;
            if(saved)setRecords([saved,...items]);
          }
          setSelectedState(saved);
        }
      } catch {setSelectionNotice('浏览器未允许读取上次选择，请手动选择已保存快照。')}
    }).catch(e=>{if(active)setError(String(e.message))}).finally(()=>{if(active){setBusy(false);setLoaded(true)}});
    return()=>{active=false};
  },[identity.userId,identity.workspaceId,selectionKey]);
  useEffect(()=>{if(!loaded)return;onContext(current?{...current,riskActions:current.id===actionScope.snapshotId?actionScope.items:undefined,reviewComparisons:current.id===reviewScope.snapshotId&&(view==='alerts'||view==='actions')?reviewScope.items:undefined,draftPending:editing&&!preview}:undefined);return()=>onContext(undefined)},[current,onContext,editing,preview,loaded,actionScope,reviewScope,view]);
  const invalidate=()=>{setPreview(undefined);setError('')};
  const inspect=async()=>{setBusy(true);setError('');try{const data=await call<ImportDiagnosis>(identity,'import-previews',{productId,name,asOf,baseCurrency:currency,navWarningFloor:warningFloor===''?null:Number(warningFloor),navFloor:floor===''?null:Number(floor),nearTermOutflow:Number(outflow),cashNeedDate:cashNeedDate||null,additionalScenarios,outflowAllocations,...(draftHoldings?{holdings:draftHoldings}:{text})});setPreview(data)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
  const save=async()=>{if(!preview)return;setBusy(true);setError('');try{const saved=await call<ImportDiagnosis>(identity,'import-snapshots',preview.snapshot);setRecords(items=>[saved,...items.filter(r=>r.id!==saved.id)].slice(0,50));setSelected(saved);setPreview(undefined);setEditing(false)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
  const reassess=async()=>{if(!selected?.id||preview)return;setBusy(true);setError('');try{const saved=await call<ImportDiagnosis>(identity,'import-snapshots',selected.snapshot);setRecords(items=>[saved,...items.filter(r=>r.id!==saved.id)].slice(0,50));setSelected(saved)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
  const readResearch=async()=>{if(!selected?.id||preview)return;setBusy(true);setError('');try{const saved=await call<ImportDiagnosis>(identity,`import-snapshots/${selected.id}/research-evaluations`,{});setRecords(items=>[saved,...items.filter(r=>r.id!==saved.id)].slice(0,50));setSelected(saved)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
  const download=()=>{const url=URL.createObjectURL(new Blob(['\ufeff'+IMPORT_TEMPLATE],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='组合持仓导入模板.csv';a.click();URL.revokeObjectURL(url)};
  return <section className="folio-panel portfolio-diagnosis">
    {view==='overview'&&<ProductRiskOverview identity={identity} revision={selected?.savedAt} selectedId={selected?.id} disabled={busy||editing} onSelect={item=>{setRecords(items=>[item,...items.filter(r=>r.id!==item.id)]);setSelected(item);setPreview(undefined)}}/>}
    <div className="risk-section-heading"><strong>组合快照诊断</strong><span>导入持仓，不生成成交，不与原账本叠加</span></div>
    <div className="diagnosis-toolbar"><label>评估对象<select aria-label="组合快照" value={selected?.id||''} disabled={busy||editing} onChange={e=>{setSelected(records.find(r=>r.id===e.target.value));setPreview(undefined);setEditing(false)}}><option value="">原账本核验 / 选择已保存快照</option>{records.map(r=><option key={r.id} value={r.id}>{r.snapshot.name} · {r.snapshot.asOf} · {r.id?.slice(0,8)}</option>)}</select></label><button className="secondary-button" disabled={busy} onClick={()=>{if(!editing)setProductId('');setEditing(!editing);setPreview(undefined);setDraftHoldings(null)}}>{editing?(draftHoldings?'取消编辑':'收起导入'):'导入组合'}</button>{selected&&!editing&&<button className="secondary-button" disabled={busy} onClick={editSnapshot}>编辑持仓并另存</button>}<button className="secondary-button" onClick={download}>下载 CSV 模板</button></div>
    {selectionNotice&&<p role="note" className="method-note">{selectionNotice}</p>}
    {error&&<p role="alert" className="inline-error" style={{whiteSpace:'pre-wrap'}}>{error}</p>}
    {editing&&<fieldset disabled={busy} className="diagnosis-import"><div className="diagnosis-fields"><label>产品编号（可选）<input value={productId} maxLength={80} placeholder="同一产品沿用固定编号" onChange={e=>{setProductId(e.target.value);invalidate()}}/></label><label>组合名称<input value={name} onChange={e=>{setName(e.target.value);invalidate()}}/></label><label>持仓截止日<input type="date" value={asOf} onChange={e=>{setAsOf(e.target.value);invalidate()}}/></label><label>基准币种<select value={currency} onChange={e=>{setCurrency(e.target.value);invalidate()}}>{['CNY','USD','HKD'].map(c=><option key={c}>{c}</option>)}</select></label><label>净值预警线（基准币）<input type="number" min="0" value={warningFloor} placeholder="可不填；金额不低于底线" onChange={e=>{setWarningFloor(e.target.value);invalidate()}}/></label><label>净值底线（基准币）<input type="number" min="0" value={floor} placeholder="可不填；不自动定义安全" onChange={e=>{setFloor(e.target.value);invalidate()}}/></label><label>近期需留资金（基准币）<input type="number" min="0" value={outflow} onChange={e=>{setOutflow(e.target.value);invalidate()}}/></label></div>
      <p className="method-note">一份快照只放一个产品的完整持仓；多个产品请分别导入，不能混在同一文件后只填写一个编号。同一产品每次沿用编号；更换编号视为另一个产品，不迁移或删除原产品记录。账户归属随本快照保存；编号不自动核验法律主体或真实账户。留空则为未归属快照。</p>
      <label>资金观察日（可选）<input type="date" min={asOf} value={cashNeedDate} onChange={e=>{setCashNeedDate(e.target.value);invalidate()}}/></label>
      <SnapshotScenarios items={additionalScenarios} onChange={items=>{setAdditionalScenarios(items);invalidate()}}/>
      <OutflowAllocations items={outflowAllocations} total={Number(outflow)} currency={currency} onChange={items=>{setOutflowAllocations(items);invalidate()}}/>
      {draftHoldings?<SnapshotHoldingEditor holdings={draftHoldings} onChange={rows=>{setDraftHoldings(rows);invalidate()}}/>:<>
      <label>CSV / TSV 文件<input type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>1_000_000){setError('文件请控制在 1 MB 内');return}setText(await file.text());invalidate()}}/></label>
      <label>持仓表格<textarea aria-label="持仓表格" rows={6} value={text} placeholder="粘贴 Excel 表格（含表头），或上传 UTF-8 CSV / TSV" onChange={e=>{setText(e.target.value);invalidate()}}/></label></>}
      {draftHoldings&&<p className="method-note">正在编辑「{selected?.snapshot.name}」的副本。未预览的修改不会进入下方报告或 Agent 上下文；预览不保存，确认保存才留档，旧版保留。</p>}
      <p className="method-note">“发行人”填股票或债券对应法律实体的完整名称，用于跨账户归并。不要填行业、集团简称、担保人或基金管理人；未知请留空。</p>
      <details className="diagnosis-help"><summary>基金赎回、卖券等预计到账怎么填</summary><p>在股票、基金或债券行填写“预计到账金额、预计到账日、收款账户、到账依据”，并设置资金观察日。金额用该行原币净额（扣除预计费用）；日期用资金预计实际可用日，不是申购开放日或赎回申请日。依据应说明赎回/交易确认、到账规则或具体假设。收款账户须有同币种现金行，可明确填 0。</p><p>只填尚未到账的计划款，已到账的款应核对并体现在现金行，避免重复。不会把持仓市值自动变成到账金额，不会代你卖出、赎回、转账或换汇。预计款与当前现金分开，计划不到账的风险仍由你核验。</p></details>
      <p className="method-note">不想手算利率损益：普通固定利率债可填“修正久期”；国债期货可填“持仓手数＋每手DV01”。换算须同时填写“利率参数日期”和具体“依据”。期货另填“合约到期日”，检查展期风险。</p>
      <details className="diagnosis-help"><summary>字段与计算口径：先确认账面金额和期货方向</summary><p>必填资产类型、市场（股票关联研究时）、代码、名称、账户、币种。账面金额是本行对净资产的贡献：现货填估值金额，债券含应计利息，负债填负数；期货不能填合约名义金额。已逐日结算、损益已在现金中的期货，可明确填 0，保证金不得重复计入。</p><p>权益 Beta 必须带对冲基准；国债及债基的“利率每基点损益”是整笔持仓在利率上行 1bp 时的本币损益（多头普通债券通常为负，空头国债期货通常为正）。来源和方法写在“依据”。基金既需权益敏感度也需利率敏感度，确实不适用才填 0。</p><p>外币行填同一快照汇率（1 单位原币等于多少基准币）。每个账户用现金行说明现金总额和可用金额。没有的数据留空，不以 0 替代。尚不自动读取 Excel 工作簿，请复制表格或另存 UTF-8 CSV。</p></details>
      {draftHoldings&&selected&&preview&&<SnapshotChanges before={selected.snapshot} after={preview.snapshot}/>}
      <div className="diagnosis-toolbar"><button className="primary-button" disabled={busy||(!draftHoldings&&!text.trim())} onClick={()=>void inspect()}>{busy?'处理中…':'预览并检查'}</button>{preview&&<button className="primary-button" disabled={busy} onClick={()=>void save()}>确认保存快照</button>}<span>预览不写账本；确认保存保留完整输入与诊断依据。</span></div>
      <details className="diagnosis-help"><summary>久期与每手 DV01 怎么填</summary><p>修正久期单位为年；债券账面金额须为含息市值。换算为 −市值 × 修正久期 ÷ 10000，只适用于普通固定利率债券的一阶平行利率情景，不适用于可转债、含权债等。不要填麦考利久期或基金净值回归久期。</p><p>每手 DV01 填正数，单位为本币金额 / 手 / bp，须对应导入的国债期货合约，可来自券商或既有定价研究；不是每百元面值 DV01、保证金或 CTD 债券 DV01。系统按手数及多空方向换算。参数日期必须与持仓日一致。</p><p>若已填整笔“利率每基点损益”，系统保留该值，不再用辅助字段覆盖。合约到期日填最后交易日，到期日及之后的合约不再计作有效对冲；系统不会据此自动结算或交易。</p></details>
    </fieldset>}
    {current&&(view==='alerts'||view==='actions')&&<SnapshotRiskActions data={current} identity={identity} register={view==='alerts'} disabled={busy||editing} onActions={onActions} onOpenSource={id=>void openSource(id)} onEvidence={onEvidence}/>}
    {!current&&<p className="method-note">导入股票、基金、债券、现金及对冲期货，先看完整性、对冲和安全垫。下方仍是原股票账本核验；导入快照与它独立选择，不合并资产。</p>}
    {current&&<><div className="diagnosis-toolbar"><button className="secondary-button" disabled={busy||editing||!current.id} onClick={()=>void reassess()}>按最新口径重评估</button><button className="secondary-button" disabled={busy||editing||!current.id||!current.snapshot.holdings.some(p=>p.assetType==='fund')} onClick={()=>void readResearch()}>{busy?'读取中…':'读取基金证据并留档'}</button><span>重评估沿用原持仓、不更新行情，保留旧版；基金证据需重新读取。不触发 AI 或抓取。</span></div><DiagnosisReport data={current} workspaceId={identity.workspaceId} view={view}/></>}
  </section>;
}

function DiagnosisReport({data,workspaceId,view}:{data:ImportDiagnosis;workspaceId:string;view:RiskViewId}) {
  const r=data.report;
  const show=(...views:RiskViewId[])=>view==='overview'||views.includes(view);
  const conclusion=(r as ImportDiagnosis['report'] & {conclusion?:Conclusion}).conclusion;
  const issuerExposure=(r as ImportDiagnosis['report'] & {issuerExposure?:IssuerExposureData}).issuerExposure;
  const liquidityPlan=(r as ImportDiagnosis['report'] & {liquidityPlan?:LiquidityPlanData}).liquidityPlan;
  const rate=(r as ImportDiagnosis['report'] & {rateHedge?:{knownAssets:number;knownFutures:number;net:number|null}}).rateHedge;
  const rateBuckets=(r as ImportDiagnosis['report'] & {rateBuckets?:Array<{currency:string;assets:number;futures:number;net:number|null}>}).rateBuckets;
  const old=(Date.now()-Date.parse(`${data.snapshot.asOf}T00:00:00`))>4*86400000;
  return <div className="diagnosis-report"><p role="status">{data.id?'已保存 · 只读快照':'导入预览 · 尚未保存'} · {data.snapshot.name} · {data.snapshot.productId?`产品 ${data.snapshot.productId}`:'未归属产品'} · {data.snapshot.asOf} · {r.baseCurrency}{old?' · 快照过期，仅作历史参考':''}</p>
    {view==='drawdown'&&<p role="note" className="method-note">当前混合组合尚无净值时间序列，不能计算实际回撤或 VaR；不使用原股票账本的历史模拟替代。</p>}
    {view==='limits'&&<p role="note" className="method-note">这里只核验当前快照的净值预警线、底线和资金预留；产品级合同限额尚未接入。修改请编辑持仓并另存。</p>}
    <section className="workbench-metrics"><article><span>诊断状态</span><strong>{old?'历史参考':r.status}</strong><small>完成测算不等于组合安全</small></article><article><span>账面净资产</span><strong>{number(r.nav)}</strong><small>缺估值时已知部分 {number(r.knownBookValue)}</small></article><article><span>距设定净值底线</span><strong>{number(r.navHeadroom)}</strong><small>不是估值折价安全边际</small></article><article><span>输入覆盖</span><strong>{r.coverage.valued} / {r.coverage.total}</strong><small>敏感度齐备 {r.coverage.sensitivity} 行；非金额覆盖率</small></article></section>
    {show()&&<>{conclusion?<PortfolioConclusion data={conclusion} currency={r.baseCurrency} old={old}/>:<p className="method-note">此版本尚无组合结论摘要，可按最新口径重评估；旧报告保持不变。</p>}
    </>}
    {show('limits','alerts')&&<NavThresholds data={r.navThresholds} currency={r.baseCurrency}/>}
    {show('alerts')&&<><details open={view==='alerts'?true:undefined} id="diagnosis-warnings" tabIndex={-1} className="diagnosis-attention"><summary>全部风险提示 {r.alerts.length} 项 · 待补证据 {r.gaps.length} 项</summary>{r.alerts.map((a,i)=><p key={i} className="negative">{a}</p>)}<ul>{r.gaps.map((g,i)=><li key={i}>{g}</li>)}</ul></details>
    </>}
    {show('alerts')&&<>{r.researchEvidence&&<><h3>基金上游证据 · 不替代组合风险参数</h3><RiskTable label="基金上游风险证据" heads={['基金 / 代码','证据日 / 状态','估算久期 / 拟合度','组合含义与依据']}>
      {r.researchEvidence.map(e=><tr key={`${e.market}:${e.symbol}`}><td>{e.name}<small>{e.market}:{e.symbol}</small></td><td>{e.asOf||'日期未提供'}<small>{({reference_only:'仅作线索',stale:'历史参考',low_fit:'低拟合',after_snapshot:'晚于快照',unavailable:'暂无证据',not_applicable:'模型不适用',unsupported:'未支持该市场',ambiguous:'代码待确认',not_loaded:'未读取'} as Record<string,string>)[e.status]||e.status}</small></td><td>{e.estimatedDuration==null?'未评估':`${number(e.estimatedDuration)} 年`}<small>R² {number(e.rSquared)}</small></td><td>{e.note}<small>{e.source} {e.method}</small></td></tr>)}</RiskTable><p className="method-note">按基金去重读取，跨账户共享同一证据。证据齐备不等于敏感度齐备；信用、赎回限制及基金穿透尚未接入。<a href={researchLink('fund-discover',workspaceId)} target="_blank" rel="noreferrer">打开基金研究核验</a></p></>}
    </>}
    {show('concentration')&&issuerExposure&&<IssuerExposure data={issuerExposure} currency={r.baseCurrency}/>}
    {show('exposure')&&<><h3>对冲前后 · 按指数基准分组</h3><RiskTable label="组合对冲暴露" heads={['基准','资产权益暴露','期货权益暴露','剩余暴露']}>
      {r.equityHedges.map(h=><tr key={h.benchmark}><td>{h.benchmark}</td><td>{number(h.assets)}</td><td>{number(h.futures)}</td><td>{number(h.net)}</td></tr>)}</RiskTable><p className="method-note">仅汇总已提供的敏感度，不把不同指数直接认定为有效对冲；不含基差与相关性变化。</p>
    {rate&&<><h3>利率对冲 · 上行 1bp 的组合损益</h3><RiskTable label="组合利率对冲" heads={['已知资产损益 / bp','已知期货损益 / bp','剩余损益 / bp']}><tr><td>{number(rate.knownAssets)}</td><td>{number(rate.knownFutures)}</td><td>{number(rate.net)}</td></tr></RiskTable><p className="method-note">假设相关利率平行变化；不同期限、信用利差与国债期货基差不因此被对冲。</p></>}
    {rateBuckets&&rateBuckets.length>0&&<><RiskTable label="分币种利率敞口" heads={['利率敞口所属币种','已知资产损益 / bp','已知期货损益 / bp','剩余损益 / bp']}>{rateBuckets.map(b=><tr key={b.currency}><td>{b.currency}</td><td>{number(b.assets)}</td><td>{number(b.futures)}</td><td>{number(b.net)}</td></tr>)}</RiskTable><p className="method-note">以上金额均已折算为 {r.baseCurrency}。按持仓币种分组只是第一层核验；不同币种、期限和收益率曲线不能仅凭净额接近零就认定有效对冲。</p></>}
    {r.rows.some(p=>p.rateInputBasis)&&<details className="diagnosis-help"><summary>利率参数换算与合约期限</summary><RiskTable label="利率参数换算依据" heads={['持仓 / 账户','输入参数','采用损益 / bp（基准币）','口径、日期与来源']}>{r.rows.filter(p=>p.rateInputBasis).map((p,i)=><tr key={i}><td>{p.name}<small>{p.account} · {p.currency}</small></td><td>{p.ratePnlPerBp!=null?`整笔损益 ${number(p.ratePnlPerBp)}`:p.modifiedDuration!=null?`修正久期 ${number(p.modifiedDuration)} 年`:p.assetType==='bond_future'&&(p.contracts!=null||p.contractDv01!=null)?`${number(p.contracts)} 手 × 每手 DV01 ${number(p.contractDv01)}`:'未提供利率参数'}</td><td>{number(p.ratePnlPerBpBase)}</td><td>{p.rateInputBasis}<small>参数日 {p.rateAsOf||'未提供'}{p.expiryDate?` · 合约到期 ${p.expiryDate}`:''}</small><small>{p.source}</small></td></tr>)}</RiskTable></details>}
    </>}
    {show('stress','limits')&&<><h3 id="diagnosis-scenarios" tabIndex={-1}>组合压力与净值安全垫</h3><p className="method-note">保留三组基础情景，并列示本快照的自定义情景。每行情景注明实际冲击，是给定敏感度的一阶测算，不是预测，也不代表全部风险。</p><RiskTable label="组合诊断情景" heads={['情景','已知资产损益','已知期货损益','组合损益','情景净资产','距底线余量']}>
      {r.scenarios.map(s=><tr key={s.label}><td>{s.label}<small>权益 {s.equityShockPct??"未提供"}% · 利率 {s.rateShockBp??"未提供"}bp</small></td><td>{number(s.knownAssetPnl)}</td><td>{number(s.knownFuturesPnl)}</td><td>{number(s.totalPnl)}</td><td>{number(s.stressNav)}</td><td>{number(s.floorHeadroom)}</td></tr>)}</RiskTable>
    <ScenarioContributions report={r}/>
    </>}
    {show('liquidity','limits')&&<><h3 id="diagnosis-cash" tabIndex={-1}>现金安全垫 · 不假设跨账户调拨</h3><p className="method-note">近期需留资金共 {number(r.nearTermOutflow)} {r.baseCurrency}；未分配到账户 {number(r.unallocatedOutflow??r.nearTermOutflow)}。账户余额扣除估算期货亏损及已分配预留；合计只再扣未分配部分，不重复扣减。合计为正也不能掩盖单账户缺口，不是最终可用资金或券商追保金额。</p><RiskTable label="组合现金合计余量" heads={['情景','扣亏损及近期需留资金后合计余量']}>{r.scenarios.map(s=><tr key={s.label}><td>{s.label}</td><td>{number(s.cashAfterKnownNeeds)}</td></tr>)}</RiskTable><RiskTable label="组合账户现金压力" heads={['情景','账户','可用现金','估算期货亏损需求','已分配预留','扣亏损及预留后余额']}>
      {r.scenarios.flatMap(s=>s.cashByAccount.map(c=><tr key={`${s.label}:${c.account}`}><td>{s.label}</td><td>{c.account}</td><td>{number(c.available)}</td><td>{number(c.futuresLossDemand)}</td><td>{number(c.reservedOutflow??0)}</td><td className={c.remaining!=null&&c.remaining<0?'negative':''}>{number(c.remaining)}</td></tr>))}</RiskTable>
    {liquidityPlan&&<LiquidityPlan data={liquidityPlan} currency={r.baseCurrency}/>}
    </>}
    {show('concentration')&&<><details open={view==='concentration'?true:undefined} className="diagnosis-help"><summary>持仓集中度（直接持有，尚未基金穿透）</summary><RiskTable label="导入快照集中度" heads={['资产','代码','折算市值','现货持仓权重']}>
      {r.concentrations.slice(0,10).map((p,i)=><tr key={i}><td>{p.name}</td><td>{p.symbol}</td><td>{number(p.baseValue)}</td><td>{p.weightPct==null?'未评估':`${number(p.weightPct)}%`}</td></tr>)}</RiskTable><p className="method-note">前十项，同一资产跨账户合并；权重分母为现货总市值，不含现金、负债及期货名义金额，不能代表穿透后的行业或发行人集中度。</p></details>
    </>}
    <details id="diagnosis-inputs" tabIndex={-1} className="diagnosis-help"><summary>持仓、输入依据与上游研究</summary><RiskTable label="导入持仓依据" heads={['资产 / 账户','类型','账面金额 / 原币','敏感度依据','上游档案']}>
      {r.rows.map((p,i)=><tr key={i}><td><strong>{p.name}</strong><small>{p.market}:{p.symbol} · {p.account}</small></td><td>{labels[p.assetType]||p.assetType}</td><td>{number(p.bookValue)} {p.currency}</td><td>{p.source}<small>{p.gaps.join('；')||'字段齐备，未独立核验'}</small></td><td>{p.references.length?p.references.map((ref,j)=><div key={j}><a href={researchLink(ref.sourceModId,workspaceId)} target="_blank" rel="noreferrer">{ref.title}</a><small>{ref.status}</small></div>):'尚无可复用档案'}</td></tr>)}</RiskTable></details>
    <details className="diagnosis-help"><summary>模型范围与未覆盖风险</summary><ul>{r.limitations.map((x,i)=><li key={i}>{x}</li>)}</ul><p>方法：{r.method}。当前不在风控重建股票、基金或债券研究；后续接入结构化上游结论后替换人工敏感度。</p></details>
  </div>;
}
