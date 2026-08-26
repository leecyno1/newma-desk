'use client'

import type { ReactNode } from 'react'
import type { FundResearchWorkspace, FundSelection } from '@/lib/newma-desk/context'
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
  useFundResearchDeskAdapter({ workspace, selection: initialSelection })

  return (
    <main
      className="newma-fund-mod"
      data-vibe-page="1.0"
      data-vibe-title={workspace.title}
      data-vibe-mod-id={workspace.modId}
    >
      {children}
    </main>
  )
}
