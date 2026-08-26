'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Scale, XCircle } from 'lucide-react'

type ForcedChoice = {
  pick: string
  pick_score: number
  pick_metrics: Record<string, number | null>
  reason: string
  rejected: Array<{ wind_code: string; score: number; reason: string }>
  note: string
}

type CounterEvidence = {
  wind_code: string
  better_peers: Array<{ wind_code: string; sharpe: number | null; name: string }>
  concentration_risk: { top_ten_weight: number; note: string } | null
  attribution_concern: { residual: number; note: string } | null
  style_drift: { latest: string; previous: string; note: string } | null
}

export default function DecisionSupportPanel({
  codes,
  nameByCode,
}: {
  codes: string[]
  nameByCode: Map<string, string>
}) {
  const [choice, setChoice] = useState<ForcedChoice | null>(null)
  const [counters, setCounters] = useState<Record<string, CounterEvidence>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (codes.length < 2) return
    let cancelled = false
    setLoading(true)
    setError('')

    async function run() {
      try {
        const choiceRes = await fetch('/api/decision-support/forced-choice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ codes }),
        })
        if (choiceRes.ok) {
          const data = (await choiceRes.json()) as ForcedChoice
          if (!cancelled) setChoice(data)
        }
        const counterResults: Record<string, CounterEvidence> = {}
        await Promise.all(
          codes.map(async (code) => {
            const res = await fetch(`/api/decision-support/counter-evidence/${encodeURIComponent(code)}`)
            if (res.ok) counterResults[code] = (await res.json()) as CounterEvidence
          }),
        )
        if (!cancelled) setCounters(counterResults)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载决策支持失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [codes.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  if (codes.length < 2) return null

  return (
    <section data-testid="decision-support" className="overflow-hidden border border-[#dbe1dc] bg-white">
      <header className="flex items-center gap-2 border-b border-[#e6ebe6] px-5 py-3">
        <Scale className="h-4 w-4 text-[#4a7c64]" />
        <h2 className="text-sm font-bold text-[#1f2d26]">决策支持</h2>
        <span className="text-[11px] text-[#748079]">规则化辅助 · 非投资建议</span>
        {loading ? <span className="ml-auto text-[11px] text-[#748079]">计算中…</span> : null}
      </header>

      {error ? <div className="px-5 py-3 text-xs text-[#8f2f21]">{error}</div> : null}

      {choice ? (
        <div className="grid gap-px bg-[#eaedea] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          {/* 三选一结论 */}
          <div className="bg-white p-4">
            <div className="text-[11px] font-bold text-[#28745c]">若只能选一只</div>
            <div className="mt-2 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-[#1f5d3f]" />
              <span className="text-sm font-bold text-[#1f2d26]">{nameByCode.get(choice.pick) || choice.pick}</span>
            </div>
            <div className="mt-1 text-[11px] text-[#748079]">{choice.reason} · 得分 {choice.pick_score}</div>
            <div className="mt-3 space-y-2">
              {choice.rejected.map((r) => (
                <div key={r.wind_code} className="flex items-start gap-2">
                  <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#a8544c]" />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-[#4a5a52]">{nameByCode.get(r.wind_code) || r.wind_code}</div>
                    <div className="text-[11px] text-[#8b978f]">弃选：{r.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 各基金反向证据 */}
          <div className="bg-white p-4">
            <div className="text-[11px] font-bold text-[#8a6b31]">反向证据（每只的看空理由）</div>
            <div className="mt-2 space-y-3">
              {codes.map((code) => {
                const counter = counters[code]
                if (!counter) return null
                const flags: string[] = []
                if (counter.better_peers.length) {
                  flags.push(`同类有 ${counter.better_peers.length} 只风险调整收益更优（如 ${counter.better_peers[0].name || counter.better_peers[0].wind_code}）`)
                }
                if (counter.concentration_risk) flags.push(counter.concentration_risk.note)
                if (counter.attribution_concern) flags.push(counter.attribution_concern.note)
                if (counter.style_drift) flags.push(counter.style_drift.note)
                return (
                  <div key={code} className="border-l-2 border-[#e4c78e] pl-2">
                    <div className="truncate text-xs font-medium text-[#1f2d26]">{nameByCode.get(code) || code}</div>
                    {flags.length === 0 ? (
                      <div className="text-[11px] text-[#748079]">暂无显著反向证据</div>
                    ) : (
                      <ul className="mt-1 space-y-0.5">
                        {flags.map((f, i) => (
                          <li key={i} className="flex items-start gap-1 text-[11px] text-[#7c5a1a]">
                            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{f}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : null}

      {choice ? <footer className="border-t border-[#eaedea] px-5 py-2 text-[10px] text-[#8b978f]">{choice.note}</footer> : null}
    </section>
  )
}
