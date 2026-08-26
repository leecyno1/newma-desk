import Link from 'next/link'
import {
  AlertCircle,
  BarChart3,
  BookOpenText,
  ClipboardCheck,
  Search,
  UserRoundSearch,
} from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

type HomeSummary = {
  fund_share_count: number
  classified_fund_count: number
  recommendation_ready_category_count: number
  recommendation_ready_fund_count: number
  fund_manager_count: number
  research_memo_count: number
  watchlist_group_count: number
  watchlist_fund_count: number
}

type PeerGroup = {
  key: string
  name: string
  classified_fund_count: number
  recommendation_ready_fund_count: number
  style_ready_fund_count: number
  href: string
}

type Manager = {
  id: string
  name: string
  company?: string | null
  category_labels?: string[]
  current_fund_count?: number
  tenure_metric_fund_count?: number
  memo_count?: number
}

type Memo = {
  id: string
  title: string
  manager_name?: string | null
  report_date?: string | null
  report_date_source?: string | null
  report_date_precision?: string | null
  source?: string | null
  summary?: string | null
  tags?: string[]
  classifications?: string[]
  style_labels?: string[]
  href: string
}

type HomePayload = {
  interface_version: string
  summary: HomeSummary
  featured_peer_groups: PeerGroup[]
  featured_managers: Manager[]
  latest_research_memos: Memo[]
}

const emptySummary: HomeSummary = {
  fund_share_count: 0,
  classified_fund_count: 0,
  recommendation_ready_category_count: 0,
  recommendation_ready_fund_count: 0,
  fund_manager_count: 0,
  research_memo_count: 0,
  watchlist_group_count: 0,
  watchlist_fund_count: 0,
}

async function loadHome() {
  try {
    const [homeRes, pendingRes] = await Promise.all([
      fetch(`${backendApiBaseUrl}/api/home`, { cache: 'no-store' }),
      fetch(`${backendApiBaseUrl}/api/data-health/pending-queue`, { cache: 'no-store' }),
    ])
    const payload = await homeRes.json().catch(() => ({}))
    if (!homeRes.ok) throw new Error(payload.detail || 'home unavailable')
    const pendingPayload = pendingRes.ok ? await pendingRes.json().catch(() => ({})) : {}
    return { data: payload as HomePayload, pendingCount: Number(pendingPayload.total || 0), error: '' }
  } catch {
    return {
      data: {
        interface_version: 'fund_selection_home_v1',
        summary: emptySummary,
        featured_peer_groups: [],
        featured_managers: [],
        latest_research_memos: [],
      } satisfies HomePayload,
      pendingCount: 0,
      error: '后端服务未连接',
    }
  }
}

function n(value: number) {
  return Number(value || 0).toLocaleString('zh-CN')
}

const PASSIVE_PREFIXES = ['指数-', '指数增强-', 'QDII-', '货币-']
function isPassiveGroup(name: string) {
  return PASSIVE_PREFIXES.some((prefix) => name.startsWith(prefix))
}

function formatMemoDate(memo: Memo) {
  const value = memo.report_date?.slice(0, 10)
  if (!value) return '—'
  if (memo.report_date_precision === 'quarter') {
    const month = Number(value.slice(5, 7))
    return `${value.slice(0, 4)}Q${Math.floor((month - 1) / 3) + 1}`
  }
  if (memo.report_date_precision === 'month') return value.slice(0, 7)
  return value
}

export default async function HomePage() {
  const { data, pendingCount, error } = await loadHome()
  const s = data.summary || emptySummary

  return (
    <div className="space-y-4">
      {/* ─── 顶部：搜索 + 数据概览 ─── */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
        <form action="/discover" className="flex h-9 items-center border border-[#d4dbd6] bg-white">
          <Search className="ml-3 h-3.5 w-3.5 shrink-0 text-[#8b978f]" />
          <input name="search" type="search" placeholder="基金名称 / 代码 / 经理 / 公司" className="h-full min-w-0 flex-1 bg-transparent px-2.5 text-xs outline-none placeholder:text-[#a3ada7]" />
          <button type="submit" className="h-full border-l border-[#d4dbd6] bg-[#f5f7f5] px-4 text-xs font-medium text-[#3d5347] hover:bg-[#eaf0eb]">搜索</button>
        </form>
        <div className="flex items-center gap-px overflow-hidden border border-[#d4dbd6] bg-[#d4dbd6] text-xs">
          <Stat label="份额" value={n(s.fund_share_count)} />
          <Stat label="已分类" value={n(s.classified_fund_count)} />
          <Stat label="可评价" value={n(s.recommendation_ready_fund_count)} />
          <Stat label="可出候选" value={`${s.recommendation_ready_category_count} 类`} />
          <Stat label="经理" value={n(s.fund_manager_count)} />
          <Stat label="纪要" value={n(s.research_memo_count)} />
          <Stat label="自选" value={n(s.watchlist_fund_count)} />
        </div>
      </div>

      {error ? <div className="flex items-center gap-2 border border-[#e4c78e] bg-[#fef9ee] px-3 py-2 text-xs text-[#78571f]"><AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}</div> : null}

      {/* ─── 主体三栏 ─── */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,.6fr)]">
        {/* 左列：同类组 + 纪要 */}
        <div className="space-y-3">
          {/* 同类组覆盖 */}
          <section className="border border-[#d9dfda] bg-white">
            <header className="flex items-center justify-between border-b border-[#eaedea] px-4 py-2">
              <span className="flex items-center gap-1.5 text-xs font-bold text-[#1f2d26]"><BarChart3 className="h-3.5 w-3.5 text-[#4a7c64]" />主动基金评价覆盖</span>
              <Link href="/recommendations" className="text-[11px] text-[#4a7c64] hover:underline">全部类别</Link>
            </header>
            <div className="grid gap-px bg-[#eaedea] sm:grid-cols-2 lg:grid-cols-3">
              {data.featured_peer_groups.filter((g) => !isPassiveGroup(g.name)).length ? data.featured_peer_groups.filter((g) => !isPassiveGroup(g.name)).map((group) => (
                <Link key={group.key} href={group.href} className="bg-white px-3 py-2.5 hover:bg-[#f7faf8]">
                  <div className="truncate text-xs font-medium text-[#1f2d26]">{group.name}</div>
                  <div className="mt-1.5 flex items-baseline gap-2 text-[11px] text-[#748079]">
                    <span>{group.classified_fund_count}</span>
                    <span className="font-bold text-[#2b6b4f]">{group.recommendation_ready_fund_count} 可评价</span>
                    {group.style_ready_fund_count ? <span>{group.style_ready_fund_count} 有风格</span> : null}
                  </div>
                </Link>
              )) : <div className="col-span-full px-4 py-6 text-center text-xs text-[#8b978f]">暂无可用同类组</div>}
            </div>
          </section>

          {/* 最近纪要 */}
          <section className="border border-[#d9dfda] bg-white">
            <header className="flex items-center justify-between border-b border-[#eaedea] px-4 py-2">
              <span className="flex items-center gap-1.5 text-xs font-bold text-[#1f2d26]"><BookOpenText className="h-3.5 w-3.5 text-[#4a7c64]" />最近入库纪要</span>
              <Link href="/research" className="text-[11px] text-[#4a7c64] hover:underline">全部</Link>
            </header>
            <div className="divide-y divide-[#eef1ee]">
              {data.latest_research_memos.length ? data.latest_research_memos.map((memo) => {
                const labels = [...(memo.classifications || []), ...(memo.style_labels || []), ...(memo.tags || [])].slice(0, 5)
                return (
                  <Link key={memo.id} href={memo.href} className="flex gap-3 px-4 py-2.5 hover:bg-[#f7faf8]">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-[#1f2d26]">{memo.title || '无标题'}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[#748079]">
                        <span className="font-medium text-[#3d5347]">{memo.manager_name || '经理待确认'}</span>
                        <span>{formatMemoDate(memo)}</span>
                        {labels.map((label) => <span key={label} className="bg-[#f0f3f0] px-1.5 py-0.5 text-[10px]">{label}</span>)}
                      </div>
                      {memo.summary ? <div className="mt-1 line-clamp-1 text-[11px] text-[#8b978f]">{memo.summary}</div> : null}
                    </div>
                  </Link>
                )
              }) : <div className="px-4 py-6 text-center text-xs text-[#8b978f]">纪要库为空</div>}
            </div>
          </section>
        </div>

        {/* 右列：经理研究 + 快捷入口 */}
        <div className="space-y-3">
          {/* 经理研究 */}
          <section className="border border-[#d9dfda] bg-white">
            <header className="flex items-center justify-between border-b border-[#eaedea] px-4 py-2">
              <span className="flex items-center gap-1.5 text-xs font-bold text-[#1f2d26]"><UserRoundSearch className="h-3.5 w-3.5 text-[#4a7c64]" />经理研究覆盖</span>
              <Link href="/managers" className="text-[11px] text-[#4a7c64] hover:underline">全部</Link>
            </header>
            <div className="divide-y divide-[#eef1ee]">
              {data.featured_managers.length ? data.featured_managers.map((manager) => (
                <Link key={manager.id} href={`/managers/${encodeURIComponent(manager.id)}`} className="flex items-center gap-3 px-4 py-2 hover:bg-[#f7faf8]">
                  <span className="grid h-7 w-7 shrink-0 place-items-center bg-[#eaf2ed] text-[11px] font-bold text-[#2b6b4f]">{manager.name?.slice(0, 1) || '?'}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium text-[#1f2d26]">{manager.name || '—'}</span>
                    <span className="block truncate text-[11px] text-[#748079]">{manager.company || ''} {(manager.category_labels || []).join('/')}</span>
                  </span>
                  <span className="text-right text-[11px]">
                    <strong className="text-[#8a6b31]">{manager.memo_count || 0}</strong><span className="text-[#a3ada7]"> 纪要</span>
                  </span>
                </Link>
              )) : <div className="px-4 py-6 text-center text-xs text-[#8b978f]">暂无</div>}
            </div>
          </section>

          {/* 快捷入口 */}
          <section className="border border-[#d9dfda] bg-white">
            <header className="border-b border-[#eaedea] px-4 py-2 text-xs font-bold text-[#1f2d26]">快捷入口</header>
            <nav className="grid grid-cols-2 gap-px bg-[#eaedea]">
              <QuickLink href="/discover" label="基金浏览器" sub="搜索/筛选/净值" />
              <QuickLink href="/compare" label="同类比较" sub="多基金对齐分析" />
              <QuickLink href="/evaluation" label="评价与分类" sub="分类内同类评分" />
              <QuickLink href="/analysis/advanced" label="业绩归因" sub="Brinson/Barra" />
              <QuickLink href="/analysis" label="AI 研究分析" sub="按需运行" />
              <QuickLink href="/recommendations" label="候选生成" sub="按类别/风格" />
              <QuickLink href="/watchlist" label="自选分组" sub={s.watchlist_fund_count ? `${s.watchlist_fund_count} 只` : '—'} />
              <QuickLink href="/research/pending" label="待确认" sub={`${pendingCount} 项`} icon={<ClipboardCheck className="h-3 w-3 text-[#8a6b31]" />} />
            </nav>
          </section>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-3 py-2 text-center">
      <div className="text-sm font-bold text-[#1f2d26]">{value}</div>
      <div className="text-[10px] text-[#748079]">{label}</div>
    </div>
  )
}

function QuickLink({ href, label, sub, icon }: { href: string; label: string; sub: string; icon?: React.ReactNode }) {
  return (
    <Link href={href} className="flex items-center gap-2 bg-white px-3 py-2.5 hover:bg-[#f7faf8]">
      {icon || null}
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-[#1f2d26]">{label}</div>
        <div className="truncate text-[10px] text-[#8b978f]">{sub}</div>
      </div>
    </Link>
  )
}
