import type { CompanyEvidence } from './company';

export function chainHandoffUrl(base: string, evidence: CompanyEvidence, sourceId: string, identity?: {user: string; workspace: string}) {
  const source = evidence?.revenueGroups.find(item => item.sourceId === sourceId);
  if (!evidence || !identity || !source?.group) return null;
  const url = new URL(base);
  url.searchParams.set('modSearch', new URLSearchParams({
    sourceModule: 'industry-prosperity', sourceWorkbookId: evidence.workbookId, sourceId,
    sourceUpdatedAt: evidence.savedAt, sourceUserId: identity.user, sourceWorkspaceId: identity.workspace,
    industry: evidence.industry,
  }).toString());
  return url.href;
}
