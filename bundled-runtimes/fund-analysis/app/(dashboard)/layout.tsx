import FundWorkspaceShell from '@/components/shell/FundWorkspaceShell'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <FundWorkspaceShell>{children}</FundWorkspaceShell>
}
