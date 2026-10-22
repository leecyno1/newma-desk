import { ReportSourceLink } from '@/components/ReportSourceLink';
import {useState} from 'react';
import {api, researchApiUrl, type EarningsPdfImport, type EarningsRevenueGroup} from '@/lib/api';
import {missingPdfRevenue} from '@/lib/earningsPdfImport';
import type {EarningsWorkbook} from '@/lib/earningsWorkbench';

const button='rounded border border-border px-3 py-2 disabled:opacity-50';
function RevenueTable({group}:{group:Pick<EarningsRevenueGroup,'rows'|'total'|'columnHeader'|'skippedRows'>}) {
  return <>
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>项目</th><th>收入（亿元）</th><th>原值及依据</th></tr></thead>
      <tbody>{[...group.rows,...(group.total?[group.total]:[])].map((row,index)=><tr key={index} className="border-t border-border align-top">
        <td className="py-2 pr-3">{row.label}</td><td className="py-2 pr-3 tabular-nums">{row.value.toLocaleString('zh-CN',{maximumFractionDigits:4})}</td>
        <td className="py-2"><details><summary className="cursor-pointer">{row.rawValue} {row.rawUnit}</summary><pre className="whitespace-pre-wrap text-xs">{group.columnHeader}{'\n'}{row.excerpt}</pre></details></td>
      </tr>)}</tbody></table></div>
    <p className="text-muted-foreground">{group.total?'原表合计仅适用于此表，不是公司总收入。':'原表未识别到合计；不能将所列项目视作公司全部收入。'}{group.skippedRows>0&&` 有 ${group.skippedRows} 行未可靠识别，需查原页。`}</p>
  </>;
}

export function EarningsRevenueImport({workbook,disabled,onBusy,onAdopt,onRemove}:{workbook:EarningsWorkbook;disabled:boolean;onBusy:(busy:boolean)=>void;onAdopt:(document:EarningsPdfImport,ids:string[],workbookId:string)=>void;onRemove:(sourceId:string,workbookId:string)=>void}) {
  const [reportId,setReportId]=useState('');
  const [document,setDocument]=useState<EarningsPdfImport|null>(null);
  const [selected,setSelected]=useState<string[]>([]);
  const [confirmed,setConfirmed]=useState(false);
  const [status,setStatus]=useState('');
  const [error,setError]=useState('');
  const [removing,setRemoving]=useState('');
  const reports=new Map<string,string>();
  for(const source of workbook.sourceMaterials) {
    const id=source.importedReport?.reportId||source.discussion?.reportId||source.capitalNote?.reportId||source.businessRevenue?.reportId;
    if(id&&!reports.has(id))reports.set(id,source.label);
  }
  if(!reports.size)return null;
  const currentId=reportId||reports.keys().next().value!;
  const clear=()=>{setDocument(null);setSelected([]);setConfirmed(false);setStatus('');setError('')};
  const read=async()=>{
    clear();onBusy(true);setStatus('正在定位主营业务收入结构…');
    try {
      const result=await api.earningsRevenueCandidates(currentId);
      const groups=missingPdfRevenue(workbook,result);
      setDocument({...result,revenueGroups:groups});
      setStatus(groups.length?`发现 ${groups.length} 张未采用表，核对后整表采纳。`:'没有可新增表：可能已采用或版式未识别；不代表公司没有相关业务。');
    } catch(e){setError(e instanceof Error?e.message:'读取失败');setStatus('原底稿未改动。')}
    finally{onBusy(false)}
  };
  return <section aria-label="主营业务收入结构" className="mb-4 border-b border-border pb-3 text-sm">
    <div className="flex flex-wrap items-center gap-3"><p className="flex-1 text-muted-foreground">分别核对行业、产品、地区与销售模式；不同划分不可相加，不等同会计报告分部。</p>
      {reports.size>1&&<select className={button} aria-label="收入结构财报" value={currentId} disabled={disabled} onChange={e=>{clear();setReportId(e.target.value)}}>{[...reports].map(([id,label])=><option key={id} value={id}>{label}</option>)}</select>}
      <button className={button} disabled={disabled} onClick={()=>void read()}>补充主营收入结构</button>
    </div>
    {status&&<p role="status" className="mt-2">{status}</p>}{error&&<p role="alert" className="mt-2 text-destructive">{error}</p>}
    {document&&<div className="mt-3 space-y-3">
      <p>{document.security.name} · {document.periodEnd} · 年度主营业务 · 人民币</p>
      {document.revenueWarnings?.map(text=><p key={text} className="text-muted-foreground">{text}</p>)}
      {document.revenueGroups?.map(group=><section key={group.id} aria-label={group.title} className="rounded border border-border p-3">
        <label className="flex items-center gap-2 font-semibold"><input type="checkbox" disabled={disabled} checked={selected.includes(group.id)} onChange={e=>{setSelected(e.target.checked?[...selected,group.id]:selected.filter(id=>id!==group.id));setConfirmed(false)}}/>采用{group.title} · 第 {group.page} 页</label>
        <RevenueTable group={group}/><ReportSourceLink className="text-primary underline" href={`${researchApiUrl(`/myreports/file/${encodeURIComponent(document.reportId)}?inline=true`)}#page=${group.page}`} target="_blank" rel="noreferrer">核对 PDF 原页</ReportSourceLink>
      </section>)}
      {!!document.revenueGroups?.length&&<><label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>已核对各表项目、期间与单位；不同维度不相加</label>
        <button className={button} disabled={disabled||!confirmed||!selected.length} onClick={()=>{
          try{onAdopt(document,selected,workbook.id);clear();setStatus('收入结构已加入草稿，请保存；未修改总收入及研究结论。')}
          catch(e){setError(e instanceof Error?e.message:'采用失败')}
        }}>确认采用收入结构</button></>}
      <button className={button} disabled={disabled} onClick={clear}>关闭收入结构预览</button>
    </div>}
    {workbook.sourceMaterials.some(source=>source.businessRevenue)&&<details aria-label="已采用收入结构" className="mt-3">
      <summary className="cursor-pointer">已采用收入结构 · {workbook.sourceMaterials.filter(s=>s.businessRevenue).length} 张表</summary>
      {workbook.sourceMaterials.filter(source=>source.businessRevenue).map(source=><section key={source.id} aria-label={source.businessRevenue!.title} className="my-3 rounded border border-border p-3">
        <h3>{source.businessRevenue!.title} · {source.periodEnd} · PDF 第 {source.businessRevenue!.pdfPage} 页</h3><RevenueTable group={source.businessRevenue!}/>
        <ReportSourceLink className="mr-3 text-primary underline" href={`${researchApiUrl(`/myreports/file/${encodeURIComponent(source.businessRevenue!.reportId)}?inline=true`)}#page=${source.businessRevenue!.pdfPage}`} target="_blank" rel="noreferrer">核对 PDF 原页</ReportSourceLink>
        {removing===source.id?<><p>仅从草稿撤下此表，不删除 PDF 或修改其他指标；保存后生效。</p><button className={button} disabled={disabled} onClick={()=>{
          onRemove(source.id,workbook.id);setRemoving('');clear();setStatus('已从草稿撤下，请保存；需要时可重新采纳。');
        }}>确认从草稿撤下</button><button className={button} disabled={disabled} onClick={()=>setRemoving('')}>保留此表</button></>:<button className={button} disabled={disabled} onClick={()=>setRemoving(source.id)}>撤下此表</button>}
      </section>)}
    </details>}
  </section>;
}
