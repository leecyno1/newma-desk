import { CheckCircle2, CircleAlert, Database, ShieldCheck } from 'lucide-react'

export type FundDataQualityCheck = {
  key: string
  passed: boolean
  message: string
  missingFields: string[]
  source: string
  value: string
  notApplicable: boolean
  observations: number
  coverageDays: number
  startDate: string
  endDate: string
  metricCount: number
  windows: string[]
}

export type FundDataQualitySnapshot = {
  score: number | null
  status: string
  summary: string
  checks: FundDataQualityCheck[]
  issues: string[]
  asOfDate: string
  fundDataAsOf: string
  profileAsOf: string
  researchLatestDate: string
  evidenceMissingItems: string[]
}

const checkLabels: Record<string, string> = {
  fund_base: '基金基础档案',
  research_profile: '专业分类与基准',
  manager_tenure_start: '现任经理任期',
  nav_coverage: '净值历史覆盖',
  metric_snapshots: '评价指标快照',
}

const sourceLabels: Record<string, string> = {
  standardized_classification: '标准化分类目录',
  fund_research_profiles: '基金研究画像',
  'tushare.fund_manager': 'Tushare 基金经理档案',
  'metric_snapshots.1y.observations': '1 年指标快照',
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function checkDetail(check: FundDataQualityCheck) {
  if (check.key === 'nav_coverage') {
    const range = check.startDate && check.endDate ? `${formatDate(check.startDate)} 至 ${formatDate(check.endDate)}` : '区间待补'
    return `${range} · ${check.observations || 0} 个净值日`
  }
  if (check.key === 'metric_snapshots') {
    return `${check.metricCount || 0} 条指标 · ${check.windows.length ? check.windows.join(' / ') : '窗口待补'}`
  }
  if (check.source) return `来源：${sourceLabels[check.source] || check.source}`
  if (check.value) return check.key === 'manager_tenure_start' ? `团队起点 ${formatDate(check.value)}` : check.value
  if (check.missingFields.length) return `缺失：${check.missingFields.join('、')}`
  return check.notApplicable ? '当前基金类别不使用该项' : '已核验'
}

export default function FundDataQualityPanel({ snapshot }: { snapshot: FundDataQualitySnapshot }) {
  const complete = snapshot.status === 'complete'
  const passedCount = snapshot.checks.filter((check) => check.passed).length

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><ShieldCheck className="h-4 w-4" />数据可信度</div>
          <h2 className="mt-2 text-lg font-bold text-[#1d2923]">{snapshot.summary || '尚未完成基础数据质量检查。'}</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">只表示分类、净值、经理任期和指标等输入是否齐全，不代表基金未来表现。</p>
        </div>
        <div className={`min-w-[7rem] border px-4 py-3 text-center ${complete ? 'border-[#b9d5c8] bg-[#f2f8f4]' : 'border-[#e2c995] bg-[#fff9ea]'}`}>
          <div className="text-[10px] font-bold text-[#6b7770]">输入完整度</div>
          <div className={`mt-1 text-2xl font-bold ${complete ? 'text-[#17604a]' : 'text-[#856222]'}`}>{snapshot.score == null ? '待检查' : `${snapshot.score}/100`}</div>
          <div className="mt-1 text-[10px] text-[#7d8882]">{passedCount} / {snapshot.checks.length || 5} 项通过</div>
        </div>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-5">
        {snapshot.checks.map((check) => (
          <article key={check.key} className="bg-white p-4">
            <div className="flex items-center justify-between gap-2">
              <strong className="text-xs text-[#34423b]">{checkLabels[check.key] || check.key}</strong>
              {check.passed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-[#28745c]" /> : <CircleAlert className="h-4 w-4 shrink-0 text-[#a16f24]" />}
            </div>
            <p className={`mt-3 text-xs font-bold ${check.passed ? 'text-[#28654f]' : 'text-[#8a6220]'}`}>{check.message}</p>
            <p className="mt-2 text-[10px] leading-5 text-[#87918c]">{checkDetail(check)}</p>
          </article>
        ))}
      </div>

      <div className="grid border-t border-[#e1e6e2] md:grid-cols-[minmax(0,1fr)_minmax(18rem,0.65fr)]">
        <div className="p-5 sm:p-6">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#26342d]"><Database className="h-4 w-4 text-[#28745c]" />数据日期</h3>
          <div className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
            <div><span className="text-[#7c8781]">评价数据截至</span><strong className="ml-2 text-[#34423b]">{formatDate(snapshot.asOfDate)}</strong></div>
            <div><span className="text-[#7c8781]">基金数据截至</span><strong className="ml-2 text-[#34423b]">{formatDate(snapshot.fundDataAsOf)}</strong></div>
            <div><span className="text-[#7c8781]">研究画像更新</span><strong className="ml-2 text-[#34423b]">{formatDate(snapshot.profileAsOf)}</strong></div>
            <div><span className="text-[#7c8781]">最新关联纪要</span><strong className="ml-2 text-[#34423b]">{formatDate(snapshot.researchLatestDate)}</strong></div>
          </div>
        </div>
        <div className="border-t border-[#e1e6e2] bg-[#f8faf8] p-5 sm:p-6 md:border-l md:border-t-0">
          <h3 className="text-sm font-bold text-[#26342d]">其他研究证据</h3>
          {snapshot.evidenceMissingItems.length ? (
            <ul className="mt-3 space-y-2 text-xs leading-5 text-[#735d31]">
              {snapshot.evidenceMissingItems.slice(0, 4).map((item) => <li key={item} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#b2812e]" />{item}</li>)}
            </ul>
          ) : <p className="mt-3 text-xs leading-6 text-[#567068]">当前未发现额外证据缺口。</p>}
        </div>
      </div>
    </section>
  )
}
