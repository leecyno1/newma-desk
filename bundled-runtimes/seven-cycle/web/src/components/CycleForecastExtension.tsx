import { AlertCircle, CheckCircle2, Search, TrendingUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useResearchData } from '../hooks/useResearchData'
import { loadForecastExtension } from '../lib/data'
import LoadingState from './LoadingState'
import PlotlyCanvas from './PlotlyCanvas'

const colors = ['#58c9ed', '#f2aa4c', '#7dd3a7', '#9e83ef', '#ef7282', '#79a7ff', '#c8d36a', '#d68ed4', '#a6b5c4']
const phaseLabels: Record<string, string> = {
  p_recovery: '复苏',
  p_expansion: '扩张',
  p_downturn: '放缓',
  p_contraction: '收缩',
}

function percent(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function dominantPhase(point: Record<string, any>) {
  const entries = Object.entries(phaseLabels).map(([key, label]) => ({ label, probability: Number(point[key] ?? 0) }))
  return entries.sort((left, right) => right.probability - left.probability)[0]
}

export default function CycleForecastExtension() {
  const { data, error } = useResearchData(loadForecastExtension)
  const [date, setDate] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const categories = useMemo(
    () => data ? ['全部', ...Array.from(new Set(data.assetConditionalForecasts.map((asset) => asset.category)))] : [],
    [data],
  )
  const forecastDates = useMemo(() => {
    if (!data?.forecast.length) return []
    const indices = [2, 5, 11, data.forecast.length - 1]
    return Array.from(new Set(indices.map((index) => data.forecast[Math.min(index, data.forecast.length - 1)].date)))
  }, [data])
  const effectiveDate = date && forecastDates.includes(date) ? date : forecastDates[2] ?? forecastDates[0] ?? ''
  const filteredAssets = useMemo(() => {
    if (!data) return []
    const normalized = query.trim().toLowerCase()
    return data.assetConditionalForecasts.filter((asset) => {
      const categoryMatch = category === '全部' || asset.category === category
      const queryMatch = !normalized || `${asset.name} ${asset.category}`.toLowerCase().includes(normalized)
      return categoryMatch && queryMatch
    })
  }, [category, data, query])
  const chart = useMemo(() => {
    const chartCategories = Array.from(new Set(filteredAssets.map((asset) => asset.category)))
    return {
      data: chartCategories.map((item, categoryIndex) => {
        const assets = filteredAssets.filter((asset) => asset.category === item)
        const points = assets.map((asset) => asset.path.find((point) => point.date === effectiveDate)).filter(Boolean) as any[]
        const pointAssets = assets.filter((asset) => asset.path.some((point) => point.date === effectiveDate))
        return {
          type: 'scatter', mode: 'markers', name: item,
          x: points.map((point) => point.phaseMixAnnVol),
          y: points.map((point) => point.phaseMixAnnReturn),
          text: pointAssets.map((asset) => asset.name),
          customdata: pointAssets.map((asset) => [asset.assetId]),
          marker: {
            size: pointAssets.map((asset) => asset.confidence === 'high' ? 11 : asset.confidence === 'medium' ? 8 : 6),
            color: colors[categoryIndex % colors.length], opacity: 0.78, line: { color: '#08111f', width: 1 },
          },
          hovertemplate: '%{text}<br>条件年化收益 %{y:.1%}<br>条件年化波动 %{x:.1%}<extra></extra>',
        }
      }),
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 58, r: 22, t: 18, b: 52 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        xaxis: { title: '预测相位混合年化波动', tickformat: '.0%', gridcolor: '#1d3146' },
        yaxis: { title: '预测相位混合年化收益', tickformat: '.0%', gridcolor: '#1d3146', zerolinecolor: '#657c91' },
        legend: { orientation: 'h', y: 1.12, font: { size: 9 } }, hovermode: 'closest',
      },
    }
  }, [effectiveDate, filteredAssets])

  if (!data) return <LoadingState error={error} />
  const selected = filteredAssets.find((asset) => asset.assetId === selectedId)
    ?? data.assetConditionalForecasts.find((asset) => asset.assetId === selectedId)
    ?? filteredAssets[0]
    ?? data.assetConditionalForecasts[0]
  const selectedPoint = selected?.path.find((point) => point.date === effectiveDate)
  const horizonPoints = [3, 6, 12].map((months) => {
    const point = data.forecast[Math.min(months - 1, data.forecast.length - 1)]
    return { months, point, phase: dominantPhase(point) }
  })

  return (
    <section className="cycle-forecast-extension" id="forecast-extension">
      <div className="integrated-forecast-heading">
        <div>
          <span>C4 预测已并入七周期研究</span>
          <h2>虚线延伸与资产条件风险—收益</h2>
          <p>上方周期图保留原预测虚线；这里展开该 vintage 的模型门槛、阶段概率和资产条件分布。</p>
        </div>
        <div className="integrated-forecast-status"><AlertCircle size={16} /><span>{data.meta.data_as_of} vintage · 已滞后 {data.meta.stale_months_at_build} 个月</span></div>
      </div>

      <div className="forecast-summary-grid">
        {horizonPoints.map(({ months, point, phase }) => (
          <article key={months}>
            <span>原预测 {months} 个月 · {point.date}</span>
            <strong>{phase.label} {percent(phase.probability, 0)}</strong>
            <small>状态中位数 {point.median.toFixed(2)}σ · 区间 {point.low.toFixed(2)}—{point.high.toFixed(2)}</small>
          </article>
        ))}
        <article className="forecast-model-card">
          <span>样本外模型</span>
          <strong>{data.qualifiedModels.join(' / ') || '无通过模型'}</strong>
          <small>{data.modelSummary.filter((model) => model.publish_eligible).length} 个候选通过发布门槛</small>
        </article>
      </div>

      <div className="integrated-model-list">
        {data.modelSummary.map((model) => (
          <div className={`model-row ${model.publish_eligible ? 'qualified' : ''}`} key={model.model}>
            {model.publish_eligible ? <CheckCircle2 size={17} /> : <span className="model-dot" />}
            <div><strong>{model.model}</strong><small>{model.governance_eligible === false && model.qualified_horizons >= 2 ? `统计通过 ${model.qualified_horizons}/3 · 治理排除` : `通过 ${model.qualified_horizons}/3 个期限`}</small></div>
            <dl><div><dt>MAE</dt><dd>{model.mean_mae.toFixed(3)}</dd></div><div><dt>相位准确率</dt><dd>{(model.mean_phase_accuracy * 100).toFixed(1)}%</dd></div></dl>
          </div>
        ))}
      </div>

      <div className="asset-forecast-header integrated">
        <div><span>C4 条件情景</span><h2>各类资产风险—收益预测图</h2><p>基于预测相位概率与历史 C4 相位收益/波动混合，不是完整七周期绝对收益预测。</p></div>
        <div className="forecast-controls">
          <label className="search-control"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索资产" /></label>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select>
          <div className="segmented small">{forecastDates.map((item) => <button key={item} className={effectiveDate === item ? 'active' : ''} onClick={() => setDate(item)}>{item}</button>)}</div>
        </div>
      </div>
      <div className="asset-forecast-grid integrated">
        <PlotlyCanvas className="asset-risk-return-chart" data={chart.data} layout={chart.layout} onClick={(point) => setSelectedId(point?.customdata?.[0] ?? null)} />
        <aside className="forecast-asset-inspector">
          <span>{selected?.category}</span><h3>{selected?.name}</h3><div className="forecast-point-date">{effectiveDate}</div>
          <dl className="metric-list">
            <div><dt>条件年化收益</dt><dd className={(selectedPoint?.phaseMixAnnReturn ?? 0) >= 0 ? 'positive' : 'negative'}>{percent(selectedPoint?.phaseMixAnnReturn)}</dd></div>
            <div><dt>条件年化波动</dt><dd>{percent(selectedPoint?.phaseMixAnnVol)}</dd></div>
            <div><dt>当月 C4 关联</dt><dd>{percent(selectedPoint?.c4AssociationMonthly, 2)}</dd></div>
            <div><dt>样本外 R²</dt><dd>{selected?.oosR2?.toFixed(3) ?? '—'}</dd></div>
          </dl>
          <div className="horizon-impact-list"><span>累计 C4 关联贡献</span>{Object.entries(selected?.horizonAssociationImpact ?? {}).map(([horizon, value]) => <div key={horizon}><span>{horizon} 个月</span><strong>{percent(value, 2)}</strong></div>)}</div>
          <div className="forecast-caveat"><TrendingUp size={16} /><p>{selected?.caveat}</p></div>
        </aside>
      </div>
    </section>
  )
}
