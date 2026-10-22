export type PageSession = { route: string; views: Record<string, unknown> }

// Store only known business routes and the cycle deep-link, never gateway/auth queries.
export function pageRoute(value: unknown): string | null {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null
  const url = new URL(value, 'https://cycle.invalid')
  if (url.origin !== 'https://cycle.invalid' || !['/', '/cycles', '/assets', '/audit', '/forecast'].includes(url.pathname)) return null
  const cycle = url.searchParams.get('cycle')
  const query = cycle && /^C[1-7]$/.test(cycle) ? `?cycle=${cycle}` : ''
  return url.pathname + query + (url.hash === '#forecast-extension' ? url.hash : '')
}

export function restorePageRoute(entry: string, saved: unknown, embedded: boolean) {
  // A direct URL always wins. Only an embedded default entry needs route restoration.
  const url = new URL(entry, 'https://cycle.invalid')
  const defaultEntry = url.pathname === '/' && !url.hash
    && [...url.searchParams.keys()].every(key => key === '__newma_mod_version')
  return embedded && defaultEntry ? pageRoute(saved) ?? '/' : pageRoute(entry) ?? '/'
}

export function readPageSession(storage: Pick<Storage, 'getItem'>, scope: string): PageSession {
  try {
    const saved = JSON.parse(storage.getItem(`seven-cycle:page-session:1:${scope}`) ?? 'null')
    return { route: pageRoute(saved?.route) ?? '/',
      views: saved?.views && typeof saved.views === 'object' && !Array.isArray(saved.views) ? saved.views : {} }
  } catch { return { route: '/', views: {} } }
}

export function writePageSession(storage: Pick<Storage, 'setItem'>, scope: string, session: PageSession) {
  try { storage.setItem(`seven-cycle:page-session:1:${scope}`, JSON.stringify(session)) } catch {
    // Storage can be disabled in an iframe; ordinary browsing must remain usable.
  }
}

export function pageChoice<T extends string>(value: unknown, choices: readonly T[], fallback: T): T {
  return typeof value === 'string' && choices.includes(value as T) ? value as T : fallback
}

export const pageText = (value: unknown, fallback = '') => typeof value === 'string' && value.length <= 240 ? value : fallback
export const pageFlag = (value: unknown, fallback: boolean) => typeof value === 'boolean' ? value : fallback
export const pageRecord = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
