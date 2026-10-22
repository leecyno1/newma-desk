import { useEffect, useRef, useState } from 'react';
import type { ValuationModel } from '@/lib/valuationWorkbench';
import { activeCapitalFields, CAPITAL_LABELS, capitalEvidenceIssue, capitalDraftIssue, type CapitalEvidenceInput, type CapitalField } from '@/lib/valuationReview';
import { capitalReferences, capitalNoteReferences, loadSavedEarningsInputs } from '@/lib/valuationInputs';
import { ValuationCapitalNotes } from './ValuationCapitalNotes';
import { ValuationCapitalLines } from './ValuationCapitalLines';
import {supportsCapitalLines, summarizeCapitalLines, type CapitalLineItem} from '@/lib/valuationCapitalLines';

const control = 'rounded border border-border bg-card px-3 py-2 text-sm disabled:opacity-50';
const GUIDANCE: Record<CapitalField, string> = {
  dilutedSharesM: '采用估值时点的稀释后股数，并说明期权、可转债等调整。期末股本、EPS 加权平均股数、市值÷股价不能未经核对直接代替。单位：百万股。',
  totalDebtM: '总债务指有息债务，不是负债合计。列明借款、债券、一年内到期债务及租赁负债的纳入情况，避免遗漏或重复。零债务也需依据。单位：百万元。',
  cashM: '说明现金及等价物与受限、客户或其他不可归属普通股股东资金的调整，不能直接采用全部货币资金或经营现金流。单位：百万元。',
  excludedCashM: '只扣除已包含在上述原始余额中、且不能用于股权桥接的资金。说明受限资金、经营必需现金和客户资金的范围，客户存款不能机械等额相减；与债务、其他权益扣减不得重计。单位：百万元。',
  nonOperatingAssetsM: '仅加回未纳入预测经营现金流、未含在现金中的非经营性资产价值，如另行估值的投资。说明估值方法、税费和归属范围；不直接用全部账面投资。无适用项也须说明。单位：百万元。',
  minorityInterestM: '只有预测包含子公司全部经营现金流时才扣除对应少数股东权益价值，范围须与 EV 一致；不能直接把账面少数股东权益当公允价值。预测已剔除少数部分则勿重复扣减。单位：百万元。',
  otherClaimsM: '列明未计入有息债务、现金剔除或稀释股数的优先股、类债务等其他索偿价值，避免可转债同时扣价值又稀释股数。无适用项须以零和依据确认。单位：百万元。',
};

function EvidenceEditor({ model, field, disabled, onAttach, onSaveDraft, onDiscardDraft, onClose, onDirtyChange, onEditSnapshot, requestDiscard }: {
  model: ValuationModel; field: CapitalField; disabled: boolean;
  onAttach: (field: CapitalField, input: CapitalEvidenceInput) => void; onClose: () => void;
  onSaveDraft: (field: CapitalField, input: CapitalEvidenceInput) => Promise<boolean>;
  onDiscardDraft: (field: CapitalField) => Promise<boolean>;
  onDirtyChange: (dirty: boolean) => void;
  onEditSnapshot?: (snapshot: unknown) => void;
  requestDiscard: (run: () => void) => void;
}) {
  const existing = model.capitalEvidence[field];
  const pending = model.capitalEvidenceDrafts?.[field];
  const initial = pending?.input;
  const initialLines = pending ? initial?.lineItems : existing?.lineItems;
  const source = model.sourceMaterials.find(row => row.id === existing?.sourceId);
  const [input, setInput] = useState<CapitalEvidenceInput>({ title: initial?.title ?? source?.label ?? '', url: initial?.url ?? source?.url ?? '',
    locator: initial?.locator ?? existing?.locator ?? '', excerpt: initial?.excerpt ?? existing?.excerpt ?? '', method: initial?.method ?? existing?.method ?? '' });
  const [confirmed, setConfirmed] = useState(false);
  const [usingLines,setUsingLines] = useState(initialLines !== undefined);
  const [lines,setLines] = useState<CapitalLineItem[]>(initialLines?.map(row=>({...row})) || []);
  const editSnapshot = JSON.stringify({input,usingLines,lines});
  const originalEdit = useRef(editSnapshot);
  const dirty = editSnapshot !== originalEdit.current;
  useEffect(() => { onDirtyChange(dirty); }, [dirty,onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  useEffect(() => { onEditSnapshot?.({ field, input: { ...input, ...(usingLines ? { lineItems: lines } : {}) }, dirty }); }, [field, input, usingLines, lines, dirty, onEditSnapshot]);
  useEffect(() => () => onEditSnapshot?.(null), [onEditSnapshot]);
  const scope = JSON.stringify([model.security.market,model.security.symbol,model.security.currency,model.asOf,model.capitalInputs.cashBasis]);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const originalScope = useRef(scope);
  const active = activeCapitalFields(model).includes(field);
  const lineSummary = summarizeCapitalLines(lines,field,model.capitalInputs.cashBasis);
  const [references, setReferences] = useState<ReturnType<typeof capitalReferences>>([]);
  const [notes, setNotes] = useState<ReturnType<typeof capitalNoteReferences>>([]);
  const [reading, setReading] = useState(false);
  const readingController = useRef<AbortController | null>(null);
  useEffect(() => () => readingController.current?.abort(), []);
  const [status, setStatus] = useState('');
  const [discardRequested,setDiscardRequested] = useState(false);
  const canReadReferences = ['dilutedSharesM','totalDebtM','cashM','excludedCashM'].includes(field);
  useEffect(() => { setConfirmed(false); }, [model.capitalInputs[field], field,scope]);
  useEffect(() => { setReferences([]);setNotes([]);setStatus(''); }, [scope]);
  const change = (key: Exclude<keyof CapitalEvidenceInput,'lineItems'>, value: string) => { setInput({ ...input, [key]: value }); setConfirmed(false); };
  return <fieldset disabled={disabled} aria-label="资本来源编辑" role="group" className="mt-3 min-w-0 space-y-3 border-t border-border pt-3">
    {pending&&<p className="text-warning" role="status">已恢复未核验编辑 · {pending.savedAt}。未采用，不影响当前数值与原确认。{capitalDraftIssue(model,field)}</p>}
    {dirty&&<p role="status" className="text-warning">当前资本编辑尚未暂存。顶部保存不包含此处输入，请先暂存或确认采用。</p>}
    {scope!==originalScope.current&&<p className="text-warning">证券、基期或现金口径已变化，编辑内容保留；请重新核对原文适用范围，不会自动换算。</p>}
    {!active&&<p className="text-warning">当前现金口径不使用此项，不能确认采用；可暂存保留，切回原始余额口径后继续核验。</p>}
    <p>{CAPITAL_LABELS[field]}：{model.capitalInputs[field] ?? '未填写'} {field === 'dilutedSharesM' ? '百万股' : '百万元'} · {model.security.symbol} · {model.security.currency} · 基期 {model.asOf}</p>
    <p className="text-muted-foreground">{GUIDANCE[field]}{field === 'cashM' && ` 当前采用${model.capitalInputs.cashBasis === 'gross' ? '原始余额，另扣需剔除现金' : '已调整净额，不再扣一次受限资金'}。`}</p>
    {supportsCapitalLines(field)&&<>
      <label className="flex gap-2"><input type="checkbox" checked={usingLines} disabled={disabled} onChange={e=>{setUsingLines(e.target.checked);setConfirmed(false)}}/>使用明细合计替代手录数值</label>
      {usingLines&&<ValuationCapitalLines items={lines} field={field} cashBasis={model.capitalInputs.cashBasis} current={model.capitalInputs[field]} disabled={disabled} onChange={rows=>{setLines(rows);setConfirmed(false)}}/>}
      {!usingLines&&existing?.lineItems&&<p className="text-warning">本次若以手录方式确认，将解除原明细关联；取消编辑则保留原明细。</p>}
    </>}
    <div className="space-y-2">
      {canReadReferences ? <button className={control} disabled={disabled || reading} onClick={async () => {
        readingController.current?.abort();
        const controller = new AbortController(); readingController.current = controller;
        setReading(true); setReferences([]); setNotes([]);
        try {
          const workbooks = await loadSavedEarningsInputs(controller.signal);
          if(scopeRef.current!==scope)return;
          const rows = capitalReferences(workbooks,model,field), passages = capitalNoteReferences(workbooks,model,field);
          setReferences(rows); setNotes(passages);
          setStatus(rows.length || passages.length ? `找到 ${rows.length} 项同证券、同币种、同基期的已保存事实及 ${passages.length} 段附注；仅引用原文，不改数值和确认状态。`
            : '没有匹配事实。请先在财报研究“补充资本项目”或“定位资本附注”并保存；本处不采用其他期间或未经核对的数据。');
        } catch(error) { if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : '读取失败'); }
        finally { if (!controller.signal.aborted) setReading(false); }
      }}>{reading ? '读取中…' : '读取已保存财报资本参考'}</button> : <p className="text-muted-foreground">此项尚无自动提取，请填写附注或独立估值依据，不能直接照搬账面金额。</p>}
      {status && <p role="status" className="text-muted-foreground">{status}</p>}
      {references.map(({workbookId,savedAt,metric,source}) => <div key={`${workbookId}:${metric.id}`} className="border-l-2 border-border pl-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><span>{metric.label}：{metric.reported?.toLocaleString('zh-CN',{maximumFractionDigits:6})} {metric.unit} · PDF 第 {source.excerpt?.pdfPage} 页</span>
          <button className={control} disabled={disabled || reading} onClick={() => {
            const citation = `财报底稿 ${workbookId} · 保存 ${savedAt} · ${source.importedReport!.columnHeader}\n${source.excerpt!.text}\n换算：${metric.reported} ${metric.unit}`;
            if(input.excerpt.includes(citation))return;
            const excerpt = [input.excerpt,citation].filter(Boolean).join('\n\n');
            const locator = [input.locator,`PDF 第 ${source.excerpt?.pdfPage} 页`].filter(Boolean).join('；');
            if(excerpt.length>3000 || locator.length>240){setStatus('原文栏已达长度上限，请先整理再引用');return;}
            setInput({...input,title:input.title || source.label,url:input.url || source.url || '',locator,excerpt});setConfirmed(false);
          }}>引用{metric.label}原文</button>
        </div><p className="mt-1 text-xs text-muted-foreground">底稿 {workbookId} · 保存 {savedAt} · 原始项目，不是最终估值输入</p>
      </div>)}
      <ValuationCapitalNotes references={notes} disabled={disabled||reading} input={input} onChange={value=>{setInput(value);setConfirmed(false)}}/>
    </div>
    <div className="grid gap-3 md:grid-cols-2">
      <label>来源标题<input aria-label="资本来源标题" maxLength={240} className={`${control} mt-1 w-full`} value={input.title} onChange={e => change('title', e.target.value)} /></label>
      <label>页码或附注<input aria-label="资本来源页码或附注" maxLength={240} className={`${control} mt-1 w-full`} value={input.locator} onChange={e => change('locator', e.target.value)} placeholder="例如：PDF 第 98 页，附注 26" /></label>
      <label className="md:col-span-2">来源链接（可选）<input aria-label="资本来源链接" maxLength={2000} className={`${control} mt-1 w-full`} value={input.url} onChange={e => change('url', e.target.value)} placeholder="原始公告或已上传 PDF 的链接" /></label>
      <label>原文摘录<textarea aria-label="资本来源原文摘录" maxLength={3000} className={`${control} mt-1 min-h-24 w-full`} value={input.excerpt} onChange={e => change('excerpt', e.target.value)} /></label>
      <label>计算与口径说明<textarea aria-label="资本计算与口径说明" maxLength={2000} className={`${control} mt-1 min-h-24 w-full`} value={input.method} onChange={e => change('method', e.target.value)} placeholder="列明原始数值、单位换算、纳入及剔除项目；零值也须说明依据" /></label>
    </div>
    <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} disabled={disabled||!active} onChange={e => setConfirmed(e.target.checked)} />{usingLines?'已核对明细、来源与不重复计量，同意用合计替换当前数值':'已核对当前数值、证券、基期、单位和上述口径'}</label>
    <div className="flex flex-wrap gap-2"><button className={control} disabled={disabled || !active || !confirmed || (usingLines&&lineSummary.total===null) || ![input.title, input.locator, input.excerpt, input.method].every(v => v.trim())} onClick={() => onAttach(field, {...input,...(usingLines?{lineItems:lines}:{})})}>{usingLines?'确认采用明细及依据':'确认关联资本依据'}</button>
      <button className={control} disabled={disabled} onClick={async()=>{
        try {if(await onSaveDraft(field,{...input,...(usingLines?{lineItems:lines}:{})}))onClose();else setStatus('尚未完成暂存，请查看页面保存提示；编辑内容仍保留。')}
        catch {setStatus('暂存失败，编辑内容仍保留，请重试。')}
      }}>暂存未核验编辑</button>
      {pending&&<button className={control} disabled={disabled} onClick={()=>setDiscardRequested(true)}>放弃已暂存编辑</button>}
      <button className={control} disabled={disabled} onClick={()=>dirty?requestDiscard(onClose):onClose()}>取消</button>
    </div>
    {pending&&discardRequested&&<div role="group" aria-label="放弃暂存确认" className="flex flex-wrap items-center gap-2 text-warning">
      <span>放弃此项暂存和当前编辑？已采用数值与原确认不变。</span>
      <button className={control} disabled={disabled} onClick={async()=>{
        try {if(await onDiscardDraft(field))onClose();else setStatus('尚未完成保存，请查看页面提示。')}
        catch {setStatus('放弃操作未能保存，请重试。')}
      }}>确认放弃暂存</button><button className={control} disabled={disabled} onClick={()=>setDiscardRequested(false)}>保留暂存</button>
    </div>}
    <p className="text-xs text-muted-foreground">暂存会保存当前模型及未核验编辑，但不会采用明细或改变资本确认；不完整内容也可暂存。刷新或离开本模块前请主动暂存，存储位置以页面保存提示为准。</p>
  </fieldset>;
}

export function ValuationCapitalEvidence({ model, disabled, onAttach, onSaveDraft, onDiscardDraft, onRevoke, editorDirty, onDirtyChange, onEditSnapshot, requestDiscard }: {
  model: ValuationModel; disabled: boolean;
  onAttach: (field: CapitalField, input: CapitalEvidenceInput) => boolean;
  onSaveDraft: (field: CapitalField, input: CapitalEvidenceInput) => Promise<boolean>;
  onDiscardDraft: (field: CapitalField) => Promise<boolean>;
  onRevoke: (field: CapitalField) => void;
  editorDirty: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onEditSnapshot?: (snapshot: unknown) => void;
  requestDiscard: (run: () => void) => void;
}) {
  const [editing, setEditing] = useState<CapitalField | null>(null);
  return <section aria-label="资本来源核验" className="mt-4 border-t border-border pt-4 text-sm">
    <h3 className="font-semibold">资本来源核验</h3>
    <p className="my-2 text-muted-foreground">记录人工核对依据，不自动读取链接或验证原文真假。适用资本项目、股权调整及情景假设均确认后，才输出每股试算；不适用项也需以零和依据确认，缺失不默认零。</p>
    <div className="divide-y divide-border">{activeCapitalFields(model).map(field => {
      const evidence = model.capitalEvidence[field];
      const issue = capitalEvidenceIssue(model, field);
      const source = model.sourceMaterials.find(row => row.id === evidence?.sourceId);
      return <div key={field} className="flex flex-wrap items-center justify-between gap-2 py-2">
        <div><span className="font-medium">{CAPITAL_LABELS[field]}</span><span className={`ml-3 ${issue ? 'text-warning' : 'text-success'}`}>{issue || '人工已确认'}</span>
          {source && <p className="mt-1 text-xs text-muted-foreground">{source.label} · {evidence?.locator} · {evidence?.confirmedAt}</p>}
          {model.capitalEvidenceDrafts?.[field]&&<p className="mt-1 text-warning">另有未核验编辑，尚未采用 · {model.capitalEvidenceDrafts[field]!.savedAt}</p>}</div>
        <div className="flex gap-2"><button className={control} disabled={disabled} onClick={() => {
          if(field===editing)return;
          if(editorDirty)requestDiscard(()=>setEditing(field));else setEditing(field);
        }}>核验{CAPITAL_LABELS[field]}</button>
          {evidence && <button className={control} disabled={disabled} onClick={() => onRevoke(field)}>撤销{CAPITAL_LABELS[field]}确认</button>}</div>
        {evidence && <details className="w-full"><summary className="cursor-pointer text-muted-foreground">查看已记录依据</summary>
          {evidence.lineItems&&<ValuationCapitalLines items={evidence.lineItems} field={field} cashBasis={model.capitalInputs.cashBasis} current={model.capitalInputs[field]} disabled={disabled}/>}
          <p className="mt-2 whitespace-pre-wrap">{evidence.excerpt}</p><p className="mt-2 whitespace-pre-wrap">{evidence.method}</p>
          {source?.url && /^https?:\/\//i.test(source.url) && <a className="text-primary underline" href={source.url} target="_blank" rel="noreferrer">查看来源</a>}
        </details>}
      </div>;
    })}</div>
    {editing && <EvidenceEditor key={`${model.id}:${editing}`} onDirtyChange={onDirtyChange} onEditSnapshot={onEditSnapshot} requestDiscard={requestDiscard}
      model={model} field={editing} disabled={disabled} onSaveDraft={onSaveDraft} onDiscardDraft={onDiscardDraft} onClose={() => setEditing(null)} onAttach={(field, input) => { if (onAttach(field, input)) setEditing(null); }} />}
  </section>;
}
