import { useEffect, useState } from 'react';
import { callPortfolioImport as call, type PortfolioIdentity } from './api';
import type { ImportDiagnosis } from './PortfolioDiagnosis';
import { RiskTable } from './RiskAnalytics';
import { compareSnapshots, SnapshotChanges } from './SnapshotChanges';

type Value = number | null | undefined;
export type ComparisonRow = { label:string; before:Value; after:Value };
const evidenceSummary=(d:ImportDiagnosis)=>({id:d.id,name:d.snapshot.name,productId:d.snapshot.productId,asOf:d.snapshot.asOf,savedAt:d.savedAt,baseCurrency:d.report.baseCurrency,method:d.report.method,coverage:d.report.coverage,alerts:d.report.alerts,gaps:d.report.gaps,limitations:d.report.limitations});
export function reviewEvidence(a:ImportDiagnosis,b:ImportDiagnosis){
  return {source:evidenceSummary(a),review:evidenceSummary(b),metrics:comparisonRows(a,b),inputChanges:compareSnapshots(a.snapshot,b.snapshot),floorExplanation:floorChangeExplanation(a,b),note:'本次已读取的历史版本对照摘要，不是实时行情。仅解释所列指标与原始输入变化；完整持仓及上游证据未包含。不得将差额认定为投资收益、处置效果或风险解除。未评估项不按零处理。'};
}
export type ReviewEvidence=ReturnType<typeof reviewEvidence>;
export type ReviewEvidenceListener=(key:string,value:ReviewEvidence|undefined)=>void;
const rates=(d:ImportDiagnosis)=>(d.report as ImportDiagnosis['report'] & {rateBuckets?:Array<{currency:string;net:number|null}>}).rateBuckets||[];
const format=(n:Value)=>n==null?'未评估':n.toLocaleString('zh-CN',{maximumFractionDigits:2});
export function floorChangeExplanation(a:ImportDiagnosis,b:ImportDiagnosis):string {
  const oldFloor=a.snapshot.navFloor,newFloor=b.snapshot.navFloor;
  if(oldFloor==null||newFloor==null||a.report.nav==null||b.report.nav==null)return '净资产或底线缺失，不能拆解安全垫变化。';
  const navChange=b.report.nav-a.report.nav,floorEffect=oldFloor-newFloor;
  return `安全垫变化 ${format(navChange+floorEffect)} = 净资产变化 ${format(navChange)} + 底线调整影响 ${format(floorEffect)}。${newFloor<oldFloor?'复核版本降低了底线，余量因此增加；这不代表资产风险下降。':'净资产变化可能来自估值、出入金或持仓修订，不等于投资收益。'}`;
}
export function comparisonRows(a:ImportDiagnosis,b:ImportDiagnosis):ComparisonRow[] {
  const rows:ComparisonRow[]=[
    {label:'账面净资产',before:a.report.nav,after:b.report.nav},
    {label:'设定净值底线',before:a.snapshot.navFloor,after:b.snapshot.navFloor},
    {label:'距底线余量',before:a.report.navHeadroom,after:b.report.navHeadroom},
    {label:'近期需留资金',before:a.report.nearTermOutflow,after:b.report.nearTermOutflow},
  ];
  // Match actual shocks, not editable labels; missing inputs never become zero.
  const scenarioKey=(s:ImportDiagnosis['report']['scenarios'][number])=>JSON.stringify([s.equityShockPct,s.rateShockBp]);
  const keys=new Set([...a.report.scenarios,...b.report.scenarios].map(scenarioKey));
  for(const key of keys){
    const left=a.report.scenarios.filter(s=>scenarioKey(s)===key),right=b.report.scenarios.filter(s=>scenarioKey(s)===key);
    const s=left[0]||right[0];
    if(s.equityShockPct==null||s.rateShockBp==null||left.length>1||right.length>1)continue;
    const x=left[0],y=right[0],label=`权益 ${s.equityShockPct}% / 利率 ${s.rateShockBp}bp`;
    rows.push({label:`${label} · 底线余量`,before:x?.floorHeadroom,after:y?.floorHeadroom});
    for(const account of new Set([...(x?.cashByAccount||[]),...(y?.cashByAccount||[])].map(c=>c.account))){
      rows.push({label:`${label} · ${account}现金余量`,before:x?.cashByAccount.find(c=>c.account===account)?.remaining,after:y?.cashByAccount.find(c=>c.account===account)?.remaining});
    }
  }
  for(const benchmark of new Set([...a.report.equityHedges,...b.report.equityHedges].map(h=>h.benchmark))){
    rows.push({label:`${benchmark} · 已知权益净暴露`,before:a.report.equityHedges.find(h=>h.benchmark===benchmark)?.net,after:b.report.equityHedges.find(h=>h.benchmark===benchmark)?.net});
  }
  for(const currency of new Set([...rates(a),...rates(b)].map(h=>h.currency))){
    rows.push({label:`${currency}利率 · 剩余损益 / bp`,before:rates(a).find(h=>h.currency===currency)?.net,after:rates(b).find(h=>h.currency===currency)?.net});
  }
  return rows;
}

export function RiskReviewComparison({sourceId,reviewId,identity,evidenceKey='',onEvidence}:{sourceId:string;reviewId:string;identity:PortfolioIdentity;evidenceKey?:string;onEvidence?:ReviewEvidenceListener}){
  const [pair,setPair]=useState<[ImportDiagnosis,ImportDiagnosis]>();
  useEffect(()=>{onEvidence?.(evidenceKey,pair?reviewEvidence(...pair):undefined);return()=>onEvidence?.(evidenceKey,undefined)},[pair,evidenceKey,onEvidence]);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const load=async()=>{
    setBusy(true);setError('');setPair(undefined);
    try{
      const [a,b]=await Promise.all([sourceId,reviewId].map(id=>call<ImportDiagnosis>(identity,`import-snapshots/${encodeURIComponent(id)}`)));
      if(!a.snapshot.productId||a.snapshot.productId!==b.snapshot.productId)throw new Error('产品归属不同，不能对照。');
      if(a.report.baseCurrency!==b.report.baseCurrency||a.report.method!==b.report.method)throw new Error('基准币种或计算方法不同，请分别查看原报告，不直接比较数值。');
      setPair([a,b]);
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  };
  return <section aria-label="来源与复核指标对照">
    <button className="secondary-button" disabled={busy} onClick={()=>void load()}>{busy?'正在读取对照…':pair?'重新读取指标对照':'对照来源与复核指标'}</button>
    {error&&<p role="alert" className="inline-error">{error}</p>}
    {pair&&<>
      <p className="method-note">来源：{pair[0].snapshot.name} · {pair[0].snapshot.asOf} · {sourceId.slice(0,8)} → 复核：{pair[1].snapshot.name} · {pair[1].snapshot.asOf} · {reviewId.slice(0,8)}。金额单位：{pair[0].report.baseCurrency}。</p>
      <RiskTable label="复核关键指标对照" heads={['指标 / 同冲击情景','来源','复核','变化（复核 − 来源）']}>
        {comparisonRows(...pair).map(row=><tr key={row.label}><td>{row.label}</td><td>{format(row.before)}</td><td>{format(row.after)}</td><td>{row.before==null||row.after==null?'不可比较':format(row.after-row.before)}</td></tr>)}
      </RiskTable>
      <p role="note" className="method-note">{floorChangeExplanation(...pair)}</p>
      <details><summary>核对持仓与风控参数变化</summary><SnapshotChanges before={pair[0].snapshot} after={pair[1].snapshot} review/></details>
      <p className="method-note">只读历史报告，不更新行情。情景按权益与利率冲击配对；缺失或无法唯一匹配的不计算变化。账户不相互抵销。底线、资金预留和持仓变化都可能影响余量；权益只汇总已知敏感度，利率净额接近零不代表有效对冲。数值变化不等于处置效果或风险解除；完整缺口及依据请分别查看原报告。</p>
    </>}
  </section>;
}
