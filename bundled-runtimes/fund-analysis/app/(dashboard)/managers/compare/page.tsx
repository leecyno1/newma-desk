import ManagerComparisonClient from './ManagerComparisonClient'

export const dynamic = 'force-dynamic'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

function values(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value
  return value ? [value] : []
}

export default async function ManagerComparisonPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams
  const managerIds = values(params.manager_id).map((item) => item.trim()).filter(Boolean).slice(0, 4)
  const productCodes = values(params.product_code).map((item) => item.trim().toUpperCase())
  const category = values(params.category)[0]?.trim() || ''

  return (
    <ManagerComparisonClient
      initialManagerIds={managerIds}
      initialProductCodes={productCodes}
      initialCategory={category}
    />
  )
}
