import { useEffect, useMemo, useRef, useState } from 'react'
import { adaptPlotlyTheme } from '../lib/theme'

interface Props {
  data: any[]
  layout: Record<string, any>
  config?: Record<string, any>
  className?: string
  onClick?: (point: any) => void
  onHover?: (point: any) => void
  preserveDataColors?: boolean
}

export default function PlotlyCanvas({ data, layout, config, className, onClick, onHover, preserveDataColors = false }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const plotlyRef = useRef<any>(null)
  const [themeRevision, setThemeRevision] = useState(0)
  const themed = useMemo(
    () => adaptPlotlyTheme(data, layout, { preserveDataColors }),
    [data, layout, preserveDataColors, themeRevision],
  )
  const dataRef = useRef(themed.data)
  const layoutRef = useRef(themed.layout)
  const configRef = useRef(config)
  const onClickRef = useRef(onClick)
  const onHoverRef = useRef(onHover)

  dataRef.current = themed.data
  layoutRef.current = themed.layout
  configRef.current = config
  onClickRef.current = onClick
  onHoverRef.current = onHover

  useEffect(() => {
    const handleThemeChange = () => setThemeRevision((revision) => revision + 1)
    window.addEventListener('newma:themechange', handleThemeChange)
    return () => window.removeEventListener('newma:themechange', handleThemeChange)
  }, [])

  useEffect(() => {
    if (!ref.current) return
    const element = ref.current as any
    let disposed = false
    let resizeObserver: ResizeObserver | null = null
    const clickHandler = (event: any) => onClickRef.current?.(event.points?.[0])
    const hoverHandler = (event: any) => onHoverRef.current?.(event.points?.[0])
    void import('plotly.js-dist-min').then((module) => {
      if (disposed) return
      plotlyRef.current = module.default
      plotlyRef.current.react(element, dataRef.current, layoutRef.current, {
        displaylogo: false,
        responsive: true,
        scrollZoom: true,
        ...configRef.current,
      })
      element.on('plotly_click', clickHandler)
      element.on('plotly_hover', hoverHandler)
      resizeObserver = new ResizeObserver(() => {
        if (!disposed && element.offsetParent !== null) {
          plotlyRef.current?.Plots.resize(element)
        }
      })
      resizeObserver.observe(element.parentElement ?? element)
    })
    return () => {
      disposed = true
      resizeObserver?.disconnect()
      element.removeListener?.('plotly_click', clickHandler)
      element.removeListener?.('plotly_hover', hoverHandler)
      plotlyRef.current?.purge(element)
      plotlyRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!ref.current || !plotlyRef.current) return
    plotlyRef.current.react(ref.current, themed.data, themed.layout, {
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
      ...config,
    })
  }, [config, themed])

  return <div ref={ref} className={className} />
}
