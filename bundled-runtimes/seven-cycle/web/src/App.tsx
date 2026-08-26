import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import AssetsPage from './pages/AssetsPage'
import AuditPage from './pages/AuditPage'
import CyclesPage from './pages/CyclesPage'
import MarketSurfacePage from './pages/MarketSurfacePage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<MarketSurfacePage />} />
        <Route path="cycles" element={<CyclesPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="forecast" element={<Navigate to="/cycles?cycle=C4#forecast-extension" replace />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
