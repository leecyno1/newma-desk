import ResearchLibraryClient from './ResearchLibraryClient'

export default async function ResearchLibraryPage({ searchParams }: { searchParams: Promise<{ search?: string }> }) {
  const { search = '' } = await searchParams
  return <ResearchLibraryClient initialQuery={search} />
}
