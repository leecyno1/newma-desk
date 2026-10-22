import { ReportSourceLink } from '@/components/ReportSourceLink';
import {useEffect, useRef, useState} from 'react';
import {Upload, Loader2} from 'lucide-react';
import {api, researchApiUrl, reportScope, assertReportScope, type ReportRequestOptions, type EarningsPdfImport, type MyReport} from '@/lib/api';
import {subscribeVibeDeskConfig} from '@/lib/vibedesk';
import {workbookFromPdf} from '@/lib/earningsPdfImport';
import type {EarningsWorkbook} from '@/lib/earningsWorkbench';
import {EarningsDiscussionCandidates} from './EarningsDiscussionCandidates';

export interface EarningsPdfPreview {
  document: EarningsPdfImport;
  selected: string[];
  discussionIds: string[];
  confirmed: boolean;
  status: string;
}

export function EarningsPdfUpload({disabled, canAdopt = true, onPreviewChange, onBusy, onAdopt}: {
  disabled: boolean; onBusy: (busy: boolean)=>void;
  canAdopt?: boolean; onPreviewChange?: (snapshot: EarningsPdfPreview | null) => void;
  onAdopt: (workbook: EarningsWorkbook)=>Promise<boolean>;
}) {
  const [scope,setScope] = useState(reportScope);
  useEffect(()=>subscribeVibeDeskConfig(()=>setScope(reportScope())),[]);
  return <ScopedPdfUpload key={scope} scope={scope} disabled={disabled} canAdopt={canAdopt} onPreviewChange={onPreviewChange} onBusy={onBusy} onAdopt={onAdopt}/>;
}

function ScopedPdfUpload({scope,disabled,canAdopt,onPreviewChange,onBusy,onAdopt}:{
  scope:string; disabled:boolean; onBusy:(busy:boolean)=>void; onAdopt:(workbook:EarningsWorkbook)=>Promise<boolean>;
  canAdopt: boolean; onPreviewChange?: (snapshot: EarningsPdfPreview | null) => void;
}) {
  const pending = useRef(new AbortController());
  const locked = useRef(false);
  useEffect(()=>{pending.current=new AbortController(); return ()=>{pending.current.abort();onBusy(false)}},[]);
  const active=()=>!pending.current.signal.aborted&&scope===reportScope();
  const input = useRef<HTMLInputElement>(null);
  const [document,setDocument] = useState<EarningsPdfImport|null>(null);
  const [uploaded,setUploaded] = useState<MyReport|null>(null);
  const [selected,setSelected] = useState<string[]>([]);
  const [discussionIds,setDiscussionIds] = useState<string[]>([]);
  const [confirmed,setConfirmed] = useState(false);
  const [busy,setBusy] = useState(false);
  const [status,setStatus] = useState('');
  const [error,setError] = useState('');
  useEffect(()=>{onPreviewChange?.(document?{document,selected,discussionIds,confirmed,status:'待采用候选，不是已保存底稿'}:null)},[document,selected,discussionIds,confirmed,onPreviewChange]);
  useEffect(()=>()=>onPreviewChange?.(null),[onPreviewChange]);
  const setWorking=(value:boolean)=>{setBusy(value);onBusy(value)};
  const extract=async(report:MyReport,options:ReportRequestOptions={scope,signal:pending.current.signal})=>{
    setStatus('文件已保存到当前资料库，正在提取指标、经营讨论和页码…');
    const result=await api.earningsPdfCandidates(report.id,options);
    if(!active())return;
    setDocument(result);setSelected(result.candidates.map(row=>row.id));setConfirmed(false);
    setDiscussionIds((result.discussion||[]).map(row=>row.id));
    setStatus(`已提取 ${result.candidates.length} 项指标、${result.discussion?.length||0} 页经营讨论候选，尚未写入底稿。`);
  };
  const upload=async(file:File)=>{
    if(locked.current||!active())return;
    if(!file.name.toLowerCase().endsWith('.pdf')||file.size>25*1024*1024){setError('请上传 25MB 以内的 PDF');return}
    locked.current=true;
    setWorking(true);setError('');setDocument(null);setUploaded(null);setStatus('正在上传 PDF 到当前资料库…');
    try {
      const content=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file)});
      assertReportScope(scope,pending.current.signal);
      const report=await api.uploadReport(file.name,content,{scope,signal:pending.current.signal});
      if(!active())return;
      setUploaded(report);await extract(report);
    }catch(e){if(active()){setError(e instanceof Error?e.message:String(e));setStatus('上传或提取未完成，未改变底稿；上传结果未知时请先到档案页核对。')}}
    finally{locked.current=false;if(active())setWorking(false)}
  };
  const adopt=async()=>{
    if(!document||!confirmed||disabled||!canAdopt||locked.current||!active())return;
    locked.current=true;
    setWorking(true);setError('');
    try{if(await onAdopt(workbookFromPdf(document,selected,discussionIds))&&active()){setDocument(null);setStatus('已保存为新的财报底稿。可点击“分析此底稿”，在统一 Copilot 中发送问题。')}}
    catch(e){if(active())setError(e instanceof Error?e.message:String(e))}finally{locked.current=false;if(active())setWorking(false)}
  };
  const retry=async()=>{
    if(!uploaded||disabled||locked.current||!active())return;
    locked.current=true;setWorking(true);setError('');
    try{await extract(uploaded)}catch(e){if(active())setError(e instanceof Error?e.message:'提取失败')}
    finally{locked.current=false;if(active())setWorking(false)}
  };
  return <section aria-label="上传财报与提取" className="mb-4 rounded-lg border border-border p-4 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">从真实财报开始</h2><p className="mt-1 text-muted-foreground">上传 → 提取候选 → 核对保存 → Agent 分析。当前支持文字版 A 股人民币年报，不支持扫描件 OCR。</p></div>
      <button disabled={disabled||busy} onClick={()=>input.current?.click()} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50">{busy?<Loader2 className="h-4 w-4 animate-spin"/>:<Upload className="h-4 w-4"/>}上传财报 PDF</button>
      <input ref={input} type="file" accept=".pdf,application/pdf" aria-label="选择财报 PDF" className="hidden" disabled={disabled||busy} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);e.target.value=''}}/>
    </div>
    {status&&<p role="status" className="mt-3">{status}</p>}
    {uploaded&&<p className="mt-2 text-muted-foreground">已上传：<ReportSourceLink className="text-primary underline" href={researchApiUrl(`/myreports/file/${uploaded.id}?inline=true`)} target="_blank" rel="noreferrer">{uploaded.name}</ReportSourceLink> · 已保存到当前资料库</p>}
    {error&&<p role="alert" className="mt-2 text-destructive">{error}</p>}
    {error&&uploaded&&!busy&&<button disabled={disabled} className="mt-2 underline disabled:opacity-50" onClick={()=>void retry()}>重试提取已上传文件</button>}
    {document&&<div className="mt-4 space-y-3">
      <p className="font-medium">{document.security.name||'公司未识别'} · {document.security.symbol||'代码未识别'} · {document.periodEnd||'报告期未识别'} · 人民币 · 年度</p>
      {document.warnings.map((warning,i)=><p key={i} className="text-muted-foreground">{warning}</p>)}
      <div className="overflow-x-auto"><table aria-label="PDF 指标候选" className="w-full text-left"><thead><tr><th>采用</th><th>指标</th><th>候选值</th><th>原值 / 单位</th><th>来源页与原文</th></tr></thead><tbody>
        {document.candidates.map(row=><tr key={row.id} className="border-t border-border"><td className="py-3 pr-3"><input type="checkbox" aria-label={`采用 ${row.label}`} disabled={disabled||busy} checked={selected.includes(row.id)} onChange={e=>{setConfirmed(false);setSelected(e.target.checked?[...selected,row.id]:selected.filter(id=>id!==row.id))}}/></td><td className="pr-3 whitespace-nowrap">{row.label}</td><td className="pr-3 whitespace-nowrap">{row.value.toLocaleString('zh-CN',{maximumFractionDigits:4})} {row.unit}</td><td className="pr-3 whitespace-nowrap">{row.rawValue} {row.rawUnit}</td><td className="py-2"><ReportSourceLink className="text-primary underline" href={`${researchApiUrl(`/myreports/file/${document.reportId}?inline=true`)}#page=${row.page}`} target="_blank" rel="noreferrer">PDF 第 {row.page} 页</ReportSourceLink><details><summary className="cursor-pointer text-muted-foreground">查看表头与摘录</summary><pre className="max-w-xl whitespace-pre-wrap py-2 text-xs">{row.columnHeader+'\n'+row.excerpt}</pre></details></td></tr>)}
      </tbody></table></div>
      <EarningsDiscussionCandidates document={document} selected={discussionIds} disabled={disabled||busy} onChange={ids=>{setConfirmed(false);setDiscussionIds(ids)}}/>
      {!document.candidates.length&&<p className="text-muted-foreground">没有可靠指标时，可仅保存已勾选的经营原文，再补充主营收入结构；财务指标保持缺失，不填零。</p>}
      <label className="flex items-start gap-2"><input type="checkbox" aria-label="已核对财报身份、期间、单位和选中指标" disabled={disabled||busy} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我已核对公司、年度、单位、选中指标及经营讨论原文；新建底稿，保留已有底稿。</label>
      {!canAdopt&&<p className="text-warning">当前保存权限或版本尚未确认。候选仍保留，可导出当前草稿后重新读取档案；上传文件不会删除。</p>}
      <button disabled={disabled||busy||!canAdopt||!confirmed||(!selected.length&&!discussionIds.length)||!document.periodEnd} onClick={()=>void adopt()} className="rounded-lg bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50">确认新建并保存底稿</button>
      <button disabled={disabled||busy} className="ml-3 rounded-lg border border-border px-3 py-2" onClick={()=>{setDocument(null);setStatus('已取消采用，上传文件仍保留在当前资料库。')}}>取消采用</button>
    </div>}
  </section>;
}
