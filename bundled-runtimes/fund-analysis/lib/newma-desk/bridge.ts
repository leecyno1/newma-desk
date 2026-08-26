'use client'

export type NewmaDeskTheme = 'light' | 'dark'
export type NewmaDeskFreshness = 'live' | 'fresh' | 'stale' | 'unknown'

export type NewmaDeskAppearance = {
  contractVersion: '1.0'
  mode: NewmaDeskTheme
  cssVars: Record<string, string>
}

export type NewmaDeskInit = {
  type: 'vibedesk:init'
  protocolVersion: '1.0'
  instanceId: string
  modId: string
  user: { id: string }
  workspace: { id: string }
  environment: {
    theme: NewmaDeskTheme
    locale: string
    timezone: string
  }
  appearance?: NewmaDeskAppearance
  gateways: {
    actions: string
    agent: string
    model: string
    data: string
    storage?: string
  }
  grants: {
    permissions: string[]
    actions: string[]
  }
  session?: {
    id: string
    expiresAt: string
  }
}

export type NewmaDeskPageContext = {
  view: { id: string; title: string }
  visibleBlocks: Array<{ id: string; type: string; title?: string }>
  selection: Record<string, unknown>
  filters: Record<string, unknown>
  data: {
    asOf?: string
    source?: string
    freshness?: NewmaDeskFreshness
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

export type NewmaDeskEvent = {
  version: '1.0'
  event: string
  source: string
  target?: string
  traceId: string
  payload: Record<string, unknown>
}

type ContextProvider = () => NewmaDeskPageContext | Promise<NewmaDeskPageContext>
type EventListener = (event: NewmaDeskEvent) => void

type PendingAction = {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
  timer: number
}

export type NewmaDeskBridge = {
  embedded: boolean
  ready: Promise<NewmaDeskInit | null>
  getConfig: () => NewmaDeskInit | null
  setContextProvider: (provider: ContextProvider) => () => void
  publishContext: () => Promise<boolean>
  emitEvent: (event: string, payload: Record<string, unknown>, target?: string) => boolean
  subscribeEvent: (listener: EventListener) => () => void
  invokeAction: <T = unknown>(actionId: string, input?: Record<string, unknown>) => Promise<T>
  close: () => void
}

const ACTION_ID_PATTERN = /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/
const CSS_VARIABLE_PATTERN = /^--[a-z0-9-]{2,80}$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function safeHttpOrigin(value: string | undefined | null) {
  if (!value) return null
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol)) return null
    if (parsed.username || parsed.password) return null
    return parsed.origin
  } catch {
    return null
  }
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  return safeHttpOrigin(value) !== null
}

export function buildHelloMessage(modId: string) {
  return {
    type: 'vibedesk:hello' as const,
    modId,
    protocolVersions: ['1.0'] as const,
    sdkVersion: 'fund-research-adapter-0.1.0',
    capabilities: ['events', 'actions', 'agent', 'data', 'context', 'theme'] as const,
  }
}

export function buildAckMessage(init: NewmaDeskInit) {
  return {
    type: 'vibedesk:ack' as const,
    protocolVersion: init.protocolVersion,
    instanceId: init.instanceId,
    modId: init.modId,
  }
}

export function isDeskInitMessage(value: unknown, expectedModId: string): value is NewmaDeskInit {
  if (!isRecord(value) || value.type !== 'vibedesk:init') return false
  if (value.protocolVersion !== '1.0' || value.modId !== expectedModId) return false
  if (typeof value.instanceId !== 'string' || !value.instanceId) return false
  if (!isRecord(value.user) || typeof value.user.id !== 'string') return false
  if (!isRecord(value.workspace) || typeof value.workspace.id !== 'string') return false
  if (!isRecord(value.environment)) return false
  if (!['light', 'dark'].includes(String(value.environment.theme))) return false
  if (typeof value.environment.locale !== 'string' || typeof value.environment.timezone !== 'string') return false
  if (!isRecord(value.gateways)) return false
  const gateways = value.gateways as Record<string, unknown>
  if (!['actions', 'agent', 'model', 'data'].every((key) => isHttpUrl(gateways[key]))) return false
  if (gateways.storage !== undefined && !isHttpUrl(gateways.storage)) return false
  if (!isRecord(value.grants)) return false
  if (!Array.isArray(value.grants.permissions) || !Array.isArray(value.grants.actions)) return false
  return true
}

export function isNewmaDeskEvent(value: unknown): value is NewmaDeskEvent {
  if (!isRecord(value)) return false
  return value.version === '1.0'
    && typeof value.event === 'string'
    && ACTION_ID_PATTERN.test(value.event)
    && typeof value.source === 'string'
    && typeof value.traceId === 'string'
    && isRecord(value.payload)
}

function requestId(prefix: string) {
  return globalThis.crypto?.randomUUID?.()
    ?? `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function sanitizedAppearance(value: unknown, theme: NewmaDeskTheme): NewmaDeskAppearance | undefined {
  if (!isRecord(value) || value.contractVersion !== '1.0' || value.mode !== theme || !isRecord(value.cssVars)) {
    return undefined
  }
  const cssVars: Record<string, string> = {}
  for (const [name, cssValue] of Object.entries(value.cssVars).slice(0, 128)) {
    if (!CSS_VARIABLE_PATTERN.test(name)) continue
    if (typeof cssValue !== 'string' || cssValue.length > 200) continue
    cssVars[name] = cssValue
  }
  return { contractVersion: '1.0', mode: theme, cssVars }
}

const appliedAppearanceVariables = new Set<string>()

export function applyNewmaDeskEnvironment(
  environment: NewmaDeskInit['environment'],
  appearanceValue?: unknown,
) {
  const root = document.documentElement
  const theme = environment.theme
  const appearance = sanitizedAppearance(appearanceValue, theme)
  const nextVariables = new Set(Object.keys(appearance?.cssVars ?? {}))

  for (const name of appliedAppearanceVariables) {
    if (!nextVariables.has(name)) root.style.removeProperty(name)
  }
  for (const [name, cssValue] of Object.entries(appearance?.cssVars ?? {})) {
    root.style.setProperty(name, cssValue)
  }
  appliedAppearanceVariables.clear()
  for (const name of nextVariables) appliedAppearanceVariables.add(name)

  root.dataset.theme = theme
  root.dataset.vibedeskTheme = theme
  root.dataset.bsTheme = theme
  root.classList.toggle('dark', theme === 'dark')
  root.classList.toggle('light', theme === 'light')
  root.style.colorScheme = theme
  root.lang = environment.locale || 'zh-CN'
  root.dataset.newmaTimezone = environment.timezone

  window.dispatchEvent(new CustomEvent('newma:themechange', {
    detail: { mode: theme, appearance },
  }))
  window.dispatchEvent(new CustomEvent('newma:environmentchange', {
    detail: environment,
  }))
}

function applyStandaloneEnvironment() {
  const theme: NewmaDeskTheme = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
  applyNewmaDeskEnvironment({
    theme,
    locale: navigator.language || 'zh-CN',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
  })
}

export function createNewmaDeskBridge(options: {
  modId: string
  parentOrigin?: string
  initialContext: NewmaDeskPageContext
  timeoutMs?: number
}): NewmaDeskBridge {
  const embedded = window.self !== window.top
  const parentOrigin = safeHttpOrigin(options.parentOrigin)
    ?? safeHttpOrigin(window.location.ancestorOrigins?.[0])
    ?? safeHttpOrigin(document.referrer)
  const eventListeners = new Set<EventListener>()
  const pendingActions = new Map<string, PendingAction>()
  let currentConfig: NewmaDeskInit | null = null
  let contextProvider: ContextProvider = () => options.initialContext
  let closed = false
  let resolveReady: (config: NewmaDeskInit | null) => void = () => undefined
  const ready = new Promise<NewmaDeskInit | null>((resolve) => {
    resolveReady = resolve
  })

  document.documentElement.classList.toggle('vibedesk-embedded', embedded)
  applyStandaloneEnvironment()

  const post = (message: unknown) => {
    if (!embedded || !parentOrigin || closed) return false
    window.parent.postMessage(message, parentOrigin)
    return true
  }

  const publishContext = async (linkedRequestId?: string) => {
    if (!currentConfig) return false
    post({
      type: 'vibedesk:context',
      requestId: linkedRequestId ?? requestId('context'),
      instanceId: currentConfig.instanceId,
      modId: currentConfig.modId,
      context: await contextProvider(),
    })
    return true
  }

  const handleMessage = (message: MessageEvent) => {
    if (closed || !parentOrigin) return
    if (message.source !== window.parent || message.origin !== parentOrigin) return

    if (isNewmaDeskEvent(message.data)) {
      for (const listener of eventListeners) listener(message.data)
      return
    }

    if (isDeskInitMessage(message.data, options.modId)) {
      currentConfig = {
        ...message.data,
        appearance: sanitizedAppearance(message.data.appearance, message.data.environment.theme),
      }
      applyNewmaDeskEnvironment(currentConfig.environment, currentConfig.appearance)
      post(buildAckMessage(currentConfig))
      resolveReady(currentConfig)
      window.dispatchEvent(new CustomEvent('newma:configchange', { detail: currentConfig }))
      return
    }

    if (!currentConfig || !isRecord(message.data)) return
    if (message.data.modId !== currentConfig.modId || message.data.instanceId !== currentConfig.instanceId) return

    if (
      message.data.type === 'vibedesk:context-request'
      && typeof message.data.requestId === 'string'
      && ['initial', 'agent', 'refresh'].includes(String(message.data.reason))
    ) {
      void publishContext(message.data.requestId)
      return
    }

    if (message.data.type !== 'vibedesk:action-result' || typeof message.data.requestId !== 'string') return
    const pending = pendingActions.get(message.data.requestId)
    if (!pending) return
    pendingActions.delete(message.data.requestId)
    window.clearTimeout(pending.timer)
    if (message.data.ok === true) {
      pending.resolve(message.data.result)
      return
    }
    const error = isRecord(message.data.error) && typeof message.data.error.message === 'string'
      ? message.data.error.message
      : 'Newma-Desk action failed'
    pending.reject(new Error(error))
  }

  if (!embedded || !parentOrigin) {
    resolveReady(null)
  } else {
    window.addEventListener('message', handleMessage)
    post(buildHelloMessage(options.modId))
    window.setTimeout(() => {
      if (!currentConfig) resolveReady(null)
    }, Math.min(Math.max(options.timeoutMs ?? 2_500, 250), 10_000))
  }

  return {
    embedded,
    ready,
    getConfig: () => currentConfig,
    setContextProvider(provider) {
      contextProvider = provider
      return () => {
        if (contextProvider === provider) contextProvider = () => options.initialContext
      }
    },
    publishContext: () => publishContext(),
    emitEvent(event, payload, target) {
      if (!currentConfig || !ACTION_ID_PATTERN.test(event)) return false
      return post({
        version: '1.0',
        event,
        source: currentConfig.modId,
        ...(target ? { target } : {}),
        traceId: requestId('event'),
        payload,
      })
    },
    subscribeEvent(listener) {
      eventListeners.add(listener)
      return () => eventListeners.delete(listener)
    },
    invokeAction<T = unknown>(actionId: string, input: Record<string, unknown> = {}) {
      if (!currentConfig) return Promise.reject(new Error('Newma-Desk host is not connected'))
      if (!currentConfig.grants.actions.includes(actionId)) {
        return Promise.reject(new Error(`Action is not granted: ${actionId}`))
      }
      const id = requestId('action')
      return new Promise<T>((resolve, reject) => {
        const timer = window.setTimeout(() => {
          pendingActions.delete(id)
          reject(new Error(`Newma-Desk action timed out: ${actionId}`))
        }, 30_000)
        pendingActions.set(id, {
          resolve: (value) => resolve(value as T),
          reject,
          timer,
        })
        post({
          type: 'vibedesk:action-request',
          requestId: id,
          instanceId: currentConfig?.instanceId,
          modId: currentConfig?.modId,
          actionId,
          input,
        })
      })
    },
    close() {
      if (closed) return
      closed = true
      if (embedded && parentOrigin) window.removeEventListener('message', handleMessage)
      for (const pending of pendingActions.values()) {
        window.clearTimeout(pending.timer)
        pending.reject(new Error('Newma-Desk bridge closed'))
      }
      pendingActions.clear()
      eventListeners.clear()
    },
  }
}

export function buildFundSelectionEventPayload(selection: {
  symbol: string
  name?: string
  assetType?: 'fund' | 'etf'
}) {
  return {
    symbol: selection.symbol.trim().toUpperCase().slice(0, 24),
    name: (selection.name || selection.symbol).trim().slice(0, 80),
    market: 'CN',
    assetType: selection.assetType ?? 'fund',
    researchModule: 'professional-fund-research',
  }
}
