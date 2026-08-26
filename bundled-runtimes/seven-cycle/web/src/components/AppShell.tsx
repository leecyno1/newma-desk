import { Activity, ChartNoAxesCombined, Database, Waves } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { to: '/', label: '市场曲面', icon: Waves },
  { to: '/cycles', label: '七周期研究', icon: Activity },
  { to: '/assets', label: '资产统计', icon: ChartNoAxesCombined },
  { to: '/audit', label: '数据与校准', icon: Database },
]

export default function AppShell() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">C</span>
          <div>
            <strong>Circle</strong>
            <span>全球周期与资产研究</span>
          </div>
        </div>
        <nav className="primary-nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}>
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="version-mark">
          <span className="live-dot" />
          研究版 2026.08
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
