import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import {
  fundResearchWorkspaceById,
  isFundResearchWorkspace,
  type FundSelection,
} from '@/lib/newma-desk/context'
import DiscoverPage from '@/app/(dashboard)/discover/page'
import ResearchLibraryPage from '@/app/(dashboard)/research/page'
import AnalysisPage from '@/app/(dashboard)/analysis/page'
import RecommendationsPage from '@/app/(dashboard)/recommendations/page'
import PerformanceAttributionPage from '@/app/(dashboard)/analysis/advanced/page'
import PortfolioPage from '@/app/(dashboard)/portfolio/page'
import FundDetailPage from '@/app/(dashboard)/funds/[id]/page'
import ComparePage from '@/app/(dashboard)/compare/page'
import ManagersPage from '@/app/(dashboard)/managers/page'
import ManagerDetailPage from '@/app/(dashboard)/managers/[id]/page'
import ManagerComparisonPage from '@/app/(dashboard)/managers/compare/page'
import ReportDetailClient from '@/app/(dashboard)/reports/[id]/ReportDetailClient'
import ReportsPage from '@/app/(dashboard)/reports/page'
import EvidenceCoveragePage from '@/app/(dashboard)/evidence-coverage/page'
import FundResearchDeskModule from './FundResearchDeskModule'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ workspace: string }>
}): Promise<Metadata> {
  const { workspace } = await params
  if (!isFundResearchWorkspace(workspace)) return { title: '基金研究模组' }
  const config = fundResearchWorkspaceById(workspace)
  return {
    title: `${config.title} · 基金研究模组`,
    description: config.purpose,
  }
}

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value
}

async function renderWorkspace(
  workspace: string,
  query: Record<string, string | string[] | undefined>,
  symbol: string | undefined,
) {
  if (workspace === 'discover') {
    if (firstParam(query.view) === 'compare') return ComparePage({ searchParams: Promise.resolve({ codes: query.codes, window: query.window }) })
    if (symbol) {
      return FundDetailPage({ params: Promise.resolve({ id: symbol }) })
    }
    return DiscoverPage({
      searchParams: Promise.resolve({
        peerGroup: query.peerGroup,
        search: query.search,
        availability: query.availability,
      }),
    })
  }
  if (workspace === 'research') {
    if (firstParam(query.view) === 'reports') return <ReportsPage />
    if (firstParam(query.view) === 'evidence') return EvidenceCoveragePage({ searchParams: Promise.resolve(query) })
    if (firstParam(query.view) === 'manager-compare') return ManagerComparisonPage({ searchParams: Promise.resolve(query) })
    if (firstParam(query.view) === 'report' && firstParam(query.reportId)) {
      return <ReportDetailClient reportId={firstParam(query.reportId)!} embedded returnTo={firstParam(query.returnTo)} />
    }
    if (firstParam(query.view) === 'managers') {
      const managerId = firstParam(query.managerId)
      return managerId ? ManagerDetailPage({ params: Promise.resolve({ id: managerId }) })
        : ManagersPage({ searchParams: Promise.resolve(query) })
    }
    return ResearchLibraryPage({
      searchParams: Promise.resolve({ search: firstParam(query.search) }),
    })
  }
  if (workspace === 'analysis') {
    return AnalysisPage({
      searchParams: Promise.resolve({ fundCode: firstParam(query.fundCode) || symbol }),
    })
  }
  if (workspace === 'recommendations') {
    return RecommendationsPage({
      searchParams: Promise.resolve({ category: query.category }),
    })
  }
  if (workspace === 'portfolio') {
    return PortfolioPage()
  }
  return PerformanceAttributionPage({
    searchParams: Promise.resolve({
      fundCode: firstParam(query.fundCode) || symbol,
      benchmark: firstParam(query.benchmark),
      quarter: firstParam(query.quarter),
      run: firstParam(query.run),
    }),
  })
}

export default async function FundResearchWorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ workspace: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [{ workspace }, query] = await Promise.all([params, searchParams])
  if (!isFundResearchWorkspace(workspace)) notFound()

  const symbol = (firstParam(query.symbol) || firstParam(query.fundCode))
    ?.trim()
    .toUpperCase()
    .slice(0, 24)
  const assetType = firstParam(query.assetType) === 'etf' ? 'etf' : 'fund'
  const initialSelection: FundSelection | null = symbol
    ? {
      symbol,
      name: firstParam(query.name)?.trim().slice(0, 80),
      assetType,
    }
    : null
  const content = await renderWorkspace(workspace, query, symbol)
  return (
    <FundResearchDeskModule
      key={`${workspace}:${JSON.stringify(query)}`}
      workspace={fundResearchWorkspaceById(workspace)}
      initialSelection={initialSelection}
    >
      {content}
    </FundResearchDeskModule>
  )
}
