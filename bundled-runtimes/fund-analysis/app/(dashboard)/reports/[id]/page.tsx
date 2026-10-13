import ReportDetailClient from './ReportDetailClient'

export default async function ReportDetailPage({ params, searchParams }: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ returnTo?: string | string[] }>
}) {
  const [{ id }, query] = await Promise.all([params, searchParams])
  const returnTo = Array.isArray(query.returnTo) ? query.returnTo[0] : query.returnTo
  return <ReportDetailClient key={id} reportId={id} returnTo={returnTo} />
}
