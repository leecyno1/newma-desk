'use client'

import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { fundDeskDestination, fundResearchWorkspaceById, type FundPageObservation, type FundResearchWorkspace, type FundSelection } from '@/lib/newma-desk/context'
import { FundNavigationContext, FundPageDataContext } from '@/lib/newma-desk/page-data'
import { useFundResearchDeskAdapter } from '@/lib/newma-desk/use-fund-research-desk-adapter'

export default function FundResearchDeskModule({
  workspace,
  initialSelection,
  children,
}: {
  workspace: FundResearchWorkspace
  initialSelection: FundSelection | null
  children: ReactNode
}) {
  const [sections, setSections] = useState<Record<string, FundPageObservation>>({})
  const setObservation = useCallback((data: FundPageObservation | undefined, section = 'page') => {
    setSections(current => {
      const next = { ...current }
      if (data) next[section] = data
      else delete next[section]
      return next
    })
  }, [])
  const observation = useMemo(() => sections.page ? {
    ...sections.page,
    visibleBlocks: Object.values(sections).flatMap(section => section.visibleBlocks),
    summary: { ...sections.page.summary,
      sections: Object.fromEntries(Object.entries(sections).filter(([key]) => key !== 'page')) },
  } : undefined, [sections])
  const [standaloneHref, setStandaloneHref] = useState<string>()
  const router = useRouter()
  const navigateHost = useFundResearchDeskAdapter({ workspace, selection: initialSelection, observation })
  const navigate = (pathname: string, search: string, hash = '') => {
    const destination = fundDeskDestination(pathname, search)
    if (!destination) return false
    if (window.self === window.top) {
      router.push(destination.href + hash)
    } else if (!navigateHost(fundResearchWorkspaceById(destination.workspace).modId, destination.search)) {
      return false
    }
    return true
  }

  return (
    <main
      className="newma-fund-mod"
      data-vibe-page="1.0"
      data-vibe-title={workspace.title}
      data-vibe-mod-id={workspace.modId}
      onClickCapture={event => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
        const link = (event.target as Element).closest('a')
        if (!link || link.target || link.hasAttribute('download')) return
        const url = new URL(link.href)
        if (url.origin !== window.location.origin) return
        if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return
        event.preventDefault()
        event.stopPropagation()
        if (!navigate(url.pathname, url.search, url.hash)) setStandaloneHref(url.href)
      }}
      onSubmitCapture={event => {
        const form = event.target as HTMLFormElement
        if (!form.hasAttribute('data-desk-navigation') || form.method.toLowerCase() !== 'get' || form.target) return
        const url = new URL(form.action)
        if (url.origin !== window.location.origin) return
        const params = new URLSearchParams()
        for (const [key, value] of new FormData(form)) if (typeof value === 'string') params.append(key, value)
        if (navigate(url.pathname, params.toString())) { event.preventDefault(); event.stopPropagation() }
      }}
    >
      {standaloneHref ? <div role="status" className="flex items-center gap-3 border-b px-4 py-3 text-sm">
        <span>此功能尚未接入 Desk，当前研究页将保留。</span>
        <a href={standaloneHref} target="_blank" rel="noopener noreferrer" className="underline">独立打开此功能</a>
        <button type="button" onClick={() => setStandaloneHref(undefined)}>关闭提示</button>
      </div> : null}
      <FundNavigationContext.Provider value={navigate}>
        <FundPageDataContext.Provider value={setObservation}>{children}</FundPageDataContext.Provider>
      </FundNavigationContext.Provider>
    </main>
  )
}
