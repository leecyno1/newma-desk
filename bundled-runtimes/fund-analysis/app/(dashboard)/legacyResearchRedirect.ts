import { redirect } from 'next/navigation'
import { mergedResearchRouteTarget, type MergedResearchRoutePath } from '@/lib/research-platform/routes'

export function redirectToMergedResearchRoute(pathname: MergedResearchRoutePath): never {
  redirect(mergedResearchRouteTarget(pathname))
}
