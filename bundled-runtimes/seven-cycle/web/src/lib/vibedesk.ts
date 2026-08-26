type ThemeMode = 'light' | 'dark'

type DeskAppearance = {
  mode?: ThemeMode
  cssVars?: Record<string, string>
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
      sdkVersion: 'seven-cycle-bridge-1.3.0',
      capabilities: ['context', 'theme'],
    })
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
      post({
        type: 'vibedesk:ack',
        protocolVersion: '1.0',
        instanceId: data.instanceId,
        modId: data.modId ?? 'seven-cycle-research',
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
