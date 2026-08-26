export type ResearchRouteQuery = URLSearchParams | Record<string, string | number | boolean | null | undefined>

function toSearchParams(query?: ResearchRouteQuery) {
  const params = new URLSearchParams()
  if (!query) return params
  if (query instanceof URLSearchParams) {
    query.forEach((value, key) => params.set(key, value))
    return params
  }
  Object.entries(query).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    params.set(key, String(value))
  })
  return params
}

export function researchHref(pathname: string, query?: ResearchRouteQuery) {
  const params = toSearchParams(query)
  const search = params.toString()
  return search ? `${pathname}?${search}` : pathname
}

export function evidenceCoverageHref(query?: ResearchRouteQuery) {
  return researchHref('/evidence-coverage', query)
}

export function marketResearchHref(query?: ResearchRouteQuery) {
  return researchHref('/market', query)
}

export function peerComparisonHref(query?: ResearchRouteQuery) {
  return researchHref('/analysis/comparison', query)
}

export function researchListHref(query?: ResearchRouteQuery) {
  return researchHref('/market', {
    ...Object.fromEntries(toSearchParams(query).entries()),
    view: 'research-lists',
  })
}

export function materialEvidenceHref(query?: ResearchRouteQuery) {
  const params = toSearchParams(query)
  params.set('section', 'materials')
  return researchHref('/evidence-coverage', params)
}

export function reviewEventsHref(query?: ResearchRouteQuery) {
  const params = toSearchParams(query)
  params.set('section', 'review-events')
  return researchHref('/evidence-coverage', params)
}

export const mergedResearchRouteSources = {
  '/investor-selection': 'merged-investor-selection',
  '/pools': 'merged-pools',
  '/rankings': 'merged-rankings',
  '/alerts': 'merged-alerts',
  '/sales-rules': 'merged-sales-rules',
} as const

export type MergedResearchRoutePath = keyof typeof mergedResearchRouteSources

export function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

export function canonicalResearchHref(href: string) {
  const value = href.trim()
  if (!value.startsWith('/')) return value
  const [pathname, rawQuery = ''] = value.split('?')
  const params = new URLSearchParams(rawQuery)
  const query = Object.fromEntries(params.entries())
  if (pathname === '/investor-selection') return marketResearchHref({ ...query, source: params.get('source') || mergedResearchRouteSources[pathname] })
  if (pathname === '/pools') return researchListHref({ ...query, source: params.get('source') || mergedResearchRouteSources[pathname] })
  if (pathname === '/rankings') return peerComparisonHref({ ...query, source: params.get('source') || mergedResearchRouteSources[pathname] })
  if (pathname === '/alerts') return reviewEventsHref({ ...query, source: params.get('source') || mergedResearchRouteSources[pathname] })
  if (pathname === '/sales-rules') return materialEvidenceHref({ ...query, source: params.get('source') || mergedResearchRouteSources[pathname] })
  return value
}

export function mergedResearchRouteTarget(pathname: MergedResearchRoutePath) {
  return canonicalResearchHref(pathname)
}
