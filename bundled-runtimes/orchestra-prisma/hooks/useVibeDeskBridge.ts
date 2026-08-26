import { useEffect, useRef } from 'react';
import type { NavigationView } from '@/components/orchestra/NavigationPanel';
import type { ExecutionMode, HealthStatus, RunSnapshot } from '@/types/orchestra';

type Freshness = 'live' | 'fresh' | 'stale' | 'unknown';

const MAX_DECISION_CONTEXT_BYTES = 14 * 1024;
const TRUNCATION_NOTICE = '\n\n[内容过长，已为 VibeDesk Agent 上下文截断]';

function utf8Bytes(value: string): number {
  let total = 0;
  for (const char of value) {
    const codePoint = char.codePointAt(0) ?? 0;
    total += codePoint <= 0x7f ? 1 : codePoint <= 0x7ff ? 2 : codePoint <= 0xffff ? 3 : 4;
  }
  return total;
}

export function truncateContextText(
  value: string,
  maxBytes = MAX_DECISION_CONTEXT_BYTES,
): string {
  if (utf8Bytes(value) <= maxBytes) return value;

  const contentBudget = Math.max(0, maxBytes - utf8Bytes(TRUNCATION_NOTICE));
  let used = 0;
  let truncated = '';
  for (const char of value) {
    const charBytes = utf8Bytes(char);
    if (used + charBytes > contentBudget) break;
    truncated += char;
    used += charBytes;
  }
  return `${truncated}${TRUNCATION_NOTICE}`;
}

export type OrchestraPageContext = {
  view: { id: string; title: string };
  visibleBlocks: Array<{ id: string; type: string; title?: string }>;
  selection: Record<string, unknown>;
  filters: Record<string, unknown>;
  data: {
    asOf?: string;
    source?: string;
    freshness?: Freshness;
    summary?: Record<string, unknown>;
  };
  actions: Array<{ id: string; label?: string; available?: boolean }>;
  tasks: Array<{ id: string; status: string; actionId?: string }>;
};

const workspaceMeta: Record<NavigationView, { modId: string; title: string; block: string }> = {
  committee: { modId: 'orchestra-committee', title: 'Orchestra 投委会', block: '投委会工作流' },
  history: { modId: 'orchestra-history', title: 'Orchestra 历史讨论', block: '历史讨论档案' },
  reports: { modId: 'orchestra-reports', title: 'Orchestra 研究成果', block: '研究成果库' },
  agents: { modId: 'orchestra-agents', title: 'Orchestra 研究席位', block: 'Agent Profile' },
  skills: { modId: 'orchestra-skills', title: 'Orchestra Skills', block: 'Skills 能力矩阵' },
  data: { modId: 'orchestra-data', title: 'Orchestra 数据工具', block: '数据工具状态' },
  workspace: { modId: 'orchestra-workspace', title: 'Orchestra 账户与组合', block: '账户与组合' },
  settings: { modId: 'orchestra-settings', title: 'Orchestra 运行设置', block: '运行设置' },
};

export function orchestraModId(workspace: NavigationView): string {
  return workspaceMeta[workspace].modId;
}

export function buildOrchestraPageContext(input: {
  workspace: NavigationView;
  topic: string;
  mode: ExecutionMode;
  snapshot: RunSnapshot | null;
  health: HealthStatus | null;
  selectedPortfolio: { id: string; name: string } | null;
  selectedAgentId?: string;
  selectedArtifactId?: string;
  eventCount: number;
  artifactCount: number;
  showThinking: boolean;
  showArtifacts: boolean;
}): OrchestraPageContext {
  const meta = workspaceMeta[input.workspace];
  const runtimes = Object.values(input.snapshot?.agents ?? {});
  const workingAgents = runtimes.filter((runtime) => runtime.status === 'working').length;
  const completedAgents = runtimes.filter((runtime) => runtime.status === 'completed').length;
  const freshness: Freshness = input.health?.status === 'ok' ? 'fresh' : 'unknown';

  return {
    view: { id: input.workspace, title: meta.title },
    visibleBlocks: [
      { id: 'commandbar', type: 'toolbar', title: '投委会命令栏' },
      { id: input.workspace, type: 'workspace', title: meta.block },
      ...(input.selectedAgentId
        ? [{ id: 'agent-profile', type: 'drawer', title: 'Agent 详情' }]
        : []),
      ...(input.selectedArtifactId
        ? [{ id: 'report-reader', type: 'document', title: 'Markdown 报告' }]
        : []),
    ],
    selection: {
      workspace: input.workspace,
      topic: input.topic,
      runId: input.snapshot?.id ?? null,
      portfolioId: input.selectedPortfolio?.id ?? null,
      portfolioName: input.selectedPortfolio?.name ?? null,
      agentId: input.selectedAgentId ?? null,
      artifactId: input.selectedArtifactId ?? null,
    },
    filters: {
      mode: input.mode,
      showThinking: input.showThinking,
      showArtifacts: input.showArtifacts,
    },
    data: {
      ...(input.snapshot?.updated_at ? { asOf: input.snapshot.updated_at } : {}),
      source: 'orchestra-api',
      freshness,
      summary: {
        status: input.snapshot?.status ?? 'idle',
        phase: input.snapshot?.phase ?? 'queued',
        revision: input.snapshot?.revision ?? 0,
        workingAgents,
        completedAgents,
        totalAgents: runtimes.length,
        eventCount: input.eventCount,
        artifactCount: input.artifactCount,
        serviceReady: input.health?.status === 'ok',
        liveReady: input.health?.live_ready ?? false,
        model: input.health?.model ?? null,
        decision: input.snapshot?.decision
          ? truncateContextText(input.snapshot.decision)
          : null,
      },
    },
    actions: [],
    tasks: input.snapshot && ['queued', 'running'].includes(input.snapshot.status)
      ? [{ id: input.snapshot.id, status: input.snapshot.phase }]
      : [],
  };
}

function exactHttpOrigin(value: string): string | null {
  try {
    const parsed = new URL(value);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.origin !== value) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function httpOriginFromUrl(value: string): string | null {
  try {
    const parsed = new URL(value);
    if (!['http:', 'https:'].includes(parsed.protocol)) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function configuredDeskOrigin(): string | null {
  const candidates = [
    import.meta.env.VITE_VIBEDESK_PARENT_ORIGIN,
    import.meta.env.VITE_NEWMA_DESK_PARENT_ORIGIN,
    import.meta.env.VITE_NEWMA_DOCK_PARENT_ORIGIN,
  ];
  for (const candidate of candidates) {
    const origin = exactHttpOrigin(candidate || '');
    if (origin) return origin;
  }
  return null;
}

function ancestorDeskOrigin(): string | null {
  const ancestors = window.location.ancestorOrigins;
  return ancestors?.length ? exactHttpOrigin(ancestors[0]) : null;
}

function originFromBootstrapConfig(data: Record<string, unknown>): string | null {
  if (data.type !== 'vibedesk:config') return null;
  return exactHttpOrigin(typeof data.gatewayOrigin === 'string' ? data.gatewayOrigin : '');
}

type ThemeMode = 'light' | 'dark';

type DeskAppearance = {
  mode?: ThemeMode;
  cssVars?: Record<string, string>;
};

const appliedAppearanceVariables = new Set<string>();

function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'light' || value === 'dark';
}

function applyDeskAppearance(
  environmentTheme: unknown,
  appearance?: DeskAppearance,
): void {
  if (!isThemeMode(environmentTheme)) return;
  const mode = environmentTheme;
  const activeAppearance = appearance?.mode === mode ? appearance : undefined;

  const root = document.documentElement;
  root.dataset.theme = mode;
  root.dataset.vibedeskTheme = mode;
  root.dataset.bsTheme = mode;
  root.classList.toggle('light', mode === 'light');
  root.classList.toggle('dark', mode === 'dark');
  root.style.colorScheme = mode;

  const variables = activeAppearance?.cssVars ?? {};
  const nextVariables = new Set(Object.keys(variables));
  for (const name of appliedAppearanceVariables) {
    if (!nextVariables.has(name)) root.style.removeProperty(name);
  }
  for (const [name, value] of Object.entries(variables)) {
    if (/^--[a-z0-9-]{2,80}$/.test(name) && typeof value === 'string') {
      root.style.setProperty(name, value);
    }
  }
  appliedAppearanceVariables.clear();
  nextVariables.forEach((name) => appliedAppearanceVariables.add(name));

  window.dispatchEvent(new CustomEvent('newma:themechange', {
    detail: { mode, ...(activeAppearance ? { appearance: activeAppearance } : {}) },
  }));
}

function requestId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useVibeDeskBridge(
  workspace: NavigationView,
  context: OrchestraPageContext,
) {
  const contextRef = useRef(context);
  const publishRef = useRef<(() => void) | null>(null);
  const trustedParentOriginRef = useRef<string | null>(
    configuredDeskOrigin()
      ?? ancestorDeskOrigin()
      ?? httpOriginFromUrl(document.referrer),
  );
  contextRef.current = context;

  useEffect(() => {
    publishRef.current?.();
  }, [context]);

  useEffect(() => {
    if (window.parent === window) {
      const media = window.matchMedia('(prefers-color-scheme: dark)');
      const syncSystemTheme = () => applyDeskAppearance(media.matches ? 'dark' : 'light');
      syncSystemTheme();
      media.addEventListener('change', syncSystemTheme);
      return () => media.removeEventListener('change', syncSystemTheme);
    }
    const modId = orchestraModId(workspace);
    let instanceId: string | null = null;
    let parentOrigin = trustedParentOriginRef.current;
    let helloSent = false;
    const root = document.documentElement;
    root.classList.add('vibedesk-embedded');

    const post = (message: unknown) => {
      if (parentOrigin) window.parent.postMessage(message, parentOrigin);
    };
    const sendHello = () => {
      if (!parentOrigin || helloSent) return;
      helloSent = true;
      post({
        type: 'vibedesk:hello',
        modId,
        protocolVersions: ['1.0'],
        sdkVersion: 'orchestra-bridge-1.1.0',
        capabilities: ['context', 'theme'],
      });
    };
    const publishContext = (linkedRequestId = requestId()) => {
      if (!instanceId) return;
      post({
        type: 'vibedesk:context',
        requestId: linkedRequestId,
        instanceId,
        modId,
        context: contextRef.current,
      });
    };
    publishRef.current = publishContext;

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return;
      const data = event.data as Record<string, unknown> | null;
      if (!data) return;
      if (!parentOrigin) {
        const bootstrapOrigin = originFromBootstrapConfig(data);
        if (!bootstrapOrigin || event.origin !== bootstrapOrigin) return;
        parentOrigin = bootstrapOrigin;
        trustedParentOriginRef.current = bootstrapOrigin;
      }
      if (event.origin !== parentOrigin) return;
      if (
        data?.type === 'vibedesk:init'
        && data.protocolVersion === '1.0'
        && data.modId === modId
        && typeof data.instanceId === 'string'
      ) {
        instanceId = data.instanceId;
        const environment = data.environment as Record<string, unknown> | undefined;
        applyDeskAppearance(
          environment?.theme,
          data.appearance as DeskAppearance | undefined,
        );
        if (typeof environment?.locale === 'string') {
          root.lang = environment.locale;
          root.dataset.vibedeskLocale = environment.locale;
        }
        if (typeof environment?.timezone === 'string') {
          root.dataset.vibedeskTimezone = environment.timezone;
        }
        post({
          type: 'vibedesk:ack',
          protocolVersion: '1.0',
          instanceId,
          modId,
        });
        return;
      }
      if (data?.type === 'vibedesk:config') {
        applyDeskAppearance(
          data.theme,
          data.appearance as DeskAppearance | undefined,
        );
        sendHello();
        return;
      }
      if (
        data?.type === 'vibedesk:context-request'
        && data.modId === modId
        && data.instanceId === instanceId
        && typeof data.requestId === 'string'
      ) {
        publishContext(data.requestId);
      }
    };

    window.addEventListener('message', handleMessage);
    if (parentOrigin) {
      sendHello();
    } else {
      // Desk deliberately uses `referrerPolicy="no-referrer"`. This empty,
      // non-sensitive legacy signal asks it to resend vibedesk:config; that
      // response is accepted only when gatewayOrigin exactly matches the
      // MessageEvent origin, after which every exchange uses the locked origin.
      window.parent.postMessage({ type: 'vibedesk:ready' }, '*');
    }

    return () => {
      window.removeEventListener('message', handleMessage);
      publishRef.current = null;
      root.classList.remove('vibedesk-embedded');
      delete root.dataset.vibedeskLocale;
      delete root.dataset.vibedeskTimezone;
    };
  }, [workspace]);
}
