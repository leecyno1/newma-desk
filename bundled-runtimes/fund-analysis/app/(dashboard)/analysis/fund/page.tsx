import FundAnalysisClient from './FundAnalysisClient'

export default async function FundAnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{
    fundId?: string
    purchasePlan?: string
    plannedAmount?: string
    lumpSumAmount?: string
    monthlyAmount?: string
  }>
}) {
  const {
    fundId = '',
    purchasePlan = 'sip',
    plannedAmount = '',
    lumpSumAmount = '',
    monthlyAmount = '',
  } = await searchParams
  const initialPurchasePlan = purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
  const initialPlannedAmount = plannedAmount || (initialPurchasePlan === 'lump_sum' ? lumpSumAmount : monthlyAmount)
  return (
    <FundAnalysisClient
      initialFundId={fundId}
      initialPurchasePlan={initialPurchasePlan}
      initialPlannedAmount={initialPlannedAmount}
    />
  )
}
