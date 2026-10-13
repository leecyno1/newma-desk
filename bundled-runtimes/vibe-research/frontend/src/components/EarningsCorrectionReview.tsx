import { useState } from 'react';
import { EARNINGS_BASIS, type EarningsSource, type EarningsWorkbook, type FilingAmountInput } from '@/lib/earningsWorkbench';
import { convertFilingAmount, filingCorrectionReadiness, filingExcerptPassage, filingExcerptTarget, reviewFilingExcerpts, previewFilingCorrection, type FilingCorrectionPreview, type FilingReadFailure } from '@/lib/earningsEvidence';
import type { AnnouncementText } from '@/lib/api';

const control='rounded border border-border bg-card px-3 py-2 text-sm disabled:opacity-50';
export function EarningsCorrectionReview({workbook,disabled,candidate,reading,readingBusy,failure,onReadSource,onPreview,onApply}:{
  workbook:EarningsWorkbook;disabled:boolean;candidate:FilingCorrectionPreview|null;
  reading:AnnouncementText|null;
  readingBusy:boolean;onReadSource:(source:EarningsSource)=>void;
  failure:FilingReadFailure|null;
  onPreview:(candidate:FilingCorrectionPreview|null)=>void;onApply:()=>void;
}) {
  const [sourceId,setSourceId]=useState('');
  const [value,setValue]=useState('');
  const [amountUnit,setAmountUnit]=useState<FilingAmountInput['unit']>('亿元');
  const [reason,setReason]=useState('');
  const [confirmed,setConfirmed]=useState(false);
  const [error,setError]=useState('');
  const sources=workbook.sourceMaterials.filter(source=>source.excerpt&&!source.correction);
  const source=sources.find(item=>item.id===sourceId);
  const target=source?filingExcerptTarget(workbook.security.symbol,source):null;
  const sourceFailure=target&&failure?.announcementId===target.announcementId&&failure.kind===target.kind&&failure.position===target.position?failure:null;
  const metric=workbook.metrics.find(item=>item.id===source?.excerpt?.metricId);
  const amountMode=metric?.unit==='亿元'&&workbook.security.currency==='CNY';
  const amountInput:FilingAmountInput|undefined=amountMode?{value:value.trim(),unit:amountUnit,currency:'CNY'}:undefined;
  let converted:number|null=null,conversionError='';
  if(amountInput&&value.trim()){
    try{converted=convertFilingAmount(amountInput)}catch(e){conversionError=e instanceof Error?e.message:String(e)}
  }
  const readingIssue=source?filingCorrectionReadiness(workbook,source.id,reading):null;
  const check=reviewFilingExcerpts(workbook,reading).find(item=>item.sourceId===sourceId);
  const passage=check&&reading&&source?.excerpt?filingExcerptPassage(reading.text,source.excerpt.text):null;
  const sourceUrl=source?.excerpt?.pdfUrl?`${source.excerpt.pdfUrl.split('#')[0]}#page=${source.excerpt.pdfPage}`:source?.url;
  const readingUrl=reading?.contentOrigin==='pdf-text'&&reading.pdfUrl?`${reading.pdfUrl.split('#')[0]}#page=${reading.pdfPage}`:reading?.url;
  const clear=()=>{onPreview(null);setConfirmed(false);setError('')};
  const preview=()=>{
    setConfirmed(false);
    try {
      if(!amountInput&&!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim()))throw new Error('请按本行单位填写修订值，不能留空');
      const after=amountInput?convertFilingAmount(amountInput):Number(value);
      onPreview(previewFilingCorrection(workbook,sourceId,after,reason,reading,amountInput));setError('');
    }catch(e){onPreview(null);setError(e instanceof Error?e.message:String(e))}
  };
  return <section aria-label="公告修订对照" className="rounded-lg border border-border p-4 space-y-3">
    <h2 className="font-semibold">财报数值补录与修订 · 逐项确认</h2>
    <p className="text-sm text-muted-foreground">先关联公告摘录，并回读其所在页/分段，再手工输入修订值。文字匹配不代表数字已核验；源站不可用时可保留底稿，不能将旧摘录当作已回读的修订依据。采用后另存底稿，不自动调整预期、指引或其他指标。</p>
    <div className="flex flex-wrap gap-2 items-end">
      <label className="text-sm flex-1 min-w-48">公告摘录<select aria-label="修订依据摘录" className={`${control} block w-full`} disabled={disabled} value={sourceId} onChange={e=>{clear();setSourceId(e.target.value);setValue('');setAmountUnit('亿元')}}><option value="">请选择</option>{sources.map((s,index)=><option key={s.id} value={s.id}>来源 {index+1} · {workbook.metrics.find(m=>m.id===s.excerpt?.metricId)?.label} · {s.label} · {s.excerpt?.contentOrigin==='pdf-text'?`PDF 第 ${s.excerpt.pdfPage} 页`:`转录第 ${s.excerpt?.segment} 段`}</option>)}</select></label>
      <label className="text-sm">拟修订数值（{amountMode?amountUnit:metric?.unit||'先选指标'}）<input aria-label="修订后实际值" className={`${control} block w-44`} inputMode="decimal" maxLength={100} disabled={disabled} value={value} onChange={e=>{clear();setValue(e.target.value)}} /></label>
      {amountMode&&<label className="text-sm">输入单位<select aria-label="修订输入单位" className={`${control} block`} disabled={disabled} value={amountUnit} onChange={e=>{clear();setAmountUnit(e.target.value as FilingAmountInput['unit'])}}>{['元','万元','亿元'].map(unit=><option key={unit}>{unit}</option>)}</select></label>}
    </div>
    {amountMode&&<p aria-label="修订金额换算" className="text-sm text-muted-foreground">{converted!==null?`${value.trim()} ${amountUnit} = ${converted} 亿元（CNY）；此处仅预览换算，采用需下方确认。`:conversionError||'可按公告表头单位填写人民币金额；不自动判断单位、币种或本期/上期列。'}</p>}
    {source&&<div aria-label="修订依据原文对照" className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <button className={control} disabled={disabled||readingBusy||Boolean(candidate)||!target} onClick={()=>onReadSource(source)}>{readingBusy?'正在回读…':'回读所选修订依据'}</button>
        <span>当前实际值 {metric?.reported??'缺失'} {metric?.unit} · {workbook.security.currency} · {workbook.fiscalPeriod.periodEnd||'期末未确认'} · {workbook.fiscalPeriod.basis?EARNINGS_BASIS[workbook.fiscalPeriod.basis]:'口径未确认'}</span>
        {candidate&&<span className="text-muted-foreground">重新回读前请取消当前修订对照。</span>}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <h3 className="font-medium">已保存摘录</h3>
          <blockquote aria-label="已保存修订摘录" className="max-h-64 overflow-y-auto border-l-2 border-border pl-3 whitespace-pre-wrap break-words leading-6">{source.excerpt?.text}</blockquote>
          <p className="text-muted-foreground">采集 {source.retrievedAt||'时间未提供'} · {sourceUrl&&<a className="text-primary" href={sourceUrl} target="_blank" rel="noreferrer">查看所选来源</a>}</p>
        </div>
        <div className="min-w-0 space-y-2">
          <h3 className="font-medium">当前回读原文</h3>
          {check&&reading?<>
            <blockquote aria-label="当前修订依据原文" className="max-h-64 overflow-y-auto border-l-2 border-primary pl-3 whitespace-pre-wrap break-words leading-6">{passage?<>{passage.prefix}<mark className="bg-primary/15 text-foreground">{passage.quote}</mark>{passage.suffix}</>:reading.text||'当前页未提取到文字。'}</blockquote>
            <p className="text-muted-foreground">采集 {reading.retrievedAt} · {readingUrl&&<a className="text-primary" href={readingUrl} target="_blank" rel="noreferrer">查看当前回读来源</a>}</p>
            <p className="text-muted-foreground">{passage?'显示首次文字匹配及附近上下文，空白已合并；高亮不是表格单元格定位。':'未定位到旧摘录，显示当前页/分段文字，请检查差异。'}请核对原页表头、单位与本期/上期列。</p>
          </>:<p role="status" className="text-muted-foreground">{readingBusy?'正在读取公告，旧摘录和底稿数值保持不变。':sourceFailure?`回读失败：${sourceFailure.message}。可点击上方回读按钮重试，或打开所选来源人工核对。`:'尚未回读所选来源；其他公告或页码的文字不会用于此处对照。'}</p>}
        </div>
      </div>
    </div>}
    <textarea aria-label="修订理由" className={`${control} w-full`} maxLength={2000} disabled={disabled} value={reason} onChange={e=>{clear();setReason(e.target.value)}} placeholder="说明改动项目、原因及公告依据；不要只写标题。" />
    {readingIssue&&<p role="status" className="text-sm text-warning">{readingIssue}</p>}
    {metric?.reported===null&&<p className="text-sm text-muted-foreground">本项原值缺失，不是零。补录后按当前底稿的期末、口径与币种记录；请核对公告是否适用，不据此计算原值增减。</p>}
    <button className={control} disabled={disabled||readingBusy||!source||Boolean(readingIssue)} onClick={preview}>{metric?.reported===null?'生成补录对照':'生成修订对照'}</button>
    {error&&<p role="status" className="text-sm">{error}</p>}
    {candidate&&<div className="space-y-3">
      <table aria-label="修订候选值" className="w-full text-left text-sm"><thead><tr><th>指标 / 单位</th><th>当前底稿</th><th>拟采用</th><th>差额（非预期差）</th></tr></thead><tbody><tr><td>{candidate.label} · {candidate.unit}</td><td>{candidate.before??'缺失（待补录）'}</td><td>{candidate.after}</td><td>{candidate.before===null?'不适用（原值缺失）':Number((candidate.after-candidate.before).toPrecision(12))}</td></tr></tbody></table>
      <p className="text-sm">{candidate.periodEnd} · {EARNINGS_BASIS[candidate.basis]} · 来源：{candidate.sourceLabel} · 尚未采用</p>
      {candidate.amountInput&&<p className="text-sm">输入留痕：{candidate.amountInput.value} {candidate.amountInput.unit} = {candidate.after} {candidate.unit} · {candidate.amountInput.currency}；输入及单位由用户确认。</p>}
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />我已核对摘录支持该修订值，且适用指标、单位、币种与报告期一致；这不是全文审计。</label>
      <button className={control} disabled={disabled||readingBusy||!confirmed||Boolean(readingIssue)} onClick={()=>{onApply();setConfirmed(false)}}>{candidate.before===null?'确认采用本项补录':'确认采用本项修订'}</button>
      <button className={`${control} ml-2`} disabled={disabled} onClick={clear}>取消修订对照</button>
    </div>}
    {workbook.sourceMaterials.filter(s=>s.correction).map(s=><details key={s.id} className="border-t border-border pt-2 text-sm"><summary>人工采用记录 · {workbook.metrics.find(m=>m.id===s.excerpt?.metricId)?.label} · {s.correction!.before??'缺失（补录）'} → {s.correction!.after} {s.excerpt?.unit}</summary><p className="mt-2">{s.correction!.reason} · 采用时间 {s.correction!.adoptedAt}</p><p>{s.label} · 公告日期 {s.asOf||'未提供'} · 原数值来源 {s.correction!.previousSourceIds.map(id=>workbook.sourceMaterials.find(item=>item.id===id)?.label||id).join('；')||'人工录入或来源未提供'}</p>{s.correction!.amountInput&&<p className="mt-2">输入留痕：{s.correction!.amountInput.value} {s.correction!.amountInput.unit} = {s.correction!.after} {s.excerpt?.unit} · {s.correction!.amountInput.currency}（用户填写，非自动提取）</p>}<blockquote className="mt-2 border-l-2 border-primary pl-3">{s.excerpt?.text}</blockquote><p className="text-muted-foreground">这是历史采用记录，不表示当前指标仍采用该值，也不表示公告已独立核验。</p></details>)}
  </section>;
}
