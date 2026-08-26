import Link from 'next/link'
import { notFound } from 'next/navigation'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpenText,
  Building2,
  CircleAlert,
  Database,
  GraduationCap,
  GitCompareArrows,
  Layers3,
  Quote,
  ShieldCheck,
  Tag,
} from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'
import FundManagerCareerChart from './FundManagerCareerChart'
import ManagerViewpointTimeline from './ManagerViewpointTimeline'
import GenerateManagerReportButton from './GenerateManagerReportButton'

export const dynamic = 'force-dynamic'

type UnknownRecord = Record<string, unknown>

type ManagerDetail = {
  manager: UnknownRecord
  coverage: UnknownRecord
  current_funds: UnknownRecord[]
  product_tenures?: { items?: UnknownRecord[] } & UnknownRecord
  manager_assessment?: UnknownRecord
  portfolio_summary?: UnknownRecord
  profile: UnknownRecord
  research_memos: { count?: number; items?: UnknownRecord[] }
  historical_viewpoints?: UnknownRecord
  evidence: UnknownRecord
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function asArray(value: unknown) {
  return Array.isArray(value) ? value : []
}

function textValue(value: unknown) {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

function numberValue(value: unknown) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function formatPercent(value: unknown, digits = 1) {
  const parsed = numberValue(value)
  if (parsed == null) return '—'
  const normalized = Math.abs(parsed) <= 2 ? parsed * 100 : parsed
  return `${normalized.toFixed(digits)}%`
}

function formatNumber(value: unknown, digits = 2) {
  const parsed = numberValue(value)
  return parsed == null ? '—' : parsed.toFixed(digits)
}

function formatYears(value: unknown) {
  const parsed = numberValue(value)
  return parsed == null ? '待补' : `${parsed.toFixed(1)} 年`
}

function formatDate(value: unknown) {
  const text = textValue(value)
  return text ? text.slice(0, 10) : '—'
}

function formatAsset(value: unknown) {
  const parsed = numberValue(value)
  return parsed == null ? '—' : `${parsed.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿`
}

function stringList(value: unknown) {
  return asArray(value).map(textValue).filter(Boolean)
}

function metricBlock(fund: UnknownRecord, window: string) {
  return asRecord(asRecord(fund.rolling_metrics)[window])
}

function fundCategory(fund: UnknownRecord) {
  return textValue(fund.peer_group) || textValue(fund.type) || '专业分类待补'
}

function evaluationLabel(fund: UnknownRecord) {
  const score = numberValue(fund.professional_score)
  return score == null
    ? textValue(fund.evaluation_summary) || '评价证据不足'
    : `${score.toFixed(1)}${textValue(fund.professional_grade) ? ` · ${textValue(fund.professional_grade)}` : ''}`
}

function tenureRank(item: UnknownRecord) {
  const ranking = asRecord(item.peer_ranking)
  const metric = asRecord(asRecord(ranking.metrics).total_return)
  const rank = numberValue(metric.rank)
  const peerCount = numberValue(metric.peer_count)
  if (rank != null && peerCount != null) return `${rank} / ${peerCount}`
  if (textValue(ranking.status) === 'insufficient_peer_sample') {
    return `样本不足（${Number(ranking.valid_peer_count || peerCount || 0)}）`
  }
  return '待补'
}

function tenureRankCoverage(item: UnknownRecord) {
  const ranking = asRecord(item.peer_ranking)
  const valid = numberValue(ranking.valid_peer_count)
  const classified = numberValue(ranking.classified_peer_count)
  if (valid != null && classified != null) return `${valid} / ${classified} 只净值可比`
  return '同区间样本待补'
}

function peerMetric(item: UnknownRecord, metricName: string) {
  return asRecord(asRecord(asRecord(item.peer_ranking).metrics)[metricName])
}

function compactPeerRank(item: UnknownRecord, metricName: string) {
  const metric = peerMetric(item, metricName)
  const rank = numberValue(metric.rank)
  const peerCount = numberValue(metric.peer_count)
  if (textValue(metric.sample_status) === 'sufficient' && rank != null && peerCount != null) return `${rank}/${peerCount}`
  if (textValue(metric.sample_status) === 'insufficient_peer_sample') return '样本不足'
  return '—'
}

function profileEvidence(profile: UnknownRecord, field: string) {
  const evidence = asRecord(profile.evidence)
  const fields = asRecord(evidence.fields)
  const framework = asRecord(evidence.framework)
  return asArray(fields[field] || framework[field]).map(asRecord)
}

function EvidenceList({ items }: { items: UnknownRecord[] }) {
  if (!items.length) return null
  return (
    <div className="mt-4 space-y-2 border-t border-[#e5e9e6] pt-3">
      {items.slice(0, 2).map((item, index) => (
        <div key={`${textValue(item.report_id)}-${index}`} className="text-xs leading-5 text-[#748079]">
          <span className="font-bold text-[#526159]">{formatDate(item.report_date)} · {textValue(item.report_title) || textValue(item.relative_path) || '来源纪要'}</span>
          <p className="mt-1">“{textValue(item.excerpt) || textValue(item.value)}”</p>
          <span>置信度 {numberValue(item.confidence) == null ? '—' : `${(Number(item.confidence) * 100).toFixed(0)}%`}</span>
        </div>
      ))}
    </div>
  )
}

async function loadManager(managerId: string): Promise<ManagerDetail | null> {
  const response = await fetch(`${backendApiBaseUrl}/api/managers/${encodeURIComponent(managerId)}`, { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('基金经理研究快照暂时不可用')
  return response.json()
}

export default async function ManagerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const managerId = decodeURIComponent(id)
  const data = await loadManager(managerId)
  if (!data) notFound()

  const manager = asRecord(data.manager)
  const coverage = asRecord(data.coverage)
  const profile = asRecord(data.profile)
  const funds = Array.isArray(data.current_funds) ? data.current_funds : []
  const productTenures = asRecord(data.product_tenures)
  const managerAssessment = asRecord(data.manager_assessment)
  const portfolioSummary = asRecord(data.portfolio_summary)
  const categoryDistribution = asArray(portfolioSummary.category_distribution).map(asRecord)
  const tenureItems = asArray(productTenures.items).map(asRecord)
  const currentTenures = tenureItems.filter((item) => Boolean(item.is_current))
  const historicalTenures = tenureItems.filter((item) => !Boolean(item.is_current))
  const reports = Array.isArray(data.research_memos?.items) ? data.research_memos.items : []
  const evidence = asRecord(data.evidence)
  const missingItems = stringList(evidence.missing_items)
  const profileStyleLabels = [
    textValue(profile.style_label),
    ...stringList(profile.style_labels_from_memos),
  ].filter(Boolean)
  const managerName = textValue(manager.name) || managerId.split('|')[0] || '姓名待补'
  const company = textValue(manager.company)
  const focusIndustries = stringList(profile.focus_industries)
  const managerFundCodes = Array.from(new Set(funds.map((fund) => textValue(fund.wind_code)).filter(Boolean)))
  const managerDetailHref = `/managers/${encodeURIComponent(managerId)}`
  const evidenceQuery = {
    codes: managerFundCodes.join(','),
    returnTo: managerDetailHref,
  }
  const managerReviewEventsHref = reviewEventsHref(evidenceQuery)
  const managerMaterialEvidenceHref = materialEvidenceHref(evidenceQuery)
  const representativeProduct = asRecord(managerAssessment.representative_product)
  const assessmentStrengths = asArray(managerAssessment.strengths).map(asRecord)
  const assessmentRisks = asArray(managerAssessment.risks).map(asRecord)
  const currentProductCount = Number(portfolioSummary.current_product_count || productTenures.current_product_count || funds.length)
  const currentShareCount = Number(portfolioSummary.current_share_count || productTenures.current_share_count || funds.length)
  const managedAssetProductCount = Number(portfolioSummary.managed_asset_product_count || 0)
  const managedAssetCoverage = numberValue(portfolioSummary.managed_asset_coverage)

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/managers" className="inline-flex items-center gap-2 text-sm font-bold text-[#28745c]">
          <ArrowLeft className="h-4 w-4" />返回基金经理
        </Link>
        <div className="flex flex-wrap gap-2">
          <GenerateManagerReportButton managerId={managerId} />
          <Link href={managerReviewEventsHref} className="inline-flex items-center gap-2 border border-[#d7b46a] bg-[#fff9eb] px-4 py-2 text-xs font-bold text-[#755722] hover:bg-[#fff3d6]">
            <CircleAlert className="h-4 w-4" />复查事件
          </Link>
          <Link href={managerMaterialEvidenceHref} className="inline-flex items-center gap-2 border border-[#a8bcb2] bg-white px-4 py-2 text-xs font-bold text-[#285d4b] hover:bg-[#edf4f0]">
            <Database className="h-4 w-4" />补研究材料
          </Link>
          <Link href={`/managers/compare?manager_id=${encodeURIComponent(managerId)}`} className="inline-flex items-center gap-2 border border-[#a8bcb2] bg-white px-4 py-2 text-xs font-bold text-[#285d4b] hover:bg-[#edf4f0]">
            <GitCompareArrows className="h-4 w-4" />加入经理对比
          </Link>
        </div>
      </div>

      <section className="relative overflow-hidden border border-[#cfd8d1] bg-[#173f35] px-6 py-7 text-white sm:px-8 sm:py-9">
        <div className="absolute -right-16 -top-20 h-64 w-64 rounded-full border border-white/10" />
        <div className="absolute -right-4 top-10 h-40 w-40 rounded-full border border-white/10" />
        <div className="relative grid gap-8 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
          <div className="max-w-3xl">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{managerName}</h1>
            <p className="mt-2 text-sm text-[#c6d8d0]">{company || '基金公司待补'} · {textValue(manager.education) || '学历待补'}</p>
          </div>
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-white/20 bg-white/20 text-[#18231e] sm:grid-cols-4">
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{formatYears(manager.management_years)}</strong><span className="text-[11px] text-[#68756e]">管理年限</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{currentProductCount} / {currentShareCount}</strong><span className="text-[11px] text-[#68756e]">产品 / 份额</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{formatAsset(portfolioSummary.managed_asset)}</strong><span className="text-[11px] text-[#68756e]">已覆盖管理规模</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{Number(data.research_memos?.count || reports.length)}</strong><span className="text-[11px] text-[#68756e]">关联纪要</span></div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Building2 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">经理档案</strong>
          <dl className="mt-3 space-y-2 text-sm text-[#66736c]">
            <div className="flex justify-between gap-4"><dt>基金公司</dt><dd className="text-right text-[#25322c]">{company || '待补'}</dd></div>
            <div className="flex justify-between gap-4"><dt>学历</dt><dd className="text-[#25322c]">{textValue(manager.education) || '待补'}</dd></div>
            <div className="flex justify-between gap-4"><dt>从业年限</dt><dd className="text-[#25322c]">{formatYears(manager.work_years)}</dd></div>
          </dl>
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Layers3 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">研究覆盖</strong>
          <p className="mt-3 text-sm leading-6 text-[#66736c]">{Number(coverage.classified_fund_count || 0)} / {funds.length} 只已有专业分类，{Number(coverage.evaluated_fund_count || 0)} / {funds.length} 只已有分类内评价，{Number(coverage.tenure_metric_fund_count || 0)} / {funds.length} 只已有经理任期指标。</p>
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Database className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">数据日期</strong>
          <p className="mt-3 text-sm leading-6 text-[#66736c]">任期指标更新至 {formatDate(evidence.fund_metric_latest_date)}；最新纪要为 {formatDate(evidence.research_latest_date)}。</p>
        </article>
      </section>

      <section className="grid gap-4 lg:grid-cols-3" data-testid="manager-portfolio-summary">
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Layers3 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">在管类型分布</strong>
          {categoryDistribution.length ? (
            <div className="mt-3 space-y-2 text-sm">
              {categoryDistribution.map((item) => (
                <div key={textValue(item.key) || textValue(item.label)} className="flex items-center justify-between gap-4 border-b border-[#edf0ed] pb-2 last:border-0 last:pb-0">
                  <span className="text-[#5f6d66]">{textValue(item.label) || '待分类'}</span>
                  <span className="font-bold text-[#25322c]">{Number(item.product_count || 0)} 个产品</span>
                </div>
              ))}
            </div>
          ) : <p className="mt-3 text-sm text-[#748079]">基金类型待分类。</p>}
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Database className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">管理规模覆盖</strong>
          <p className="mt-3 text-2xl font-bold text-[#24322b]">{formatAsset(portfolioSummary.managed_asset)}</p>
          <p className="mt-2 text-sm leading-6 text-[#66736c]">
            已覆盖 {managedAssetProductCount} / {currentProductCount} 个产品
            {managedAssetCoverage == null ? '' : `（${formatPercent(managedAssetCoverage)}）`}。
          </p>
          <p className="mt-2 text-[11px] leading-5 text-[#87918c]">{textValue(portfolioSummary.managed_asset_scope) || '按基金产品合并份额后统计。'}</p>
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Building2 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">机构持有占比</strong>
          <p className="mt-3 text-2xl font-bold text-[#24322b]">
            {numberValue(portfolioSummary.institutional_holding_ratio) == null ? '待接入' : formatPercent(portfolioSummary.institutional_holding_ratio)}
          </p>
          <p className="mt-2 text-sm leading-6 text-[#66736c]">{textValue(portfolioSummary.institutional_holding_scope) || '持有人结构数据尚未接入，不进行推测。'}</p>
        </article>
      </section>

      {missingItems.length > 0 && (
        <section className="flex flex-wrap items-center justify-between gap-4 border-l-4 border-[#d7b46a] bg-[#fff9eb] px-5 py-4 text-xs leading-6 text-[#755722]">
          <div className="flex items-start gap-2"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" /><span>待补证据：{missingItems.join('；')}。</span></div>
          <div className="flex flex-wrap gap-3 font-bold">
            <Link href={managerReviewEventsHref} className="hover:text-[#4f3812]">查看复查事件</Link>
            <Link href={managerMaterialEvidenceHref} className="hover:text-[#4f3812]">补充名下基金材料</Link>
          </div>
        </section>
      )}

      <section className="border border-[#cfd8d1] bg-white" data-testid="manager-assessment-summary">
        <div className="border-b border-[#e1e6e2] bg-[#f4f7f4] px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-bold tracking-[0.12em] text-[#28745c]">经理评价摘要</div>
              <h2 className="mt-2 text-2xl font-bold text-[#1f2d26]">先看证据覆盖，再看具体产品</h2>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-[#647169]">{textValue(managerAssessment.summary) || '经理任期评价证据待补。'}</p>
            </div>
            <div className="grid grid-cols-3 gap-px bg-[#dbe2dd] text-center text-xs">
              <div className="bg-white px-4 py-3"><strong className="block text-lg text-[#24322b]">{Number(managerAssessment.current_product_count || currentTenures.length)}</strong><span className="text-[#748079]">在管产品</span></div>
              <div className="bg-white px-4 py-3"><strong className="block text-lg text-[#24322b]">{Number(managerAssessment.tenure_evaluated_product_count || 0)}</strong><span className="text-[#748079]">任期可评</span></div>
              <div className="bg-white px-4 py-3"><strong className="block text-lg text-[#24322b]">{Number(managerAssessment.peer_ranked_product_count || 0)}</strong><span className="text-[#748079]">同类可比</span></div>
            </div>
          </div>
        </div>

        <div className="grid gap-px bg-[#dfe5e1] lg:grid-cols-[1.1fr_1fr_1fr]">
          <article className="bg-white p-5">
            <h3 className="text-sm font-bold text-[#26342d]">代表性观察产品</h3>
            {Object.keys(representativeProduct).length ? (
              <>
                <Link href={`/funds/${encodeURIComponent(textValue(representativeProduct.fund_code))}`} className="mt-3 block text-lg font-bold text-[#28745c] hover:underline">{textValue(representativeProduct.fund_name) || textValue(representativeProduct.fund_code)}</Link>
                <p className="mt-1 text-xs text-[#748079]">{textValue(representativeProduct.category) || '分类待补'} · 任职 {formatDate(representativeProduct.start_date)} 至 {textValue(representativeProduct.end_date) ? formatDate(representativeProduct.end_date) : '今'}</p>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-[#f6f8f5] p-3"><strong className="block text-[#267257]">{formatPercent(representativeProduct.tenure_return)}</strong><span className="text-[#7b8680]">任期收益</span></div>
                  <div className="bg-[#f6f8f5] p-3"><strong className="block text-[#8b4f48]">{formatPercent(representativeProduct.max_drawdown)}</strong><span className="text-[#7b8680]">最大回撤</span></div>
                </div>
                <p className="mt-3 text-[11px] leading-5 text-[#7b8680]">{textValue(representativeProduct.selection_reason)}</p>
              </>
            ) : <p className="mt-3 text-sm text-[#748079]">暂无任期指标完整的当前产品。</p>}
          </article>

          <article className="bg-white p-5">
            <h3 className="text-sm font-bold text-[#267257]">已证实的相对优势</h3>
            {assessmentStrengths.length ? (
              <div className="mt-3 space-y-3">
                {assessmentStrengths.map((item, index) => <div key={`${textValue(item.fund_code)}-${textValue(item.metric_name)}-${index}`} className="border-l-2 border-[#6aa58c] pl-3"><strong className="text-sm text-[#314139]">{textValue(item.label)}</strong><p className="mt-1 text-xs leading-5 text-[#68756e]">{textValue(item.statement)}</p></div>)}
              </div>
            ) : <p className="mt-3 text-sm leading-6 text-[#748079]">暂无达到同类前 20% 且样本充分的优势证据。</p>}
          </article>

          <article className="bg-white p-5">
            <h3 className="text-sm font-bold text-[#9a5149]">需要关注的相对弱项</h3>
            {assessmentRisks.length ? (
              <div className="mt-3 space-y-3">
                {assessmentRisks.map((item, index) => <div key={`${textValue(item.fund_code)}-${textValue(item.metric_name)}-${index}`} className="border-l-2 border-[#c9877f] pl-3"><strong className="text-sm text-[#503632]">{textValue(item.label)}</strong><p className="mt-1 text-xs leading-5 text-[#74625f]">{textValue(item.statement)}</p></div>)}
              </div>
            ) : <p className="mt-3 text-sm leading-6 text-[#748079]">暂无落入同类后 20% 且样本充分的风险证据。</p>}
          </article>
        </div>
        <div className="border-t border-[#e1e6e2] px-5 py-3 text-[11px] leading-5 text-[#748079]">{textValue(managerAssessment.scope_note) || '不生成经理综合收益、综合净值或综合分。'}</div>
      </section>

      <FundManagerCareerChart managerId={managerId} initialFundCode={textValue(representativeProduct.fund_code)} />

      <section>
        <div className="mb-4">
            <div className="flex items-center gap-2 text-[#28745c]"><BarChart3 className="h-5 w-5" /><span className="text-xs font-bold tracking-[0.12em]">当前产品</span></div>
          <h2 className="mt-2 text-2xl font-bold">当前管理基金与任期证据</h2>
          <p className="mt-1 text-sm text-[#6d7872]">每只基金单独展示自身类别和任期指标；不把债券、指数、主动权益等不同类别合成经理总收益。</p>
        </div>
        {funds.length ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {funds.map((fund) => {
              const code = textValue(fund.wind_code)
              const productTenure = asRecord(fund.manager_product_tenure)
              const exactProductTenure = textValue(productTenure.status) === 'manager_product_tenure'
              const tenure = exactProductTenure ? productTenure : {}
              const oneYear = metricBlock(fund, '1y')
              const displayed = Object.keys(tenure).length ? tenure : oneYear
              const metricLabel = exactProductTenure ? '该经理任期' : Object.keys(oneYear).length ? '近 1 年（经理任期待补）' : '指标待补'
              const shareCodes = stringList(fund.share_codes)
              const productPeerRanking = asRecord(productTenure.peer_ranking)
              return (
                <article key={code} className="border border-[#d7ded8] bg-white p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <span className="text-[11px] font-bold tracking-[0.08em] text-[#6f7b74]">{fundCategory(fund)}</span>
                      <h3 className="mt-1 text-lg font-bold text-[#1e2b25]">{textValue(fund.name) || code}</h3>
                      <p className="mt-1 text-xs text-[#7b8680]">{code} · 规模 {formatAsset(fund.total_asset)}{shareCodes.length > 1 ? ` · 含 ${shareCodes.length} 个份额` : ''}</p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <span className={`rounded-full px-3 py-1 text-xs font-bold ${numberValue(fund.professional_score) == null ? 'bg-[#fff3d6] text-[#805f1d]' : 'bg-[#e8f1ec] text-[#28624e]'}`}>分类内评价 {evaluationLabel(fund)}</span>
                      <span className="rounded-full bg-[#f0f1ef] px-3 py-1 text-xs font-bold text-[#53615a]">同类任期 {tenureRank({ peer_ranking: productPeerRanking })}</span>
                    </div>
                  </div>
                  <div className="mt-5 grid grid-cols-4 gap-px overflow-hidden border border-[#e3e7e4] bg-[#e3e7e4] text-center">
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm text-[#267257]">{formatPercent(displayed.total_return ?? displayed.annualized_return)}</strong><span className="text-[10px] text-[#7d8782]">{metricLabel}收益</span></div>
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm text-[#8b4f48]">{formatPercent(displayed.max_drawdown)}</strong><span className="text-[10px] text-[#7d8782]">最大回撤</span></div>
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm">{formatPercent(displayed.annualized_volatility)}</strong><span className="text-[10px] text-[#7d8782]">年化波动</span></div>
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm">{formatNumber(displayed.sharpe_ratio)}</strong><span className="text-[10px] text-[#7d8782]">夏普比率</span></div>
                  </div>
                  <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-xs">
                    <span className="text-[#76827c]">数据日期 {formatDate(displayed.as_of_date || fund.nav_date)}{shareCodes.length > 1 ? ` · 份额 ${shareCodes.join(' / ')}` : ''}</span>
                    <Link href={`/funds/${encodeURIComponent(code)}`} className="inline-flex items-center gap-1 font-bold text-[#28745c]">查看基金详情<ArrowRight className="h-3.5 w-3.5" /></Link>
                  </div>
                </article>
              )
            })}
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748079]">当前基金关联待补。</div>}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[#28745c]"><Layers3 className="h-5 w-5" /><span className="text-xs font-bold tracking-[0.12em]">完整任职记录</span></div>
            <h2 className="mt-2 text-2xl font-bold">产品任职全景</h2>
            <p className="mt-1 text-sm text-[#6d7872]">同时保留现任与已卸任产品；同一产品的 A/C 等份额不重复计算产品数。</p>
          </div>
          <div className="flex gap-2 text-xs font-bold">
            <span className="bg-[#e8f1ec] px-3 py-1.5 text-[#28624e]">现任 {Number(productTenures.current_product_count || currentTenures.length)} 个产品 / {Number(productTenures.current_share_count || currentTenures.length)} 个份额</span>
            <span className="bg-[#f0f1ef] px-3 py-1.5 text-[#65716a]">历史 {Number(productTenures.historical_product_count || historicalTenures.length)} 个产品 / {Number(productTenures.historical_share_count || historicalTenures.length)} 个份额</span>
          </div>
        </div>
        {tenureItems.length ? (
          <div className="overflow-x-auto border border-[#d7ded8] bg-white">
            <table className="min-w-[1120px] w-full text-left text-sm">
              <thead className="bg-[#f3f5f2] text-xs text-[#637068]">
                <tr>
                  <th className="px-4 py-3">产品</th>
                  <th className="px-4 py-3">分类</th>
                  <th className="px-4 py-3">任职开始</th>
                  <th className="px-4 py-3">任职结束</th>
                  <th className="px-4 py-3">任期</th>
                  <th className="px-4 py-3">任期收益</th>
                  <th className="px-4 py-3">同类任期排名</th>
                  <th className="px-4 py-3">年化收益</th>
                  <th className="px-4 py-3">最大回撤</th>
                  <th className="px-4 py-3">回撤同类</th>
                  <th className="px-4 py-3">夏普同类</th>
                  <th className="px-4 py-3">规模</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e3e7e4]">
                {tenureItems.map((item) => {
                  const code = textValue(item.fund_code)
                  const tenureDays = numberValue(item.tenure_days)
                  const isCurrent = Boolean(item.is_current)
                  return (
                    <tr key={`${code}-${textValue(item.start_date)}`} className={isCurrent ? '' : 'bg-[#fbfbfa] text-[#68736d]'}>
                      <td className="px-4 py-3">
                        <Link href={`/funds/${encodeURIComponent(code)}`} className="font-bold text-[#24322b] hover:text-[#28745c]">{textValue(item.fund_name) || code}</Link>
                        <div className="mt-1 text-xs text-[#7b8680]">{code} {isCurrent ? '· 现任' : '· 已卸任'}{Number(item.share_count || 1) > 1 ? ` · ${Number(item.share_count)} 个份额` : ''}</div>
                      </td>
                      <td className="px-4 py-3">{textValue(item.category) || textValue(item.type) || '待分类'}</td>
                      <td className="px-4 py-3">{formatDate(item.start_date)}</td>
                      <td className="px-4 py-3">{isCurrent ? '至今' : formatDate(item.end_date)}</td>
                      <td className="px-4 py-3">{tenureDays == null ? '—' : `${(tenureDays / 365.25).toFixed(1)} 年`}</td>
                      <td className="px-4 py-3 font-bold text-[#267257]">{formatPercent(item.tenure_return)}</td>
                      <td className="px-4 py-3">
                        <div className="font-bold text-[#34433b]">{tenureRank(item)}</div>
                        <div className="mt-1 text-[10px] text-[#7b8680]">{textValue(asRecord(item.peer_ranking).peer_group_name) || '同类组待补'} · 同区间</div>
                        <div className="mt-0.5 text-[10px] text-[#8a948f]">{tenureRankCoverage(item)}</div>
                      </td>
                      <td className="px-4 py-3">{formatPercent(item.annualized_return)}</td>
                      <td className="px-4 py-3 text-[#8b4f48]">{formatPercent(item.max_drawdown)}</td>
                      <td className="px-4 py-3">{compactPeerRank(item, 'max_drawdown')}</td>
                      <td className="px-4 py-3">{compactPeerRank(item, 'sharpe_ratio')}</td>
                      <td className="px-4 py-3">{formatAsset(item.total_asset)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-12 text-center text-sm text-[#748079]">产品任职关系待同步。</div>}
      </section>

      <section>
        <div className="mb-4">
            <div className="flex items-center gap-2 text-[#28745c]"><Tag className="h-5 w-5" /><span className="text-xs font-bold tracking-[0.12em]">纪要画像</span></div>
          <h2 className="mt-2 text-2xl font-bold">投资框架与风格画像</h2>
          <p className="mt-1 text-sm text-[#6d7872]">只展示经理画像库和调研纪要中已有的证据；没有证据时不根据基金名称自动编写投资理念。</p>
        </div>
        {textValue(profile.status) !== 'empty' ? (
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-3">
              <article className="border border-[#bfcfc5] bg-[#f4f8f5] p-5">
                <Layers3 className="h-5 w-5 text-[#28745c]" />
                <h3 className="mt-4 font-bold">产品定位</h3>
                <p className="mt-3 text-sm leading-7 text-[#53645b]">{textValue(profile.product_positioning) || '待从纪要确认产品覆盖范围、策略边界和差异化定位。'}</p>
                <EvidenceList items={profileEvidence(profile, 'product_positioning')} />
              </article>
              <article className="border border-[#bfcfc5] bg-[#f4f8f5] p-5">
                <ShieldCheck className="h-5 w-5 text-[#28745c]" />
                <h3 className="mt-4 font-bold">投资目标</h3>
                <p className="mt-3 text-sm leading-7 text-[#53645b]">{textValue(profile.investment_objective) || '待从纪要确认经理追求的收益目标与回撤约束。'}</p>
                <EvidenceList items={profileEvidence(profile, 'investment_objective')} />
              </article>
              <article className="border border-[#bfcfc5] bg-[#f4f8f5] p-5">
                <Quote className="h-5 w-5 text-[#28745c]" />
                <h3 className="mt-4 font-bold">投资方法</h3>
                <p className="mt-3 text-sm leading-7 text-[#53645b]">{textValue(profile.investment_method) || '待从纪要确认宏观、行业和个股研究如何组合使用。'}</p>
                <EvidenceList items={profileEvidence(profile, 'investment_method')} />
              </article>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
            <article className="border border-[#bfcfc5] bg-[#f4f8f5] p-5">
              <BarChart3 className="h-5 w-5 text-[#28745c]" />
              <div className="mt-4 flex items-center justify-between gap-3">
                <h3 className="font-bold">超额收益来源</h3>
                <span className="text-[10px] font-bold tracking-[0.08em] text-[#668077]">纪要证据</span>
              </div>
              <p className="mt-3 text-sm leading-7 text-[#53645b]">{textValue(profile.excess_return_source) || '待从纪要确认经理主要依靠行业选择、个股选择、组合调整或其他方式获取超额。'}</p>
              <EvidenceList items={profileEvidence(profile, 'excess_return_source')} />
            </article>
            <article className="border border-[#bfcfc5] bg-[#f4f8f5] p-5">
              <Layers3 className="h-5 w-5 text-[#28745c]" />
              <div className="mt-4 flex items-center justify-between gap-3">
                <h3 className="font-bold">持股风格</h3>
                <span className="text-[10px] font-bold tracking-[0.08em] text-[#668077]">纪要证据</span>
              </div>
              <p className="mt-3 text-sm leading-7 text-[#53645b]">{textValue(profile.holding_style) || '待从纪要确认市值、价值成长、集中分散等持仓特征。'}</p>
              <EvidenceList items={profileEvidence(profile, 'holding_style')} />
            </article>
            <article className="border border-[#d7ded8] bg-white p-5">
              <Quote className="h-5 w-5 text-[#28745c]" />
              <h3 className="mt-4 font-bold">投资理念与选股逻辑</h3>
              <p className="mt-3 text-sm leading-7 text-[#5f6d66]">{textValue(profile.core_philosophy) || '核心投资理念待从纪要确认。'}</p>
              <p className="mt-3 text-sm leading-7 text-[#5f6d66]">{textValue(profile.stock_selection_logic) || '选股逻辑待从纪要确认。'}</p>
              <EvidenceList items={[...profileEvidence(profile, 'core_philosophy'), ...profileEvidence(profile, 'stock_selection_logic')]} />
            </article>
            <article className="border border-[#d7ded8] bg-white p-5">
              <ShieldCheck className="h-5 w-5 text-[#28745c]" />
              <h3 className="mt-4 font-bold">风险意识与能力边界</h3>
              <p className="mt-3 text-sm leading-7 text-[#5f6d66]">{textValue(profile.risk_philosophy) || '风险理念待从纪要确认。'}</p>
              <p className="mt-3 text-sm leading-7 text-[#5f6d66]">{textValue(profile.competence_boundaries) || '能力边界待从纪要确认。'}</p>
              <EvidenceList items={[...profileEvidence(profile, 'risk_philosophy'), ...profileEvidence(profile, 'competence_boundaries')]} />
            </article>
            <article className="border border-[#d7ded8] bg-white p-5">
              <Layers3 className="h-5 w-5 text-[#28745c]" />
              <h3 className="mt-4 font-bold">能力优势与行业范围</h3>
              <p className="mt-3 text-sm leading-7 text-[#5f6d66]">{textValue(profile.competence_advantages) || '能力优势待从纪要确认。'}</p>
              {focusIndustries.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{focusIndustries.map((industry) => <span key={industry} className="rounded-full bg-[#f0f3f1] px-2.5 py-1 text-[11px] text-[#526159]">{industry}</span>)}</div>}
              <EvidenceList items={profileEvidence(profile, 'competence_advantages')} />
            </article>
            <article className="border border-[#d7ded8] bg-white p-5">
              <BarChart3 className="h-5 w-5 text-[#28745c]" />
              <h3 className="mt-4 font-bold">组合特征</h3>
              <dl className="mt-3 space-y-3 text-sm text-[#66736c]">
                <div><dt className="font-bold text-[#34433b]">集中度</dt><dd className="mt-1 leading-6">{textValue(profile.concentration) || '待从纪要确认'}</dd></div>
                <div><dt className="font-bold text-[#34433b]">换手特征</dt><dd className="mt-1 leading-6">{textValue(profile.turnover) || '待从纪要确认'}</dd></div>
              </dl>
              <EvidenceList items={[...profileEvidence(profile, 'concentration'), ...profileEvidence(profile, 'turnover')]} />
            </article>
            {profileStyleLabels.length > 0 && (
              <div className="lg:col-span-2 flex flex-wrap gap-2 border border-[#d7ded8] bg-white p-5">
                {Array.from(new Set(profileStyleLabels)).map((label) => <span key={label} className="rounded-full bg-[#e8f1ec] px-3 py-1.5 text-xs font-bold text-[#28624e]">{label}</span>)}
              </div>
            )}
            </div>
          </div>
        ) : (
          <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-12 text-center">
            <GraduationCap className="mx-auto h-6 w-6 text-[#8b9a92]" />
            <p className="mt-3 text-sm font-bold text-[#34433b]">经理画像待从纪要确认</p>
            <p className="mt-2 text-xs text-[#748079]">系统不会根据经理姓名或基金名称生成模板化投资理念。</p>
          </div>
        )}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[#28745c]"><BookOpenText className="h-5 w-5" /><span className="text-xs font-bold tracking-[0.12em]">调研纪要</span></div>
            <h2 className="mt-2 text-2xl font-bold">调研纪要与历史观点</h2>
            <p className="mt-1 text-sm text-[#6d7872]">这里只展示已确认绑定到该经理规范 ID 的纪要，原文件仍保存在本地纪要库。</p>
          </div>
          <Link href={`/research?search=${encodeURIComponent(managerName)}`} className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">打开调研库<ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
        {reports.length ? (
          <ManagerViewpointTimeline
            managerName={managerName}
            data={asRecord(data.historical_viewpoints)}
          />
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748079]">尚未关联调研纪要。</div>}
      </section>
    </div>
  )
}
