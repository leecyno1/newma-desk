import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api, type Announcement, type AnnouncementSearch, type AnnouncementText } from '@/lib/api';
import { EARNINGS_BASIS, type EarningsSource, type EarningsWorkbook } from '@/lib/earningsWorkbench';
import { announcementRevisionHint, filingExcerptTarget, reviewFilingExcerpts, linkFilingExcerpt, type FilingReadFailure } from '@/lib/earningsEvidence';

const control='rounded border border-border bg-card px-3 py-2 text-sm disabled:opacity-50';

export function EarningsFilingEvidence({workbook,disabled,onAttach,onRemove,onReadingChange,onSearchChange,onFailureChange,renderReview}:{
  workbook:EarningsWorkbook; disabled:boolean;
  onAttach:(source:EarningsSource)=>void;
  onRemove:(id:string)=>void;
  onReadingChange:(document:AnnouncementText|null)=>void;
  onSearchChange:(result:AnnouncementSearch|null)=>void;
  onFailureChange:(failure:FilingReadFailure|null)=>void;
  renderReview:(readSource:(source:EarningsSource)=>void,busy:boolean)=>ReactNode;
}) {
  const now=new Date();
  const today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
  const [begin,setBegin]=useState(workbook.fiscalPeriod.periodEnd||`${today.slice(0,4)}-01-01`);
  const [end,setEnd]=useState(today);
  const [category,setCategory]=useState<'all'|'financial'>('all');
  const [searchResult,setSearchResult]=useState<AnnouncementSearch|null>(null);
  const [announcements,setAnnouncements]=useState<Announcement[]|null>(null);
  const [document,setDocument]=useState<AnnouncementText|null>(null);
  const [pdfPage,setPdfPage]=useState('1');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [failure,setFailure]=useState<FilingReadFailure|null>(null);
  const [excerpt,setExcerpt]=useState('');
  const [metricId,setMetricId]=useState('revenue');
  const [confirmed,setConfirmed]=useState(false);
  const requestId=useRef(0);
  const selectedMetric=workbook.metrics.find(metric=>metric.id===metricId);
  useEffect(()=>setConfirmed(false),[selectedMetric?.reported,selectedMetric?.unit]);
  useEffect(()=>()=>{requestId.current++;onReadingChange(null);onSearchChange(null);onFailureChange(null)},[onReadingChange,onSearchChange,onFailureChange]);
  const updateFailure=(next:FilingReadFailure|null)=>{setFailure(next);onFailureChange(next)};
  const readTarget=(id:string,kind:FilingReadFailure['kind'],position:number):FilingReadFailure=>{
    const previous=document?.announcementId===id?document:failure?.announcementId===id?failure:null;
    const item=announcements?.find(item=>item.announcementId===id||item.url.includes(`/${id}.html`));
    const saved=workbook.sourceMaterials.find(source=>filingExcerptTarget(workbook.security.symbol,source)?.announcementId===id);
    const pdfUrl=previous?.pdfUrl||saved?.excerpt?.pdfUrl;
    return {announcementId:id,title:previous?.title||item?.title||saved?.label||id,kind,position,message:'',...(pdfUrl?{pdfUrl}:{})};
  };
  const invalidateSearch=()=>{
    requestId.current++;setSearchResult(null);setAnnouncements(null);setDocument(null);setExcerpt('');setConfirmed(false);setMessage('');
    onSearchChange(null);onReadingChange(null);updateFailure(null);
  };
  const search=async(page=1)=>{
    invalidateSearch();
    if(!begin||!end||begin>end){setMessage('请填写有效披露日期区间，开始日期不能晚于结束日期');return}
    const request=++requestId.current;
    setBusy(true);
    try {
      const result=await api.announcementSearch(workbook.security.symbol,begin,end,category,page);
      if(request!==requestId.current)return;
      if(!result||result.symbol!==workbook.security.symbol||result.begin!==begin||result.end!==end||result.category!==category||result.page!==page)throw new Error('检索结果与当前查询不一致，请重新查询');
      setSearchResult(result);setAnnouncements(result.items);onSearchChange(result);
    }catch(error){if(request===requestId.current)setMessage(error instanceof Error?error.message:String(error))}
    finally{if(request===requestId.current)setBusy(false)}
  };
  const read=async(id?:string,segment=1)=>{
    const target=id?readTarget(id,'transcription',segment):null;
    const request=++requestId.current;
    setBusy(true);setMessage('');setDocument(null);onReadingChange(null);setExcerpt('');setConfirmed(false);updateFailure(null);
    if(!id){setAnnouncements(null);setSearchResult(null);onSearchChange(null)}
    try {
      if(id){
        const result=await api.announcementText(workbook.security.symbol,id,segment);
        if(request!==requestId.current)return;
        if(!result||result.symbol!==workbook.security.symbol||result.announcementId!==id||result.contentOrigin!=='provider-transcription'||result.segment!==segment||!result.text.trim())throw new Error('未读到匹配当前证券与分段的转录文字');
        setDocument(result);onReadingChange(result);
      } else {
        const result=await api.announcements(workbook.security.symbol);
        if(request!==requestId.current)return;
        setAnnouncements(result||[]);
      }
    } catch(error) {
      if(request===requestId.current){
        const message=error instanceof Error?error.message:String(error);
        if(target)updateFailure({...target,message});else setMessage(message);
      }
    } finally {if(request===requestId.current)setBusy(false)}
  };
  const attach=()=>{
    if(!document||!confirmed)return;
    try {
      onAttach(linkFilingExcerpt(workbook,document,metricId,excerpt));
      setExcerpt('');setConfirmed(false);setMessage('摘录已关联到草稿，请保存底稿；未改动实际值或其原来源。');
    }catch(error){setMessage(error instanceof Error?error.message:String(error))}
  };
  const readPdf=async(id:string,page=1)=>{
    if(!Number.isInteger(page)||page<1||page>1000){setMessage('请填写 1 至 1000 的 PDF 页码');return}
    const target=readTarget(id,'pdf',page);
    const request=++requestId.current;
    setBusy(true);setMessage('');setDocument(null);onReadingChange(null);setExcerpt('');setConfirmed(false);updateFailure(null);
    try {
      const result=await api.announcementPdfPage(workbook.security.symbol,id,page);
      if(request!==requestId.current)return;
      if(!result||result.symbol!==workbook.security.symbol||result.announcementId!==id||result.contentOrigin!=='pdf-text'||result.pdfPage!==page||!result.pdfUrl||!result.pdfPageCount||page>result.pdfPageCount)throw new Error('PDF 返回内容或页码不匹配，请重新读取');
      setDocument(result);setPdfPage(String(page));onReadingChange(result);
    }catch(error){if(request===requestId.current)updateFailure({...target,message:error instanceof Error?error.message:String(error)})}
    finally{if(request===requestId.current)setBusy(false)}
  };
  const references=workbook.sourceMaterials.filter(source=>source.excerpt&&!source.correction);
  const excerptChecks=reviewFilingExcerpts(workbook,document);
  const readSource=(source:EarningsSource)=>{
    const target=filingExcerptTarget(workbook.security.symbol,source);
    if(disabled||busy||!target)return;
    setMetricId(source.excerpt!.metricId);
    void(target.kind==='pdf'?readPdf(target.announcementId,target.position):read(target.announcementId,target.position));
  };
  const unavailable=disabled||busy||workbook.security.market!=='CN'||!/^\d{6}$/.test(workbook.security.symbol);
  return <><section aria-label="公告证据链" className="rounded-lg border border-border p-4 space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">公告文字与指标证据</h2><button className={control} disabled={disabled||busy||workbook.security.market!=='CN'||!/^\d{6}$/.test(workbook.security.symbol)} onClick={()=>void read()}>读取近期公告</button></div>
    <p className="text-sm text-muted-foreground">A 股近期入口显示最近 15 条，也可按披露日期分页检索。可读取东财转录或 PDF 单页文字；披露日期不是财报期末，不自动核验数字或最新报告期。</p>
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-sm">披露开始日期<input aria-label="公告披露开始日期" type="date" className={`${control} block`} disabled={disabled||busy} value={begin} onChange={event=>{invalidateSearch();setBegin(event.target.value)}} /></label>
      <label className="text-sm">披露结束日期<input aria-label="公告披露结束日期" type="date" className={`${control} block`} disabled={disabled||busy} value={end} onChange={event=>{invalidateSearch();setEnd(event.target.value)}} /></label>
      <label className="text-sm">公告分类<select aria-label="公告检索分类" className={`${control} block`} disabled={disabled||busy} value={category} onChange={event=>{invalidateSearch();setCategory(event.target.value as 'all'|'financial')}}><option value="all">全部公告（含更正线索）</option><option value="financial">财务报告</option></select></label>
      <button className={control} disabled={unavailable} onClick={()=>void search()}>检索历史公告</button>
      <button className={control} disabled={disabled||busy||!workbook.fiscalPeriod.periodEnd} onClick={()=>{invalidateSearch();setBegin(workbook.fiscalPeriod.periodEnd!);setEnd(today)}}>用底稿期末设置窗口</button>
    </div>
    <p className="text-sm text-muted-foreground">默认查询期末至今的披露，需自行调整窗口；不能据此认定公告属于该期。更正/修订仅按标题提示，不自动替代原报告。只选“财务报告”可能漏掉归入其他分类的更正公告。</p>
    {searchResult&&<div aria-label="公告检索覆盖" className="flex flex-wrap items-center gap-3 text-sm"><span>{searchResult.begin} 至 {searchResult.end} · 第 {searchResult.page} 页 · 本页 {searchResult.items.length} 条 · 来源报告共 {searchResult.total??'未知'} 条；仅当前页索引已读取，正文需另行读取</span><button className={control} disabled={disabled||busy||searchResult.page<=1} onClick={()=>void search(searchResult.page-1)}>上一页公告</button><button className={control} disabled={disabled||busy||!searchResult.hasMore||searchResult.page>=500} onClick={()=>void search(searchResult.page+1)}>下一页公告</button>{searchResult.page>=500&&searchResult.hasMore&&<span>达到分页上限，请缩小日期窗口。</span>}</div>}
    {busy&&<p role="status">正在读取公告…</p>}
    {message&&<p role="status" className="text-sm">{message}</p>}
    {failure&&<div aria-label="公告读取恢复" className="border-l-2 border-warning pl-3 space-y-2 text-sm">
      <p className="font-medium">{failure.title} · {failure.kind==='pdf'?`PDF 第 ${failure.position} 页`:`转录第 ${failure.position} 段`}未读取</p>
      <p role="status">{failure.message}</p>
      <p className="text-muted-foreground">已清除临时正文，已保存摘录与财务数值不变。转录分段不对应 PDF 页码，切换来源后需重新核对。</p>
      <div className="flex flex-wrap items-center gap-3">
        <button className={control} disabled={disabled||busy} onClick={()=>void(failure.kind==='pdf'?readPdf(failure.announcementId,failure.position):read(failure.announcementId,failure.position))}>{failure.kind==='pdf'?`重试 PDF 第 ${failure.position} 页`:`重试转录第 ${failure.position} 段`}</button>
        <button className={control} disabled={disabled||busy} onClick={()=>void(failure.kind==='pdf'?read(failure.announcementId):readPdf(failure.announcementId))}>{failure.kind==='pdf'?'改读转录文字（非 PDF）':'改读 PDF 首页'}</button>
        <a className="text-primary" href={`https://data.eastmoney.com/notices/detail/${encodeURIComponent(workbook.security.symbol)}/${encodeURIComponent(failure.announcementId)}.html`} target="_blank" rel="noreferrer">打开该公告详情核对</a>
        {failure.pdfUrl&&<a className="text-primary" href={`${failure.pdfUrl.split('#')[0]}#page=${failure.kind==='pdf'?failure.position:1}`} target="_blank" rel="noreferrer">在浏览器打开 PDF 核对</a>}
      </div>
    </div>}
    {announcements&&<div className="max-h-52 overflow-y-auto divide-y divide-border" aria-label="近期公告列表">
      {announcements.length===0&&<p className="py-2 text-sm">本次未返回公告，不代表公司没有披露。</p>}
      {announcements.map((item,index)=>{
        const id=item.announcementId||item.url.match(/\/(AN\d+)\.html/)?.[1];
        return <div key={id||index} className="flex items-center gap-3 py-2 text-sm"><span className="shrink-0 text-muted-foreground">{item.date||'日期未知'}</span><span className="flex-1">{item.title||'标题缺失'}{announcementRevisionHint(item.title)&&<span className="ml-2 text-warning">{announcementRevisionHint(item.title)}</span>}</span><button className={control} aria-label={`读取公告文字 ${item.title}`} disabled={!id||busy||disabled} onClick={()=>void read(id)}>读取文字</button><button className={control} aria-label={`读取公告 PDF ${item.title}`} disabled={!id||busy||disabled} onClick={()=>id&&void readPdf(id)}>读 PDF</button></div>;
      })}
    </div>}
    {document&&<div className="space-y-3">
      {announcementRevisionHint(document.title)&&<p className="text-sm text-warning">{announcementRevisionHint(document.title)}：请核对适用报告、变更项目及原披露，不自动覆盖原底稿。</p>}
      <div className="flex flex-wrap gap-3 text-sm"><strong>{document.title}</strong><span>公告日期 {document.date||'未提供'}</span><a className="text-primary" href={document.url} target="_blank" rel="noreferrer">公告详情</a>{document.pdfUrl&&<a className="text-primary" href={`${document.pdfUrl.split('#')[0]}#page=${document.pdfPage||1}`} target="_blank" rel="noreferrer">{document.contentOrigin==='pdf-text'?'打开 PDF 原页核对':'打开 PDF（未读取）'}</a>}</div>
      {document.contentOrigin==='pdf-text'?<>
        <div className="flex flex-wrap items-center gap-3 text-sm"><span>PDF 物理页 {document.pdfPage} / {document.pdfPageCount}（含封面，不等于印刷页码）</span>
          <button className={control} disabled={disabled||busy||document.pdfPage!<=1} onClick={()=>void readPdf(document.announcementId,document.pdfPage!-1)}>上一页 PDF</button>
          <button className={control} disabled={disabled||busy||document.pdfPage!>=Math.min(document.pdfPageCount!,1000)} onClick={()=>void readPdf(document.announcementId,document.pdfPage!+1)}>下一页 PDF</button>
          <input aria-label="PDF 跳转页码" type="number" min={1} max={Math.min(document.pdfPageCount!,1000)} className={`${control} w-24`} value={pdfPage} onChange={e=>setPdfPage(e.target.value)} />
          <button className={control} disabled={disabled||busy} onClick={()=>void readPdf(document.announcementId,Number(pdfPage))}>读取指定页</button>
          <button className={control} disabled={disabled||busy} onClick={()=>void read(document.announcementId)}>切换转录文字</button>
        </div>
        <p className="text-sm text-muted-foreground">仅提取当前页文字，未核验全文；表格列序、合并单元格和单位需对照原页。暂不识别扫描文字，也不自动回填数字。{document.truncated?'本页仅显示前 60000 字。':''}</p>
        {!document.text.trim()&&<p role="status">本页未提取到文字，可能是扫描图像或空白页；请打开原页核对，不能当作已读取正文。</p>}
      </>:<div className="flex flex-wrap items-center gap-3 text-sm"><span>来源文字分段 {document.segment} / {document.segmentCount??'未知'}（不是 PDF 页码）{document.truncated?' · 本段仅显示前 60000 字':''}</span><button className={control} disabled={disabled||busy||document.segment<=1} onClick={()=>void read(document.announcementId,document.segment-1)}>上一段</button><button className={control} disabled={disabled||busy||document.segment>=1000||Boolean(document.segmentCount&&document.segment>=document.segmentCount)} onClick={()=>void read(document.announcementId,document.segment+1)}>下一段</button><button className={control} disabled={disabled||busy||!document.pdfUrl} onClick={()=>void readPdf(document.announcementId)}>读取 PDF 首页</button></div>}
      <pre aria-label="已读取公告文字" className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted/30 p-3 font-sans text-sm leading-6">{document.text}</pre>
      <div className="flex flex-wrap items-center gap-3"><label>关联指标 <select aria-label="摘录关联指标" className={control} value={metricId} onChange={event=>{setMetricId(event.target.value);setConfirmed(false)}}>{workbook.metrics.map(metric=><option key={metric.id} value={metric.id}>{metric.label} · {metric.reported??'缺失'} {metric.unit}</option>)}</select></label><span className="text-sm text-muted-foreground">底稿 {workbook.fiscalPeriod.periodEnd||'期末未确认'} · {workbook.fiscalPeriod.basis?EARNINGS_BASIS[workbook.fiscalPeriod.basis]:'口径未确认'}</span></div>
      <textarea aria-label="公告原文摘录" maxLength={2000} className={`${control} w-full min-h-24`} value={excerpt} onChange={event=>{setExcerpt(event.target.value);setConfirmed(false)}} placeholder="从上方已读取文字复制相关句段（最多 2000 字），不要填研究推断。" />
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} />我已核对这段文字与所选指标、底稿期末及口径的关联；不代表整份报告已核验。</label>
      <button className={control} disabled={disabled||busy||!confirmed||!excerpt.trim()||!document.text.trim()} onClick={attach}>关联摘录到草稿</button>
    </div>}
    {references.map(source=>{
      const ref=source.excerpt!;
      const target=filingExcerptTarget(workbook.security.symbol,source);
      const check=excerptChecks.find(item=>item.sourceId===source.id);
      const metric=workbook.metrics.find(item=>item.id===ref.metricId);
      const changed=!metric||metric.reported!==ref.reportedValue||metric.unit!==ref.unit||source.periodEnd!==workbook.fiscalPeriod.periodEnd||source.basis!==workbook.fiscalPeriod.basis;
      return <details key={source.id} className="border-t border-border pt-2 text-sm"><summary className="cursor-pointer">{metric?.label||ref.metricId} · {source.label} · {changed?'数字或底稿口径已变化，需重新核对':'已关联摘录（人工确认，非自动验证）'}</summary>{announcementRevisionHint(source.label)&&<p className="mt-2 text-warning">{announcementRevisionHint(source.label)}：此摘录与原报告的替代关系尚未核验。</p>}<blockquote className="my-2 whitespace-pre-wrap border-l-2 border-primary pl-3">{ref.text}</blockquote><p className="text-muted-foreground">关联时实际值 {ref.reportedValue??'缺失'} {ref.unit} · 底稿期末（人工关联）{source.periodEnd} · {ref.contentOrigin==='pdf-text'?`PDF 物理页 ${ref.pdfPage} / ${ref.pdfPageCount}`:`来源分段 ${ref.segment}`} · 公告日期 {source.asOf||'未提供'} · 采集 {source.retrievedAt}</p>{ref.pdfUrl&&<a className="text-primary" href={`${ref.pdfUrl.split('#')[0]}#page=${ref.pdfPage}`} target="_blank" rel="noreferrer">回到摘录所在 PDF 页</a>}{check&&<p role="status" className="mt-2 text-sm">{check.status}</p>}<button className={`${control} mt-2 mr-2`} disabled={disabled||busy||!target} onClick={()=>readSource(source)}>回读并核对摘录</button>{!target&&<span className="text-muted-foreground">来源身份或页定位不完整，暂不能回读。</span>}<button className={`${control} mt-2`} disabled={disabled||workbook.sourceMaterials.some(s=>s.correction&&(s.correction.evidenceSourceId===source.id||s.correction.previousSourceIds.includes(source.id)))} onClick={()=>onRemove(source.id)}>取消这条摘录关联</button></details>;
    })}
  </section>{renderReview(readSource,busy)}</>;
}
