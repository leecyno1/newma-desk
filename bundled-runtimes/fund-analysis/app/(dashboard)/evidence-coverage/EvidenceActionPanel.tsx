'use client'

import { useMemo, useRef, useState } from 'react'
import { useFundPageData } from '@/lib/newma-desk/page-data'
import { isValidWindCode, validateSalesRule } from '@/lib/sales-rule-validation'

export type EvidenceAction = { kind: 'material'; code: string } | { kind: 'event'; id: string; title: string; status: string }
const labels: Record<string, string> = { open: '待处理', acknowledged: '已知悉', resolved: '已解决' }
const numericFields = [
  ['purchaseFeeRate', '申购费率（%）'], ['salesServiceFeeRate', '销售服务费（%）'],
  ['minPurchaseAmount', '最低申购金额（元）'], ['minSipAmount', '定投起点（元）'], ['dailyLimitAmount', '每日限购（元）'],
] as const
const fieldClass = 'w-full border border-[var(--vibe-border)] bg-[var(--vibe-bg)] px-3 py-2'

export default function EvidenceActionPanel({ action, onCancel, onSaved }: {
  action: EvidenceAction; onCancel: () => void; onSaved: (message: string) => void
}) {
  const [draft, setDraft] = useState<Record<string, string>>({ windCode: action.kind === 'material' ? action.code : '', platform: '', sourceUrl: '', sourceUpdatedAt: '', notes: '', purchaseStatus: 'unknown', riskLevel: '', supportsSip: '' })
  const [nextStatus, setNextStatus] = useState(action.kind === 'event' && action.status === 'open' ? 'acknowledged' : 'resolved')
  const [confirmed, setConfirmed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = useRef(false)
  const [preview, setPreview] = useState(false)
  const material = useMemo(() => {
    const value: Record<string, unknown> = {
      windCode: draft.windCode.trim().toUpperCase(), platform: draft.platform.trim(),
      sourceUrl: draft.sourceUrl.trim(), sourceUpdatedAt: draft.sourceUpdatedAt,
      notes: draft.notes.trim(), purchaseStatus: draft.purchaseStatus,
      purchaseStatusLabel: ({ open: '开放申购', closed: '暂停申购', limited: '限额申购', unknown: '申购待核' })[draft.purchaseStatus],
    }
    for (const [key] of numericFields) if (draft[key]?.trim()) value[key] = Number(draft[key])
    if (draft.riskLevel) value.riskLevel = draft.riskLevel
    if (draft.supportsSip) value.supportsSip = draft.supportsSip === 'true'
    return value
  }, [draft])
  const errors = useMemo(() => action.kind !== 'material' ? [] : [
    ...(!isValidWindCode(material.windCode) ? ['请填写完整基金代码，如 000001.OF'] : []),
    ...(!material.platform ? ['请填写实际销售平台或机构'] : []),
    ...validateSalesRule(material),
  ], [action.kind, material])
  useFundPageData(useMemo(() => ({ title: action.kind === 'material' ? '新增来源证据草稿' : '复查处置确认', selection: null,
    filters: {}, visibleBlocks: [{ id: 'evidence-action', type: 'form', title: '待人工确认的变更' }],
    summary: { status: saving ? 'saving' : error ? 'error' : preview ? 'preview' : 'draft', action,
      proposed: action.kind === 'material' ? material : { id: action.id, status: nextStatus }, confirmed, error,
      boundary: '这是未提交草稿或在途操作，不是已保存证据；只有服务端确认成功后才刷新列表。标记已解决不代表投资风险消失，也不自动恢复历史报告有效性。' },
  }), [action, saving, error, preview, material, nextStatus, confirmed]), 'evidence-action')
  function change(key: string, value: string) {
    setDraft(current => ({ ...current, [key]: value })); setPreview(false); setConfirmed(false); setError(null)
  }
  async function save() {
    if (busy.current || !confirmed || (action.kind === 'material' && (!preview || errors.length))) return
    busy.current = true; setSaving(true); setError(null)
    try {
      const response = await fetch(action.kind === 'material' ? '/api/evidence-coverage/materials' : `/api/evidence-coverage/review-events/events/${encodeURIComponent(action.id)}`, {
        method: action.kind === 'material' ? 'POST' : 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(action.kind === 'material' ? { createOnly: true, rules: [material] } : { status: nextStatus }),
      })
      const result = await response.json()
      if (!response.ok || (action.kind === 'material' && (result.savedCount !== 1 || result.failedCount !== 0))) {
        throw new Error(result.failed?.map((item: { error: string }) => item.error).join('；') || result.error || '服务未确认保存成功，请刷新核对后再操作')
      }
      if (action.kind === 'event' && (result.id !== action.id || result.status !== nextStatus)) throw new Error('返回的事件状态不匹配，请刷新核对')
      onSaved(action.kind === 'material' ? `${material.windCode} 的来源证据已新增；需重新读取报告或复核，不能直接视为全部证据通过。` : `${action.title} 已标记为${labels[nextStatus]}；此状态不代表风险消失。`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '未收到保存确认，请刷新核对，不能假定未写入')
    } finally { busy.current = false; setSaving(false) }
  }
  return <section aria-label="证据处置" className="border border-[var(--vibe-border-strong)] bg-[var(--vibe-surface)] p-4">
    <div className="mb-3 flex items-center justify-between gap-4"><h2 className="font-semibold">{action.kind === 'material' ? '新增来源证据' : `处置：${action.title}`}</h2><button disabled={saving} onClick={onCancel}>取消</button></div>
    <fieldset disabled={saving} className="space-y-4">
      {action.kind === 'material' ? <>
        <p className="text-[var(--vibe-text-soft)]">只新增，不覆盖同基金、同平台已有记录。空白不作为零；来源日期遵循现有 30 天核验规则。暂不编辑已有材料及赎回分档。</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {([['windCode', '补证基金代码'], ['platform', '证据平台或机构'], ['sourceUrl', '来源链接'], ['sourceUpdatedAt', '来源核验日期']] as const).map(([key, label]) => <label key={key} className="space-y-1">{label}<input className={fieldClass} aria-label={label} type={key === 'sourceUpdatedAt' ? 'date' : 'text'} value={draft[key]} onChange={event => change(key, event.target.value)} /></label>)}
          <label>申购状态<select className={fieldClass} value={draft.purchaseStatus} onChange={event => change('purchaseStatus', event.target.value)}><option value="unknown">未核验</option><option value="open">开放申购</option><option value="closed">暂停申购</option><option value="limited">限额申购</option></select></label>
          <label>销售风险等级<select className={fieldClass} value={draft.riskLevel} onChange={event => change('riskLevel', event.target.value)}><option value="">未核验</option>{['R1','R2','R3','R4','R5'].map(value => <option key={value}>{value}</option>)}</select></label>
          {numericFields.map(([key, label]) => <label key={key}>{label}<input className={fieldClass} aria-label={label} inputMode="decimal" value={draft[key] || ''} onChange={event => change(key, event.target.value)} /></label>)}
          <label>支持定投<select className={fieldClass} value={draft.supportsSip} onChange={event => change('supportsSip', event.target.value)}><option value="">未核验</option><option value="true">是</option><option value="false">否</option></select></label>
        </div>
        <label className="block">来源说明<textarea aria-label="来源说明" className={fieldClass} value={draft.notes} onChange={event => change('notes', event.target.value)} placeholder="说明销售平台、招募说明书及适用条件，不填写占位内容" /></label>
        <button className="border border-[var(--vibe-border)] px-4 py-2" onClick={() => { setPreview(true); setError(null) }}>检查并预览</button>
        {preview && errors.length ? <ul role="alert" className="list-inside list-disc text-[var(--vibe-gold)]">{errors.map(message => <li key={message}>{message}</li>)}</ul> : null}
        {preview && !errors.length ? <p>将新增 {String(material.windCode)} / {String(material.platform)}，核验日期 {String(material.sourceUpdatedAt)}。申购费 {draft.purchaseFeeRate ? `${draft.purchaseFeeRate}%` : '未填'}，服务费 {draft.salesServiceFeeRate ? `${draft.salesServiceFeeRate}%` : '未填'}，风险等级 {draft.riskLevel || '未填'}；未填项不补零，也不覆盖其他来源。</p> : null}
      </> : <>
        <p>当前状态：{labels[action.status] || action.status}。仅改变跟进状态，不更改原始事件与风险证据。</p>
        <label>更新状态<select aria-label="更新状态" className={fieldClass} value={nextStatus} onChange={event => { setNextStatus(event.target.value); setConfirmed(false); setError(null) }}>{Object.entries(labels).filter(([value]) => value !== 'open').map(([value, label]) => <option key={value} value={value} disabled={value === action.status}>{label}</option>)}</select></label>
        <p className="text-[var(--vibe-gold)]">标记已解决需自行完成证据复核，不等于风险消失。本轮不提供已解决事件重新打开，也不生成审批审计记录。</p>
      </>}
      <label className="flex items-center gap-2"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />我已核对对象、来源和本次变更，确认提交</label>
      {error ? <p role="alert">{error}</p> : null}
      <button className="border border-[var(--vibe-accent)] px-4 py-2 disabled:opacity-40" disabled={!confirmed || (action.kind === 'material' && (!preview || errors.length > 0))} onClick={() => void save()}>{saving ? '提交中…' : '确认提交'}</button>
    </fieldset>
  </section>
}
