type ThemeMode = 'light' | 'dark'

type DeskAppearance = {
  mode?: ThemeMode
  cssVars?: Record<string, string>
}

type DeskPageContext = {
  view: { id: string; title: string }
  visibleBlocks: Array<{ id: string; type: string; title?: string }>
  selection: Record<string, unknown>
  filters: Record<string, unknown>
  data: {
    asOf?: string
    source?: string
    freshness?: 'live' | 'fresh' | 'stale' | 'unknown'
    summary?: Record<string, unknown>
  }
  actions: Array<{
    id: string
    label?: string
    available?: boolean
    inputSchema?: unknown
  }>
  tasks: Array<{ id: string; status: string; actionId?: string }>
}

type DeskContextProvider = () => DeskPageContext | null | Promise<DeskPageContext | null>

type DeskVisualCapture = {
  dataUrl: string
  width: number
  height: number
  capturedAt?: string
  title?: string
}

type DeskVisualCaptureProvider = (request: {
  reason: 'agent' | 'refresh'
  maxBytes: number
}) => DeskVisualCapture | null | Promise<DeskVisualCapture | null>

let contextProvider: DeskContextProvider | undefined
let visualCaptureProvider: DeskVisualCaptureProvider | undefined
let publishCurrentContext: (() => Promise<boolean>) | undefined

export function registerVibeDeskContextProvider(provider: DeskContextProvider) {
  contextProvider = provider
  return () => {
    if (contextProvider === provider) contextProvider = undefined
  }
}

export function registerVibeDeskVisualCaptureProvider(provider: DeskVisualCaptureProvider) {
  visualCaptureProvider = provider
  return () => {
    if (visualCaptureProvider === provider) visualCaptureProvider = undefined
  }
}

export function publishVibeDeskContext() {
  return publishCurrentContext?.() ?? Promise.resolve(false)
}

const root = document.documentElement
const isEmbedded = window.self !== window.top
const appliedVariables = new Set<string>()
const cssVariableName = /^--[a-z0-9-]{2,80}$/

function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'light' || value === 'dark'
}

function exactHttpOrigin(value: unknown): string | null {
  if (typeof value !== 'string' || !value) return null
  try {
    const parsed = new URL(value)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    return parsed.origin
  } catch {
    return null
  }
}

function configuredParentOrigin(): string | null {
  const candidates = [
    import.meta.env.VITE_VIBEDESK_PARENT_ORIGIN,
    import.meta.env.VITE_NEWMA_DESK_PARENT_ORIGIN,
    import.meta.env.VITE_NEWMA_DOCK_PARENT_ORIGIN,
  ]
  for (const candidate of candidates) {
    if (typeof candidate !== 'string' || !candidate) continue
    const origin = exactHttpOrigin(candidate)
    if (origin === candidate) return origin
  }
  return null
}

function ancestorParentOrigin(): string | null {
  const ancestors = window.location.ancestorOrigins
  return ancestors?.length ? exactHttpOrigin(ancestors[0]) : null
}

function originFromBootstrapConfig(data: Record<string, unknown>): string | null {
  if (data.type !== 'vibedesk:config') return null
  const gatewayOrigin = typeof data.gatewayOrigin === 'string' ? data.gatewayOrigin : ''
  const origin = exactHttpOrigin(gatewayOrigin)
  return origin === gatewayOrigin ? origin : null
}

function applyTheme(environmentTheme: unknown, appearance?: DeskAppearance) {
  if (!isThemeMode(environmentTheme)) return
  const mode = environmentTheme
  const activeAppearance = appearance?.mode === mode ? appearance : undefined

  root.dataset.theme = mode
  root.dataset.vibedeskTheme = mode
  root.dataset.bsTheme = mode
  root.classList.toggle('light', mode === 'light')
  root.classList.toggle('dark', mode === 'dark')
  root.style.colorScheme = mode

  const variables = Object.entries(activeAppearance?.cssVars ?? {})
    .filter(([name, value]) => cssVariableName.test(name) && typeof value === 'string')
  const nextVariables = new Set(variables.map(([name]) => name))
  appliedVariables.forEach((name) => {
    if (!nextVariables.has(name)) root.style.removeProperty(name)
  })
  variables.forEach(([name, value]) => {
    root.style.setProperty(name, value)
  })
  appliedVariables.clear()
  nextVariables.forEach((name) => appliedVariables.add(name))

  window.dispatchEvent(new CustomEvent('newma:themechange', {
    detail: { mode, ...(activeAppearance ? { appearance: activeAppearance } : {}) },
  }))
}

function compactText(value: string | null | undefined, limit: number) {
  return (value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit)
}

function isVisible(element: HTMLElement) {
  const style = window.getComputedStyle(element)
  const rect = element.getBoundingClientRect()
  return style.display !== 'none'
    && style.visibility !== 'hidden'
    && Number(style.opacity || '1') > 0
    && rect.width > 0
    && rect.height > 0
}

function controlLabel(element: HTMLElement) {
  return compactText(
    element.getAttribute('aria-label')
      ?? element.getAttribute('title')
      ?? element.textContent,
    160,
  )
}

function collectRenderedDomContext(): DeskPageContext {
  const contentRoot = document.querySelector<HTMLElement>('main')
    ?? document.querySelector<HTMLElement>('#root')
    ?? document.body
  const heading = contentRoot.querySelector<HTMLElement>('h1')
  const title = compactText(heading?.textContent ?? document.title, 160) || '周期叠加'
  const viewId = compactText(window.location.pathname.replace(/^\/+|\/+$/g, '').replace(/[^a-zA-Z0-9_-]+/g, '-'), 120)
    || 'market-surface'

  const visibleBlocks = Array.from(contentRoot.querySelectorAll<HTMLElement>('section, article, aside'))
    .filter(isVisible)
    .slice(0, 80)
    .map((element, index) => {
      const blockHeading = element.querySelector<HTMLElement>('h1, h2, h3, [role="heading"]')
      const blockTitle = compactText(blockHeading?.textContent, 160)
      return {
        id: compactText(element.id || `${viewId}-block-${index + 1}`, 128),
        type: element.tagName.toLowerCase(),
        ...(blockTitle ? { title: blockTitle } : {}),
      }
    })

  const activeControls = Array.from(contentRoot.querySelectorAll<HTMLElement>(
    'button.active, button.selected, [aria-pressed="true"], [aria-selected="true"], option:checked',
  ))
    .filter((element) => element instanceof HTMLOptionElement || isVisible(element))
    .map(controlLabel)
    .filter(Boolean)
    .slice(0, 120)

  const inputs = Array.from(contentRoot.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select'))
    .filter((element) => isVisible(element))
    .flatMap((element) => {
      const label = compactText(
        element.getAttribute('aria-label')
          ?? element.getAttribute('placeholder')
          ?? element.labels?.[0]?.textContent,
        120,
      )
      if (element instanceof HTMLInputElement && ['password', 'hidden'].includes(element.type)) return []
      const value = compactText(element.value, 240)
      return label || value ? [{ label, value }] : []
    })
    .slice(0, 80)

  const clone = contentRoot.cloneNode(true) as HTMLElement
  const visualElementCount = Array.from(contentRoot.querySelectorAll<HTMLElement>(
    'canvas, svg, img, video, [role="img"], [data-visual-context]',
  )).filter((element) => {
    if (element instanceof HTMLCanvasElement || element instanceof HTMLVideoElement) return true
    const rect = element.getBoundingClientRect()
    return rect.width >= 240 && rect.height >= 120
  }).length
  clone.querySelectorAll('script, style, noscript, svg, canvas').forEach((element) => element.remove())
  clone.querySelectorAll<HTMLElement>('[style]').forEach((element) => element.removeAttribute('style'))
  clone.querySelectorAll<HTMLInputElement>('input').forEach((element) => {
    if (['password', 'hidden'].includes(element.type)) {
      element.remove()
      return
    }
    element.setAttribute('value', element.value)
  })
  clone.querySelectorAll<HTMLOptionElement>('option').forEach((element) => {
    if (element.selected) element.setAttribute('selected', '')
  })

  return {
    view: { id: viewId, title },
    visibleBlocks,
    selection: { activeControls },
    filters: { inputs },
    data: {
      source: 'seven-cycle-rendered-dom',
      freshness: 'unknown',
      summary: {
        contextSource: 'dom-html-fallback',
        location: `${window.location.pathname}${window.location.search}${window.location.hash}`,
        visibleText: compactText(contentRoot.innerText, 16_000),
        renderedHtml: compactText(clone.outerHTML, 24_000),
        visualElementCount,
        warning: '这是当前已渲染页面的 DOM/HTML 兜底，不是 Manifest，也不等同于结构化研究数据。',
      },
    },
    actions: [],
    tasks: [],
  }
}

function pngDataUrlBytes(dataUrl: string) {
  const prefix = 'data:image/png;base64,'
  if (!dataUrl.startsWith(prefix)) throw new Error('视觉快照必须是 PNG')
  const payload = dataUrl.slice(prefix.length)
  const padding = payload.endsWith('==') ? 2 : payload.endsWith('=') ? 1 : 0
  return Math.floor(payload.length * 3 / 4) - padding
}

const systemTheme: ThemeMode = window.matchMedia('(prefers-color-scheme: dark)').matches
  ? 'dark'
  : 'light'
applyTheme(systemTheme)

if (isEmbedded) {
  root.dataset.vibedeskEmbedded = 'true'
  let parentOrigin = configuredParentOrigin()
    ?? ancestorParentOrigin()
    ?? exactHttpOrigin(document.referrer)
  let helloSent = false
  let activeInstanceId: string | null = null
  let activeModId = 'seven-cycle-research'

  const post = (message: unknown) => {
    if (parentOrigin) window.parent.postMessage(message, parentOrigin)
  }
  const sendHello = () => {
    if (!parentOrigin || helloSent) return
    helloSent = true
    post({
      type: 'vibedesk:hello',
      modId: 'seven-cycle-research',
      protocolVersions: ['1.0'],
      sdkVersion: 'seven-cycle-bridge-1.4.0',
      capabilities: ['context', 'theme', 'visual-context'],
    })
  }
  const respondWithContext = async (request: Record<string, any>) => {
    if (
      !activeInstanceId
      || request.instanceId !== activeInstanceId
      || request.modId !== activeModId
      || typeof request.requestId !== 'string'
    ) return

    let context: DeskPageContext | null = null
    let providerError: string | undefined
    try {
      context = contextProvider ? await contextProvider() : null
    } catch (error) {
      providerError = error instanceof Error ? error.message : '页面结构化上下文生成失败'
    }
    if (!context) context = collectRenderedDomContext()
    if (providerError) {
      context.data.summary = {
        ...(context.data.summary ?? {}),
        providerError,
      }
    }
    post({
      type: 'vibedesk:context',
      requestId: request.requestId,
      instanceId: activeInstanceId,
      modId: activeModId,
      context,
    })
  }
  publishCurrentContext = async () => {
    if (!activeInstanceId) return false
    await respondWithContext({
      requestId: crypto.randomUUID(),
      instanceId: activeInstanceId,
      modId: activeModId,
    })
    return true
  }
  const respondWithVisualContext = async (request: Record<string, any>) => {
    if (
      !activeInstanceId
      || request.instanceId !== activeInstanceId
      || request.modId !== activeModId
      || typeof request.requestId !== 'string'
    ) return
    if (!visualCaptureProvider) {
      post({
        type: 'vibedesk:visual-context',
        requestId: request.requestId,
        instanceId: activeInstanceId,
        modId: activeModId,
        ok: false,
        error: { code: 'visual_context_unavailable', message: '当前页面未提供视觉快照' },
      })
      return
    }
    try {
      const maxBytes = Number(request.maxBytes)
      if (!Number.isInteger(maxBytes) || maxBytes < 64 * 1024 || maxBytes > 5 * 1024 * 1024) {
        throw new Error('视觉快照大小限制无效')
      }
      const capture = await visualCaptureProvider({
        reason: request.reason === 'refresh' ? 'refresh' : 'agent',
        maxBytes,
      })
      if (!capture) throw new Error('当前页面没有可读取的图表')
      if (pngDataUrlBytes(capture.dataUrl) > maxBytes) throw new Error('视觉快照超过大小限制')
      post({
        type: 'vibedesk:visual-context',
        requestId: request.requestId,
        instanceId: activeInstanceId,
        modId: activeModId,
        ok: true,
        capture: {
          ...capture,
          capturedAt: capture.capturedAt ?? new Date().toISOString(),
        },
      })
    } catch (error) {
      post({
        type: 'vibedesk:visual-context',
        requestId: request.requestId,
        instanceId: activeInstanceId,
        modId: activeModId,
        ok: false,
        error: {
          code: 'visual_context_failed',
          message: error instanceof Error ? error.message.slice(0, 500) : '视觉快照生成失败',
        },
      })
    }
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || !event.data || typeof event.data !== 'object') return

    const data = event.data as Record<string, any>
    if (!parentOrigin) {
      const bootstrapOrigin = originFromBootstrapConfig(data)
      if (!bootstrapOrigin || event.origin !== bootstrapOrigin) return
      parentOrigin = bootstrapOrigin
    }
    if (event.origin !== parentOrigin) return

    if (data.type === 'vibedesk:context-request') {
      void respondWithContext(data)
      return
    }
    if (data.type === 'vibedesk:visual-context-request') {
      void respondWithVisualContext(data)
      return
    }
    if (data.type !== 'vibedesk:config' && data.type !== 'vibedesk:init') return

    const appearance = data.appearance as DeskAppearance | undefined
    const environmentTheme = data.type === 'vibedesk:init'
      ? data.environment?.theme
      : data.theme
    applyTheme(environmentTheme, appearance)
    if (data.type === 'vibedesk:config') sendHello()

    if (
      data.type === 'vibedesk:init'
      && data.protocolVersion === '1.0'
      && typeof data.instanceId === 'string'
    ) {
      activeInstanceId = data.instanceId
      activeModId = typeof data.modId === 'string' ? data.modId : 'seven-cycle-research'
      post({
        type: 'vibedesk:ack',
        protocolVersion: '1.0',
        instanceId: activeInstanceId,
        modId: activeModId,
      })
    }
  })

  if (parentOrigin) {
    post({ type: 'vibedesk:ready' })
    sendHello()
  } else {
    // Firefox does not expose ancestorOrigins. This empty legacy signal asks
    // Desk to resend vibedesk:config; only an exact gatewayOrigin/event.origin
    // match can lock the channel, and all subsequent messages use that origin.
    window.parent.postMessage({ type: 'vibedesk:ready' }, '*')
  }
} else {
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  media.addEventListener('change', (event) => applyTheme(event.matches ? 'dark' : 'light'))
}
