import PendingReviewClient from './PendingReviewClient'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '待确认收件箱',
}

export default function PendingReviewPage() {
  return <PendingReviewClient />
}
