import Link from 'next/link'
import {
  ArrowRight,
  BarChart3,
  BookOpenText,
  Building2,
  Database,
  GitCompareArrows,
  Search,
  Tags,
  UserRoundSearch,
} from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

export const dynamic = 'force-dynamic'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

type ManagerSummary = {
  id: string
  name: string
  company?: string | null
  management_years?: number | null
  current_fund_codes?: string[]
  current_fund_count: number
  current_share_count: number
  classified_fund_count: number
  metric_fund_count: number
  tenure_metric_fund_count: number
  memo_count: number
  latest_memo_date?: string | null
  latest_metric_date?: string | null
  category_labels: string[]
  strategy_names: string[]
  peer_groups: string[]
  style_labels: string[]
  focus_industries: string[]
  representative_fund?: {
    wind_code?: string | null
    name?: string | null
    quantitative_evidence?: {
      window?: string | null
      label?: string | null
      as_of_date?: string | null
      annualized_return?: number | null
      max_drawdown?: number | null
      sharpe_ratio?: number | null
      annualized_volatility?: number | null
    } | null
  } | null
  latest_memo?: {
    id: string
    title?: string | null
    summary?: string | null
    report_date?: string | null
    report_date_source?: string | null
    report_date_precision?: string | null
    viewpoint_topics?: string[]
    research_domains?: string[]
  } | null
}

type CategoryOption = { key: string; label: string }
type EvidenceOption = { key: string; label: string }

type ManagerBrowserPayload = {
  managers: ManagerSummary[]
  total: number
  page: number
  page_size: number
  keyword: string
  category: string
  evidence: string
  categories: CategoryOption[]
  evidence_filters: EvidenceOption[]
  methodology?: Record<string, string>
}

const defaultCategories: CategoryOption[] = [
  { key: 'all', label: '全部' },
  { key: 'fixed_income', label: '固收' },
  { key: 'fixed_income_plus', label: '固收+' },
  { key: 'active_equity', label: '主动权益' },
  { key: 'passive_equity', label: '被动权益' },
  { key: 'qdii', label: 'QDII' },
  { key: 'fof', label: 'FOF' },
  { key: 'money_market', label: '货币' },
  { key: 'other', label: '其他' },
]

const defaultEvidenceFilters: EvidenceOption[] = [
  { key: 'all', label: '全部经理' },
  { key: 'with_memo', label: '有调研纪要' },
  { key: 'with_metrics', label: '有量化数据' },
  { key: 'research_ready', label: '调研+量化' },
]

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] || '' : value || ''
}

function positiveInt(value: string, fallback: number) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function formatYears(value: number | null | undefined) {
  return value == null ? '待补' : `${Number(value).toFixed(1)} 年`
}

function formatDate(value: string | null | undefined) {
  return value ? value.slice(0, 10) : '待补'
}

function formatMemoDate(memo: ManagerSummary['latest_memo']) {
  const value = memo?.report_date?.slice(0, 10)
  if (!value) return '日期待确认'
  if (memo?.report_date_precision === 'quarter') {
    const month = Number(value.slice(5, 7))
    return `${value.slice(0, 4)} Q${Math.floor((month - 1) / 3) + 1}`
  }
  if (memo?.report_date_precision === 'month') return `${value.slice(0, 7)} 月`
  return value
}

function formatPercent(value: number | null | undefined) {
  return value == null || !Number.isFinite(Number(value)) ? '待补' : `${(Number(value) * 100).toFixed(1)}%`
}

function formatRatio(value: number | null | undefined) {
  return value == null || !Number.isFinite(Number(value)) ? '待补' : Number(value).toFixed(2)
}

function buildHref(params: { keyword: string; category: string; evidence: string; page: number }) {
  const query = new URLSearchParams()
  if (params.keyword) query.set('search', params.keyword)
  if (params.category !== 'all') query.set('category', params.category)
  if (params.evidence !== 'all') query.set('evidence', params.evidence)
  if (params.page > 1) query.set('page', String(params.page))
  const suffix = query.toString()
  return suffix ? `/managers?${suffix}` : '/managers'
}

async function loadManagers(keyword: string, category: string, evidence: string, page: number) {
  const url = new URL('/api/managers/browser', backendApiBaseUrl)
  url.searchParams.set('keyword', keyword)
  url.searchParams.set('category', category)
  url.searchParams.set('evidence', evidence)
  url.searchParams.set('page', String(page))
  url.searchParams.set('page_size', '24')
  try {
    const response = await fetch(url, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || 'manager browser unavailable')
    return { data: payload as ManagerBrowserPayload, error: '' }
  } catch {
    return {
      data: {
        managers: [],
        total: 0,
        page,
        page_size: 24,
        keyword,
        category,
        evidence,
        categories: defaultCategories,
        evidence_filters: defaultEvidenceFilters,
      } satisfies ManagerBrowserPayload,
      error: '基金经理数据库暂时无法连接，请先启动后端服务。',
    }
  }
}

export default async function ManagersPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams
  const keyword = firstParam(params.search).trim()
  const requestedCategory = firstParam(params.category).trim().toLowerCase() || 'all'
  const category = defaultCategories.some((item) => item.key === requestedCategory) ? requestedCategory : 'all'
  const requestedEvidence = firstParam(params.evidence).trim().toLowerCase() || 'all'
  const evidence = defaultEvidenceFilters.some((item) => item.key === requestedEvidence) ? requestedEvidence : 'all'
  const page = positiveInt(firstParam(params.page), 1)
  const { data, error } = await loadManagers(keyword, category, evidence, page)
  const managers = Array.isArray(data.managers) ? data.managers : []
  const categories = Array.isArray(data.categories) && data.categories.length ? data.categories : defaultCategories
  const evidenceFilters = Array.isArray(data.evidence_filters) && data.evidence_filters.length ? data.evidence_filters : defaultEvidenceFilters
  const totalPages = Math.max(1, Math.ceil(Number(data.total || 0) / Number(data.page_size || 24)))
  const currentLabel = categories.find((item) => item.key === category)?.label || '全部'

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden border border-[#cfd8d1] bg-[#173f35] px-6 py-8 text-white sm:px-8 sm:py-10">
        <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full border border-white/10" />
        <div className="absolute -right-2 top-14 h-44 w-44 rounded-full border border-white/10" />
        <div className="relative flex justify-end">
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-white/20 bg-white/20 text-[#18231e]">
            <div className="bg-[#f7f5ed] px-5 py-4"><strong className="block text-2xl">{data.total}</strong><span className="text-[11px] text-[#68756e]">当前结果</span></div>
            <div className="bg-[#f7f5ed] px-5 py-4"><strong className="block text-2xl">{currentLabel}</strong><span className="text-[11px] text-[#68756e]">所选类别</span></div>
          </div>
        </div>
      </section>

      <section className="border border-[#d9e0db] bg-white p-5 sm:p-6">
        <form action="/managers" className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <input type="hidden" name="category" value={category} />
          <input type="hidden" name="evidence" value={evidence} />
          <label className="relative block">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7c8982]" />
            <input
              type="search"
              name="search"
              defaultValue={keyword}
              placeholder="搜索基金经理、基金公司或代表基金"
              className="h-12 w-full border border-[#ccd6cf] bg-[#fbfcfa] pl-11 pr-4 text-sm outline-none transition focus:border-[#28745c]"
            />
          </label>
          <button type="submit" className="h-12 bg-[#28745c] px-7 text-sm font-bold text-white hover:bg-[#205e4b]">搜索</button>
        </form>
        <div className="mt-5 flex flex-wrap gap-2">
          {categories.map((item) => (
            <Link
              key={item.key}
              href={buildHref({ keyword, category: item.key, evidence, page: 1 })}
              className={item.key === category
                ? 'bg-[#173f35] px-4 py-2 text-xs font-bold text-white'
                : 'border border-[#d7ded9] bg-[#f8faf8] px-4 py-2 text-xs font-bold text-[#526159] hover:border-[#8bb19f]'}
            >
              {item.label}
            </Link>
          ))}
        </div>
        <div className="mt-5 border-t border-[#e1e6e2] pt-5">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#77847d]">证据筛选</div>
          <div className="flex flex-wrap gap-2">
            {evidenceFilters.map((item) => (
              <Link
                key={item.key}
                href={buildHref({ keyword, category, evidence: item.key, page: 1 })}
                className={item.key === evidence
                  ? 'bg-[#9a7436] px-4 py-2 text-xs font-bold text-white'
                  : 'border border-[#ded7c9] bg-[#fffdf8] px-4 py-2 text-xs font-bold text-[#6f624c] hover:border-[#b99a62]'}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
        <p className="mt-4 text-xs leading-6 text-[#718078]">“调研+量化”只保留同时有经理纪要和代表基金量化指标的经理。量化摘要优先经理任期，缺失时显示近 1 年。</p>
      </section>

      {error ? (
        <section className="border border-[#e7c8b9] bg-[#fff7f1] px-6 py-12 text-center text-sm text-[#875b48]">{error}</section>
      ) : managers.length ? (
        <section className="grid gap-4 xl:grid-cols-2">
          {managers.map((manager) => {
            const representative = manager.representative_fund
            const quantitative = representative?.quantitative_evidence
            const latestMemo = manager.latest_memo
            const categoryLabels = manager.category_labels || []
            const researchReady = manager.memo_count > 0
            const managerFundCodes = Array.from(new Set((manager.current_fund_codes || []).filter(Boolean)))
            const managerDetailHref = `/managers/${encodeURIComponent(manager.id)}`
            const managerEvidenceHref = materialEvidenceHref({
              codes: managerFundCodes.join(','),
              returnTo: managerDetailHref,
            })
            return (
              <article key={manager.id} className="group border border-[#d8dfda] bg-white p-5 transition hover:border-[#94b2a4] hover:shadow-[0_14px_40px_rgba(40,72,58,0.08)] sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap gap-2">
                      {categoryLabels.length ? categoryLabels.map((label) => <span key={label} className="bg-[#e8f1ec] px-2.5 py-1 text-[11px] font-bold text-[#28624e]">{label}</span>) : <span className="bg-[#f2f3f1] px-2.5 py-1 text-[11px] text-[#6f7b74]">分类待补</span>}
                      {researchReady ? <span className="bg-[#fff5df] px-2.5 py-1 text-[11px] font-bold text-[#82662c]">有调研纪要</span> : null}
                      {manager.current_fund_count === 0 && researchReady ? <span className="bg-[#eef0f3] px-2.5 py-1 text-[11px] font-bold text-[#59616d]">历史经理 · 当前无在管</span> : null}
                    </div>
                    <h2 className="mt-3 text-2xl font-bold text-[#1f2d26]">
                      <Link href={managerDetailHref} className="hover:text-[#28745c] hover:underline">
                        {manager.name || '姓名待补'}
                      </Link>
                    </h2>
                    <p className="mt-1 flex items-center gap-1.5 text-sm text-[#68766f]"><Building2 className="h-3.5 w-3.5" />{manager.company || '基金公司待补'}</p>
                  </div>
                  <div className="text-right">
                    <strong className="block text-lg text-[#1f2d26]">{formatYears(manager.management_years)}</strong>
                    <span className="text-[11px] text-[#7c8982]">管理年限</span>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-4 gap-px overflow-hidden border border-[#e3e7e4] bg-[#e3e7e4] text-center">
                  <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#25332c]">{manager.current_fund_count}</strong><span className="text-[10px] text-[#7d8782]">当前基金</span></div>
                  <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#28745c]">{manager.classified_fund_count}</strong><span className="text-[10px] text-[#7d8782]">专业分类</span></div>
                  <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#28745c]">{manager.tenure_metric_fund_count}</strong><span className="text-[10px] text-[#7d8782]">任期指标</span></div>
                  <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#9a7436]">{manager.memo_count}</strong><span className="text-[10px] text-[#7d8782]">调研纪要</span></div>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <div className="bg-[#f7f8f5] p-4">
                    <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.1em] text-[#6c7a72]"><BarChart3 className="h-3.5 w-3.5" />代表基金</div>
                    {representative?.wind_code ? (
                      <Link href={`/funds/${encodeURIComponent(representative.wind_code)}`} className="mt-2 block text-sm font-bold text-[#244f40] hover:underline">
                        {representative.name || representative.wind_code}
                        <span className="mt-1 block text-[11px] font-normal text-[#7a8780]">{representative.wind_code}</span>
                      </Link>
                    ) : <p className="mt-2 text-sm text-[#77847d]">代表基金待补</p>}
                  </div>
                  <div className="bg-[#f7f8f5] p-4">
                    <div className="flex items-center justify-between gap-3 text-[11px] font-bold uppercase tracking-[0.1em] text-[#6c7a72]"><span className="flex items-center gap-2"><BarChart3 className="h-3.5 w-3.5" />量化摘要</span><span>{quantitative?.label || '待补'}</span></div>
                    {quantitative ? (
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                        <div><strong className="block text-sm text-[#28745c]">{formatPercent(quantitative.annualized_return)}</strong><span className="text-[10px] text-[#7a8780]">年化收益</span></div>
                        <div><strong className="block text-sm text-[#9b5f4a]">{formatPercent(quantitative.max_drawdown)}</strong><span className="text-[10px] text-[#7a8780]">最大回撤</span></div>
                        <div><strong className="block text-sm text-[#34423b]">{formatRatio(quantitative.sharpe_ratio)}</strong><span className="text-[10px] text-[#7a8780]">夏普</span></div>
                      </div>
                    ) : <p className="mt-2 text-sm text-[#77847d]">代表基金量化指标待补</p>}
                    <p className="mt-2 text-[10px] text-[#8a958f]">截至 {formatDate(quantitative?.as_of_date || manager.latest_metric_date)}</p>
                  </div>
                </div>

                {latestMemo ? (
                  <div className="mt-4 border-l-2 border-[#c59a50] bg-[#fffaf0] px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.1em] text-[#82662c]"><BookOpenText className="h-3.5 w-3.5" />最新经理观点</div>
                      <span className="text-[10px] text-[#8d8067]">{formatMemoDate(latestMemo)}</span>
                    </div>
                    <Link href={`/research?search=${encodeURIComponent(manager.name)}`} className="mt-2 block text-sm font-bold text-[#4d4029] hover:underline">{latestMemo.title || '查看经理纪要'}</Link>
                    {latestMemo.summary ? <p className="mt-2 line-clamp-2 text-xs leading-6 text-[#6f654f]">{latestMemo.summary}</p> : null}
                    {latestMemo.viewpoint_topics?.length ? <div className="mt-2 flex flex-wrap gap-1.5">{latestMemo.viewpoint_topics.slice(0, 5).map((topic) => <span key={topic} className="bg-white px-2 py-1 text-[10px] text-[#806632]">#{topic}</span>)}</div> : null}
                  </div>
                ) : null}

                {manager.style_labels?.length || manager.focus_industries?.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {manager.style_labels.slice(0, 3).map((label) => <span key={`style-${label}`} className="bg-[#e8f1ec] px-2.5 py-1 text-[11px] font-bold text-[#28624e]">长期风格 · {label}</span>)}
                    {manager.focus_industries.slice(0, 5).map((label) => <span key={`focus-${label}`} className="bg-[#f3f4f1] px-2.5 py-1 text-[11px] text-[#647169]">关注 · {label}</span>)}
                  </div>
                ) : null}

                {manager.peer_groups?.length ? (
                  <div className="mt-4 flex items-start gap-2 text-xs leading-6 text-[#67756e]">
                    <Tags className="mt-1 h-3.5 w-3.5 shrink-0 text-[#28745c]" />
                    <span>{manager.peer_groups.slice(0, 3).join(' · ')}</span>
                  </div>
                ) : null}

                <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#e5e9e6] pt-4 text-xs">
                  <span className="flex items-center gap-1.5 text-[#718078]"><Database className="h-3.5 w-3.5" />{manager.current_share_count > manager.current_fund_count ? `${manager.current_share_count} 个份额已合并展示` : '按基金实体展示'}</span>
                  <div className="flex flex-wrap items-center gap-3">
                    <Link href={managerEvidenceHref} className="inline-flex items-center gap-1 font-bold text-[#5e6d65] hover:text-[#28745c]">
                      <Database className="h-3.5 w-3.5" />补产品证据
                    </Link>
                    <Link href={`/managers/compare?manager_id=${encodeURIComponent(manager.id)}`} className="inline-flex items-center gap-1 font-bold text-[#5e6d65] hover:text-[#28745c]">
                      <GitCompareArrows className="h-3.5 w-3.5" />加入对比
                    </Link>
                    <Link href={managerDetailHref} className="inline-flex items-center gap-1 font-bold text-[#28745c]">
                      查看经理研究<ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                    </Link>
                  </div>
                </div>
              </article>
            )
          })}
        </section>
      ) : (
        <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-16 text-center">
          <UserRoundSearch className="mx-auto h-7 w-7 text-[#8b9991]" />
          <h2 className="mt-4 text-lg font-bold text-[#314038]">没有找到可核验的基金经理</h2>
          <p className="mt-2 text-sm text-[#718078]">可更换关键词或类别。QDII、FOF 等类别为空时，表示本地标准分类和经理关联尚未入库。</p>
          <Link href="/managers" className="mt-5 inline-flex bg-[#28745c] px-5 py-2.5 text-xs font-bold text-white">查看全部</Link>
        </section>
      )}

      {!error && data.total > 0 ? (
        <nav className="flex items-center justify-between border-t border-[#dce2de] pt-5 text-sm">
          <span className="text-[#718078]">第 {Math.min(page, totalPages)} / {totalPages} 页，共 {data.total} 位经理</span>
          <div className="flex gap-2">
            {page > 1 ? <Link href={buildHref({ keyword, category, evidence, page: page - 1 })} className="border border-[#cdd7d0] bg-white px-4 py-2 font-bold text-[#405148]">上一页</Link> : null}
            {page < totalPages ? <Link href={buildHref({ keyword, category, evidence, page: page + 1 })} className="bg-[#173f35] px-4 py-2 font-bold text-white">下一页</Link> : null}
          </div>
        </nav>
      ) : null}
    </div>
  )
}
