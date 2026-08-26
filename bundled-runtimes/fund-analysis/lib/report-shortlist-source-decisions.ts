export type ShortlistSourceDecisionCard = {
  windCode: string
  fundName: string
  label: string
  latestConclusion: string
  nextAction: string
  bullets: string[]
  hardBoundary: string
  reviewFreshnessStatus: string
  reviewFreshnessLabel: string
  reviewFreshnessDetail: string
}

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

const asTrimmedStringArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : []

const cleanMarkdownValue = (value: string) =>
  value
    .replace(/\*\*/g, '')
    .replace(/。$/u, '')
    .trim()

const splitEvidenceBullets = (value: string) =>
  cleanMarkdownValue(value)
    .split(/[；;]/u)
    .map((item) => item.trim())
    .filter(Boolean)

function markdownLine(section: string, label: string) {
  const match = section.match(new RegExp(`^-\\s+${label}：(.+)$`, 'mu'))
  return cleanMarkdownValue(match?.[1] || '')
}

function parseMarkdownShortlistSourceDecisions(content: string): ShortlistSourceDecisionCard[] {
  if (!content.includes('来源决策留痕')) return []
  return content
    .split(/\n(?=###\s+\d+\.\s+)/u)
    .map((section) => {
      const heading = section.match(/^###\s+\d+\.\s+(.+?)（([^）]+)）/mu)
      const label = markdownLine(section, '来源决策留痕')
      const latestConclusion = markdownLine(section, '来源结论')
      const nextAction = markdownLine(section, '来源下一步')
      const bullets = splitEvidenceBullets(markdownLine(section, '来源关键依据'))
      const hardBoundary = markdownLine(section, '来源硬边界')
      const reviewFreshness = markdownLine(section, '复查时效')
      const [reviewFreshnessLabel, ...reviewFreshnessDetailParts] = reviewFreshness.split(/[；;]/u)
      return {
        windCode: String(heading?.[2] || '').trim().toUpperCase(),
        fundName: String(heading?.[1] || heading?.[2] || '').trim(),
        label,
        latestConclusion: latestConclusion === '待补' ? '' : latestConclusion,
        nextAction,
        bullets: bullets.filter((item) => item !== '待补'),
        hardBoundary,
        reviewFreshnessStatus: '',
        reviewFreshnessLabel: String(reviewFreshnessLabel || '').trim(),
        reviewFreshnessDetail: reviewFreshnessDetailParts.join('；').trim(),
      }
    })
    .filter((card) => card.windCode || card.fundName || card.label || card.latestConclusion || card.nextAction || card.bullets.length || card.hardBoundary || card.reviewFreshnessLabel)
}

function structuredShortlistSourceDecisionCards(members: unknown[]): ShortlistSourceDecisionCard[] {
  return members
    .map((member) => {
      const record = asRecord(member)
      const label = String(record.sourceDecisionLabel || '').trim()
      return {
        windCode: String(record.windCode || '').trim().toUpperCase(),
        fundName: String(record.fundName || record.windCode || '').trim(),
        label,
        latestConclusion: String(record.sourceDecisionLatestConclusion || '').trim(),
        nextAction: String(record.sourceDecisionNextAction || '').trim(),
        bullets: asTrimmedStringArray(record.sourceDecisionBullets),
        hardBoundary: String(record.sourceDecisionHardBoundary || '').trim(),
        reviewFreshnessStatus: String(record.reviewFreshnessStatus || '').trim(),
        reviewFreshnessLabel: String(record.reviewFreshnessLabel || '').trim(),
        reviewFreshnessDetail: String(record.reviewFreshnessDetail || '').trim(),
      }
    })
    .filter((card) => card.windCode || card.fundName || card.label || card.latestConclusion || card.nextAction || card.bullets.length || card.hardBoundary || card.reviewFreshnessLabel)
}

export function shortlistSourceDecisionCards(
  members: unknown[],
  options: { content?: string } = {},
): ShortlistSourceDecisionCard[] {
  const structured = structuredShortlistSourceDecisionCards(members)
  if (structured.length) return structured
  return parseMarkdownShortlistSourceDecisions(options.content || '')
}
