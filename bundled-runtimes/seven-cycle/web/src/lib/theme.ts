export type NewmaChartPalette = {
  grid: string
  text: string
  axis: string
  tooltipBg: string
  tooltipBorder: string
  tooltipText: string
  series: string[]
}

const lightFallback: NewmaChartPalette = {
  grid: '#d8cdbb',
  text: '#66766e',
  axis: '#b9aa90',
  tooltipBg: '#fffaf1',
  tooltipBorder: '#b9aa90',
  tooltipText: '#173128',
  series: ['#a87432', '#3f7667', '#8f6b50', '#77825c', '#a45e52'],
}

const darkFallback: NewmaChartPalette = {
  grid: '#2a3931',
  text: '#a8b4a5',
  axis: '#405146',
  tooltipBg: '#1a2821',
  tooltipBorder: '#405146',
  tooltipText: '#f3ecdd',
  series: ['#c89a5a', '#70a596', '#b67b64', '#9da96f', '#cf756b'],
}

function cssValue(style: CSSStyleDeclaration, name: string, fallback: string) {
  return style.getPropertyValue(name).trim() || fallback
}

export function getNewmaChartPalette(): NewmaChartPalette {
  const mode = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
  const fallback = mode === 'dark' ? darkFallback : lightFallback
  const style = getComputedStyle(document.documentElement)
  return {
    grid: cssValue(style, '--vibe-chart-grid', fallback.grid),
    text: cssValue(style, '--vibe-chart-text', fallback.text),
    axis: cssValue(style, '--vibe-chart-axis', fallback.axis),
    tooltipBg: cssValue(style, '--vibe-chart-tooltip-bg', fallback.tooltipBg),
    tooltipBorder: cssValue(style, '--vibe-chart-tooltip-border', fallback.tooltipBorder),
    tooltipText: cssValue(style, '--vibe-chart-tooltip-text', fallback.tooltipText),
    series: fallback.series.map((value, index) => (
      cssValue(style, `--vibe-chart-series-${index + 1}`, value)
    )),
  }
}

function parseHex(value: string) {
  const match = /^#([0-9a-f]{6})$/i.exec(value.trim())
  if (!match) return null
  return {
    r: Number.parseInt(match[1].slice(0, 2), 16),
    g: Number.parseInt(match[1].slice(2, 4), 16),
    b: Number.parseInt(match[1].slice(4, 6), 16),
    alpha: 1,
  }
}

function parseRgba(value: string) {
  const match = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(0?\.\d+|0|1))?\s*\)$/i.exec(value.trim())
  if (!match) return null
  return {
    r: Number(match[1]),
    g: Number(match[2]),
    b: Number(match[3]),
    alpha: match[4] == null ? 1 : Number(match[4]),
  }
}

function toRgba(value: string, alpha: number) {
  const parsed = parseHex(value) ?? parseRgba(value)
  if (!parsed) return value
  return `rgba(${parsed.r}, ${parsed.g}, ${parsed.b}, ${Math.max(0, Math.min(1, alpha))})`
}

function legacyColorRole(value: string): 'gold' | 'verdigris' | 'clay' | 'olive' | 'red' | 'neutral' | null {
  const parsed = parseHex(value) ?? parseRgba(value)
  if (!parsed || parsed.alpha === 0) return null
  const { r, g, b } = parsed
  const max = Math.max(r, g, b) / 255
  const min = Math.min(r, g, b) / 255
  const light = (max + min) / 2
  const delta = max - min
  let hue = 0
  if (delta) {
    if (max === r / 255) hue = ((g - b) / 255 / delta) % 6
    else if (max === g / 255) hue = (b - r) / 255 / delta + 2
    else hue = (r - g) / 255 / delta + 4
    hue = (hue * 60 + 360) % 360
  }
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * light - 1))
  if (saturation < .2) return 'neutral'
  if (hue >= 345 || hue < 18) return 'red'
  if (hue < 78) return 'gold'
  if (hue < 170) return 'verdigris'
  if (hue < 235) return 'verdigris'
  if (hue < 285) return 'olive'
  if (hue < 345) return 'clay'
  return 'neutral'
}

function themedColor(value: string, key: string, palette: NewmaChartPalette) {
  const normalizedKey = key.toLowerCase()
  if (normalizedKey.includes('gridcolor')) return palette.grid
  if (normalizedKey.includes('zerolinecolor') || normalizedKey.includes('linecolor')) return palette.axis
  if (normalizedKey.includes('tickfont')) return palette.text

  const parsed = parseHex(value) ?? parseRgba(value)
  const role = legacyColorRole(value)
  if (!parsed || !role) return value
  const target = role === 'gold'
    ? palette.series[0]
    : role === 'verdigris'
      ? palette.series[1]
      : role === 'clay'
        ? palette.series[2]
        : role === 'olive'
          ? palette.series[3]
          : role === 'red'
            ? palette.series[4]
            : palette.text
  return parsed.alpha < 1 ? toRgba(target, parsed.alpha) : target
}

function adaptValue(value: any, key: string, palette: NewmaChartPalette): any {
  if (typeof value === 'string') return themedColor(value, key, palette)
  if (Array.isArray(value)) {
    if (key === 'colorscale') return value
    if (
      key !== 'color'
      && value.every((item) => item == null || ['string', 'number', 'boolean'].includes(typeof item))
    ) return value
    let changed = false
    const next = value.map((item) => {
      const adapted = adaptValue(item, key, palette)
      changed ||= adapted !== item
      return adapted
    })
    return changed ? next : value
  }
  if (!value || typeof value !== 'object') return value
  let changed = false
  const next: Record<string, any> = {}
  Object.entries(value).forEach(([childKey, childValue]) => {
    const adapted = adaptValue(childValue, childKey, palette)
    next[childKey] = adapted
    changed ||= adapted !== childValue
  })
  return changed ? next : value
}

export function adaptPlotlyTheme(data: any[], layout: Record<string, any>, options: { preserveDataColors?: boolean } = {}) {
  const palette = getNewmaChartPalette()
  const themedData = options.preserveDataColors ? data : adaptValue(data, 'data', palette)
  const themedLayout = adaptValue(layout, 'layout', palette)
  return {
    data: themedData,
    layout: {
      ...themedLayout,
      colorway: palette.series,
      font: { ...themedLayout.font, color: palette.text },
      hoverlabel: {
        ...themedLayout.hoverlabel,
        bgcolor: palette.tooltipBg,
        bordercolor: palette.tooltipBorder,
        font: { ...themedLayout.hoverlabel?.font, color: palette.tooltipText },
      },
    },
  }
}
