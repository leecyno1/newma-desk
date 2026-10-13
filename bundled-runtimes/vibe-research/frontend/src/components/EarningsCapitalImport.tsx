import {useState} from 'react';
import {api, researchApiUrl, type EarningsPdfImport} from '@/lib/api';
import {missingPdfCapital, missingPdfCapitalNotes} from '@/lib/earningsPdfImport';
import type {EarningsWorkbook} from '@/lib/earningsWorkbench';

const button = 'rounded border border-border px-3 py-2 disabled:opacity-50';

export function EarningsCapitalImport({workbook, disabled, onBusy, onAdopt, onAdoptNotes}: {
  workbook: EarningsWorkbook; disabled: boolean; onBusy: (busy: boolean) => void;
  onAdopt: (document: EarningsPdfImport, ids: string[], workbookId: string) => void;
  onAdoptNotes: (document: EarningsPdfImport, ids: string[], workbookId: string) => void;
}) {
  const [reportId,setReportId] = useState('');
  const [document,setDocument] = useState<EarningsPdfImport|null>(null);
  const [selected,setSelected] = useState<string[]>([]);
  const [confirmed,setConfirmed] = useState(false);
  const [status,setStatus] = useState('');
  const reports = new Map<string,string>();
  for (const source of workbook.sourceMaterials) {
    const id = source.importedReport?.reportId || source.discussion?.reportId || source.capitalNote?.reportId;
    if (id && !reports.has(id)) reports.set(id,source.label);
  }
  if (!reports.size) return null;
  const currentId = reportId || reports.keys().next().value!;
  const read = async () => {
    onBusy(true); setDocument(null); setConfirmed(false); setStatus('正在定位已上传 PDF 的合并资产负债表…');
    try {
      const result = await api.earningsCapitalCandidates(currentId);
      const rows = missingPdfCapital(workbook,result);
      setDocument({...result,capitalCandidates:rows}); setSelected([]);
      setStatus(rows.length ? `发现 ${rows.length} 项未采用资本事实，请逐项核对后选择。` : '没有可新增项目：可能已采用，或版式无法可靠识别。缺失不代表零。');
    } catch(error) { setStatus(error instanceof Error ? error.message : '读取失败，原底稿未改动'); }
    finally { onBusy(false); }
  };
  const readNotes = async () => {
    onBusy(true); setDocument(null); setConfirmed(false); setSelected([]); setStatus('正在定位合并财务报表资本附注…');
    try {
      const result = await api.earningsCapitalNotes(currentId);
      const rows = missingPdfCapitalNotes(workbook,result);
      setDocument({...result,capitalNotes:rows});
      setStatus(rows.length ? `发现 ${rows.length} 段未采用资本附注，请展开核对后选择。` : '没有可新增附注；可能已采用或未识别，请查阅原报。');
    } catch(error) { setStatus(error instanceof Error ? error.message : '读取失败，原底稿未改动'); }
    finally { onBusy(false); }
  };
  return <section aria-label="补充财报资本项目" className="mb-4 border-b border-border pb-3 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-muted-foreground">补充合并报表资本事实，供估值核验引用；不重复上传、不自动回填估值。</p>
      {reports.size>1 && <select aria-label="资本项目财报" className={button} disabled={disabled} value={currentId} onChange={e=>{setReportId(e.target.value);setDocument(null);setConfirmed(false);setStatus('')}}>
        {[...reports].map(([id,label])=><option key={id} value={id}>{label}</option>)}
      </select>}
      <button className={button} disabled={disabled} onClick={()=>void read()}>补充资本项目</button>
      <button className={button} disabled={disabled} onClick={()=>void readNotes()}>定位资本附注</button>
    </div>
    {status && <p role="status" className="mt-2">{status}</p>}
    {document && <div className="mt-3 space-y-3">
      <p>{document.security.name} · {document.security.symbol} · {document.periodEnd} · 合并报表 · 人民币</p>
      {(document.capitalNotesWarnings || document.capitalWarnings || document.warnings).map((text,i)=><p key={i} className="text-muted-foreground">{text}</p>)}
      {!!document.capitalNotes?.length && <section aria-label="资本附注候选" className="space-y-3">
        {document.capitalNotes.map(row=><div key={row.id} className="flex items-start gap-2">
          <input type="checkbox" className="mt-1" aria-label={`采用${row.title}第 ${row.page} 页`} disabled={disabled} checked={selected.includes(row.id)} onChange={e=>{setSelected(e.target.checked?[...selected,row.id]:selected.filter(id=>id!==row.id));setConfirmed(false)}}/>
          <details className="min-w-0 flex-1"><summary className="cursor-pointer">{row.title} · 第 {row.page} 页{row.truncated?' · 内容已截断':''}</summary>
            <a className="text-primary underline" href={`${researchApiUrl(`/myreports/file/${document.reportId}?inline=true`)}#page=${row.page}`} target="_blank" rel="noreferrer">核对 PDF 原页</a>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap py-2 text-sm">{row.text}</pre>
          </details>
        </div>)}
        <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>已核对附注原文及页码，仅保存证据，不自动修改金额</label>
        <button className={button} disabled={disabled||!confirmed||!selected.length} onClick={()=>{
          try {onAdoptNotes(document,selected,workbook.id);setDocument(null);setConfirmed(false);setStatus('资本附注已加入草稿，请保存后供估值与 Agent 引用。')}
          catch(error){setStatus(error instanceof Error?error.message:'采用失败')}
        }}>确认采用资本附注</button>
      </section>}
      {!!document.capitalCandidates?.length && <>
        <div className="overflow-x-auto"><table aria-label="资本项目候选" className="w-full text-left"><thead><tr><th>采用</th><th>原始项目</th><th>百万元</th><th>原值 / 物理页</th><th>原文</th></tr></thead>
          <tbody>{document.capitalCandidates.map(row=><tr key={row.id} className="border-t border-border align-top">
            <td className="py-2"><input type="checkbox" aria-label={`采用${row.label}`} disabled={disabled} checked={selected.includes(row.id)} onChange={e=>{setSelected(e.target.checked?[...selected,row.id]:selected.filter(id=>id!==row.id));setConfirmed(false)}}/></td>
            <td className="p-2">{row.label}</td><td className="p-2 tabular-nums">{row.value.toLocaleString('zh-CN',{maximumFractionDigits:6})}</td>
            <td className="p-2">{row.rawValue} {row.rawUnit}<br/>第 {row.page} 页</td><td className="p-2"><details><summary className="cursor-pointer">核对表头与原文</summary><p>{row.columnHeader}</p><p className="whitespace-pre-wrap">{row.excerpt}</p></details></td>
          </tr>)}</tbody></table></div>
        <label className="flex gap-2"><input type="checkbox" checked={confirmed} disabled={disabled} onChange={e=>setConfirmed(e.target.checked)}/>已核对合并范围、期间、单位与原文，仅保存原始事实</label>
        <button className={button} disabled={disabled||!confirmed||!selected.length} onClick={()=>{
          try {onAdopt(document,selected,workbook.id);setDocument(null);setConfirmed(false);setStatus('资本项目已补充到草稿，请保存；现有指标与研究判断未改动。')}
          catch(error){setStatus(error instanceof Error?error.message:'采用失败')}
        }}>确认补充资本项目</button>
      </>}
      <button className={button} disabled={disabled} onClick={()=>{setDocument(null);setStatus('已关闭资本预览，未改动底稿')}}>关闭资本预览</button>
    </div>}
    {workbook.sourceMaterials.some(source=>source.capitalNote) && <details aria-label="已采用资本附注" className="mt-3">
      <summary className="cursor-pointer">已采用资本附注 · {workbook.sourceMaterials.filter(source=>source.capitalNote).length} 段</summary>
      {workbook.sourceMaterials.filter(source=>source.capitalNote).map(source=><details key={source.id} className="border-t border-border py-2">
        <summary className="cursor-pointer">{source.label}{source.capitalNote!.truncated?' · 内容已截断':''}</summary>
        <a className="text-primary underline" href={source.url} target="_blank" rel="noreferrer">核对 PDF 原页</a>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap py-2 text-sm">{source.capitalNote!.text}</pre>
      </details>)}
    </details>}
  </section>;
}
