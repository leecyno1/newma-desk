// @vitest-environment jsdom

import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildOrchestraPageContext,
  orchestraModId,
  truncateContextText,
  useVibeDeskBridge,
} from '@/hooks/useVibeDeskBridge';

const context = buildOrchestraPageContext({
  workspace: 'history',
  topic: '光模块投资价值',
  mode: 'demo',
  snapshot: null,
  health: null,
  selectedPortfolio: null,
  eventCount: 4,
  artifactCount: 2,
  showThinking: true,
  showArtifacts: true,
});

const Harness = () => {
  useVibeDeskBridge('history', context);
  return <div>bridge</div>;
};

describe('VibeDesk bridge', () => {
  const originalParent = window.parent;

  afterEach(() => {
    Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
    document.documentElement.classList.remove('vibedesk-embedded');
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.vibedeskTheme;
    delete document.documentElement.dataset.bsTheme;
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.style.removeProperty('--vibe-accent');
    vi.unstubAllEnvs();
  });

  it('maps every Orchestra workspace to its dedicated Mod id', () => {
    expect(orchestraModId('committee')).toBe('orchestra-committee');
    expect(orchestraModId('reports')).toBe('orchestra-reports');
    expect(orchestraModId('settings')).toBe('orchestra-settings');
  });

  it('keeps oversized decisions within the Agent context budget', () => {
    const oversized = '投委会正式决议。'.repeat(2000);
    const truncated = truncateContextText(oversized);

    expect(new TextEncoder().encode(truncated).byteLength).toBeLessThanOrEqual(14 * 1024);
    expect(truncated).toContain('已为 VibeDesk Agent 上下文截断');
    expect(truncated.length).toBeLessThan(oversized.length);
  });

  it('completes the handshake and responds with current page context', async () => {
    const parent = { postMessage: vi.fn() };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    vi.stubEnv('VITE_VIBEDESK_PARENT_ORIGIN', 'https://desk.example');
    render(<Harness />);

    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vibedesk:hello', modId: 'orchestra-history' }),
      'https://desk.example',
    );

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:init',
          protocolVersion: '1.0',
          instanceId: 'instance-1',
          modId: 'orchestra-history',
          environment: { theme: 'dark', locale: 'zh-CN', timezone: 'Asia/Shanghai' },
        },
      }));
    });

    expect(document.documentElement.classList.contains('vibedesk-embedded')).toBe(true);
    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vibedesk:ack', instanceId: 'instance-1' }),
      'https://desk.example',
    );

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:context-request',
          requestId: 'context-1',
          instanceId: 'instance-1',
          modId: 'orchestra-history',
          reason: 'agent',
        },
      }));
    });

    await waitFor(() => {
      expect(parent.postMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'vibedesk:context',
          requestId: 'context-1',
          context: expect.objectContaining({
            view: { id: 'history', title: 'Orchestra 历史讨论' },
            selection: expect.objectContaining({ topic: '光模块投资价值' }),
          }),
        }),
        'https://desk.example',
      );
    });
  });

  it('uses the Desk environment theme as authority and clears stale appearance variables', () => {
    const parent = { postMessage: vi.fn() };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    vi.stubEnv('VITE_VIBEDESK_PARENT_ORIGIN', 'https://desk.example');
    render(<Harness />);

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:init',
          protocolVersion: '1.0',
          instanceId: 'instance-theme',
          modId: 'orchestra-history',
          environment: { theme: 'dark', locale: 'zh-CN', timezone: 'Asia/Shanghai' },
          appearance: {
            mode: 'light',
            cssVars: { '--vibe-accent': '#0066ff' },
          },
        },
      }));
    });

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('--vibe-accent')).toBe('');

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:config',
          theme: 'dark',
          appearance: {
            mode: 'dark',
            cssVars: { '--vibe-accent': '#c89a5a' },
          },
        },
      }));
    });

    expect(document.documentElement.style.getPropertyValue('--vibe-accent')).toBe('#c89a5a');

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:config',
          theme: 'light',
          appearance: { mode: 'dark', cssVars: { '--vibe-accent': '#0066ff' } },
        },
      }));
    });

    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.documentElement.style.getPropertyValue('--vibe-accent')).toBe('');
  });

  it('securely bootstraps from legacy config when Desk suppresses the referrer', () => {
    const parent = { postMessage: vi.fn() };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    render(<Harness />);

    expect(parent.postMessage).toHaveBeenCalledWith({ type: 'vibedesk:ready' }, '*');

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://desk.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:config',
          gatewayOrigin: 'https://desk.example',
          theme: 'dark',
          appearance: {
            mode: 'dark',
            cssVars: { '--vibe-accent': '#c89a5a' },
          },
        },
      }));
    });

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('--vibe-accent')).toBe('#c89a5a');
    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vibedesk:hello', modId: 'orchestra-history' }),
      'https://desk.example',
    );

    act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        origin: 'https://evil.example',
        source: parent as unknown as Window,
        data: {
          type: 'vibedesk:config',
          gatewayOrigin: 'https://evil.example',
          theme: 'light',
          appearance: { mode: 'light', cssVars: { '--vibe-accent': '#0066ff' } },
        },
      }));
    });

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.getPropertyValue('--vibe-accent')).toBe('#c89a5a');
  });

  it('accepts the Newma Desk parent-origin environment alias', () => {
    const parent = { postMessage: vi.fn() };
    Object.defineProperty(window, 'parent', { configurable: true, value: parent });
    vi.stubEnv('VITE_NEWMA_DESK_PARENT_ORIGIN', 'https://desk.example');
    render(<Harness />);

    expect(parent.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'vibedesk:hello', modId: 'orchestra-history' }),
      'https://desk.example',
    );
  });
});
