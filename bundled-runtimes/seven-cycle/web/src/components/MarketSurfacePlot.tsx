import { useMemo } from 'react'
import PlotlyCanvas from './PlotlyCanvas'
import type { MarketTrack } from '../types'

export type SurfaceMode = 'governed' | 'research'
export type SurfaceView = '3d' | '2d'
export type TimeRange = '20y' | '50y' | 'all'
export type SurfaceCameraPreset = 'overview' | 'top' | 'along-track' | 'along-time'

interface SelectedPoint {
  trackId: string
  index: number
  forecast?: boolean
}

interface Props {
  tracks: MarketTrack[]
  mode: SurfaceMode
  view: SurfaceView
  range: TimeRange
  showForecast: boolean
  focusTrackId?: string
  cameraRevision: number
  cameraPreset: SurfaceCameraPreset
  onPoint: (point: SelectedPoint) => void
}

const colorScale = [
  [0, '#176d67'],
  [0.22, '#3f978c'],
  [0.42, 'rgba(86, 145, 132, .68)'],
  [0.49, 'rgba(110, 126, 117, .30)'],
  [0.51, 'rgba(110, 126, 117, .30)'],
  [0.62, 'rgba(205, 157, 86, .68)'],
  [0.82, '#d48350'],
  [1, '#c94f49'],
]

const cameraPresets: Record<SurfaceCameraPreset, Record<string, any>> = {
  overview: {
    eye: { x: 1.55, y: 0.6, z: 1.78 },
    center: { x: 0, y: -0.04, z: 0 },
    up: { x: 0, y: 1, z: 0 },
    projection: { type: 'perspective' },
  },
  top: {
    eye: { x: 0.001, y: -2.75, z: 0.001 },
    center: { x: 0, y: 0, z: 0 },
    up: { x: 0, y: 0, z: 1 },
    projection: { type: 'orthographic' },
  },
  'along-track': {
    eye: { x: 0.001, y: 0.001, z: 2.75 },
    center: { x: 0, y: 0, z: 0 },
    up: { x: 0, y: 1, z: 0 },
    projection: { type: 'orthographic' },
  },
  'along-time': {
    eye: { x: 2.75, y: 0.001, z: 0.001 },
    center: { x: 0, y: 0, z: 0 },
    up: { x: 0, y: 0, z: 1 },
    projection: { type: 'orthographic' },
  },
}

const plotConfig = {
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  doubleClick: 'reset',
}

function yearValue(date: string) {
  const [year, month] = date.split('-').map(Number)
  return year + (month - 1) / 12
}

function inRange(date: string, range: TimeRange) {
  if (range === 'all') return true
  const cutoff = range === '20y' ? 2006 : 1976
  return Number(date.slice(0, 4)) >= cutoff
}

function quantile(values: number[], probability: number) {
  if (!values.length) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const position = (sorted.length - 1) * probability
  const lower = Math.floor(position)
  const upper = Math.ceil(position)
  if (lower === upper) return sorted[lower]
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
}

export default function MarketSurfacePlot({ tracks, mode, view, range, showForecast, focusTrackId, cameraRevision, cameraPreset, onPoint }: Props) {
  const chart = useMemo(() => {
    const stackKey = mode === 'governed' ? 'governedStack' : 'researchStack'
    const traces: any[] = []
    if (view === '2d') {
      tracks.forEach((track) => {
        const indices = track.dates.map((date, index) => ({ date, index })).filter(({ date }) => inRange(date, range))
        traces.push({
          type: 'scatter',
          mode: 'lines',
          name: track.label,
          x: indices.map(({ date }) => date),
          y: indices.map(({ index }) => track[stackKey][index]),
          customdata: indices.map(({ index }) => [track.id, index]),
          line: { width: 1.7 },
          hovertemplate: `${track.label}<br>%{x}<br>周期合成 %{y:.2f}σ<extra></extra>`,
        })
        if (showForecast && track.forecast.status === 'limited' && track.forecast.dates.length) {
          const bridgeDates = track.forecast.bridge ? [track.forecast.bridge.date] : []
          const bridgeValues = track.forecast.bridge ? [track.forecast.bridge.value] : []
          const forecastDates = [...bridgeDates, ...track.forecast.dates]
          const forecastMedian = [...bridgeValues, ...track.forecast.median]
          const forecastLow = [
            ...(track.forecast.bridge ? [track.forecast.bridge.value] : []),
            ...track.forecast.low.map((value, index) => value ?? track.forecast.median[index]),
          ]
          const forecastHigh = [
            ...(track.forecast.bridge ? [track.forecast.bridge.value] : []),
            ...track.forecast.high.map((value, index) => value ?? track.forecast.median[index]),
          ]
          if (track.id === focusTrackId) {
            traces.push({
              type: 'scatter', mode: 'lines', x: forecastDates, y: forecastLow,
              line: { width: 0 }, hoverinfo: 'skip', showlegend: false,
            })
            traces.push({
              type: 'scatter', mode: 'lines', x: forecastDates, y: forecastHigh,
              line: { width: 0 }, fill: 'tonexty', fillcolor: 'rgba(241,170,75,.13)',
              hoverinfo: 'skip', showlegend: false,
            })
          }
          traces.push({
            type: 'scatter',
            mode: 'lines+markers',
            name: `${track.label} · 受限预测`,
            x: forecastDates,
            y: forecastMedian,
            customdata: [
              ...(track.forecast.bridge ? [[track.id, Math.max(0, track.dates.length - 1), false]] : []),
              ...track.forecast.dates.map((_, index) => [track.id, index, true]),
            ],
              line: { color: '#e9a348', width: 3, dash: 'dash' },
              marker: { color: '#f1bd72', size: 3 },
            showlegend: false,
            hovertemplate: `${track.label}<br>%{x}<br>受限延伸 %{y:.2f}σ<extra></extra>`,
          })
        }
      })
      return {
        data: traces,
        layout: {
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          margin: { l: 54, r: 20, t: 12, b: 48 },
          font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 11 },
          xaxis: { title: '时间', gridcolor: '#1d3146', zeroline: false },
          yaxis: { title: '变化率（σ）', gridcolor: '#1d3146', zerolinecolor: '#668099' },
          legend: { orientation: 'h', y: 1.05, font: { size: 10 } },
          hovermode: 'closest',
          uirevision: `market-surface-2d-${cameraRevision}`,
        },
      }
    }

    const dateSet = new Set<string>()
    tracks.forEach((track) => track.dates.forEach((date) => inRange(date, range) && dateSet.add(date)))
    const dates = [...dateSet].sort()
    const vertexIndex = new Map<string, number>()
    const meshX: number[] = []
    const meshY: number[] = []
    const meshZ: number[] = []
    const intensity: number[] = []
    const zPositions = tracks.map((_, index) => index)
    tracks.forEach((track, trackIndex) => {
      const valueByDate = new Map(track.dates.map((date, index) => [date, track[stackKey][index]]))
      dates.forEach((date) => {
        const value = valueByDate.get(date)
        if (value == null || !Number.isFinite(value)) return
        const key = `${trackIndex}|${date}`
        vertexIndex.set(key, meshX.length)
        meshX.push(yearValue(date))
        meshY.push(value)
        meshZ.push(zPositions[trackIndex])
        intensity.push(value)
      })
    })
    const i: number[] = []
    const j: number[] = []
    const k: number[] = []
    for (let trackIndex = 0; trackIndex < tracks.length - 1; trackIndex += 1) {
      for (let dateIndex = 0; dateIndex < dates.length - 1; dateIndex += 1) {
        const a = vertexIndex.get(`${trackIndex}|${dates[dateIndex]}`)
        const b = vertexIndex.get(`${trackIndex}|${dates[dateIndex + 1]}`)
        const c = vertexIndex.get(`${trackIndex + 1}|${dates[dateIndex]}`)
        const d = vertexIndex.get(`${trackIndex + 1}|${dates[dateIndex + 1]}`)
        if ([a, b, c, d].some((value) => value == null)) continue
        i.push(a!, b!)
        j.push(b!, d!)
        k.push(c!, c!)
      }
    }
    if (i.length) {
      traces.push({
        type: 'mesh3d',
        x: meshX,
        y: meshY,
        z: meshZ,
        i,
        j,
        k,
        intensity,
        colorscale: colorScale,
        cmin: -3,
        cmax: 3,
        opacity: 0.76,
        flatshading: false,
        lighting: { ambient: 0.76, diffuse: 0.68, specular: 0.06, roughness: 0.88, fresnel: 0.05 },
        lightposition: { x: 100, y: -180, z: 220 },
        hoverinfo: 'skip',
        showscale: true,
        colorbar: {
          title: { text: '变化率（σ）', side: 'top', font: { size: 10 } },
          thickness: 10,
          len: 0.5,
          x: 0.985,
          y: 0.55,
          tickvals: [-3, -1.5, 0, 1.5, 3],
          ticktext: ['-3', '-1.5', '0', '+1.5', '+3'],
          tickfont: { size: 9 },
          outlinewidth: 0,
          bgcolor: 'rgba(0,0,0,0)',
        },
      })

      const ribX: Array<number | null> = []
      const ribY: Array<number | null> = []
      const ribZ: Array<number | null> = []
      const ribStep = Math.max(1, Math.ceil(dates.length / 20))
      for (let dateIndex = 0; dateIndex < dates.length; dateIndex += ribStep) {
        for (let trackIndex = 0; trackIndex < tracks.length; trackIndex += 1) {
          const vertex = vertexIndex.get(`${trackIndex}|${dates[dateIndex]}`)
          if (vertex == null) continue
          ribX.push(meshX[vertex])
          ribY.push(meshY[vertex])
          ribZ.push(meshZ[vertex])
        }
        ribX.push(null)
        ribY.push(null)
        ribZ.push(null)
      }
      traces.push({
        type: 'scatter3d',
        mode: 'lines',
        x: ribX,
        y: ribY,
        z: ribZ,
        line: { width: 0.8, color: '#28443f' },
        hoverinfo: 'skip',
        showlegend: false,
      })
    }
    tracks.forEach((track, trackIndex) => {
      const indices = track.dates.map((date, index) => ({ date, index })).filter(({ date }) => inRange(date, range))
      traces.push({
        type: 'scatter3d',
        mode: 'lines+markers',
        name: track.label,
        x: indices.map(({ date }) => yearValue(date)),
        y: indices.map(({ index }) => track[stackKey][index]),
        z: indices.map(() => zPositions[trackIndex]),
        customdata: indices.map(({ date, index }) => [track.id, index, false, date]),
        line: {
          width: track.id === focusTrackId ? 4.2 : 1,
          color: track.id === focusTrackId ? '#a8eadf' : '#315b54',
        },
        marker: {
          size: indices.map((_, index) => index === indices.length - 1 ? (track.id === focusTrackId ? 3.4 : 2) : 0),
          opacity: 0.9,
          color: track.id === focusTrackId ? '#d0f5ee' : '#55766f',
        },
        hovertemplate: `${track.label}<br>%{customdata[3]}<br>周期合成 %{y:.2f}σ<extra></extra>`,
        showlegend: false,
      })
      if (showForecast && track.forecast.status === 'limited' && track.forecast.dates.length) {
        const bridgeDates = track.forecast.bridge ? [track.forecast.bridge.date] : []
        const bridgeValues = track.forecast.bridge ? [track.forecast.bridge.value] : []
        const forecastDates = [...bridgeDates, ...track.forecast.dates]
        const forecastLow = [
          ...(track.forecast.bridge ? [track.forecast.bridge.value] : []),
          ...track.forecast.low.map((value, index) => value ?? track.forecast.median[index]),
        ]
        const forecastHigh = [
          ...(track.forecast.bridge ? [track.forecast.bridge.value] : []),
          ...track.forecast.high.map((value, index) => value ?? track.forecast.median[index]),
        ]
        const bandX = [...forecastDates.map(yearValue), ...forecastDates.map(yearValue)]
        const bandY = [...forecastLow, ...forecastHigh]
        const bandZ = bandX.map(() => zPositions[trackIndex])
        const bandI: number[] = []
        const bandJ: number[] = []
        const bandK: number[] = []
        for (let index = 0; index < forecastDates.length - 1; index += 1) {
          const lowCurrent = index
          const lowNext = index + 1
          const highCurrent = forecastDates.length + index
          const highNext = forecastDates.length + index + 1
          bandI.push(lowCurrent, lowNext)
          bandJ.push(lowNext, highNext)
          bandK.push(highCurrent, highCurrent)
        }
        if (track.id === focusTrackId) {
          traces.push({
            type: 'mesh3d', x: bandX, y: bandY, z: bandZ,
            i: bandI, j: bandJ, k: bandK,
            color: '#e9a348', opacity: 0.14,
            hoverinfo: 'skip', showscale: false, flatshading: false, showlegend: false,
          })
        }
        traces.push({
          type: 'scatter3d',
          mode: 'lines+markers',
          name: `${track.label} · 受限预测`,
          x: forecastDates.map(yearValue),
          y: [...bridgeValues, ...track.forecast.median],
          z: forecastDates.map(() => zPositions[trackIndex]),
          customdata: [
            ...(track.forecast.bridge ? [[track.id, Math.max(0, track.dates.length - 1), false, track.forecast.bridge.date]] : []),
            ...track.forecast.dates.map((date, index) => [track.id, index, true, date]),
          ],
          line: {
            width: track.id === focusTrackId ? 5.5 : 2.4,
            color: track.id === focusTrackId ? '#eda84d' : '#986a34',
            dash: 'dash',
          },
          marker: {
            size: forecastDates.map((_, index) => index === forecastDates.length - 1 ? (track.id === focusTrackId ? 3.2 : 1.8) : 0),
            color: '#f3c47d',
            opacity: .9,
          },
          hovertemplate: `${track.label}<br>%{customdata[3]}<br>预测延伸 %{y:.2f}σ<extra></extra>`,
          showlegend: false,
        })
      }
    })
    const firstYear = dates.length ? Number(dates[0].slice(0, 4)) : 2000
    const lastYear = dates.length ? Number(dates[dates.length - 1].slice(0, 4)) + 2 : 2027
    const tickStep = Math.max(2, Math.ceil((lastYear - firstYear) / 8))
    const xTicks = Array.from({ length: Math.floor((lastYear - firstYear) / tickStep) + 1 }, (_, index) => firstYear + index * tickStep)
    const robustAbsolute = quantile(intensity.map((value) => Math.abs(value)), 0.985)
    const yLimit = Math.max(2.25, Math.min(4, Math.ceil(robustAbsolute * 2) / 2))
    return {
      data: traces,
      layout: {
        paper_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 0, r: 0, t: 4, b: 0 },
        font: { color: '#c9d7e5', family: 'Inter, PingFang SC, sans-serif', size: 10 },
        uirevision: `market-surface-3d-${cameraPreset}-${cameraRevision}`,
        scene: {
          bgcolor: 'rgba(0,0,0,0)',
          camera: cameraPresets[cameraPreset],
          uirevision: `market-surface-scene-${cameraPreset}-${cameraRevision}`,
          aspectmode: 'manual',
          aspectratio: { x: 2.4, y: 1.12, z: Math.max(0.84, Math.min(1.12, tracks.length / 10)) },
          dragmode: 'orbit',
          xaxis: {
            title: { text: '时间', font: { size: 10 } },
            tickvals: xTicks,
            ticktext: xTicks.map(String),
            tickfont: { size: 9 },
            gridcolor: 'rgba(137, 157, 147, .22)',
            linecolor: 'rgba(137, 157, 147, .35)',
            showbackground: false,
            zeroline: false,
          },
          yaxis: {
            title: { text: '变化率（σ）', font: { size: 10 } },
            range: [-yLimit, yLimit],
            tickfont: { size: 9 },
            gridcolor: 'rgba(137, 157, 147, .22)',
            linecolor: 'rgba(137, 157, 147, .35)',
            zerolinecolor: 'rgba(232, 198, 139, .58)',
            zerolinewidth: 2,
            showbackground: false,
          },
          zaxis: {
            title: { text: '指标轨道', font: { size: 10 } },
            tickvals: zPositions,
            ticktext: tracks.map((track, index) => `${String(index + 1).padStart(2, '0')} ${track.label}`),
            tickfont: { size: 9 },
            gridcolor: 'rgba(137, 157, 147, .18)',
            linecolor: 'rgba(137, 157, 147, .35)',
            showbackground: false,
          },
        },
        hovermode: 'closest',
      },
    }
  }, [cameraPreset, cameraRevision, focusTrackId, mode, range, showForecast, tracks, view])

  const handlePoint = (point: any) => {
    const custom = point?.customdata
    if (!Array.isArray(custom)) return
    onPoint({ trackId: custom[0], index: Number(custom[1]), forecast: Boolean(custom[2]) })
  }

  return (
    <PlotlyCanvas
      className="surface-plot"
      data={chart.data}
      layout={chart.layout}
      config={plotConfig}
      preserveDataColors
      onClick={handlePoint}
      onHover={handlePoint}
    />
  )
}
