import { useEffect, useState } from 'react'

export function useResearchData<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    loader()
      .then((result) => active && setData(result))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : '数据加载失败'))
    return () => {
      active = false
    }
  }, [loader])

  return { data, error }
}
