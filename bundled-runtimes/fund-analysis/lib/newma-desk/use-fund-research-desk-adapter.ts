'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef } from 'react'
import {
  createNewmaDeskBridge,
  type NewmaDeskBridge,
} from './bridge'
import {
  buildFundResearchPageContext,
  type FundResearchWorkspace,
  type FundSelection,
  type FundPageObservation,
} from './context'

function selectionHref(workspaceId: string, selection: FundSelection) {
  const params = new URLSearchParams({
    symbol: selection.symbol,
    fundCode: selection.symbol,
    name: selection.name || selection.symbol,
    assetType: selection.assetType,
  })
  return `/mod/fund-research/${workspaceId}?${params.toString()}`
}

export function useFundResearchDeskAdapter({
  workspace,
  selection,
  observation,
}: {
  workspace: FundResearchWorkspace
  selection: FundSelection | null
  observation?: FundPageObservation
}) {
  const router = useRouter()
  const { id: workspaceId, modId } = workspace
  const bridgeRef = useRef<NewmaDeskBridge | null>(null)
  const context = useMemo(
    () => buildFundResearchPageContext({ workspace, selection, observation }),
    [selection, workspace, observation],
  )
  const contextRef = useRef(context)

  useEffect(() => {
    contextRef.current = context
    void bridgeRef.current?.publishContext()
  }, [context])

  useEffect(() => {
    const bridge = createNewmaDeskBridge({
      modId,
      initialContext: contextRef.current,
    })
    bridgeRef.current = bridge
    const unregisterContext = bridge.setContextProvider(() => contextRef.current)
    const unsubscribeEvent = bridge.subscribeEvent((event) => {
      if (event.event !== 'security.selected') return
      if (typeof event.payload.symbol !== 'string') return
      if (!['fund', 'etf'].includes(String(event.payload.assetType ?? 'fund'))) return

      const symbol = event.payload.symbol.trim().toUpperCase().slice(0, 24)
      if (!symbol) return

      router.replace(selectionHref(workspaceId, {
        symbol,
        name: typeof event.payload.name === 'string'
          ? event.payload.name.trim().slice(0, 80)
          : symbol,
        assetType: event.payload.assetType === 'etf' ? 'etf' : 'fund',
      }))
    })

    return () => {
      unregisterContext()
      unsubscribeEvent()
      bridge.close()
      bridgeRef.current = null
    }
  }, [router, workspaceId, modId])

  return (targetModId: string, search: string) => bridgeRef.current?.navigate(targetModId, search) ?? false
}
