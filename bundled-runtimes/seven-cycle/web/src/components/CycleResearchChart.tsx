import { useMemo } from 'react'
import PlotlyCanvas from './PlotlyCanvas'
import type { CycleResearchData } from '../types'

export default function CycleResearchChart({ cycleId, data }: { cycleId: string; data: CycleResearchData }) {
  const chart = useMemo(() => {
    const commonLayout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      margin: { l: 54, r: 28, t: 22, b: 48 },
      font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 11 },
      xaxis: { gridcolor: '#1d3146', zeroline: false },
      yaxis: { title: '周期水平', gridcolor: '#1d3146', zerolinecolor: '#6a8197' },
      hovermode: 'x unified',
      legend: { orientation: 'h', x: 0, y: 1.12 },
    }
    if (cycleId === 'C1') {
      const c1 = data.C1
      const familyColors = ['#52748a', '#796f91', '#5c8277', '#8c765d', '#65798f', '#7b6e79', '#a5844e']
      return {
        data: [
          ...Object.entries(c1.familySeries).map(([family, values], index) => ({
            type: 'scatter', mode: 'lines', name: family, x: c1.dates, y: values,
            line: { color: familyColors[index % familyColors.length], width: .8 }, opacity: .28, visible: 'legendonly',
          })),
          { type: 'scatter', mode: 'lines', name: '全球实体七家族综合因子', x: c1.dates, y: c1.composite, line: { color: '#8295a7', width: 1.2 } },
          { type: 'scatter', mode: 'lines', name: '35–70年多方法中位分量', x: c1.dates, y: c1.longWave, line: { color: '#5bd0f3', width: 2.5 } },
        ],
        layout: {
          ...commonLayout,
          xaxis: { ...commonLayout.xaxis, title: '年份（1600—2024）' },
          yaxis: { ...commonLayout.yaxis, title: '长期结构研究值（σ）' },
          annotations: [{ x: 0.99, y: 0.03, xref: 'paper', yref: 'paper', text: '解释层：不发布精确相位与预测虚线', showarrow: false, font: { color: '#f2ad55' } }],
        },
      }
    }
    if (cycleId === 'C4') {
      const history = data.C4.cycle
      const forecast = data.C4Forecast.forecast
      const historicalEnd = history[history.length - 1]?.date
      const realtimeTimeline = data.C4Realtime?.timeline ?? []
      const bridge = realtimeTimeline.filter((row: any) => row.date >= historicalEnd && row.date <= data.C4Forecast.meta.data_as_of)
      return {
        data: [
          { type: 'scatter', mode: 'lines', name: '历史高位', x: history.map((row: any) => row.date), y: history.map((row: any) => row.high), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
          { type: 'scatter', mode: 'lines', name: '历史不确定区间', x: history.map((row: any) => row.date), y: history.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(69,190,231,.15)', line: { width: 0 }, hoverinfo: 'skip' },
          { type: 'scatter', mode: 'lines', name: 'C4 历史相位因子', x: history.map((row: any) => row.date), y: history.map((row: any) => row.factor), line: { color: '#54c9ed', width: 2.5 } },
          { type: 'scatter', mode: 'markers', name: '峰谷', x: data.C4.turns.map((row: any) => row.date), y: data.C4.turns.map((row: any) => row.value), text: data.C4.turns.map((row: any) => row.kind === 'peak' ? '峰值' : '谷值'), marker: { color: '#f4ad50', size: 7, symbol: 'diamond' }, hovertemplate: '%{x}<br>%{text} %{y:.2f}<extra></extra>' },
          { type: 'scatter', mode: 'lines+markers', name: 'PMI/PPI 单边桥接', x: bridge.map((row: any) => row.date), y: bridge.map((row: any) => row.rt_level), line: { color: '#69ce9f', width: 2.4, dash: 'dot' }, marker: { color: '#69ce9f', size: 4 }, hovertemplate: '%{x}<br>桥接状态 %{y:.2f}σ<extra></extra>' },
          { type: 'scatter', mode: 'lines', name: '预测高位', x: forecast.map((row: any) => row.date), y: forecast.map((row: any) => row.high), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
          { type: 'scatter', mode: 'lines', name: '预测不确定区间', x: forecast.map((row: any) => row.date), y: forecast.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(244,173,80,.12)', line: { width: 0 }, hoverinfo: 'skip' },
          { type: 'scatter', mode: 'lines', name: 'Ridge 受限预测', x: forecast.map((row: any) => row.date), y: forecast.map((row: any) => row.median), line: { color: '#f4ad50', width: 2.5, dash: 'dash' } },
        ],
        layout: {
          ...commonLayout,
          shapes: [
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: -4, y1: 0, fillcolor: 'rgba(44,83,120,.08)', line: { width: 0 } },
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: 4, fillcolor: 'rgba(32,142,142,.05)', line: { width: 0 } },
          ],
          annotations: [{ x: data.C4Forecast.meta.data_as_of, y: 1.02, xref: 'x', yref: 'paper', text: '桥接 / 预测分界', showarrow: true, arrowcolor: '#f4ad50', font: { color: '#f4ad50' } }],
        },
      }
    }
    if (cycleId === 'C5' && data.diagnostics?.C5?.liquidityState) {
      const liquidity = data.diagnostics.C5.liquidityState
      const addMonths = (date: string, months: number) => {
        const [year, month] = date.split('-').map(Number)
        const value = new Date(Date.UTC(year, month - 1 + months, 1))
        return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}`
      }
      const forecastPath = (liquidity.forecastPath ?? liquidity.currentForecasts)
        .filter((row: any) => row.qualified)
        .sort((left: any, right: any) => left.horizonMonths - right.horizonMonths)
      const scenario = [
        { date: liquidity.current.date, median: liquidity.current.level, low: liquidity.current.level, high: liquidity.current.level },
        ...forecastPath.map((row: any) => ({ date: addMonths(row.asOf, row.horizonMonths), median: row.scenarioLevel, low: row.scenarioLow, high: row.scenarioHigh })),
      ]
      const regimeColors: Record<string, string> = {
        宽松充裕: '#69ce9f', 宽松回落: '#54c9ed', 紧张修复: '#f1aa4b', 紧张加剧: '#9b83ef', 中性改善: '#55c9ed', 中性收紧: '#ef6d7c', 中性稳定: '#8ca0b0',
      }
      return {
        data: [
          { type: 'scatter', mode: 'lines', name: '国内政策流动性', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.domesticPolicy), line: { color: '#69ce9f', width: 1.2 }, opacity: .55, visible: 'legendonly' },
          { type: 'scatter', mode: 'lines', name: '信用传导', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.creditTransmission), line: { color: '#f1aa4b', width: 1.2 }, opacity: .55, visible: 'legendonly' },
          { type: 'scatter', mode: 'lines', name: '全球美元流动性', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.globalDollar), line: { color: '#9b83ef', width: 1.2 }, opacity: .55, visible: 'legendonly' },
          { type: 'scatter', mode: 'lines', name: 'NFCI 独立确认', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.nfciConfirmation), line: { color: '#64798b', width: 1, dash: 'dot' }, opacity: .5, visible: 'legendonly' },
          { type: 'scatter', mode: 'lines', name: '流动性冲击状态', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.state), line: { color: '#8bcfe4', width: 2.2 } },
          { type: 'scatter', mode: 'markers', name: '状态分类', x: liquidity.timeline.map((row: any) => row.date), y: liquidity.timeline.map((row: any) => row.state), text: liquidity.timeline.map((row: any) => row.regime), marker: { color: liquidity.timeline.map((row: any) => regimeColors[row.regime] ?? '#8ca0b0'), size: 4 }, hovertemplate: '%{x}<br>%{text}<br>状态 %{y:.2f}σ<extra></extra>' },
          { type: 'scatter', mode: 'lines', name: '情景上沿', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.high), line: { width: 0, shape: 'spline', smoothing: .55 }, hoverinfo: 'skip', showlegend: false },
          { type: 'scatter', mode: 'lines', name: '历史变化区间', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)', line: { width: 0, shape: 'spline', smoothing: .55 }, hoverinfo: 'skip' },
          { type: 'scatter', mode: 'lines+markers', name: '1–12月直接期限模型', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.median), text: scenario.map((row: any, index: number) => index === 0 ? '当前状态' : `${index}个月后`), line: { color: '#f1aa4b', width: 2.5, dash: 'dash', shape: 'spline', smoothing: .55 }, marker: { color: '#f1aa4b', size: scenario.map((_: any, index: number) => [0, 3, 6, 12].includes(index) ? 6 : 3) }, hovertemplate: '%{x}<br>%{text}<br>条件状态 %{y:.2f}σ<extra></extra>' },
        ],
        layout: {
          ...commonLayout,
          xaxis: { ...commonLayout.xaxis, title: '月份（历史状态 / 受限方向情景）' },
          yaxis: { ...commonLayout.yaxis, title: '流动性冲击状态（σ）' },
          shapes: [
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: -4, y1: 0, fillcolor: 'rgba(91,68,144,.06)', line: { width: 0 } },
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: 4, fillcolor: 'rgba(45,133,104,.05)', line: { width: 0 } },
          ],
          annotations: [
            { x: liquidity.current.date, y: 1.02, xref: 'x', yref: 'paper', text: '历史 / 预测分界', showarrow: true, arrowcolor: '#f1aa4b', font: { color: '#f1aa4b' } },
            { x: .99, y: .03, xref: 'paper', yref: 'paper', text: '三层状态路径可用 · 固定周期与资产预测阻断', showarrow: false, font: { color: '#f1aa4b' } },
          ],
        },
      }
    }
    if (cycleId === 'C7' && data.diagnostics?.C7?.riskAppetiteState) {
      const riskState = data.diagnostics.C7.riskAppetiteState
      const qualified = (riskState.forecastPath ?? riskState.currentForecasts).filter((row: any) => row.qualified).sort((left: any, right: any) => left.horizonMonths - right.horizonMonths)
      const addMonths = (date: string, months: number) => {
        const [year, month] = date.split('-').map(Number)
        const value = new Date(Date.UTC(year, month - 1 + months, 1))
        return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}`
      }
      const scenario = [
        { date: riskState.current.date, median: riskState.current.level, low: riskState.current.level, high: riskState.current.level },
        ...qualified.map((row: any) => ({ date: addMonths(row.asOf, row.horizonMonths), median: row.scenarioLevel, low: row.scenarioLow, high: row.scenarioHigh })),
      ]
      const regimeColors: Record<string, string> = {
        风险偏好扩张: '#69ce9f', 风险偏好高位降温: '#f1aa4b', 风险规避修复: '#55c9ed', 风险规避加深: '#9b83ef', 中性转强: '#54c9ed', 中性转弱: '#ef6d7c', 中性震荡: '#8ca0b0',
      }
      return {
        data: [
          { type: 'scatter', mode: 'lines', name: '风险偏好状态', x: riskState.timeline.map((row: any) => row.date), y: riskState.timeline.map((row: any) => row.state), line: { color: '#8bcfe4', width: 2.2 } },
          { type: 'scatter', mode: 'markers', name: '状态分类', x: riskState.timeline.map((row: any) => row.date), y: riskState.timeline.map((row: any) => row.state), text: riskState.timeline.map((row: any) => row.regime), marker: { color: riskState.timeline.map((row: any) => regimeColors[row.regime] ?? '#8ca0b0'), size: 4 }, hovertemplate: '%{x}<br>%{text}<br>状态 %{y:.2f}σ<extra></extra>' },
          { type: 'scatter', mode: 'lines', name: '情景上沿', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.high), line: { width: 0, shape: 'spline', smoothing: .55 }, hoverinfo: 'skip', showlegend: false },
          { type: 'scatter', mode: 'lines', name: '历史条件区间', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)', line: { width: 0, shape: 'spline', smoothing: .55 }, hoverinfo: 'skip' },
          { type: 'scatter', mode: 'lines+markers', name: '1–5个月风险区间情景', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.median), text: scenario.map((row: any, index: number) => index === 0 ? '当前状态' : `${index}个月后`), line: { color: '#f1aa4b', width: 2.5, dash: 'dash', shape: 'spline', smoothing: .55 }, marker: { color: '#f1aa4b', size: scenario.map((_: any, index: number) => [0, 1, 3, 5].includes(index) ? 6 : 3) }, hovertemplate: '%{x}<br>%{text}<br>条件状态 %{y:.2f}σ<extra></extra>' },
        ],
        layout: {
          ...commonLayout,
          xaxis: { ...commonLayout.xaxis, title: '月份（历史状态 / 1–5个月受限情景）' },
          yaxis: { ...commonLayout.yaxis, title: '风险偏好状态（σ）' },
          shapes: [
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: -4, y1: 0, fillcolor: 'rgba(91,68,144,.06)', line: { width: 0 } },
            { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: 4, fillcolor: 'rgba(45,133,104,.05)', line: { width: 0 } },
          ],
          annotations: [
            { x: riskState.current.date, y: 1.02, xref: 'x', yref: 'paper', text: '历史 / 预测分界', showarrow: true, arrowcolor: '#f1aa4b', font: { color: '#f1aa4b' } },
            { x: .99, y: .03, xref: 'paper', yref: 'paper', text: '预测未来处于风险偏好区间的概率 · 不等于继续上涨', showarrow: false, font: { color: '#f1aa4b' } },
          ],
        },
      }
    }
    if (cycleId === 'C6') {
      return {
        data: [
          { type: 'bar', name: '月份结构', x: data.C6.monthPattern.map((row: any) => `${row.month}月`), y: data.C6.monthPattern.map((row: any) => row.value), marker: { color: data.C6.monthPattern.map((row: any) => row.value >= 0 ? '#43c4da' : '#536d8a') } },
        ],
        layout: { ...commonLayout, xaxis: { title: '日历月份' }, yaxis: { title: '默认十轨平均标准化变化', gridcolor: '#1d3146' }, showlegend: false },
      }
    }
    const diagnostic = data.diagnostics?.[cycleId]
    if (diagnostic) {
      if (cycleId === 'C2' && diagnostic.regimeRefactor) {
        const regime = diagnostic.regimeRefactor
        const history = regime.state.history
        const historicalTurns = regime.historicalDating.turningPoints
        const phaseColors: Record<string, string> = { recovery: '#55c9ed', expansion: '#69ce9f', slowdown: '#f1aa4b', contraction: '#9b83ef' }
        const phaseLabels: Record<string, string> = { recovery: '复苏', expansion: '扩张', slowdown: '放缓', contraction: '收缩' }
        const forecasts = [...diagnostic.longPanel.currentForecasts].sort((left: any, right: any) => left.horizonYears - right.horizonYears)
        const anchor = regime.state.current.activity
        const currentFactor = forecasts[0].currentFactor
        const addYears = (year: number, years: number) => `${year + years}-12-31`
        const scenario = [
          { date: `${regime.state.current.year}-12-31`, median: anchor, low: anchor, high: anchor },
          ...forecasts.map((row: any) => ({
            date: addYears(regime.state.current.year, row.horizonYears),
            median: anchor + row.scenarioFactor - currentFactor,
            low: anchor + row.scenarioLow - currentFactor,
            high: anchor + row.scenarioHigh - currentFactor,
          })),
        ]
        return {
          data: [
            { type: 'scatter', mode: 'lines', name: '住房—按揭活动核心', x: history.map((row: any) => `${row.year}-12-31`), y: history.map((row: any) => row.activity), line: { color: '#8bcfe4', width: 2.3 }, hovertemplate: '%{x|%Y}<br>活动核心 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'markers', name: '直接四相位', x: history.map((row: any) => `${row.year}-12-31`), y: history.map((row: any) => row.activity), text: history.map((row: any) => `${phaseLabels[row.phase] ?? row.phase} · 持续${row.phaseDurationYears}年`), marker: { color: history.map((row: any) => phaseColors[row.phase] ?? '#8ca0b0'), size: 4, opacity: .76 }, hovertemplate: '%{x|%Y}<br>%{text}<br>活动核心 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'markers', name: '历史共识峰谷', x: historicalTurns.map((row: any) => `${row.year}-12-31`), y: historicalTurns.map((row: any) => row.value), text: historicalTurns.map((row: any) => `${row.kind === 'peak' ? '峰值' : '谷值'} · 参数支持 ${(row.support * 100).toFixed(0)}%`), marker: { color: '#eef6fb', size: 8, symbol: 'diamond', line: { color: '#28485d', width: 1 } }, hovertemplate: '%{x|%Y}<br>%{text}<br>%{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'lines', name: '方向情景上沿', x: scenario.map((row) => row.date), y: scenario.map((row) => row.high), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
            { type: 'scatter', mode: 'lines', name: '历史变化区间', x: scenario.map((row) => row.date), y: scenario.map((row) => row.low), fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)', line: { width: 0 }, hoverinfo: 'skip' },
            { type: 'scatter', mode: 'lines+markers', name: '1/2/3年因子方向情景', x: scenario.map((row) => row.date), y: scenario.map((row) => row.median), line: { color: '#f1aa4b', width: 2.5, dash: 'dash' }, marker: { color: '#f1aa4b', size: 6 }, hovertemplate: '%{x|%Y}<br>受限方向情景 %{y:.2f}σ<extra></extra>' },
          ],
          layout: {
            ...commonLayout,
            xaxis: { ...commonLayout.xaxis, title: '年份（直接状态 / 受限方向情景）' },
            yaxis: { ...commonLayout.yaxis, title: '住房—按揭活动核心（σ）' },
            shapes: [
              { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#657c91', width: 1, dash: 'dot' } },
            ],
            annotations: [
              { x: .99, y: .03, xref: 'paper', yref: 'paper', text: `当前${regime.state.current.phase === 'contraction' ? '收缩' : regime.state.current.phase} · 转相分数 ${(regime.state.transitionEvidence.score * 100).toFixed(0)}/${(regime.state.transitionEvidence.requiredScore * 100).toFixed(0)} · 资产预测阻断`, showarrow: false, font: { color: '#f1aa4b' } },
            ],
          },
        }
      }
      if (cycleId === 'C3' && diagnostic.regimeRefactor) {
        const regime = diagnostic.regimeRefactor
        const history = regime.state.history
        const historical = history.filter((row: any) => row.year <= 2020)
        const bridge = history.filter((row: any) => row.year > 2020)
        const phaseColors: Record<string, string> = { recovery: '#55c9ed', expansion: '#69ce9f', slowdown: '#f1aa4b', contraction: '#9b83ef' }
        const phaseLabels: Record<string, string> = { recovery: '复苏', expansion: '扩张', slowdown: '放缓', contraction: '收缩' }
        const forecasts = [...regime.currentForecasts].sort((left: any, right: any) => left.horizonYears - right.horizonYears)
        const current = regime.state.current
        const currentPlotDate = regime.partialNowcast.point.date
        const addYears = (value: string, years: number) => {
          const date = new Date(`${value}T00:00:00Z`)
          date.setUTCFullYear(date.getUTCFullYear() + years)
          return date.toISOString().slice(0, 10)
        }
        const scenario = [
          { date: currentPlotDate, median: current.value, low: current.value, high: current.value },
          ...forecasts.map((row: any) => ({
            date: addYears(currentPlotDate, row.horizonYears),
            median: current.value + row.scenarioFactor - row.currentFactor,
            low: current.value + row.scenarioLow - row.currentFactor,
            high: current.value + row.scenarioHigh - row.currentFactor,
          })),
        ]
        return {
          data: [
            { type: 'scatter', mode: 'lines', name: '投资—信用双核心原值', x: historical.map((row: any) => `${row.year}-12-31`), y: historical.map((row: any) => row.rawValue), line: { color: '#496b83', width: 1.2 }, hovertemplate: '%{x|%Y}<br>双核心原值 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'lines', name: '动态资本周期分量', x: historical.map((row: any) => `${row.year}-12-31`), y: historical.map((row: any) => row.value), line: { color: '#8bcfe4', width: 2.3 }, hovertemplate: '%{x|%Y}<br>周期分量 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'markers', name: '历史四相位', x: historical.map((row: any) => `${row.year}-12-31`), y: historical.map((row: any) => row.value), text: historical.map((row: any) => `${phaseLabels[row.phase]} · 动态周期 ${row.periodYears.toFixed(1)}年`), marker: { color: historical.map((row: any) => phaseColors[row.phase]), size: 4, opacity: .72 }, hovertemplate: '%{x|%Y}<br>%{text}<br>周期分量 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'lines+markers', name: '现代数据桥接', x: bridge.map((row: any) => row.year === 2026 ? currentPlotDate : `${row.year}-12-31`), y: bridge.map((row: any) => row.value), text: bridge.map((row: any) => `${phaseLabels[row.phase]} · ${row.countryCount}国`), line: { color: '#69ce9f', width: 2.4, dash: 'dot' }, marker: { color: bridge.map((row: any) => phaseColors[row.phase]), size: 6 }, hovertemplate: '%{x|%Y}<br>%{text}<br>周期分量 %{y:.2f}σ<extra></extra>' },
            { type: 'scatter', mode: 'lines', name: '方向情景上沿', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.high), line: { width: 0, shape: 'spline', smoothing: .65 }, hoverinfo: 'skip', showlegend: false },
            { type: 'scatter', mode: 'lines', name: '历史变化区间', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)', line: { width: 0, shape: 'spline', smoothing: .65 }, hoverinfo: 'skip' },
            { type: 'scatter', mode: 'lines+markers', name: '1/2/3年双核心方向情景', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.median), line: { color: '#f1aa4b', width: 2.5, dash: 'dash', shape: 'spline', smoothing: .65 }, marker: { color: '#f1aa4b', size: 6 }, hovertemplate: '%{x|%Y}<br>受限方向情景 %{y:.2f}σ<extra></extra>' },
          ],
          layout: {
            ...commonLayout,
            xaxis: { ...commonLayout.xaxis, title: '年份（历史状态 / 现代桥接 / 受限方向情景）' },
            yaxis: { ...commonLayout.yaxis, title: 'C3 投资—信用周期分量（σ）' },
            shapes: [
              { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#657c91', width: 1, dash: 'dot' } },
            ],
            annotations: [
              { x: .99, y: .03, xref: 'paper', yref: 'paper', text: `当前${phaseLabels[current.phase]} · 动态周期 ${current.periodYears.toFixed(1)}年 · 资产仅${regime.assetValidation.passedTargets}/${regime.assetValidation.targetCount}通过`, showarrow: false, font: { color: '#f1aa4b' } },
            ],
          },
        }
      }
      if (diagnostic.longPanel) {
        const longPanel = diagnostic.longPanel
        const phaseCandidate = diagnostic.phaseCandidate
        const historical = phaseCandidate?.history ?? longPanel.history
        const historyDates = historical.map((row: any) => `${row.year ?? row.date}-12-31`)
        const historyValues = historical.map((row: any) => row.value)
        const phaseColors: Record<string, string> = { recovery: '#55c9ed', expansion: '#69ce9f', slowdown: '#f1aa4b', contraction: '#9b83ef' }
        const historicalEnd = Number(data.meta?.historicalEnd ?? 2020)
        const currentPhaseCandidate = phaseCandidate?.currentPhaseCandidate
        const exactPhasePublishable = currentPhaseCandidate?.exactPhaseStatus === 'limited'
        const broadStateLabel = currentPhaseCandidate?.governedBroadState?.label
        const phaseBridge = currentPhaseCandidate
          ? currentPhaseCandidate.recentHistory.filter((row: any) => Number(row.year) > historicalEnd)
          : []
        const bridge = phaseBridge.length
          ? phaseBridge.map((row: any) => ({ ...row, date: String(row.year) }))
          : longPanel.bridgeHistory.filter((row: any) => Number(row.date) > historicalEnd)
        const partialPoint = longPanel.partialNowcast?.validation?.status === 'passed_limited'
          ? longPanel.partialNowcast.point
          : null
        const partialFamilyLabel = longPanel.partialNowcast?.updatedFamilyLabel ?? '当前指标'
        const forecasts = [...longPanel.currentForecasts].sort((left: any, right: any) => left.horizonYears - right.horizonYears)
        const current = forecasts[0]
        const currentPlotDate = partialPoint?.date ?? `${current.asOfYear}-12-31`
        const addYears = (value: string, years: number) => {
          const date = new Date(`${value}T00:00:00Z`)
          date.setUTCFullYear(date.getUTCFullYear() + years)
          return date.toISOString().slice(0, 10)
        }
        const phaseAnchor = currentPhaseCandidate?.current?.value ?? current.currentFactor
        const scenario = [
          { date: currentPlotDate, median: phaseAnchor, low: phaseAnchor, high: phaseAnchor },
          ...forecasts.map((row: any) => ({
            date: addYears(currentPlotDate, row.horizonYears),
            median: phaseAnchor + row.scenarioFactor - row.currentFactor,
            low: phaseAnchor + row.scenarioLow - row.currentFactor,
            high: phaseAnchor + row.scenarioHigh - row.currentFactor,
          })),
        ]
        const bridgeDates = bridge.map((row: any) => Number(row.date) === current.asOfYear && partialPoint ? partialPoint.date : `${row.date}-12-31`)
        const bridgeValues = bridge.map((row: any) => row.value)
        const bridgePhaseColors = bridge.map((row: any) => exactPhasePublishable ? phaseColors[row.phase] ?? '#7ed8b2' : '#7ed8b2')
        return {
          data: [
            { type: 'scatter', mode: 'lines', name: phaseCandidate ? '自适应状态空间周期分量' : 'JST跨国历史因子', x: historyDates, y: historyValues, line: { color: '#8bcfe4', width: 1.8 } },
            ...(phaseCandidate ? [{ type: 'scatter', mode: 'markers', name: '历史四相位', x: historyDates, y: historyValues, text: phaseCandidate.history.map((row: any) => `${row.phase} · 动态周期 ${row.periodYears?.toFixed?.(1) ?? '—'}年`), marker: { color: phaseCandidate.history.map((row: any) => phaseColors[row.phase] ?? '#8bcfe4'), size: 5 }, hovertemplate: '%{x}<br>%{text}<br>周期分量 %{y:.2f}<extra></extra>' }] : []),
            ...(phaseCandidate ? [{ type: 'scatter', mode: 'markers', name: '历史峰谷', x: phaseCandidate.turns.map((row: any) => `${row.year}-12-31`), y: phaseCandidate.turns.map((row: any) => row.value), text: phaseCandidate.turns.map((row: any) => row.kind === 'peak' ? '峰值' : '谷值'), marker: { color: '#eef6fb', size: 7, symbol: 'diamond', line: { color: '#28485d', width: 1 } }, hovertemplate: '%{x|%Y}<br>%{text} %{y:.2f}<extra></extra>' }] : []),
            { type: 'scatter', mode: phaseBridge.length ? 'lines+markers' : 'lines', name: phaseBridge.length ? '宏观当前状态桥接' : 'BIS/WB完整年度桥接', x: bridgeDates, y: bridgeValues, text: bridge.map((row: any) => exactPhasePublishable ? row.phase : broadStateLabel ?? '当前宽状态'), line: { color: '#7ed8b2', width: 2.2, dash: 'dash' }, marker: { color: bridgePhaseColors, size: 6 }, hovertemplate: '%{x|%Y}<br>%{text}<br>宏观因子 %{y:.2f}<extra></extra>' },
            ...(!phaseBridge.length && partialPoint && bridge.length ? [{
              type: 'scatter', mode: 'lines+markers', name: `${partialPoint.label} 部分年度`,
              x: [`${bridge[bridge.length - 1].date}-12-31`, partialPoint.date],
              y: [bridge[bridge.length - 1].value, partialPoint.value],
              text: ['上一完整年度', `${partialPoint.updatedCountryCount}/${partialPoint.countryCount}国更新${partialFamilyLabel}`],
              line: { color: '#69ce9f', width: 2.5, dash: 'dot' }, marker: { color: '#69ce9f', size: 7 },
              hovertemplate: '%{x}<br>%{text}<br>部分年度因子 %{y:.2f}<extra></extra>',
            }] : []),
            { type: 'scatter', mode: 'lines', name: '情景上沿', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.high), line: { width: 0, shape: 'spline', smoothing: .65 }, hoverinfo: 'skip', showlegend: false },
            { type: 'scatter', mode: 'lines', name: '历史变化分布区间', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.low), fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)', line: { width: 0, shape: 'spline', smoothing: .65 }, hoverinfo: 'skip' },
            { type: 'scatter', mode: 'lines+markers', name: '1/2/3年方向概率情景', x: scenario.map((row: any) => row.date), y: scenario.map((row: any) => row.median), line: { color: '#f1aa4b', width: 2.4, dash: 'dash', shape: 'spline', smoothing: .65 }, marker: { color: '#f1aa4b', size: 6 } },
          ],
          layout: {
            ...commonLayout,
            xaxis: { ...commonLayout.xaxis, title: '年份（历史 / 当前桥接 / 方向情景）' },
            yaxis: { ...commonLayout.yaxis, title: '自适应周期分量（标准化研究值）' },
            annotations: [
              { x: `${historicalEnd}-12-31`, y: 1.02, xref: 'x', yref: 'paper', text: 'JST历史终点', showarrow: true, arrowcolor: '#7ed8b2', font: { color: '#7ed8b2' } },
              { x: .99, y: .03, xref: 'paper', yref: 'paper', text: currentPhaseCandidate ? `${currentPhaseCandidate.periodRobustness?.periodRangeYears?.[0]?.toFixed?.(1) ?? currentPhaseCandidate.current.periodYears.toFixed(1)}—${currentPhaseCandidate.periodRobustness?.periodRangeYears?.[1]?.toFixed?.(1) ?? currentPhaseCandidate.current.periodYears.toFixed(1)}年范围 · ${broadStateLabel ?? '宽状态研究'} · 四相位仍阻断` : '方向概率通过 · 精确相位仍阻断', showarrow: false, font: { color: '#f1aa4b' } },
            ],
          },
        }
      }
      const periodUnit = diagnostic.frequency === 'A' ? '年' : '月'
      const traces: any[] = [
        { type: 'scatter', mode: 'lines', name: '家族分歧上沿', x: diagnostic.dates, y: diagnostic.directionalState.map((value: number | null, index: number) => value == null ? null : value + (diagnostic.familyDisagreement[index] ?? 0) * .45), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
        { type: 'scatter', mode: 'lines', name: '指标家族分歧', x: diagnostic.dates, y: diagnostic.directionalState.map((value: number | null, index: number) => value == null ? null : value - (diagnostic.familyDisagreement[index] ?? 0) * .45), fill: 'tonexty', fillcolor: 'rgba(85,201,237,.10)', line: { width: 0 }, hoverinfo: 'skip' },
        { type: 'scatter', mode: 'lines', name: '方向性动态因子', x: diagnostic.dates, y: diagnostic.directionalState, line: { color: '#55c9ed', width: 2.5 } },
        ...diagnostic.candidateBands.map((band: any, index: number) => ({
          type: 'scatter', mode: 'lines', name: `候选 ${band.period}${periodUnit}`, x: diagnostic.dates, y: band.values,
          line: { color: ['#f1aa4b', '#9a83ef', '#69ce9f'][index % 3], width: 1.2, dash: 'dot' }, opacity: .68,
        })),
        { type: 'scatter', mode: 'lines', name: '候选带中位数', x: diagnostic.dates, y: diagnostic.candidateConsensus, line: { color: '#f1aa4b', width: 1.8, dash: 'dash' } },
      ]
      return {
        data: traces,
        layout: {
          ...commonLayout,
          yaxis: { ...commonLayout.yaxis, title: '研究诊断状态（σ）' },
          annotations: [{ x: .99, y: .03, xref: 'paper', yref: 'paper', text: '研究诊断 · 正式状态仍阻断', showarrow: false, font: { color: '#f1aa4b' } }],
        },
      }
    }
    return null
  }, [cycleId, data])

  if (!chart) return null
  return <PlotlyCanvas className="cycle-research-chart" data={chart.data} layout={chart.layout} />
}
