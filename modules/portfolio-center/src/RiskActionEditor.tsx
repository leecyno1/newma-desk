import { useState } from 'react';
import { portfolioClient, type PortfolioIdentity } from './api';
import type { PortfolioRiskAction } from './types';
const date=(value?:string|null)=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未提供';
const errorText=(e:unknown)=>e instanceof Error?e.message:'操作失败，请重试';

export function RiskActionEditor({ action, identity, onRefresh, reviewCandidate }: { action: PortfolioRiskAction; identity: PortfolioIdentity; reviewCandidate?:{id:string;name:string;asOf:string}; onRefresh(): void }) {
  const [reviewId,setReviewId] = useState(action.reviewSnapshotId||null);
  const [owner,setOwner] = useState(action.owner || '');
  const [note,setNote] = useState(action.note || '');
  const [due,setDue] = useState(action.dueAt ? new Date(new Date(action.dueAt).getTime() - new Date(action.dueAt).getTimezoneOffset() * 60000).toISOString().slice(0,16) : '');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const closed = ['resolved','waived'].includes(action.status);
  const overdue = !closed && action.dueAt && Date.parse(action.dueAt) < Date.now();
  const update = async (status: PortfolioRiskAction['status']) => {
    if (status !== 'open' && !owner.trim()) { setError('请填写负责人'); return; }
    if (status === 'acknowledged' && !due) { setError('请填写处理期限'); return; }
    if (['resolved','waived'].includes(status) && !note.trim()) { setError('结案需要复核依据；豁免需要理由'); return; }
    setBusy(true); setError('');
    try { await portfolioClient(identity).updateRiskAction(action.id, { ...(action.sourceSnapshotId?{reviewSnapshotId:reviewId}:{}),status, owner, note, dueAt: due ? new Date(due).toISOString() : null }); onRefresh(); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  };
  return <article className="risk-action-editor"><header><strong>{action.title}</strong><span>{({open:'待处理',acknowledged:'处理中',resolved:'已复核结案',waived:'已豁免'})[action.status]}{overdue ? ' · 已逾期' : ''}</span></header><p>{action.detail}</p>
    {action.sourceSnapshotId&&<div className="method-note">复核快照：{reviewId||'未关联'}{reviewId!== (action.reviewSnapshotId||null)?' · 尚未保存':''}
      {!closed&&<><p>先选择同一产品的新快照，再点击采用；关联不证明风险改善，仍须填写复核说明。可不关联快照而引用其他核验依据。</p>
        {reviewCandidate&&reviewCandidate.id!==action.sourceSnapshotId&&<button className="secondary-button" disabled={busy} onClick={()=>setReviewId(reviewCandidate.id)}>采用当前快照复核</button>}
        {reviewCandidate&&reviewCandidate.id!==action.sourceSnapshotId&&<span> {reviewCandidate.name} · {reviewCandidate.asOf}</span>}
        {reviewId&&<button className="secondary-button" disabled={busy} onClick={()=>setReviewId(null)}>清除待保存关联</button>}
      </>}
    </div>}
    {closed ? <p>负责人：{action.owner || '历史记录未填写'} · 期限：{date(action.dueAt)}<br/>复核 / 豁免依据：{action.note || '历史记录未填写'}<br/>结案：{date(action.resolvedAt)}</p> : <><div className="risk-editor-fields"><label>负责人<input value={owner} onChange={e => setOwner(e.target.value)} maxLength={80}/></label><label>处理期限<input type="datetime-local" value={due} onChange={e => setDue(e.target.value)}/></label><label className="risk-editor-note">处置说明 / 复核依据 / 豁免理由<textarea rows={2} value={note} onChange={e => setNote(e.target.value)} maxLength={1000}/></label></div><div className="inline-controls"><button className="secondary-button" disabled={busy} onClick={() => void update(action.status)}>保存记录</button>{action.status === 'open' && <button className="secondary-button" disabled={busy} onClick={() => void update('acknowledged')}>确认接手</button>}{action.status === 'acknowledged' && <button className="secondary-button" disabled={busy} onClick={() => void update('resolved')}>复核结案</button>}<button className="secondary-button" disabled={busy} onClick={() => void update('waived')}>风险豁免</button></div></>}
    {error && <p role="alert" className="inline-error">{error}</p>}<small>登记 {date(action.createdAt)} · 更新 {date(action.updatedAt)} · 结案后只读，风险再次发生须新建记录。</small>
  </article>;
}
