export type ResearchActionPriority = 'high' | 'medium' | 'low'

export type ResearchAction = {
  key: string
  label: string
  href?: string
  priority: ResearchActionPriority
  reason: string
}
