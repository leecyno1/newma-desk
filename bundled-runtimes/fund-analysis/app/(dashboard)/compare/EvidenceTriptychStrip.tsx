'use client'

import { BadgeCheck, BookOpenText, ChartNoAxesCombined } from 'lucide-react'
import type { ComparisonFund } from './SimpleComparisonClient'

/**
 * 同类比较三面证据条：把评价 / 归因 / 纪要三个决策面并排放在同一屏，
 * 让"为什么选它、不选另一个"直接看到证据来源。
 *
 * - 评价面：分类内评价的 score / grade / peer_rank + 数据质量状态
 * - 归因面：Brinson 配置/选择效应 headline + 公开持仓覆盖率残差 + Barra 就绪
 * - 纪要面：Top 3 纪要摘要（区分基金层 vs 经理层，因为经理层不能推导为该基金持仓）
 */
export default function EvidenceTriptychStrip({ funds }: { funds: ComparisonFund[] }) {
  if (funds.length < 2) return null

  return (
    <section
      data-testid="evidence-triptych"
      className="overflow-hidden border border-[#dbe1dc] bg-white"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-[#e6ebe6] bg-[#f5f8f6] px-5 py-3">
        <div>
          <h2 className="text-lg font-bold text-[#18231e]">评价 / 归因 / 纪要 · 三面证据</h2>
          <p className="mt-1 text-xs text-[#6f7c74]">
            同一屏对齐三个决策面。归因用于解释，不进入基金综合评分；经理层纪要不推导为该基金的实际持仓。
          </p>
        </div>
      </header>

      <div className="grid gap-px bg-[#eef1ee]" style={{ gridTemplateColumns: `repeat(${funds.length}, minmax(0, 1fr))` }}>
        {funds.map((fund) => (
          <FundColumn key={fund.fund.windCode} fund={fund} />
        ))}
      </div>
    </section>
  )
}

function FundColumn({ fund }: { fund: ComparisonFund }) {
  const { attributionEvidence, styleEvidence, memoHighlights } = fund
  const evaluation = fund.evaluation
  const evaluationReady = evaluation.score != null

  return (
    <div className="flex flex-col gap-4 bg-white p-4">
      <div className="border-b border-[#eaeeea] pb-2">
        <div className="text-xs text-[#7a8580]">{fund.fund.windCode}</div>
        <div className="mt-0.5 truncate text-sm font-bold text-[#18231e]">{fund.fund.name || fund.fund.windCode}</div>
      </div>

      {/* 评价面 */}
      <section>
        <div className="flex items-center gap-1.5 text-xs font-bold text-[#28624e]">
          <BadgeCheck className="h-3.5 w-3.5" /> 评价面（分类内）
        </div>
        <div className="mt-2 space-y-1 text-xs text-[#4a5a52]">
          {evaluationReady ? (
            <>
              <div>
                综合评分 <strong className="text-[#1f5d3f]">{evaluation.score?.toFixed(1)}</strong> · 等级 <strong>{evaluation.grade || '—'}</strong>
              </div>
              <div>
                同类 <strong>{fund.classification.peerGroup || '待分类'}</strong>
                {evaluation.validPeerCount ? ` · 有效样本 ${evaluation.validPeerCount}` : ''}
                {evaluation.minimumPeerCount ? ` / 门槛 ${evaluation.minimumPeerCount}` : ''}
              </div>
            </>
          ) : (
            <div className="text-[#8f2f21]">评价证据不足：{evaluation.status || 'unavailable'}</div>
          )}
        </div>
      </section>

      {/* 归因面 */}
      <section>
        <div className="flex items-center gap-1.5 text-xs font-bold text-[#8a6b31]">
          <ChartNoAxesCombined className="h-3.5 w-3.5" /> 归因面（解释性，不入综合评分）
        </div>
        <div className="mt-2 space-y-1.5 text-xs text-[#4a5a52]">
          {attributionEvidence.status === 'unavailable' && !styleEvidence.labels.length && !styleEvidence.memoLabels.length ? (
            <div className="text-[#8f2f21]">归因证据不足</div>
          ) : (
            <>
              {attributionEvidence.headline ? (
                <div className="font-semibold text-[#1f2d26]">{attributionEvidence.headline}</div>
              ) : null}
              {attributionEvidence.detail ? (
                <div className="text-[#6a7570]">{attributionEvidence.detail}</div>
              ) : null}
              {attributionEvidence.coverage != null ? (
                <div>
                  公开持仓覆盖率 <strong className={attributionEvidence.coverage < 0.6 ? 'text-[#8f2f21]' : 'text-[#1f5d3f]'}>
                    {Math.round(attributionEvidence.coverage * 100)}%
                  </strong>
                  {attributionEvidence.coverage < 0.6 ? '（残差偏大）' : ''}
                </div>
              ) : null}
              <div className="text-[10px] text-[#7a8580]">
                {attributionEvidence.formalBarraReady
                  ? '✓ 正式 Barra 就绪'
                  : attributionEvidence.barraDescriptorReady
                    ? '公开持仓风格描述子（非正式 Barra）'
                    : ''}
              </div>
              {styleEvidence.labels.length ? (
                <div className="flex flex-wrap gap-1">
                  {styleEvidence.labels.slice(0, 4).map((label) => (
                    <span key={`s-${label}`} className="bg-[#eff5f0] px-1.5 py-0.5 text-[10px] text-[#28624e]">
                      持仓风格：{label}
                    </span>
                  ))}
                </div>
              ) : null}
              {styleEvidence.memoLabels.length ? (
                <div className="flex flex-wrap gap-1">
                  {styleEvidence.memoLabels.slice(0, 3).map((label) => (
                    <span key={`m-${label}`} className="bg-[#f5edd7] px-1.5 py-0.5 text-[10px] text-[#7c5a1a]">
                      纪要风格：{label}
                    </span>
                  ))}
                </div>
              ) : null}
              {styleEvidence.quarter ? (
                <div className="text-[10px] text-[#8b978f]">证据季度：{styleEvidence.quarter}</div>
              ) : null}
            </>
          )}
        </div>
      </section>

      {/* 纪要面 */}
      <section>
        <div className="flex items-center gap-1.5 text-xs font-bold text-[#5a3a6f]">
          <BookOpenText className="h-3.5 w-3.5" /> 纪要面（{fund.researchMemoCount} 份）
        </div>
        <div className="mt-2 space-y-2 text-xs">
          {memoHighlights.length === 0 ? (
            <div className="text-[#7a8580]">暂无可引用纪要。经理层纪要不能推导为该基金的实际持仓。</div>
          ) : (
            memoHighlights.map((memo) => (
              <div key={memo.id || `${memo.title}-${memo.reportDate}`} className="border-l-2 border-[#c9b7d6] pl-2">
                <div className="flex flex-wrap items-baseline gap-1.5 text-[10px] text-[#7a8580]">
                  <span className={memo.scope === 'fund' ? 'bg-[#e8efe8] px-1 py-0.5 text-[#2b5a3f]' : 'bg-[#f0eaf5] px-1 py-0.5 text-[#5a3a6f]'}>
                    {memo.scope === 'fund' ? '基金层' : memo.scope === 'manager' ? '经理层' : '其他'}
                  </span>
                  {memo.managerName ? <span>{memo.managerName}</span> : null}
                  {memo.reportDate ? <span>{memo.reportDate.slice(0, 10)}</span> : null}
                </div>
                <div className="mt-1 font-semibold text-[#25332c] line-clamp-2">{memo.title}</div>
                {memo.summary ? (
                  <div className="mt-0.5 line-clamp-2 text-[#6a7570]">{memo.summary}</div>
                ) : null}
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
