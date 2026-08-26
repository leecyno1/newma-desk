import { AlertTriangle, ArrowDownUp, ChevronDown, Search, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { AssetCycleStateForecastData, AssetCycleStateForecastEstimate, AssetCycleStateForecastRow } from '../types'
import PlotlyCanvas from './PlotlyCanvas'
import StatusBadge from './StatusBadge'

const horizonLabels = { '1': '1个月', '3': '3个月', '6': '6个月' } as const
const horizonDescriptions = {
  '1': '逐期选择历史表现更稳的模型',
  '3': '综合多个模型，降低单一模型偏差',
  '6': '相似状态预测，并做双时钟复核',
} as const
const horizonKeys = ['1', '3', '6'] as const
const contributionCycleLabels = { C4: 'C4 库存', C5: 'C5 流动性', C7: 'C7 风偏' } as const
const chartColors = ['#58c9ed', '#f1aa4b', '#69ce9f', '#9b83ef', '#ef6d7c', '#7195ff', '#c4d36b', '#d98bd5', '#94a9ba']
type HorizonKey = keyof typeof horizonLabels
type SortKey = 'status' | 'probability' | 'return' | 'volatility' | 'attribution'
type AttributionFilter = 'all' | 'stable' | 'mixed' | 'low_impact' | 'unstable'

function modelLabel(model: string | null | undefined) {
  if (model === 'state_analog') return '状态近邻'
  if (model === 'state_analog_shrunk') return '稳健状态近邻'
  if (model === 'state_analog_strong_shrink') return '强收缩状态近邻'
  if (model === 'state_analog_recency') return '稳健时间衰减近邻'
  if (model === 'state_ridge') return 'Ridge 特征模型'
  if (model === 'category_context_ridge') return '类别上下文 Ridge'
  if (model === 'state_model_consensus') return '固定规则模型共识'
  if (model === 'nested_model_average') return '嵌套前四模型平均'
  return '—'
}

function percent(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function decimal(value: number | null | undefined, digits = 3) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

function signedPercent(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—'
  const scaled = value * 100
  return `${scaled > 0 ? '+' : ''}${scaled.toFixed(digits)}%`
}

function attributionStabilityLabel(value: string) {
  if (value === 'stable') return '历史表现稳定'
  if (value === 'mixed') return '历史表现混合'
  if (value === 'low_impact') return '周期增量较小'
  return '历史表现不稳定'
}

function attributionStabilityRank(value: string | null | undefined) {
  if (value === 'stable') return 4
  if (value === 'mixed') return 3
  if (value === 'low_impact') return 2
  if (value === 'unstable') return 1
  return 0
}

function median(values: number[]) {
  if (values.length === 0) return null
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle]
}

function evidenceLabel(value: string | null | undefined) {
  if (value === 'strong') return '强'
  if (value === 'moderate') return '中等'
  if (value === 'weak') return '弱'
  return '—'
}

function reasonLabel(reason: string) {
  if (reason === 'passed') return '通过方向、概率、收益三组样本外基准'
  if (reason === 'insufficient_recursive_observations') return '递归样本不足，暂不发布'
  if (reason === 'did_not_beat_all_baselines') return '未同时战胜历史频率和无条件收益基准'
  return reason
}

function reasonCodeLabel(reason: string) {
  const labels: Record<string, string> = {
    direction_above_55: '方向准确率低于 55%',
    direction_beats_baseline: '方向未战胜历史频率基准',
    brier_beats_baseline: '概率校准未战胜基准',
    mae_beats_baseline: '收益误差未战胜无条件基准',
    positive_oos_r2: '样本外 R² 不为正',
    insufficient_recursive_observations: '递归样本不足',
    current_forecast_unavailable: '当前截点无法形成预测分布',
    source_reporting_lag: '官方数据源正常滞后1个月',
    stale_asset_data: '资产数据未刷新到当前截点',
    recent_window_instability: '最近48次递归检验稳定性不足',
    non_overlapping_instability: '非重叠独立路径稳定性不足',
    nested_selection_insufficient: '嵌套外层验证样本不足',
    nested_selection_instability: '历史选模流程未通过外层样本检验',
    nested_selection_recent_instability: '历史选模流程近期稳定性不足',
    recency_half_life_instability: '时间衰减结果未通过36/60/96个月稳健性检验',
    strong_shrink_materiality: '强收缩优势未达到固定增益显著性门槛',
    nested_ensemble_size_instability: '前3/4/5模型组合未全部通过稳健性检验',
    synchronous_reference_instability: '同步参照时钟未重复通过',
  }
  return labels[reason] ?? reason
}

function forecastConclusion(
  horizon: HorizonKey,
  qualified: boolean,
  forecast: AssetCycleStateForecastEstimate | null | undefined,
  reasonCodes: string[],
) {
  if (!forecast) return '当前样本不足，暂不判断。'
  if (!qualified) {
    const reason = reasonCodes[0] ? reasonCodeLabel(reasonCodes[0]) : '历史检验未通过'
    return `研究值暂不采用：${reason}。`
  }
  const direction = forecast.probabilityUp >= .6 ? '偏上涨' : forecast.probabilityUp <= .4 ? '偏下跌' : '方向不明显'
  return `${horizonLabels[horizon]}模型显示${direction}，预期收益 ${percent(forecast.medianReturn)}。`
}

interface Props {
  data: AssetCycleStateForecastData
}

export default function CurrentAssetForecast({ data }: Props) {
  const [horizon, setHorizon] = useState<HorizonKey>('6')
  const [query, setQuery] = useState('')
  const [majorCategory, setMajorCategory] = useState('全部大类')
  const [category, setCategory] = useState('全部')
  const [onlyQualified, setOnlyQualified] = useState(true)
  const [attributionFilter, setAttributionFilter] = useState<AttributionFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const categories = useMemo(
    () => ['全部', ...Array.from(new Set(data.assets.map((asset) => asset.category)))],
    [data.assets],
  )
  const majorCategories = useMemo(
    () => ['全部大类', ...Array.from(new Set(data.assets.map((asset) => asset.majorCategory)))],
    [data.assets],
  )
  const majorCategorySummaries = useMemo(
    () => majorCategories.slice(1).map((item) => {
      const assets = data.assets.filter((asset) => asset.majorCategory === item)
      const research = assets
        .map((asset) => asset.horizons[horizon])
        .filter((result) => result?.forecast)
      const published = research.filter((result) => result.publicationQualified)
      return {
        name: item,
        researchAssets: research.length,
        qualifiedAssets: published.length,
        publishedReturn: median(published.map((result) => result.forecast!.medianReturn)),
        publishedVolatility: median(published.map((result) => result.forecast!.conditionalVol)),
      }
    }),
    [data.assets, horizon, majorCategories],
  )
  const qualifiedAssetRows = useMemo(() => data.assets
    .map((asset) => ({
      asset,
      qualifiedHorizons: horizonKeys.filter((item) => asset.horizons[item]?.publicationQualified && asset.horizons[item]?.forecast),
    }))
    .filter((row) => row.qualifiedHorizons.length > 0)
    .sort((left, right) => right.qualifiedHorizons.length - left.qualifiedHorizons.length
      || Number(right.qualifiedHorizons.at(-1)) - Number(left.qualifiedHorizons.at(-1))
      || left.asset.name.localeCompare(right.asset.name, 'zh-CN')),
  [data.assets])
  const qualifiedMajorCounts = useMemo(() => qualifiedAssetRows.reduce((counts, row) => ({
    ...counts,
    [row.asset.majorCategory]: (counts[row.asset.majorCategory] ?? 0) + 1,
  }), {} as Record<string, number>), [qualifiedAssetRows])
  const visibleAssets = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return data.assets
      .filter((asset) => asset.horizons[horizon])
      .filter((asset) => majorCategory === '全部大类' || asset.majorCategory === majorCategory)
      .filter((asset) => category === '全部' || asset.category === category)
      .filter((asset) => !onlyQualified || asset.horizons[horizon].publicationQualified)
      .filter((asset) => attributionFilter === 'all' || asset.horizons[horizon].cycleAttributionStability?.status === attributionFilter)
      .filter((asset) => !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized))
      .sort((left, right) => {
        const leftHorizon = left.horizons[horizon]
        const rightHorizon = right.horizons[horizon]
        if (sortKey === 'probability') return (rightHorizon.forecast?.probabilityUp ?? -Infinity) - (leftHorizon.forecast?.probabilityUp ?? -Infinity)
        if (sortKey === 'return') return (rightHorizon.forecast?.medianReturn ?? -Infinity) - (leftHorizon.forecast?.medianReturn ?? -Infinity)
        if (sortKey === 'volatility') return (leftHorizon.forecast?.conditionalVol ?? Infinity) - (rightHorizon.forecast?.conditionalVol ?? Infinity)
        if (sortKey === 'attribution') return attributionStabilityRank(rightHorizon.cycleAttributionStability?.status) - attributionStabilityRank(leftHorizon.cycleAttributionStability?.status)
        return Number(rightHorizon.publicationQualified) - Number(leftHorizon.publicationQualified)
          || Number(Boolean(rightHorizon.forecast)) - Number(Boolean(leftHorizon.forecast))
          || (rightHorizon.forecast?.probabilityUp ?? -Infinity) - (leftHorizon.forecast?.probabilityUp ?? -Infinity)
      })
  }, [attributionFilter, category, data.assets, horizon, majorCategory, onlyQualified, query, sortKey])

  const chart = useMemo(() => {
    const chartAssets = visibleAssets.filter((asset) => asset.horizons[horizon].forecast)
    const chartCategories = Array.from(new Set(chartAssets.map((asset) => asset.category)))
    return {
      data: chartCategories.map((item, categoryIndex) => {
        const assets = chartAssets
          .filter((asset) => asset.category === item)
          .map((asset) => ({ asset, forecast: asset.horizons[horizon].forecast! }))
        return {
          type: 'scatter',
          mode: 'markers',
          name: item,
          x: assets.map(({ forecast }) => forecast.conditionalVol),
          y: assets.map(({ forecast }) => forecast.medianReturn),
          text: assets.map(({ asset }) => asset.name),
          customdata: assets.map(({ asset, forecast }) => [
            asset.assetId,
            forecast.probabilityUp,
            forecast.downsideProbability,
            modelLabel(forecast.model),
          ]),
          error_y: {
            type: 'data',
            symmetric: false,
            array: assets.map(({ forecast }) => forecast.high80 - forecast.medianReturn),
            arrayminus: assets.map(({ forecast }) => forecast.medianReturn - forecast.low20),
            color: chartColors[categoryIndex % chartColors.length],
            thickness: 1,
            width: 2,
          },
          marker: {
            size: assets.map(({ asset }) => asset.horizons[horizon].publicationQualified ? 11 : 7),
            symbol: assets.map(({ asset }) => asset.horizons[horizon].publicationQualified ? 'diamond' : 'circle-open'),
            color: chartColors[categoryIndex % chartColors.length],
            opacity: assets.map(({ asset }) => asset.horizons[horizon].publicationQualified ? .9 : .42),
            line: { color: '#08111f', width: 1 },
          },
          hovertemplate: '%{text}<br>%{customdata[3]}<br>上涨概率 %{customdata[1]:.0%}<br>下行概率 %{customdata[2]:.0%}<br>稳健收益估计 %{y:.1%}<br>条件波动 %{x:.1%}<extra></extra>',
        }
      }),
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 62, r: 22, t: 32, b: 54 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        xaxis: { title: '条件波动', tickformat: '.0%', gridcolor: '#1d3146', rangemode: 'tozero' },
        yaxis: { title: '预期收益', tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
        legend: { orientation: 'h', y: 1.15, font: { size: 9 } },
        hovermode: 'closest',
      },
    }
  }, [horizon, visibleAssets])

  const selected = data.assets.find((asset) => asset.assetId === selectedId && visibleAssets.some((visible) => visible.assetId === asset.assetId))
    ?? visibleAssets[0]
  const selectedHorizon = selected?.horizons[horizon]
  const selectedForecast = selectedHorizon?.forecast
  const selectedAttribution = selectedHorizon?.cycleAttribution
  const selectedAttributionStability = selectedHorizon?.cycleAttributionStability
  const selectionValidation = selectedHorizon?.selectionValidation
  const fixedModelPolicy = selectedHorizon?.selectionPolicy === 'fixed_model'
  const selectionUncertainty = selectionValidation?.uncertainty
  const validationTrace = selectedHorizon?.validation.recentTrace ?? []
  const nonOverlapValidation = selectedHorizon?.validation.nonOverlappingValidation
  const validationChart = useMemo(() => ({
    data: [
      {
        type: 'scatter',
        mode: 'lines+markers',
        name: '实际收益',
        x: validationTrace.map((point) => point.date),
        y: validationTrace.map((point) => point.actualReturn),
        line: { color: '#f1aa4b', width: 2 },
        marker: { size: 4 },
        hovertemplate: '预测截点 %{x}<br>实际未来收益 %{y:.1%}<extra></extra>',
      },
      {
        type: 'scatter',
        mode: 'lines',
        name: '当时模型预测',
        x: validationTrace.map((point) => point.date),
        y: validationTrace.map((point) => point.predictedReturn),
        customdata: validationTrace.map((point) => point.probabilityUp),
        line: { color: '#58c9ed', width: 2.5 },
        hovertemplate: '预测截点 %{x}<br>模型收益 %{y:.1%}<br>上涨概率 %{customdata:.0%}<extra></extra>',
      },
      {
        type: 'scatter',
        mode: 'lines',
        name: '历史无条件基准',
        x: validationTrace.map((point) => point.date),
        y: validationTrace.map((point) => point.baselineReturn),
        line: { color: '#7d91a4', width: 1.5, dash: 'dot' },
        hovertemplate: '预测截点 %{x}<br>基准收益 %{y:.1%}<extra></extra>',
      },
    ],
    layout: {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      margin: { l: 62, r: 22, t: 18, b: 48 },
      font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
      xaxis: { title: '当时预测截点', gridcolor: '#1d3146' },
      yaxis: { title: `${horizonLabels[horizon]}未来收益`, tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
      legend: { orientation: 'h', y: 1.12, font: { size: 9 } },
      hovermode: 'x unified',
    },
  }), [horizon, validationTrace])
  const horizonSummary = data.summary.horizons[horizon]
  const stateClock = data.meta.stateClock?.cycles ?? []
  const clockComparison = data.clockComparison?.horizons?.[horizon]
  const topBlockers = Object.entries(horizonSummary.blockedReasonCounts)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5)

  const selectAsset = (asset: AssetCycleStateForecastRow) => setSelectedId(asset.assetId)
  const selectMajorCategory = (value: string) => {
    setMajorCategory(value)
    setCategory('全部')
    setSelectedId(null)
  }
  const selectQualifiedSignal = (asset: AssetCycleStateForecastRow, selectedHorizon: HorizonKey) => {
    setHorizon(selectedHorizon)
    setMajorCategory('全部大类')
    setCategory('全部')
    setOnlyQualified(true)
    setAttributionFilter('all')
    setQuery('')
    setSelectedId(asset.assetId)
  }

  return (
    <section className="current-asset-forecast">
      <div className="current-forecast-heading">
        <div>
          <span>联合周期预测 · {data.meta.includedCycles.join(' + ')} · 截至 {data.meta.assetDataThrough}</span>
          <h2>资产风险收益预测</h2>
          <p>点越高，预期收益越高；越靠右，波动越大；误差线表示历史相似状态区间。</p>
        </div>
        <div className="current-forecast-governance"><ShieldCheck size={16} /><span>默认只看通过历史检验的结果</span></div>
      </div>

      <div className="current-forecast-summary">
        {horizonKeys.map((item) => {
          const summary = data.summary.horizons[item]
          return (
            <button key={item} className={horizon === item ? 'active' : ''} onClick={() => setHorizon(item)}>
              <span>{horizonLabels[item]}</span>
              <strong>{summary.qualifiedAssets}<small> / {summary.validatedAssets} 通过</small></strong>
              <small>{horizonDescriptions[item]}</small>
            </button>
          )
        })}
        <div className="current-forecast-summary-note">
          <span>数据更新</span><strong>{data.summary.refreshedAssets} / {data.summary.assets}</strong><small>滞后 {data.summary.sourceLagAssets} · 过期 {data.summary.staleAssets}</small>
        </div>
      </div>

      <div className="current-forecast-signal-overview">
        <div className="current-forecast-signal-heading">
          <div>
            <span>跨期限通过结果</span>
            <h3>当前可发布资产信号</h3>
            <p>只展示通过完整历史检验的结果；点击任一格进入对应期限的风险收益图。</p>
          </div>
          <div className="current-forecast-signal-counts">
            <strong>{qualifiedAssetRows.length}<small> / {data.assets.length} 条资产</small></strong>
            <span>股票 {qualifiedMajorCounts['股票'] ?? 0} · 债券 {qualifiedMajorCounts['债券'] ?? 0} · 商品 {qualifiedMajorCounts['商品'] ?? 0} · 外汇 {qualifiedMajorCounts['外汇'] ?? 0}</span>
          </div>
        </div>
        <div className="current-forecast-signal-table-wrap">
          <table className="research-table current-forecast-signal-table">
            <thead>
              <tr><th>资产</th>{horizonKeys.map((item) => <th key={item}>{horizonLabels[item]}</th>)}<th>数据截至</th></tr>
            </thead>
            <tbody>
              {qualifiedAssetRows.map(({ asset }) => (
                <tr key={asset.assetId}>
                  <td><strong>{asset.name}</strong><small>{asset.majorCategory} · {asset.category}</small></td>
                  {horizonKeys.map((item) => {
                    const result = asset.horizons[item]
                    const forecast = result?.forecast
                    if (!result?.publicationQualified || !forecast) return <td key={item}><span className="signal-not-qualified">未通过</span></td>
                    return (
                      <td key={item}>
                        <button
                          className={`qualified-signal-cell ${selectedId === asset.assetId && horizon === item ? 'active' : ''}`}
                          onClick={() => selectQualifiedSignal(asset, item)}
                        >
                          <strong className={forecast.medianReturn >= 0 ? 'positive' : 'negative'}>{percent(forecast.medianReturn)}</strong>
                          <small>上涨 {percent(forecast.probabilityUp, 0)} · 5%情景 {percent(forecast.valueAtRisk95)}</small>
                        </button>
                      </td>
                    )
                  })}
                  <td>{asset.dataEnd ?? '—'}<small>{asset.freshnessStatus === 'current' ? '已更新' : asset.freshnessStatus === 'source_lag' ? '源端滞后' : '过期'}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="current-forecast-major-section">
        <div className="current-forecast-major-heading">
          <div><span>大类概览</span><p>点击即可筛选。</p></div>
          <button className={majorCategory === '全部大类' ? 'active' : ''} onClick={() => selectMajorCategory('全部大类')}>全部资产</button>
        </div>
        <div className="current-forecast-major-grid">
          {majorCategorySummaries.map((summary) => (
            <button key={summary.name} className={majorCategory === summary.name ? 'active' : ''} onClick={() => selectMajorCategory(summary.name)}>
              <span>{summary.name}</span>
              <strong>{percent(summary.publishedReturn)}</strong>
              <small>通过资产中位收益</small>
              <em>波动 {percent(summary.publishedVolatility)} · {summary.qualifiedAssets}/{summary.researchAssets} 通过</em>
            </button>
          ))}
        </div>
      </div>

      <div className="current-forecast-toolbar">
        <label className="search-control"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索预测资产" /></label>
        <select value={majorCategory} onChange={(event) => selectMajorCategory(event.target.value)}>{majorCategories.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={attributionFilter} onChange={(event) => setAttributionFilter(event.target.value as AttributionFilter)} aria-label="贡献稳定性筛选">
          <option value="all">全部贡献状态</option>
          <option value="stable">历史表现稳定</option>
          <option value="mixed">历史表现混合</option>
          <option value="low_impact">周期增量较小</option>
          <option value="unstable">历史表现不稳定</option>
        </select>
        <label className="qualified-toggle"><input type="checkbox" checked={onlyQualified} onChange={(event) => setOnlyQualified(event.target.checked)} /><span>仅显示通过资产</span></label>
        <div className="segmented small current-forecast-sort">
          <ArrowDownUp size={14} />
          <button className={sortKey === 'status' ? 'active' : ''} onClick={() => setSortKey('status')}>发布状态</button>
          <button className={sortKey === 'probability' ? 'active' : ''} onClick={() => setSortKey('probability')}>上涨概率</button>
          <button className={sortKey === 'return' ? 'active' : ''} onClick={() => setSortKey('return')}>收益</button>
          <button className={sortKey === 'volatility' ? 'active' : ''} onClick={() => setSortKey('volatility')}>波动</button>
          <button className={sortKey === 'attribution' ? 'active' : ''} onClick={() => setSortKey('attribution')}>贡献稳定性</button>
        </div>
        <span className="row-count">{visibleAssets.length} 条</span>
      </div>

      <div className="current-forecast-visual">
        <PlotlyCanvas
          className="current-forecast-chart"
          data={chart.data}
          layout={chart.layout}
          onClick={(point) => setSelectedId(point?.customdata?.[0] ?? null)}
        />
        <aside className="current-forecast-inspector">
          {selected && selectedHorizon ? (
            <>
              <div className="current-forecast-asset-title">
                <div><span>{selected.category}</span><h3>{selected.name}</h3></div>
                <span className={`forecast-simple-status ${selectedHorizon.publicationQualified ? 'passed' : 'blocked'}`}>{selectedHorizon.publicationQualified ? '通过' : '未通过'}</span>
              </div>
              <div className="forecast-point-date">{horizonLabels[horizon]} · {selected.dataEnd ?? '无数据'}{selected.freshnessStatus === 'source_lag' ? ' · 官方源端滞后1个月' : selected.freshnessStatus === 'stale' ? ` · 过期${selected.lagMonths ?? '—'}个月` : ''}</div>
              <dl className="current-forecast-primary-metrics">
                <div><dt>上涨概率</dt><dd>{percent(selectedForecast?.probabilityUp, 0)}</dd></div>
                <div><dt>预期收益</dt><dd className={(selectedForecast?.medianReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(selectedForecast?.medianReturn)}</dd></div>
                <div className="wide"><dt>常见区间</dt><dd>{percent(selectedForecast?.low20)} — {percent(selectedForecast?.high80)}</dd></div>
                <div><dt>波动率</dt><dd>{percent(selectedForecast?.conditionalVol)}</dd></div>
                <div><dt>较差情景（5%）</dt><dd className="negative">{percent(selectedForecast?.valueAtRisk95)}</dd></div>
                <div className="wide"><dt>极端情景平均</dt><dd className="negative">{percent(selectedForecast?.expectedShortfall95)}</dd></div>
              </dl>
              {selectedHorizon.publicationQualified && selectedAttribution && (
                <div className="current-forecast-cycle-attribution">
                  <div className="current-forecast-cycle-attribution-heading">
                    <strong>周期贡献 · 可加总</strong>
                    <span>当前状态反事实</span>
                  </div>
                  {selectedAttribution.ranking.map((cycleId) => {
                    const contribution = selectedAttribution.contributions[cycleId]
                    return (
                      <div className="current-forecast-cycle-attribution-row" key={cycleId}>
                        <strong>{contributionCycleLabels[cycleId]}</strong>
                        <span>收益 <b className={contribution.medianReturn >= 0 ? 'positive' : 'negative'}>{signedPercent(contribution.medianReturn)}</b></span>
                        <span>概率 <b className={contribution.probabilityUp >= 0 ? 'positive' : 'negative'}>{signedPercent(contribution.probabilityUp)}</b></span>
                        <span>5%情景 <b className={contribution.valueAtRisk95 >= 0 ? 'positive' : 'negative'}>{signedPercent(contribution.valueAtRisk95)}</b></span>
                      </div>
                    )
                  })}
                  {selectedAttributionStability && (
                    <div className={`current-forecast-cycle-stability ${selectedAttributionStability.status}`}>
                      <strong>{attributionStabilityLabel(selectedAttributionStability.status)}</strong>
                      <span>{selectedAttributionStability.observations} 个非重叠截点</span>
                      {selectedAttributionStability.status === 'low_impact'
                        ? <small>当前三周期绝对收益贡献合计仅 {percent(selectedAttributionStability.absoluteCurrentReturnContribution)}，预测主要来自中性基线和资产自身状态。</small>
                        : <small>{contributionCycleLabels[selectedAttributionStability.currentDominantCycle]} 主导保持 {percent(selectedAttributionStability.dominantPersistence, 0)} · 方向同向 {percent(selectedAttributionStability.dominantSignConsistency, 0)}</small>}
                    </div>
                  )}
                  <p>中性基线 {percent(selectedAttribution.baseline.medianReturn)} + 三周期贡献 = 当前预测 {percent(selectedAttribution.full.medianReturn)}。仅表示模型敏感度，不是因果归因。</p>
                </div>
              )}
              <div className={`current-forecast-verdict ${selectedHorizon.publicationQualified ? 'qualified' : ''}`}>
                <strong>{selectedHorizon.publicationQualified ? '通过历史检验' : '未通过历史检验'}</strong>
                <p>{forecastConclusion(horizon, selectedHorizon.publicationQualified, selectedForecast, selectedHorizon.publicationReasonCodes)}</p>
              </div>
            </>
          ) : <div className="current-forecast-empty">当前筛选无资产</div>}
        </aside>
      </div>

      <div className="current-forecast-table-wrap">
        <table className="research-table current-forecast-table">
          <thead><tr><th>资产</th><th>状态</th><th>贡献稳定性</th><th>上涨概率</th><th>预期收益</th><th>常见区间</th><th>波动率</th><th>较差情景（5%）</th><th>历史方向准确率</th></tr></thead>
          <tbody>
            {visibleAssets.map((asset) => {
              const result = asset.horizons[horizon]
              const forecast = result.forecast
              const stability = result.cycleAttributionStability
              return (
                <tr key={asset.assetId} className={`${selected?.assetId === asset.assetId ? 'selected' : ''} ${result.publicationQualified ? 'qualified' : 'blocked'}`} onClick={() => selectAsset(asset)}>
                  <td><strong>{asset.name}</strong><small>{asset.category} · {asset.observations}个月</small></td>
                  <td><span className={`forecast-simple-status ${result.publicationQualified ? 'passed' : 'blocked'}`}>{result.publicationQualified ? '通过' : '未通过'}</span></td>
                  <td className="attribution-stability-cell">
                    {stability ? (
                      <span className={`attribution-stability-badge ${stability.status}`}>
                        <strong>{attributionStabilityLabel(stability.status)}</strong>
                        <small>{stability.status === 'low_impact'
                          ? `绝对贡献 ${percent(stability.absoluteCurrentReturnContribution)}`
                          : `${stability.currentDominantCycle} 主导 ${percent(stability.dominantPersistence, 0)}`}</small>
                      </span>
                    ) : <span className="signal-not-qualified">—</span>}
                  </td>
                  <td>{percent(forecast?.probabilityUp, 0)}</td>
                  <td className={(forecast?.medianReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(forecast?.medianReturn)}</td>
                  <td>{percent(forecast?.low20)} — {percent(forecast?.high80)}</td>
                  <td>{percent(forecast?.conditionalVol)}</td>
                  <td className="negative">{percent(forecast?.valueAtRisk95)}</td>
                  <td>{percent(result.validation.directionAccuracy)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <details className="current-forecast-methods">
        <summary>
          <div><strong>查看方法与验证</strong><span>数据时钟、模型表现、阻断原因和历史验证曲线</span></div>
          <ChevronDown size={17} />
        </summary>
        <div className="current-forecast-method-content">
          <div className="current-forecast-method-overview">
            <div>
              <span>当前期限方法</span>
              <strong>{horizonDescriptions[horizon]}</strong>
              <p>{data.meta.definition}</p>
            </div>
            <div>
              <span>发布过程</span>
              <strong>研究估计 {horizonSummary.researchForecastAssets} · 最终通过 {horizonSummary.qualifiedAssets}</strong>
              <small>全样本通过 {horizonSummary.fullSampleQualifiedAssets} · 嵌套外层 {horizonSummary.nestedQualifiedAssets}/{horizonSummary.nestedValidatedAssets}</small>
              <p className="current-forecast-model-counts">近邻 {horizonSummary.championModels.state_analog} · 收缩 {horizonSummary.championModels.state_analog_shrunk} · 强收缩 {horizonSummary.championModels.state_analog_strong_shrink} · 衰减 {horizonSummary.championModels.state_analog_recency} · Ridge {horizonSummary.championModels.state_ridge} · 类别 Ridge {horizonSummary.championModels.category_context_ridge} · 共识 {horizonSummary.championModels.state_model_consensus} · 组合 {horizonSummary.championModels.nested_model_average}</p>
            </div>
          </div>

          {selected && selectedHorizon && (
            <div className="current-forecast-technical-asset">
              <div className="current-forecast-technical-heading">
                <div><span>当前资产技术详情</span><h3>{selected.name} · {horizonLabels[horizon]}</h3></div>
                <span className="forecast-model-pill">{modelLabel(selectedHorizon.championModel)}</span>
              </div>
              <dl className="metric-list current-forecast-method-metrics">
                <div><dt>治理状态</dt><dd><StatusBadge status={selectedHorizon.status} /></dd></div>
                <div><dt>相似样本数</dt><dd>{selectedForecast?.analogs ?? '—'}</dd></div>
                <div><dt>下行概率</dt><dd>{percent(selectedForecast?.downsideProbability, 0)}</dd></div>
                {selectedForecast?.localWeight != null && <div><dt>局部状态权重</dt><dd>{percent(selectedForecast.localWeight, 0)}</dd></div>}
                {selectedForecast?.halfLifeMonths != null && <div><dt>时间衰减半衰期</dt><dd>{selectedForecast.halfLifeMonths.toFixed(0)}个月</dd></div>}
                {selectedForecast?.componentCount != null && <div><dt>{selectedForecast.model === 'nested_model_average' ? '组合模型数' : '共识模型数'}</dt><dd>{selectedForecast.componentCount}</dd></div>}
                {selectedForecast?.componentModels?.length ? <div><dt>组合成员</dt><dd>{selectedForecast.componentModels.map(modelLabel).join('、')}</dd></div> : null}
                <div><dt>方向准确率</dt><dd>{percent(selectedHorizon.validation.directionAccuracy)}</dd></div>
                <div><dt>样本外 R²</dt><dd>{decimal(selectedHorizon.validation.oosR2)}</dd></div>
                <div><dt>{fixedModelPolicy ? '固定模型方向准确率' : '嵌套外层方向准确率'}</dt><dd>{percent(selectionValidation?.directionAccuracy)}</dd></div>
                <div><dt>{fixedModelPolicy ? '固定模型样本外 R²' : '嵌套外层样本外 R²'}</dt><dd>{decimal(selectionValidation?.oosR2)}</dd></div>
                <div><dt>方向准确率90%区间</dt><dd>{percent(selectionUncertainty?.directionAccuracy.low, 0)} — {percent(selectionUncertainty?.directionAccuracy.high, 0)}</dd></div>
                <div><dt>样本外 R² 90%区间</dt><dd>{decimal(selectionUncertainty?.oosR2.low)} — {decimal(selectionUncertainty?.oosR2.high)}</dd></div>
                <div><dt>统计证据强度</dt><dd>{evidenceLabel(selectionUncertainty?.evidenceStrength)}</dd></div>
                <div><dt>{fixedModelPolicy ? '模型策略' : '历史选模切换次数'}</dt><dd>{fixedModelPolicy ? '固定，不逐资产选模' : selectionValidation?.switches ?? '—'}</dd></div>
                {fixedModelPolicy && <div><dt>同步时钟复核</dt><dd>{selectedHorizon.synchronousReferenceStable ? '通过' : '未通过'}</dd></div>}
                <div><dt>非重叠路径稳定</dt><dd>{horizon === '1' ? '不适用' : nonOverlapValidation ? `${nonOverlapValidation.stablePaths} / ${nonOverlapValidation.eligiblePaths}` : '—'}</dd></div>
                <div><dt>路径中位样本外 R²</dt><dd>{horizon === '1' ? '不适用' : decimal(nonOverlapValidation?.medianOosR2)}</dd></div>
                <div><dt>Brier / 基准</dt><dd>{decimal(selectedHorizon.validation.brier)} / {decimal(selectedHorizon.validation.baseBrier)}</dd></div>
                <div><dt>近期48次稳定性</dt><dd>{selectedHorizon.validation.recentValidation?.passedGateCount ?? 0} / 5</dd></div>
                {selectedHorizon.validation.robustness && <div><dt>半衰期稳健性</dt><dd>{selectedHorizon.validation.robustnessStable ? '36 / 60 / 96个月均通过' : '未全部通过'}</dd></div>}
                {selectedHorizon.validation.challengerMateriality && <div><dt>挑战者增益门槛</dt><dd>{selectedHorizon.validation.challengerMateriality.passed ? '通过' : '未通过'}</dd></div>}
              </dl>
              <div className={`current-forecast-verdict ${selectedHorizon.publicationQualified ? 'qualified' : ''}`}>
                <strong>{selectedHorizon.publicationQualified ? '通过发布门槛' : '完整阻断原因'}</strong>
                <p>{selectedHorizon.publicationQualified ? reasonLabel(selectedHorizon.validation.reason) : '模型、当前预测和数据时效必须同时通过。'}</p>
                {!selectedHorizon.publicationQualified && selectedHorizon.publicationReasonCodes.length > 0 && (
                  <ul>{selectedHorizon.publicationReasonCodes.map((reason) => <li key={reason}>{reasonCodeLabel(reason)}</li>)}</ul>
                )}
              </div>
            </div>
          )}

          <div className="forecast-clock-strip">
            <div className="forecast-clock-title">
              <span>月末可得信息时钟</span>
              <strong>决策月 {data.meta.stateClock?.decisionAsOf ?? data.meta.asOf}</strong>
              <small>C4/C5 使用上月已发布状态，C7 与资产使用当月数据。</small>
            </div>
            {stateClock.map((cycle) => (
              <div key={cycle.cycleId}>
                <span>{cycle.cycleId}</span>
                <strong>使用 {cycle.observationUsed}</strong>
                <small>源数据截至 {cycle.sourceDataThrough} · 滞后 {cycle.availabilityLagMonths} 月</small>
              </div>
            ))}
          </div>

          {clockComparison && (
            <div className="forecast-clock-comparison">
              <div>
                <span>异步实时候选</span>
                <strong>准确率 {percent(clockComparison.asynchronous.directionAccuracyMedian, 1)}</strong>
                <small>Brier {decimal(clockComparison.asynchronous.brierMedian)} · MAE {percent(clockComparison.asynchronous.maeMedian)} · R² {decimal(clockComparison.asynchronous.oosR2Median)}</small>
                <em>{clockComparison.asynchronous.publicationQualifiedAssets} 条正式通过</em>
              </div>
              <div>
                <span>同步修订后参照</span>
                <strong>准确率 {percent(clockComparison.synchronous.directionAccuracyMedian, 1)}</strong>
                <small>Brier {decimal(clockComparison.synchronous.brierMedian)} · MAE {percent(clockComparison.synchronous.maeMedian)} · R² {decimal(clockComparison.synchronous.oosR2Median)}</small>
                <em>{clockComparison.synchronous.publicationQualifiedAssets} 条正式通过</em>
              </div>
              <p>{clockComparison.assetsCompared} 条资产使用共同近期样本对照；同步结果不参与当前发布。</p>
            </div>
          )}

          <div className="current-forecast-gate-strip">
            <div><span>研究估计覆盖</span><strong>{horizonSummary.researchForecastAssets}</strong><small>有模型分布，不代表通过发布</small></div>
            {topBlockers.map(([reason, count]) => (
              <div key={reason}><span>{reasonCodeLabel(reason)}</span><strong>{count}</strong><small>条资产未通过该门槛</small></div>
            ))}
          </div>

          <div className="current-forecast-validation-panel">
            <div className="current-forecast-validation-heading">
              <div>
                <span>{fixedModelPolicy ? '固定模型近期递归样本外记录' : '冠军模型近期递归样本外记录'}</span>
                <h3>{selected?.name ?? '当前资产'} · {horizonLabels[horizon]}实际收益与当时预测</h3>
                <p>每个点只使用该截点以前的数据。图中展示月度滚动结果；正式发布另用互不重叠路径检验。</p>
              </div>
              <div className="current-forecast-validation-metrics">
                <span>近期样本 <strong>{selectedHorizon?.validation.recentValidation?.observations ?? 0}</strong></span>
                <span>方向准确率 <strong>{percent(selectedHorizon?.validation.recentValidation?.directionAccuracy, 0)}</strong></span>
                <span>样本外 R² <strong>{decimal(selectedHorizon?.validation.recentValidation?.oosR2)}</strong></span>
                <span>{fixedModelPolicy ? '固定模型 R²' : '嵌套外层 R²'} <strong>{decimal(selectionValidation?.oosR2)}</strong></span>
                <span>独立路径 <strong>{horizon === '1' ? '不适用' : nonOverlapValidation ? `${nonOverlapValidation.stablePaths}/${nonOverlapValidation.eligiblePaths}` : '—'}</strong></span>
              </div>
            </div>
            {validationTrace.length > 0
              ? <PlotlyCanvas className="current-forecast-validation-chart" data={validationChart.data} layout={validationChart.layout} />
              : <div className="current-forecast-validation-empty">当前资产没有足够的近期递归样本外记录</div>}
            {horizon !== '1' && nonOverlapValidation && (
              <div className="current-forecast-path-audit">
                <div className="current-forecast-path-audit-heading">
                  <div>
                    <span>非重叠独立路径审计</span>
                    <p>按预测起点月份错位拆分；每条路径至少通过 4 / 5 项门槛且样本外 R² 为正，才计为稳定。</p>
                  </div>
                  <strong>{nonOverlapValidation.stablePaths} / {nonOverlapValidation.eligiblePaths} 稳定</strong>
                </div>
                <div className="current-forecast-path-table-wrap">
                  <table className="research-table current-forecast-path-table">
                    <thead><tr><th>路径</th><th>样本</th><th>方向准确率</th><th>样本外 R²</th><th>通过门槛</th><th>结果</th></tr></thead>
                    <tbody>
                      {nonOverlapValidation.paths.map((path) => (
                        <tr key={path.offset} className={path.stable ? 'stable' : 'blocked'}>
                          <td>起点月 {path.offset + 1}</td>
                          <td>{path.observations}</td>
                          <td>{percent(path.directionAccuracy, 0)}</td>
                          <td>{decimal(path.oosR2)}</td>
                          <td>{path.passedGateCount} / 5</td>
                          <td>{path.stable ? '通过' : '阻断'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          <p className="current-forecast-method-caveat">{data.caveat}</p>
        </div>
      </details>

      <div className="current-forecast-caveat"><AlertTriangle size={15} /><p>预测来自历史相似周期状态，不是组合回测或配置建议。</p><span>{horizonLabels[horizon]} · 通过 {horizonSummary.qualifiedAssets} / {horizonSummary.validatedAssets}</span></div>
    </section>
  )
}
