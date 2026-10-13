import {useState} from 'react';
import {api, type EarningsPdfImport} from '@/lib/api';
import {missingPdfDiscussion} from '@/lib/earningsPdfImport';
import type {EarningsWorkbook} from '@/lib/earningsWorkbench';
import {EarningsDiscussionCandidates} from './EarningsDiscussionCandidates';

export function EarningsDiscussionImport({workbook, disabled, onBusy, onAdopt}: {
  workbook: EarningsWorkbook; disabled: boolean; onBusy: (busy:boolean)=>void;
  onAdopt: (document:EarningsPdfImport, ids:string[], workbookId:string)=>void;
}) {
  const [reportId,setReportId] = useState('');
  const [document,setDocument] = useState<EarningsPdfImport|null>(null);
  const [selected,setSelected] = useState<string[]>([]);
  const [confirmed,setConfirmed] = useState(false);
  const [status,setStatus] = useState('');
  const [error,setError] = useState('');
  const reports = new Map<string,string>();
  for (const source of workbook.sourceMaterials) {
    const id=source.importedReport?.reportId || source.discussion?.reportId;
    if(id&&!reports.has(id))reports.set(id,source.label);
  }
  if(!reports.size)return null;
  const currentId=reportId || reports.keys().next().value!;
  const read=async()=>{
    onBusy(true);setDocument(null);setError('');setConfirmed(false);setStatus('正在读取已保存的 PDF，不会再次上传或改动指标…');
    try {
      const result=await api.earningsPdfCandidates(currentId);
      const missing=missingPdfDiscussion(workbook,result);
      setDocument({...result,discussion:missing});setSelected(missing.map(row=>row.id));
      setStatus(missing.length?`找到 ${missing.length} 页尚未采用的经营讨论，核对确认前不会进入底稿。`:
        result.discussion?.length?'本次识别到的经营讨论已全部采用，不重复添加。':'本次读取范围未找到经营讨论，不代表公司没有披露。');
    }catch(e){setError(e instanceof Error?e.message:String(e));setStatus('读取未完成，现有底稿保持不变。')}
    finally{onBusy(false)}
  };
  const adopt=()=>{
    if(!document||!confirmed)return;
    try{onAdopt(document,selected,workbook.id);setDocument(null);setConfirmed(false);setError('');setStatus('已补充到当前草稿，请点击顶部“保存”；未改动已有指标、预期和结论。')}
    catch(e){setError(e instanceof Error?e.message:String(e))}
  };
  return <section aria-label="补充已有财报原文" className="mb-4 border-b border-border pb-3 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-muted-foreground">已有 PDF 可继续补充经营讨论，无需重新上传。仅读取前 30 页，已采用内容不覆盖。</p>
      {reports.size>1&&<select aria-label="选择已关联财报" className="max-w-80 rounded border border-border bg-card p-2" disabled={disabled} value={currentId} onChange={e=>{setReportId(e.target.value);setDocument(null);setConfirmed(false);setStatus('');setError('')}}>
        {[...reports].map(([id,label])=><option key={id} value={id}>{label} · {id.slice(0,8)}</option>)}
      </select>}
      <button disabled={disabled} onClick={()=>void read()} className="rounded-lg border border-border px-3 py-2 disabled:opacity-50">补充已上传财报原文</button>
    </div>
    {status&&<p role="status" className="mt-3">{status}</p>}
    {error&&<p role="alert" className="mt-2 text-destructive">{error}</p>}
    {!!document?.discussion?.length&&<div className="mt-3 space-y-3">
      <p>{document.security.name} · {document.security.symbol} · {document.periodEnd} · 人民币年度报告</p>
      {document.warnings.map((warning,index)=><p key={index} className="text-muted-foreground">{warning}</p>)}
      <EarningsDiscussionCandidates document={document} selected={selected} disabled={disabled} onChange={ids=>{setSelected(ids);setConfirmed(false)}}/>
      <label className="flex gap-2"><input type="checkbox" aria-label="已核对补充的经营讨论原文" checked={confirmed} disabled={disabled} onChange={e=>setConfirmed(e.target.checked)}/>我已核对所选原文；仅补充到当前草稿，不修改原有数据。</label>
      <button disabled={disabled||!confirmed||!selected.length} className="rounded-lg bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50" onClick={adopt}>确认补充到草稿</button>
      <button disabled={disabled} className="ml-3 rounded-lg border border-border px-3 py-2" onClick={()=>{setDocument(null);setConfirmed(false);setStatus('已取消补充，底稿保持不变。')}}>取消补充</button>
    </div>}
  </section>;
}
