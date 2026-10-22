import { BarChart3, ChevronDown, Compass, FlaskConical, Layers3, LineChart, Maximize2, RotateCcw, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import MarketSurfacePlot, { type SurfaceCameraPreset, type SurfaceMode, type SurfaceView, type TimeRange } from '../components/MarketSurfacePlot'
import IndicatorContributionHistory from '../components/IndicatorContributionHistory'
import LoadingState from '../components/LoadingState'
import StatusBadge from '../components/StatusBadge'
import { useResearchData } from '../hooks/useResearchData'
import { loadCycleResearch, loadMarketSurface } from '../lib/data'
import { marketTrackRole, sortMarketTracks } from '../lib/marketTracks'
import { publishVibeDeskContext, registerVibeDeskContextProvider, registerVibeDeskUiActionHandler, registerVibeDeskVisualCaptureProvider } from '../lib/vibedesk'
import { createMarketControls, marketComparison, marketControlAction } from '../lib/marketControls'
import type { MarketTrack } from '../types'
import { usePageState } from '../hooks/usePageSession'
import { pageChoice, pageFlag, pageText } from '../lib/pageSession'

function formatValue(value: number | null | undefined, unit = '') {
  if (value == null || !Number.isFinite(value)) return '不可用'
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 3 })}${unit ? ` ${unit}` : ''}`
}

function monthIndex(value: string) {
  const [year, month] = value.split('-').map(Number)
  return year * 12 + (month || 1)
}

function trackLagMonths(asOf: string, track: MarketTrack) {
  return Math.max(0, monthIndex(asOf) - monthIndex(track.coverage.end))
}

function forecastBridgeGapMonths(track: MarketTrack) {
  if (!track.forecast.bridge) return 0
  return Math.max(0, monthIndex(track.forecast.bridge.date) - monthIndex(track.coverage.end))
}

function pngDataUrlBytes(dataUrl: string) {
  const payload = dataUrl.slice('data:image/png;base64,'.length)
  const padding = payload.endsWith('==') ? 2 : payload.endsWith('=') ? 1 : 0
  return Math.floor(payload.length * 3 / 4) - padding
}

export default function MarketSurfacePage() {
  const marketState = useResearchData(loadMarketSurface)
  const cycleState = useResearchData(loadCycleResearch)
  const [selectedIds, setSelectedIds] = usePageState<string[]>('market.tracks', [], value => Array.isArray(value)
    ? [...new Set(value.filter((item): item is string => typeof item === 'string' && item.length <= 120))].slice(0, 24) : [])
  const [expanded, setExpanded] = usePageState('market.drawer', false, value => pageFlag(value, false))
  const [query, setQuery] = usePageState('market.query', '', value => pageText(value))
  const [group, setGroup] = usePageState<'all' | 'market' | 'economic'>('market.group', 'all', value => pageChoice(value, ['all', 'market', 'economic'], 'all'))
  const mode: SurfaceMode = 'governed'
  const [view, setView] = usePageState<SurfaceView>('market.view', 'heatmap', value => pageChoice(value, ['heatmap', '2d', '3d'], 'heatmap'))
  const [range, setRange] = usePageState<TimeRange>('market.range', '5y', value => pageChoice(value, ['5y', '20y', '50y', 'all'], '5y'))
  const [showForecast, setShowForecast] = usePageState('market.forecast', true, value => pageFlag(value, true))
  const [cameraRevision, setCameraRevision] = useState(0)
  const [cameraPreset, setCameraPreset] = usePageState<SurfaceCameraPreset>('market.camera', 'overview', value => pageChoice(value, ['overview', 'top', 'along-track', 'along-time'], 'overview'))
  const [selectedPoint, setSelectedPoint] = useState<{ trackId: string; index: number; forecast?: boolean } | null>(null)
  const [comparisonDate, setComparisonDate] = usePageState<string | null>('market.comparison', null,
    value => typeof value === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : null)
  const controls = useRef<ReturnType<typeof createMarketControls> | null>(null)

  useEffect(() => {
    const controller = createMarketControls(state => {
      setSelectedIds(state.selectedTrackIds)
      setView(state.view)
      setRange(state.timeRange)
      setShowForecast(state.forecastLayer === 'history-and-forecast')
      setComparisonDate(state.comparisonDate)
      setSelectedPoint(null)
    })
    controls.current = controller
    const unregister = registerVibeDeskUiActionHandler(controller.perform)
    return () => { unregister(); controller.cancel(); controls.current = null }
  }, [])

  const market = marketState.data
  const cycleResearch = cycleState.data
  const activeIds = selectedIds.length ? selectedIds : market?.meta.defaultTrackIds ?? []
  const selectedTracks = useMemo(
    () => sortMarketTracks(activeIds.map((id) => market?.tracks.find((track) => track.id === id)).filter(Boolean) as MarketTrack[]),
    [activeIds, market],
  )
  const filteredTracks = useMemo(() => {
    if (!market) return []
    const normalized = query.trim().toLowerCase()
    return market.tracks.filter((track) => {
      const groupMatch = group === 'all' || track.group === group
      const queryMatch = !normalized || `${track.label} ${track.category} ${track.sourceCode}`.toLowerCase().includes(normalized)
      return groupMatch && queryMatch
    })
  }, [group, market, query])
  const { visible: visibleComparisonDates, newest: newestComparisonDate, effective: effectiveComparisonDate } = useMemo(
    () => marketComparison(selectedTracks, range, comparisonDate), [selectedTracks, range, comparisonDate],
  )
  const comparisonRows = selectedTracks.flatMap((track) => {
    const index = track.dates.indexOf(effectiveComparisonDate)
    const value = index >= 0 ? track.governedStack[index] : null
    return value != null && Number.isFinite(value) ? [{ id: track.id, label: track.label, value }] : []
  })
  const comparisonPositive = comparisonRows.filter((row) => row.value > 0).length
  const comparisonNegative = comparisonRows.filter((row) => row.value < 0).length
  const comparisonHigh = comparisonRows.reduce<(typeof comparisonRows)[number] | null>((best, row) => !best || row.value > best.value ? row : best, null)
  const comparisonLow = comparisonRows.reduce<(typeof comparisonRows)[number] | null>((best, row) => !best || row.value < best.value ? row : best, null)
  const today = new Date()
  const selectedObservationEnds = selectedTracks.map((track) => track.coverage.end).sort()
  const oldestObservation = selectedObservationEnds[0] ?? market?.meta.asOf ?? ''
  const newestObservation = selectedObservationEnds.at(-1) ?? market?.meta.asOf ?? ''
  const marketLagMonths = market ? Math.max(0, today.getFullYear() * 12 + today.getMonth() + 1 - monthIndex(oldestObservation)) : 0
  const staleSelectedTracks = selectedTracks.filter((track) => Math.max(0, today.getFullYear() * 12 + today.getMonth() + 1 - monthIndex(track.coverage.end)) > 1).length
  const forecastLagMonths = market ? Math.max(0, today.getFullYear() * 12 + today.getMonth() + 1 - monthIndex(market.meta.forecastVintage)) : 0
  const marketFreshness = market && marketLagMonths <= 1 ? 'fresh' : 'stale'

  useEffect(() => {
    const unregister = registerVibeDeskContextProvider(() => {
      if (!market || !cycleResearch) return null
      const selectedTrackIds = selectedIds.length ? selectedIds : market.meta.defaultTrackIds
      const tracks = sortMarketTracks(selectedTrackIds
        .map((id) => market.tracks.find((track) => track.id === id))
        .filter(Boolean) as MarketTrack[])
      const focusedTrack = tracks.find((track) => track.id === (selectedPoint?.trackId ?? selectedTrackIds[0])) ?? tracks[0]
      const focusedIndex = selectedPoint?.index ?? Math.max(0, (focusedTrack?.dates.length ?? 1) - 1)
      const forecastPoint = view !== 'heatmap' && showForecast && Boolean(selectedPoint?.forecast)
      const focusedDate = forecastPoint
        ? focusedTrack?.forecast.dates[focusedIndex]
        : focusedTrack?.dates[focusedIndex]
      const cycleComposite = forecastPoint
        ? focusedTrack?.forecast.median[focusedIndex]
        : focusedTrack?.governedStack[focusedIndex]
      const limitedDirections = cycleResearch.governance.cycles.flatMap((cycle) => {
        const publication = cycleResearch.diagnostics?.[cycle.id]?.directionPublication
        return publication?.status === 'limited'
          ? [{ id: cycle.id, name: cycle.name, label: publication.label, asOf: publication.asOf, current: publication.currentLabel }]
          : []
      })

      return {
        view: { id: 'market-surface', title: '全球周期—市场曲面' },
        visibleBlocks: [
          { id: 'surface-toolbar', type: 'controls', title: '曲面筛选与视角' },
          { id: 'surface-stage', type: view === '3d' ? 'plotly-3d' : view === 'heatmap' ? 'plotly-heatmap' : 'plotly-2d', title: '周期识别市场曲面' },
          ...(view === 'heatmap' ? [{ id: 'surface-cross-section', type: 'metrics', title: '同月截面' }] : [{ id: 'track-rail', type: 'selection-list', title: '周期传导轨道' }]),
          { id: 'point-inspector', type: 'metrics', title: focusedTrack?.label ?? '轨道指标' },
          { id: 'cycle-direction-panel', type: 'evidence', title: '通过样本外门槛的周期方向层' },
        ],
        selection: {
          selectedTrackIds,
          focusedTrackId: focusedTrack?.id,
          focusedTrackLabel: focusedTrack?.label,
          focusedDate,
          pointLayer: forecastPoint ? 'forecast' : 'history',
          comparisonDate: view === 'heatmap' ? effectiveComparisonDate : null,
        },
        filters: {
          view,
          timeRange: range,
          forecastLayer: view !== 'heatmap' && showForecast ? 'history-and-forecast' : 'history-only',
          cameraPreset,
          trackGroup: group,
          trackQuery: query,
          trackDrawerExpanded: expanded,
        },
        data: {
          asOf: oldestObservation,
          source: 'Circle Seven Cycle Research',
          freshness: marketFreshness,
          summary: {
            contextSource: 'structured-page-provider',
            methodology: '图中颜色或高度为 C4 + C6 周期识别合成的标准化轨道变化率，不是资产收益或组合建议。热图仅显示历史观测，不显示预测。',
            freshness: {
              marketData: { status: marketFreshness, oldestObservation, newestObservation, staleSelectedTracks, lagMonths: marketLagMonths, researchBuildAsOf: market.meta.asOf },
              forecast: {
                status: forecastLagMonths <= 1 ? 'fresh' : 'stale',
                vintage: market.meta.forecastVintage,
                staleMonths: forecastLagMonths,
              },
            },
            market: {
              asOf: market.meta.asOf,
              selectedObservationRange: { oldest: oldestObservation, newest: newestObservation },
              staleSelectedTracks,
              snapshotGenerated: market.meta.generated,
              trackCount: market.meta.trackCount,
              selectedTrackCount: tracks.length,
              forecastVintage: market.meta.forecastVintage,
              forecastStaleMonths: forecastLagMonths,
              forecastTrackCounts: market.meta.forecastTrackCounts,
              refreshPolicy: '这是 Circle 已发布研究快照；网页刷新只重新读取同一快照，必须重新生成研究数据才能更新观测期和预测 vintage。',
            },
            focusedTrack: focusedTrack ? {
              id: focusedTrack.id,
              label: focusedTrack.label,
              category: focusedTrack.category,
              source: focusedTrack.source,
              sourceCode: focusedTrack.sourceCode,
              frequency: focusedTrack.frequency,
              transform: focusedTrack.transform,
              proxyStatus: focusedTrack.proxyStatus,
              coverage: focusedTrack.coverage,
              date: focusedDate,
              rawValue: forecastPoint ? null : focusedTrack.raw[focusedIndex],
              change: forecastPoint ? null : focusedTrack.change[focusedIndex],
              standardizedChange: forecastPoint ? null : focusedTrack.standardized[focusedIndex],
              cycleComposite,
              forecastStatus: focusedTrack.forecast.status,
              forecastInterval: forecastPoint ? {
                low: focusedTrack.forecast.low[focusedIndex],
                median: focusedTrack.forecast.median[focusedIndex],
                high: focusedTrack.forecast.high[focusedIndex],
              } : null,
              forecastJudgment: focusedTrack.forecast.judgment ?? null,
              caveat: focusedTrack.caveat ?? null,
            } : null,
            selectedTracks: tracks.map((track) => ({
              id: track.id,
              label: track.label,
              category: track.category,
              coverageEnd: track.coverage.end,
              proxyStatus: track.proxyStatus,
              forecastStatus: track.forecast.status,
            })),
            availableTracks: market.tracks.map(({ id, label, group }) => ({ id, label, group })),
            crossSection: view === 'heatmap' ? {
              date: effectiveComparisonDate,
              observed: comparisonRows.length,
              selected: selectedTracks.length,
              rising: comparisonPositive,
              falling: comparisonNegative,
              highest: comparisonHigh,
              lowest: comparisonLow,
              spread: comparisonHigh && comparisonLow ? comparisonHigh.value - comparisonLow.value : null,
              rule: '仅按相同观测月的历史 C4+C6 周期合成比较；缺失值不补齐，正负方向不等于投资收益或配置建议。',
            } : null,
            limitedCycleDirections: limitedDirections,
          },
        },
        actions: [marketControlAction],
        tasks: [],
      }
    })
    controls.current?.commit(market && cycleResearch ? {
      view, timeRange: range, selectedTrackIds: activeIds,
      forecastLayer: view !== 'heatmap' && showForecast ? 'history-and-forecast' : 'history-only',
      comparisonDate: view === 'heatmap' ? effectiveComparisonDate : null,
    } : null, market?.tracks ?? [])
    void publishVibeDeskContext()
    return unregister
  }, [cameraPreset, comparisonHigh?.id, comparisonHigh?.value, comparisonLow?.id, comparisonLow?.value, comparisonNegative, comparisonPositive, comparisonRows.length, cycleResearch, effectiveComparisonDate, expanded, forecastLagMonths, group, market, marketFreshness, marketLagMonths, newestObservation, oldestObservation, query, range, selectedIds, selectedPoint, selectedTracks.length, showForecast, staleSelectedTracks, view])

  useEffect(() => registerVibeDeskVisualCaptureProvider(async ({ maxBytes }) => {
    const element = document.querySelector<HTMLElement>('.surface-stage .surface-plot') as any
    if (!element?._fullLayout) return null
    const rect = element.getBoundingClientRect()
    const width = Math.max(640, Math.min(1600, Math.round(rect.width)))
    const height = Math.max(420, Math.min(1000, Math.round(rect.height)))
    const Plotly = (await import('plotly.js-dist-min')).default
    let dataUrl = await Plotly.toImage(element, { format: 'png', width, height, scale: 1 })
    let outputWidth = width
    let outputHeight = height
    if (pngDataUrlBytes(dataUrl) > maxBytes) {
      outputWidth = Math.min(width, 1024)
      outputHeight = Math.min(height, 640)
      dataUrl = await Plotly.toImage(element, {
        format: 'png',
        width: outputWidth,
        height: outputHeight,
        scale: 1,
      })
    }
    return {
      dataUrl,
      width: outputWidth,
      height: outputHeight,
      title: `全球周期—市场曲面 · ${view === 'heatmap' ? '同期热图' : view === '3d' ? '3D' : '2D'} · ${range}${view === '3d' ? ` · ${cameraPreset}` : ''}`,
    }
  }), [cameraPreset, range, view])

  if (!market || !cycleResearch) return <LoadingState error={marketState.error ?? cycleState.error} />

  const pointTrack = selectedTracks.find((track) => track.id === (selectedPoint?.trackId ?? activeIds[0])) ?? selectedTracks[0]
  const pointIndex = selectedPoint?.index ?? Math.max(0, (pointTrack?.dates.length ?? 1) - 1)
  const isForecast = view !== 'heatmap' && showForecast && Boolean(selectedPoint?.forecast)
  const pointDate = isForecast ? pointTrack?.forecast.dates[pointIndex] : pointTrack?.dates[pointIndex]
  const pointTrackLag = pointTrack ? trackLagMonths(market.meta.asOf, pointTrack) : 0
  const pointForecastGap = pointTrack ? forecastBridgeGapMonths(pointTrack) : 0
  const pointStack = isForecast
    ? pointTrack?.forecast.median[pointIndex]
    : mode === 'governed'
      ? pointTrack?.governedStack[pointIndex]
      : pointTrack?.researchStack[pointIndex]
  const pointContribution = !isForecast && pointTrack?.cycleContribution.status === 'retrospective_diagnostic'
    ? pointTrack.cycleContribution
    : null
  const contributionRows = Object.entries(pointContribution?.paths?.components ?? {}).map(([cycleId, values]) => ({
    cycleId,
    value: values[pointIndex],
  })).filter((row) => row.value != null && Number.isFinite(row.value))
  const contributionAbsoluteTotal = contributionRows.reduce((sum, row) => sum + Math.abs(row.value ?? 0), 0)
  const pointCycleTotal = pointContribution?.paths?.cycleTotal[pointIndex]
  const pointResidual = pointContribution?.paths?.residual[pointIndex]
  const pointBaseline = pointContribution?.paths?.baseline
  const directionSignals = cycleResearch.governance.cycles.flatMap((cycle) => {
    const publication = cycleResearch.diagnostics?.[cycle.id]?.directionPublication
    return publication?.status === 'limited' ? [{ cycle, publication }] : []
  })

  const toggleTrack = (trackId: string) => {
    const current = activeIds
    setSelectedPoint(null)
    if (current.includes(trackId)) {
      const next = current.filter((id) => id !== trackId)
      setSelectedIds(next.length ? next : [market.meta.defaultTrackIds[0]])
      setComparisonDate(null)
      return
    }
    if (current.length >= 24) return
    setSelectedIds([...current, trackId])
    setComparisonDate(null)
  }

  const resetSurface = () => {
    setSelectedIds(market.meta.defaultTrackIds)
    setView('heatmap')
    setRange('5y')
    setShowForecast(true)
    setCameraPreset('overview')
    setCameraRevision((value) => value + 1)
    setSelectedPoint(null)
    setComparisonDate(null)
  }

  const changeCameraPreset = (preset: SurfaceCameraPreset) => {
    setCameraPreset(preset)
    setCameraRevision((value) => value + 1)
  }

  return (
    <div className="page market-page" onClickCapture={() => controls.current?.cancel()} onChangeCapture={() => controls.current?.cancel()}>
      <section className="page-heading market-heading">
        <div>
          <h1>全球周期—市场曲面</h1>
          <p>时间 × 周期分解合成变化率 × 市场与经济轨道。原值、变化、代理和预测资格可逐点复核。</p>
        </div>
        <div className="heading-meta">
          <span>所选轨道观测 {oldestObservation}—{newestObservation} · {staleSelectedTracks} 条滞后超过 1 个月</span>
          <span>预测 vintage {market.meta.forecastVintage} · 距今 {forecastLagMonths} 个月</span>
          <span>{market.meta.trackCount} 条真实/显式代理轨道</span>
        </div>
      </section>

      {marketFreshness === 'stale' && <p className="snapshot-freshness-note">最慢轨道距今 {marketLagMonths} 个月。研究构建基线 {market.meta.asOf} 不是所有轨道的观测期；这是 {market.meta.generated} 生成的研究快照，刷新网页不会更新观测期。</p>}

      <section className="surface-toolbar">
        <span className="surface-track-mode">周期识别轨道 · 默认10条</span>
        <div className="segmented">
          <button aria-pressed={view === 'heatmap'} className={view === 'heatmap' ? 'active' : ''} onClick={() => { setView('heatmap'); setSelectedPoint(null) }}>同期热图</button>
          <button aria-pressed={view === '3d'} className={view === '3d' ? 'active' : ''} onClick={() => { setView('3d'); setSelectedPoint(null) }}>3D 曲面</button>
          <button aria-pressed={view === '2d'} className={view === '2d' ? 'active' : ''} onClick={() => { setView('2d'); setSelectedPoint(null) }}>2D 轨道</button>
        </div>
        <div className="segmented">
          {(['5y', '20y', '50y', 'all'] as TimeRange[]).map((item) => (
            <button key={item} aria-pressed={range === item} className={range === item ? 'active' : ''} onClick={() => setRange(item)}>
              {item === '5y' ? '5年' : item === '20y' ? '20年' : item === '50y' ? '50年' : '全历史'}
            </button>
          ))}
        </div>
        {view !== 'heatmap' && <div className="segmented forecast-layer-toggle">
          <button aria-pressed={showForecast} className={showForecast ? 'active' : ''} onClick={() => setShowForecast(true)}><LineChart size={13} />含预测</button>
          <button aria-pressed={!showForecast} className={!showForecast ? 'active' : ''} onClick={() => { setShowForecast(false); setSelectedPoint(null) }}>仅历史</button>
        </div>}
        <button className="toolbar-button" onClick={() => setExpanded((value) => !value)}>
          <Layers3 size={15} />展开全部轨道 {market.meta.trackCount}<ChevronDown size={14} />
        </button>
        <button className="icon-button" onClick={resetSurface} title="重置视角与轨道"><RotateCcw size={16} /></button>
      </section>

      <section className="surface-model-scope">
        <div><span>曲面高度</span><strong>周期识别合成 · C4 + C6</strong><small>标准化轨道变化率，不是资产收益</small></div>
        <div><span>虚线延伸</span><strong>轨道级条件预测</strong><small>{market.meta.forecastTrackCounts.limited} 条通过 · {market.meta.forecastTrackCounts.blocked} 条阻断</small></div>
        <Link to="/assets"><BarChart3 size={15} /><span>资产风险收益</span><strong>C4 + C5 + C7 独立模型</strong><small>与曲面高度分开验证</small></Link>
      </section>

      <section className={`surface-workspace ${view === 'heatmap' ? 'heatmap-view' : ''} ${expanded ? 'tracks-expanded' : ''}`}>
        <aside className="track-rail">
          <div className="rail-title">
            <span>周期传导轨道</span>
            <strong>{activeIds.length} 条</strong>
          </div>
          <div className="track-list compact">
            {selectedTracks.map((track, index) => (
              <button key={track.id} className={pointTrack?.id === track.id ? 'selected' : ''} onClick={() => setSelectedPoint({ trackId: track.id, index: Math.max(0, track.dates.length - 1) })}>
                <span className="track-index">{String(index + 1).padStart(2, '0')}</span>
                <span><strong>{track.label}</strong><small>{marketTrackRole(track)}</small></span>
                <b className={`track-forecast-state ${track.forecast.status}`}>{track.forecast.status === 'limited' ? '预测' : '阻断'}</b>
                <i className={`identity-dot ${track.proxyStatus}`} />
              </button>
            ))}
          </div>
        </aside>

        <div className="surface-stage">
          <div className="surface-legend">
            <span><i className="legend-line historical" />历史轨道 · {selectedTracks.length} 条</span>
            <span className="surface-color-key"><i className="negative" />回落<i className="neutral" />中性<i className="positive" />上行</span>
            {view === 'heatmap' && <span className="forecast-counts">仅历史观测 · 预测请切换曲线或曲面 · 空白=无数据</span>}
            {view !== 'heatmap' && showForecast && <span className="forecast-legend"><i className="legend-line forecast" />预测虚线与区间 · {market.meta.forecastVintage}</span>}
            {view !== 'heatmap' && showForecast && <span className="forecast-counts">可发布 {market.meta.forecastTrackCounts.limited} · 阻断 {market.meta.forecastTrackCounts.blocked}</span>}
            <span className="surface-note">曲面口径 C4 + C6 · 阻断周期不进入高度</span>
          </div>
          {view === '3d' && (
            <div className="surface-camera-panel">
              <div className="surface-camera-heading"><Compass size={14} /><span>视角</span><small>X 时间 · Y 变化率 · Z 指标</small></div>
              <div className="surface-camera-buttons">
                <button className={cameraPreset === 'overview' ? 'active' : ''} onClick={() => changeCameraPreset('overview')} title="立体查看时间、变化率和指标轨道">总览</button>
                <button className={cameraPreset === 'top' ? 'active' : ''} onClick={() => changeCameraPreset('top')} title="时间 × 指标，适合快速比较全部轨道">俯视</button>
                <button className={cameraPreset === 'along-track' ? 'active' : ''} onClick={() => changeCameraPreset('along-track')} title="时间 × 变化率，观察波峰和波谷">沿轨道</button>
                <button className={cameraPreset === 'along-time' ? 'active' : ''} onClick={() => changeCameraPreset('along-time')} title="指标 × 变化率，观察横截面差异">沿时间</button>
              </div>
            </div>
          )}
          <MarketSurfacePlot tracks={selectedTracks} mode={mode} view={view} range={range} showForecast={showForecast} focusTrackId={view === 'heatmap' ? undefined : pointTrack?.id} cameraRevision={cameraRevision} cameraPreset={cameraPreset} onPoint={(point) => {
            controls.current?.cancel()
            setSelectedPoint(point)
            if (view === 'heatmap') setComparisonDate(selectedTracks.find((track) => track.id === point.trackId)?.dates[point.index] ?? null)
          }} />
          <div className="axis-caption"><Maximize2 size={13} />{view === 'heatmap' ? '悬停看合成值 · 点击读取原值与来源' : view === '3d' ? '拖动旋转 · 滚轮缩放 · 点击读取原值与来源' : '悬停或点击轨道 · 读取原值与来源'}</div>
        </div>

        <aside className="point-inspector">
          <div className="inspector-heading">
            <div>
              <span>{pointTrack?.category}</span>
              <h2>{pointTrack?.label}</h2>
            </div>
            <span className={`identity-label ${pointTrack?.proxyStatus}`}>{pointTrack?.proxyStatus === 'proxy' ? '显式代理' : '直接数据'}</span>
          </div>
          <div className="inspector-date-row">
            <div className="inspector-date">{pointDate ?? '无可用时点'}</div>
            {pointTrack && <small className={`track-freshness ${pointTrackLag >= 12 ? 'stale' : pointTrackLag >= 3 ? 'delayed' : ''}`}>轨道数据截至 {pointTrack.coverage.end} · {pointTrackLag ? `比曲面基线早 ${pointTrackLag} 个月` : '与曲面基线一致'}</small>}
            {pointTrack?.forecast.status === 'limited' && pointTrack.forecast.bridge && pointForecastGap > 1 && <small className="forecast-gap-warning">历史末点与预测桥接相隔 {pointForecastGap} 个月，虚线不代表中间月份实测值</small>}
          </div>
          {view !== 'heatmap' && showForecast && pointTrack?.forecast.status === 'limited' && (
            <div className="forecast-inspector-actions">
              <button className={!isForecast ? 'active' : ''} onClick={() => setSelectedPoint({ trackId: pointTrack.id, index: Math.max(0, pointTrack.dates.length - 1) })}>最新历史</button>
              <button className={isForecast ? 'active' : ''} onClick={() => setSelectedPoint({ trackId: pointTrack.id, index: Math.max(0, pointTrack.forecast.dates.length - 1), forecast: true })}>预测终点</button>
            </div>
          )}
          <dl className="metric-list">
            <div><dt>原始值</dt><dd>{isForecast ? '预测期不适用' : formatValue(pointTrack?.raw[pointIndex], pointTrack?.unit)}</dd></div>
            <div><dt>变化率</dt><dd>{isForecast ? '条件延伸' : formatValue(pointTrack?.change[pointIndex], '变化单位')}</dd></div>
            <div><dt>标准化变化</dt><dd>{isForecast ? '—' : formatValue(pointTrack?.standardized[pointIndex], 'σ')}</dd></div>
            <div><dt>周期合成</dt><dd className={(pointStack ?? 0) >= 0 ? 'positive' : 'negative'}>{formatValue(pointStack, 'σ')}</dd></div>
            {!isForecast && pointContribution && <div><dt>重构基线</dt><dd>{formatValue(pointBaseline, 'σ')}</dd></div>}
            {!isForecast && pointContribution && <div><dt>频带重构</dt><dd className={(pointCycleTotal ?? 0) >= 0 ? 'positive' : 'negative'}>{formatValue(pointCycleTotal, 'σ')}</dd></div>}
            {!isForecast && pointContribution && <div><dt>未解释残差</dt><dd>{formatValue(pointResidual, 'σ')}</dd></div>}
            {isForecast && <div><dt>预测区间</dt><dd>{formatValue(pointTrack?.forecast.low[pointIndex], 'σ')} — {formatValue(pointTrack?.forecast.high[pointIndex], 'σ')}</dd></div>}
          </dl>
          {!isForecast && pointContribution && (
            <div className="cycle-contributions">
              <div className="subsection-title"><span>周期频带影响</span><SlidersHorizontal size={14} /></div>
              {contributionRows.map(({ cycleId, value }) => {
                const blocked = ['C2', 'C3', 'C5', 'C7'].includes(cycleId)
                const share = contributionAbsoluteTotal > 0 ? Math.abs(value ?? 0) / contributionAbsoluteTotal : 0
                return (
                  <div className="contribution-row" key={cycleId}>
                    <span>{cycleId}{blocked ? ' · 探索' : ''}</span>
                    <div><i style={{ width: `${Math.min(100, share * 100)}%` }} className={(value ?? 0) >= 0 ? 'positive' : 'negative'} /></div>
                    <strong>{formatValue(value, 'σ')}</strong><small>{(share * 100).toFixed(0)}%</small>
                  </div>
                )
              })}
              <p className="contribution-method-note">各周期频带与基线、残差逐点加总到标准化指标；占比按频带绝对影响计算。</p>
            </div>
          )}
          <div className="data-identity-box">
            <span>数据身份</span>
            <strong>{pointTrack?.source}</strong>
            <small>{pointTrack?.sourceCode} · {pointTrack?.frequency}频 · {pointTrack?.transform}</small>
            <small>曲面身份：回溯终点估计，不等于真实实时 vintage</small>
            {pointContribution && <small>频带贡献：Gaussian FFT × Butterworth复核 · 拟合R² {((pointContribution.diagnostics?.reconstructionR2 ?? 0) * 100).toFixed(0)}% · 当前严格稳定 {pointContribution.filterRobustness?.stableCycles ?? 0}/{pointContribution.filterRobustness?.comparableCycles ?? 0}</small>}
            {pointTrack?.forecast.status === 'limited' && <small className="forecast-identity">预测层：{pointTrack.forecast.method}</small>}
            {pointTrack?.forecast.status === 'limited' && pointTrack.forecast.judgment && <small className="forecast-identity">模型判断：3个月方向{pointTrack.forecast.judgment.direction3 ?? '不确定'}{pointTrack.forecast.judgment.turningPoint ? ` · 路径首个转折 ${pointTrack.forecast.judgment.turningPoint}` : ''}</small>}
            {pointTrack?.forecast.status === 'blocked' && <small className="forecast-identity">预测层：{pointTrack.forecast.statusReason ?? '未通过轨道级样本外门槛，不绘制虚线'}</small>}
            {pointTrack?.caveat && <p>{pointTrack.caveat}</p>}
          </div>
        </aside>

        {expanded && (
          <div className="track-drawer">
            <div className="drawer-toolbar">
              <label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索轨道、类别或数据代码" /></label>
              <div className="segmented small">
                {(['all', 'market', 'economic'] as const).map((item) => (
                  <button key={item} className={group === item ? 'active' : ''} onClick={() => setGroup(item)}>
                    {item === 'all' ? '全部' : item === 'market' ? `市场 ${market.meta.groupCounts.market}` : `经济 ${market.meta.groupCounts.economic}`}
                  </button>
                ))}
              </div>
            </div>
            <div className="drawer-grid">
              {filteredTracks.map((track) => (
                <button key={track.id} className={activeIds.includes(track.id) ? 'active' : ''} onClick={() => toggleTrack(track.id)}>
                  <span>{track.label}</span>
                  <small>{track.category} · {track.coverage.start}—{track.coverage.end}</small>
                  <i>{track.proxyStatus === 'proxy' ? '代理' : '直接'} · {track.forecast.status === 'limited' ? '预测可用' : '预测阻断'}</i>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {view === 'heatmap' && <section className="surface-cross-section" aria-label="同月截面">
        <div className="cross-section-date"><span>同月截面</span><input type="month" aria-label="对比月份" min={visibleComparisonDates[0]} max={newestComparisonDate} value={effectiveComparisonDate} onChange={(event) => setComparisonDate(event.target.value)} /></div>
        <div><span>同期覆盖</span><strong>{comparisonRows.length} / {selectedTracks.length}</strong><small>缺失不补齐</small></div>
        <div><span>轨道方向</span><strong>{comparisonPositive} 上行 · {comparisonNegative} 回落</strong><small>仅周期合成方向</small></div>
        <div className="cross-section-spread"><span>最大分歧</span><strong>{comparisonHigh && comparisonLow ? `${formatValue(comparisonHigh.value - comparisonLow.value, 'σ')}` : '不可比'}</strong><small>{comparisonHigh && comparisonLow ? `${comparisonHigh.label} ↔ ${comparisonLow.label}` : '需至少两条同期轨道'}</small></div>
        <p>同月历史观测 · C4 + C6 标准化变化；正负方向不等于资产收益或配置建议。</p>
      </section>}

      {pointTrack && (
        <details className="surface-secondary-research">
          <summary><span>{pointTrack.label} · 周期贡献历史</span><small>展开查看逐点守恒、端点修订和各周期贡献路径</small><ChevronDown size={16} /></summary>
          <IndicatorContributionHistory track={pointTrack} />
        </details>
      )}

      <section className="cycle-direction-panel">
        <div className="cycle-direction-heading">
          <div><FlaskConical size={16} /><span>已通过独立样本外门槛的周期方向层</span></div>
          <p>仅展示方向或状态概率，不改变曲面高度，也不等于精确周期、资产收益或配置结论。</p>
        </div>
        <div className="cycle-direction-grid">
          {directionSignals.map(({ cycle, publication }) => (
            <button key={cycle.id} onClick={() => window.location.assign(`/cycles?cycle=${cycle.id}`)}>
              <div className="cycle-direction-title">
                <span>{cycle.id}</span>
                <div><strong>{cycle.name}</strong><small>{publication.label} · {publication.asOf}</small></div>
                <em className="status-badge status-research">{publication.badgeLabel}</em>
              </div>
              <b>{publication.currentLabel}</b>
              <div className="cycle-direction-horizons">
                {publication.horizons.map((horizon) => (
                  <span key={horizon.months}><small>{horizon.label} · {horizon.outcome}</small><strong>{(horizon.probability * 100).toFixed(0)}%</strong><i>验证 {(horizon.accuracy * 100).toFixed(0)}%</i></span>
                ))}
              </div>
              <i className="cycle-direction-caveat">精确周期与资产映射仍阻断</i>
            </button>
          ))}
        </div>
      </section>

      <section className="cycle-status-strip">
        {cycleResearch.governance.cycles.map((cycle) => {
          const publication = cycleResearch.diagnostics?.[cycle.id]?.directionPublication
          return (
            <button key={cycle.id} onClick={() => window.location.assign(`/cycles?cycle=${cycle.id}`)}>
              <span>{cycle.id}</span>
              <strong>{cycle.name}</strong>
              <small>{publication ? `${publication.label} · 精确周期阻断` : `${cycle.centerPriorMonths} 个月中心先验`}</small>
              {publication ? <em className="status-badge status-research">{publication.badgeLabel}</em> : <StatusBadge status={cycle.publication.historical} />}
            </button>
          )
        })}
      </section>
    </div>
  )
}
