import EvidenceCoverageClient from './EvidenceCoverageClient'
import EvidenceRecordsClient from './EvidenceRecordsClient'

export const dynamic = 'force-dynamic'

export default async function EvidenceCoveragePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams
  const query = Object.fromEntries(Object.entries(params).flatMap(([key, value]) => value === undefined ? [] : [[key, Array.isArray(value) ? value[0] : value]]))
  if (query.section === 'materials' || query.section === 'review-events') return <EvidenceRecordsClient key={JSON.stringify(query)} section={query.section} query={query} />
  return <EvidenceCoverageClient />
}
