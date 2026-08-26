import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import type { NavigationView } from '@/components/orchestra/NavigationPanel';

const workspaces: readonly NavigationView[] = [
  'committee',
  'history',
  'reports',
  'agents',
  'skills',
  'data',
  'workspace',
  'settings',
];
const workspaceSet = new Set<NavigationView>(workspaces);

export const ORCHESTRA_WORKSPACES = workspaces;

export function orchestraWorkspaceFromUrl(href = window.location.href): NavigationView {
  try {
    const value = new URL(href).searchParams.get('workspace') as NavigationView | null;
    return value && workspaceSet.has(value) ? value : 'committee';
  } catch {
    return 'committee';
  }
}

export function panelForWorkspace(workspace: NavigationView): NavigationView | null {
  return workspace === 'committee' ? null : workspace;
}

export function workspaceForPanel(panel: NavigationView | null): NavigationView {
  return panel ?? 'committee';
}

function updateWorkspaceUrl(workspace: NavigationView, replace = false) {
  const url = new URL(window.location.href);
  url.searchParams.set('workspace', workspace);
  window.history[replace ? 'replaceState' : 'pushState']({}, '', url);
}

export function useOrchestraWorkspace(): {
  workspace: NavigationView;
  activePanel: NavigationView | null;
  setActivePanel: Dispatch<SetStateAction<NavigationView | null>>;
} {
  const [activePanel, setActivePanelState] = useState<NavigationView | null>(() =>
    panelForWorkspace(orchestraWorkspaceFromUrl()),
  );
  const activePanelRef = useRef(activePanel);
  activePanelRef.current = activePanel;

  useEffect(() => {
    const syncFromLocation = () => {
      const next = panelForWorkspace(orchestraWorkspaceFromUrl());
      activePanelRef.current = next;
      setActivePanelState(next);
    };
    window.addEventListener('popstate', syncFromLocation);
    return () => window.removeEventListener('popstate', syncFromLocation);
  }, []);

  const setActivePanel = useCallback<Dispatch<SetStateAction<NavigationView | null>>>((value) => {
    const next = typeof value === 'function' ? value(activePanelRef.current) : value;
    activePanelRef.current = next;
    setActivePanelState(next);
    updateWorkspaceUrl(workspaceForPanel(next));
  }, []);

  return {
    workspace: workspaceForPanel(activePanel),
    activePanel,
    setActivePanel,
  };
}
