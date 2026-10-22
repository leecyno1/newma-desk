import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { readPageSession, restorePageRoute, pageRoute, writePageSession, type PageSession } from '../lib/pageSession'
import { getPageSessionScope, subscribePageSession, getResearchSessionRevision, subscribeResearchSession, researchAccessReady } from '../lib/vibedesk'

const SessionContext = createContext<{
  session: PageSession
  save: () => void
} | null>(null)

function ScopedPageSession({ scope, entry, children }: { scope: string | null; entry: string; children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const session = useRef<PageSession | null>(null)
  if (!session.current) {
    try { session.current = scope ? readPageSession(window.sessionStorage, scope) : { route: '/', views: {} } }
    catch { session.current = { route: '/', views: {} } }
  }
  const [ready, setReady] = useState(false)
  const save = () => {
    if (!scope) return
    try { writePageSession(window.sessionStorage, scope, session.current!) } catch { /* storage disabled */ }
  }
  useLayoutEffect(() => {
    const target = restorePageRoute(entry, session.current!.route, window.self !== window.top)
    navigate(target, { replace: true })
    setReady(true)
  }, [])
  useEffect(() => {
    if (!ready) return
    session.current!.route = pageRoute(location.pathname + location.search + location.hash) ?? '/'
    save()
  }, [ready, location.pathname, location.search, location.hash])
  return ready ? <SessionContext.Provider value={{ session: session.current, save }}>{children}</SessionContext.Provider> : null
}

export function PageSessionBoundary({ children }: { children: ReactNode }) {
  const scope = useSyncExternalStore(subscribePageSession, getPageSessionScope)
  const revision = useSyncExternalStore(subscribeResearchSession, getResearchSessionRevision)
  const location = useLocation()
  const entry = useRef(location.pathname + location.search + location.hash)
  if (!researchAccessReady()) return <section role="status">等待 Desk 周期读取授权；未使用匿名研究快照。</section>
  return <ScopedPageSession key={`${scope ?? 'unconnected'}:${revision}`} scope={scope} entry={entry.current}>{children}</ScopedPageSession>
}

// Values are public view preferences only, never data responses or action/run state.
export function usePageState<T>(key: string, initial: T, decode: (value: unknown) => T): [T, Dispatch<SetStateAction<T>>] {
  const context = useContext(SessionContext)
  const [value, setValue] = useState<T>(() => context && key in context.session.views ? decode(context.session.views[key]) : initial)
  useEffect(() => {
    if (!context) return
    context.session.views[key] = value
    context.save()
  }, [value, context])
  return [value, setValue]
}
