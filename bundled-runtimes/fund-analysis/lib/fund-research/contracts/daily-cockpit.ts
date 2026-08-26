export type DailyCockpitStatus = 'ready' | 'partial' | 'unavailable'
export type DailyCockpitTone = 'positive' | 'neutral' | 'warning' | 'danger'
export type DailyCockpitSourceStatus = 'healthy' | 'stale' | 'unavailable'

export type DailyCockpitTask = {
  id: string
  title: string
  detail: string
  href: string
  tone: DailyCockpitTone
  source: string
  actionId?: string
}

export type DailyCockpitAlert = {
  id: string
  title: string
  detail: string
  severity: 'high' | 'medium' | 'low'
  fundCode?: string
  href: string
}

export type DailyCockpitSource = {
  id: string
  label: string
  detail: string
  asOf?: string
  status: DailyCockpitSourceStatus
}

export type DailyCockpitSelectedFund = {
  id: string
  symbol: string
  name: string
  type: string
  nav: number | null
  navDate: string | null
  totalAsset: number | null
  evidenceCoverage: number | null
  benchmark: string
  peerGroup: string
  styleLabel: string
  managers: string[]
  dataQualityStatus: string
  dataAsOf: string | null
  detailHref: string
}

export type DailyResearchCockpitSnapshot = {
  generatedAt: string
  status: DailyCockpitStatus
  errors: string[]
  brief: {
    label: string
    title: string
    detail: string
    tone: DailyCockpitTone
  }
  metrics: {
    totalFunds: number | null
    evidenceCoverage: number | null
    candidateCount: number | null
    blockedCandidateCount: number | null
    unresolvedAlertCount: number | null
    highAlertCount: number | null
    staleDatasetCount: number | null
    failedSyncCount: number | null
  }
  selectedFund: DailyCockpitSelectedFund | null
  tasks: DailyCockpitTask[]
  alerts: DailyCockpitAlert[]
  sources: DailyCockpitSource[]
}
