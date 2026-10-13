'use client'

import { createContext, useContext, useEffect } from 'react'
import type { FundPageObservation } from './context'

// Optional adapter seam: standalone pages have no provider and do not publish.
export const FundPageDataContext = createContext<((data: FundPageObservation | undefined, section?: string) => void) | null>(null)
export const FundNavigationContext = createContext<((pathname: string, search: string) => boolean) | null>(null)

export function useFundPageData(data: FundPageObservation, section = 'page') {
  const publish = useContext(FundPageDataContext)
  useEffect(() => {
    publish?.(data, section)
    return () => publish?.(undefined, section)
  }, [data, publish, section])
}

export function FundServerPageData({ data }: { data: FundPageObservation }) {
  useFundPageData(data)
  return null
}
