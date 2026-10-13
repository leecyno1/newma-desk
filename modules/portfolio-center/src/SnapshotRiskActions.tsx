import { useEffect, useState } from 'react';
import { callPortfolioImport as call, type PortfolioIdentity } from './api';
import type { ImportDiagnosis } from './PortfolioDiagnosis';
import type { PortfolioRiskAction } from './types';
import { RiskActionEditor } from './RiskActionEditor';
import { RiskTable } from './RiskAnalytics';
import { RiskReviewComparison, type ReviewEvidenceListener } from './RiskReviewComparison';

export function SnapshotRiskActions({data,identity,register,disabled,onActions,onOpenSource,onEvidence}:{data:ImportDiagnosis;identity:PortfolioIdentity;register:boolean;disabled:boolean;onActions(items:PortfolioRiskAction[]|undefined):void;onOpenSource(id:string):void;onEvidence:ReviewEvidenceListener}){
  const [items,setItems]=useState<PortfolioRiskAction[]>([]);
  const [revision,setRevision]=useState(0);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [filter,setFilter]=useState('all');
  const refresh=()=>setRevision(v=>v+1);
  useEffect(()=>{
    let active=true;setLoading(true);setError('');onActions(undefined);
    if(!data.id){setItems([]);setLoading(false);return}
    void call<PortfolioRiskAction[]>(identity,`import-snapshots/${data.id}/risk-actions`).then(values=>{
      if(active){setItems(values);onActions(values)}
    }).catch(e=>{if(active){setItems([]);setError(e instanceof Error?e.message:String(e))}}).finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[data.id,identity.userId,identity.workspaceId,revision,onActions]);
  const create=async(category:'alerts'|'gaps',index:number)=>{
    if(!data.id)return;setBusy(true);setError('');
    try{await call(identity,`import-snapshots/${data.id}/risk-actions`,{category,index});refresh()}
    catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}
  };
  if(!data.id)return <p>请先保存快照，再登记风险处置。预览不能作为留档依据。</p>;
  const open=(a:PortfolioRiskAction)=>!['resolved','waived'].includes(a.status);
  const visible=items.filter(a=>filter==='all'||(filter==='open'?open(a):!open(a)));
  return <section aria-label="产品风险处置" className="diagnosis-conclusion">
    <h3>产品风险处置</h3>
    <p className="method-note">{data.snapshot.productId?`产品 ${data.snapshot.productId} 的跨版本处置`:'未归属产品，仅列本快照处置'}。登记依据来自原快照，可能为历史或压力假设，不代表风险仍在发生。结案、豁免不清除原报告预警，不自动交易或通知他人。</p>
    {error&&<p role="alert" className="inline-error">{error}</p>}
    {register&&<details open><summary>从当前快照登记风险与数据缺口</summary>
      <RiskTable label="快照风险登记" heads={['来源 / 原始依据','登记']}>
        {(['alerts','gaps'] as const).flatMap(category=>data.report[category].map((detail,index)=>{
          const existing=items.find(a=>a.sourceSnapshotId===data.id&&a.ruleId===`snapshot:${data.id}:${category}:${index}`&&open(a));
          const label=category==='alerts'?'风险提示':'待补证据';
          return <tr key={`${category}:${index}`}><td><small>{label} {index+1}</small>{detail}</td><td>{existing?'处置中':<button className="secondary-button" disabled={disabled||busy||loading} onClick={()=>void create(category,index)} aria-label={`登记${label} ${index+1}`}>登记处置</button>}</td></tr>;
        }))}
      </RiskTable>
      {!data.report.alerts.length&&!data.report.gaps.length&&<p>本快照没有可登记的风险提示或数据缺口；不代表整体安全。</p>}
    </details>}
    <label>处置筛选<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部</option><option value="open">未结事项</option><option value="closed">已结事项</option></select></label>
    {loading?<p>正在读取处置记录…</p>:!error&&!visible.length?<p>当前范围暂无匹配处置记录。</p>:null}
    {visible.map(action=><details key={action.id} className="risk-action-row"><summary>{action.title} · {({open:'待处理',acknowledged:'处理中',resolved:'已复核结案',waived:'已豁免'})[action.status]} · {action.owner||'未分配'}{open(action)&&action.dueAt&&Date.parse(action.dueAt)<Date.now()?' · 已逾期':''}</summary>
      <button className="secondary-button" disabled={disabled||busy||action.sourceSnapshotId===data.id} onClick={()=>action.sourceSnapshotId&&onOpenSource(action.sourceSnapshotId)}>查看来源快照</button><small title={action.sourceSnapshotId||undefined}>来源快照 {action.sourceSnapshotId?.slice(0,8)}</small>
      {action.reviewSnapshotId&&<button className="secondary-button" disabled={disabled||busy||action.reviewSnapshotId===data.id} onClick={()=>onOpenSource(action.reviewSnapshotId!)}>查看复核快照</button>}
      {action.sourceSnapshotId&&action.reviewSnapshotId&&<RiskReviewComparison key={JSON.stringify([data.id,identity.userId,identity.workspaceId,action.sourceSnapshotId,action.reviewSnapshotId])} sourceId={action.sourceSnapshotId} reviewId={action.reviewSnapshotId} identity={identity} evidenceKey={action.id} onEvidence={onEvidence}/>}
      <fieldset disabled={disabled||busy||loading}><RiskActionEditor key={action.updatedAt} action={action} identity={identity} reviewCandidate={{id:data.id!,name:data.snapshot.name,asOf:data.snapshot.asOf}} onRefresh={refresh}/></fieldset>
    </details>)}
  </section>;
}
