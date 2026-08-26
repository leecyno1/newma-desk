import type { PublicationStatus } from '../types'

const labels: Record<PublicationStatus, string> = {
  formal: '正式',
  limited: '受限',
  blocked: '阻断',
  scenario_only: '仅情景',
  calendar_only: '仅日历',
}

export default function StatusBadge({ status }: { status: PublicationStatus }) {
  return <span className={`status-badge status-${status}`}>{labels[status]}</span>
}
