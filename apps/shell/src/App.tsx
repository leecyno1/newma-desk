import { AlertTriangle, Boxes, Eye, LoaderCircle, RotateCw } from "lucide-react";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  ModEvent,
  ModPageContext,
  WikiHandoff,
  WikiLink,
  WikiPageContext,
} from "@newma-desk/contracts";

import {
  getModRevision,
  listMods,
  type StoredMod,
} from "./api/modules";
import {
  createWikiHandoff,
  deleteWikiHandoff,
  getWikiHandoff,
  resolveWikiLinks,
} from "./api/wiki";
import { ModCopilot } from "./components/ModCopilot";
import {
  ModFrame,
  type ModFrameHandle,
} from "./components/ModuleFrame";
import { InterfaceSettings } from "./components/InterfaceSettings";
import { ModStore } from "./components/ModStore";
import { Sidebar } from "./components/Sidebar";
import { SuiteSettings } from "./components/SuiteSettings";
import { ShellEventBus } from "./events/ShellEventBus";
import {
  loadCategoryOverrides,
  loadSidebarNavigationPreferences,
  loadThemeMode,
  resolveTheme,
  saveCategoryOverrides,
  saveSidebarNavigationPreferences,
  saveThemeMode,
  systemPrefersDark,
  type SidebarNavigationPreferences,
  type ThemeMode,
} from "./lib/workspacePreferences";
import { loadWorkspaceIdentity } from "./lib/workspaceIdentity";
import {
  newmaHostIdentityFromLocation,
  parseNewmaHostContextRequest,
  postNewmaHostContext,
} from "./lib/hostBridge";
import { compileSidebarNavigation } from "./lib/sidebarNavigation";

const ACTIVE_MOD_KEY = "vibedesk.activeMod";
const LEGACY_ACTIVE_MODULE_KEY = "vibe.shell.activeModule";
const DEFAULT_MOD_ID = "global-situation";
const RETIRED_MOD_ALIASES: Readonly<Record<string, string>> = {
  "event-intelligence": DEFAULT_MOD_ID,
};
const PREVIEW_PATTERN = /^([a-z][a-z0-9-]{2,63})@([1-9]\d*)$/;
const HANDOFF_PATTERN = /^hf_[A-Za-z0-9_-]{8,120}$/;

const AgentSettings = lazy(async () => {
  const module = await import("./components/AgentSettings");
  return { default: module.AgentSettings };
});

type ShellView = "mod" | "agent-settings" | "interface-settings" | "store" | "suite-settings";
const DIRECTORY_PATTERN = /^[a-z][a-z0-9-]{1,63}$/;

interface AppProps {
  embedded?: boolean;
}

export function isEmbeddedShellContext(
  target: { self: unknown; top: unknown } = window,
): boolean {
  try {
    return target.self !== target.top;
  } catch {
    // Cross-origin frame access should fail closed into the embedded shell.
    return true;
  }
}

function directoryFromLocation(): string | undefined {
  const directory = new URLSearchParams(window.location.search).get("directory");
  return directory && DIRECTORY_PATTERN.test(directory) ? directory : undefined;
}

function viewFromLocation(): ShellView {
  const view = new URLSearchParams(window.location.search).get("view");
  if (
    view === "agent-settings" ||
    view === "interface-settings" ||
    view === "store" ||
    (view === "suite-settings" && directoryFromLocation() !== undefined)
  ) return view;
  return "mod";
}

function copilotFromLocation(): boolean {
  const value = new URLSearchParams(window.location.search).get("copilot");
  return value === "1" || value === "true" || value === "open";
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Mod 加载失败";
}

function storedSelection(): string | null {
  try {
    return (
      window.localStorage.getItem(ACTIVE_MOD_KEY) ??
      window.localStorage.getItem(LEGACY_ACTIVE_MODULE_KEY)
    );
  } catch {
    return null;
  }
}

function rememberSelection(modId: string) {
  try {
    window.localStorage.setItem(ACTIVE_MOD_KEY, modId);
  } catch {
    // A blocked storage backend must not prevent Mod navigation.
  }
}

function eventSummary(event: ModEvent): string {
  const symbol = event.payload.symbol;
  return `${event.event}${typeof symbol === "string" ? ` · ${symbol}` : ""}`;
}

function preferredMod(mods: StoredMod[]): StoredMod | undefined {
  const params = new URLSearchParams(window.location.search);
  const requestedRaw = params.get("mod") ?? params.get("module");
  const requested = requestedRaw
    ? RETIRED_MOD_ALIASES[requestedRaw] ?? requestedRaw
    : undefined;
  const storedRaw = storedSelection();
  const stored = storedRaw
    ? RETIRED_MOD_ALIASES[storedRaw] ?? storedRaw
    : undefined;
  return (
    mods.find((mod) => mod.moduleId === requested) ??
    mods.find((mod) => mod.moduleId === DEFAULT_MOD_ID) ??
    mods.find((mod) => mod.moduleId === stored) ??
    mods[0]
  );
}

function requestedModFromLocation(): string | undefined {
  const params = new URLSearchParams(window.location.search);
  const requestedRaw = params.get("mod") ?? params.get("module");
  return requestedRaw
    ? RETIRED_MOD_ALIASES[requestedRaw] ?? requestedRaw
    : undefined;
}

function handoffFromLocation(): string | undefined {
  const handoffId = new URLSearchParams(window.location.search).get("handoff");
  return handoffId && HANDOFF_PATTERN.test(handoffId) ? handoffId : undefined;
}

function writeModLocation(
  modId: string,
  mode: "push" | "replace",
  handoffId?: string,
) {
  const url = new URL(window.location.href);
  url.searchParams.delete("preview");
  url.searchParams.delete("module");
  url.searchParams.delete("view");
  url.searchParams.delete("directory");
  url.searchParams.set("mod", modId);
  if (handoffId) url.searchParams.set("handoff", handoffId);
  else url.searchParams.delete("handoff");
  window.history[mode === "push" ? "pushState" : "replaceState"](
    null,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

function writeCopilotLocation(open: boolean) {
  const url = new URL(window.location.href);
  if (open) url.searchParams.set("copilot", "1");
  else url.searchParams.delete("copilot");
  window.history.replaceState(
    null,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

interface ErrorBannerProps {
  message: string;
  onRetry: () => void;
}

function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <AlertTriangle size={18} aria-hidden="true" />
      <span>{message}</span>
      <button type="button" onClick={onRetry}>
        <RotateCw size={14} aria-hidden="true" />
        重试
      </button>
    </div>
  );
}

export function App({ embedded = isEmbeddedShellContext() }: AppProps = {}) {
  const [identity] = useState(loadWorkspaceIdentity);
  const [newmaHostIdentity] = useState(newmaHostIdentityFromLocation);
  const [eventBus] = useState(() => new ShellEventBus());
  const [lastEvent, setLastEvent] = useState<ModEvent>();
  const [modules, setModules] = useState<StoredMod[]>([]);
  const modulesRef = useRef<StoredMod[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [activeView, setActiveView] = useState<ShellView>(() =>
    embedded ? "mod" : viewFromLocation(),
  );
  const [suiteSettingsDirectoryId, setSuiteSettingsDirectoryId] = useState(
    () => (embedded ? undefined : directoryFromLocation()),
  );
  const [themeMode, setThemeMode] = useState<ThemeMode>(loadThemeMode);
  const [prefersDark, setPrefersDark] = useState(systemPrefersDark);
  const [categoryOverrides, setCategoryOverrides] = useState(
    loadCategoryOverrides,
  );
  const [navigationPreferences, setNavigationPreferences] = useState(
    loadSidebarNavigationPreferences,
  );
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const [registryError, setRegistryError] = useState<string>();
  const [previewMode, setPreviewMode] = useState(false);
  const [preview, setPreview] = useState<StoredMod>();
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string>();
  const [copilotOpen, setCopilotOpen] = useState(() =>
    embedded ? false : copilotFromLocation(),
  );
  const [wikiContext, setWikiContext] = useState<WikiPageContext>();
  const [wikiLinks, setWikiLinks] = useState<WikiLink[]>([]);
  const [wikiLoading, setWikiLoading] = useState(false);
  const [wikiResolutionError, setWikiResolutionError] = useState<string>();
  const [wikiActiveLinkId, setWikiActiveLinkId] = useState<string>();
  const [pendingHandoff, setPendingHandoff] = useState<WikiHandoff>();
  const [handoffLocationId, setHandoffLocationId] = useState(
    handoffFromLocation,
  );
  const [handoffError, setHandoffError] = useState<string>();
  const [handoffRetryNonce, setHandoffRetryNonce] = useState(0);
  const moduleFrameRef = useRef<ModFrameHandle>(null);
  const previewRequestRef = useRef<AbortController | undefined>(undefined);
  const previewRequestSequenceRef = useRef(0);
  const wikiRequestRef = useRef<AbortController | undefined>(undefined);
  const wikiContextKeyRef = useRef("");
  const deliveringHandoffRef = useRef<string | undefined>(undefined);
  const resolvedTheme = resolveTheme(themeMode, prefersDark);

  useEffect(() => {
    if (embedded) return;
    if (activeView === "agent-settings") {
      document.title = "Agent 设置 · Newma-Desk";
    } else if (activeView === "interface-settings") {
      document.title = "界面设置 · Newma-Desk";
    } else if (activeView === "store") {
      document.title = "Mod 商店 · Newma-Desk";
    }
  }, [activeView, embedded]);

  useEffect(() => {
    if (!embedded || !newmaHostIdentity) return;
    const handleHostRequest = (event: MessageEvent): void => {
      if (event.source !== window.parent) return;
      if (event.origin !== newmaHostIdentity.parentMessageOrigin) return;
      const request = parseNewmaHostContextRequest(event.data);
      if (
        !request ||
        request.projectId !== newmaHostIdentity.projectId ||
        request.workspaceId !== newmaHostIdentity.workspaceId ||
        request.modId !== selectedId
      ) {
        return;
      }
      void moduleFrameRef.current
        ?.requestContext(request.reason)
        .then((context) => {
          if (!context) return;
          postNewmaHostContext({
            context,
            identity: newmaHostIdentity,
            modId: request.modId,
            requestId: request.requestId,
          });
        });
    };
    window.addEventListener("message", handleHostRequest);
    return () => window.removeEventListener("message", handleHostRequest);
  }, [embedded, newmaHostIdentity, selectedId]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = (event: MediaQueryListEvent) => setPrefersDark(event.matches);
    setPrefersDark(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", resolvedTheme === "dark" ? "#0f1714" : "#f4efe3");
  }, [resolvedTheme]);

  const cancelPreviewRequest = useCallback(() => {
    previewRequestSequenceRef.current += 1;
    previewRequestRef.current?.abort();
    previewRequestRef.current = undefined;
  }, []);

  const loadRegistry = useCallback(async () => {
    setRegistryLoading(true);
    setRegistryError(undefined);

    try {
      const rows = await listMods();
      modulesRef.current = rows;
      setModules(rows);
      setRegistryLoaded(true);
      const requestedMod = requestedModFromLocation();
      if (
        embedded &&
        requestedMod &&
        !rows.some((module) => module.moduleId === requestedMod)
      ) {
        setSelectedId(undefined);
        setRegistryError(
          `当前 NewmaDesk 运行时未安装「${requestedMod}」，请先同步或更新该 Mod。`,
        );
        return;
      }
      setSelectedId((current) => {
        const selection =
          rows.find((module) => module.moduleId === current) ??
          preferredMod(rows);

        if (
          selection &&
          !new URLSearchParams(window.location.search).has("preview") &&
          (embedded || viewFromLocation() === "mod")
        ) {
          rememberSelection(selection.moduleId);
          const params = new URLSearchParams(window.location.search);
          const requested = params.get("mod") ?? params.get("module");
          if (requested !== selection.moduleId) {
            writeModLocation(
              selection.moduleId,
              "replace",
              handoffFromLocation(),
            );
          }
        }

        return selection?.moduleId;
      });
    } catch (reason) {
      setRegistryError(errorMessage(reason));
    } finally {
      setRegistryLoading(false);
    }
  }, [embedded]);

  const loadPreviewValue = useCallback(
    async (rawPreview: string) => {
      cancelPreviewRequest();
      const requestSequence = previewRequestSequenceRef.current;
      setPreviewMode(true);
      setPreview(undefined);
      setPreviewError(undefined);

      const match = PREVIEW_PATTERN.exec(rawPreview);
      if (!match) {
        setPreviewLoading(false);
        setPreviewError("预览地址无效，请使用 mod-id@revision。");
        return;
      }

      const moduleId = match[1];
      const revision = match[2];
      if (!moduleId || !revision) return;

      const controller = new AbortController();
      previewRequestRef.current = controller;
      setPreviewLoading(true);

      try {
        const result = await getModRevision(
          moduleId,
          revision,
          controller.signal,
        );
        if (
          controller.signal.aborted ||
          previewRequestSequenceRef.current !== requestSequence
        ) {
          return;
        }
        if (result.status !== "draft") {
          setPreviewError(
            `仅草稿修订可预览，当前修订状态为 ${result.status}。`,
          );
          return;
        }
        setPreview(result);
      } catch (reason) {
        if (
          controller.signal.aborted ||
          previewRequestSequenceRef.current !== requestSequence
        ) {
          return;
        }
        setPreviewError(errorMessage(reason));
      } finally {
        if (previewRequestSequenceRef.current === requestSequence) {
          previewRequestRef.current = undefined;
          setPreviewLoading(false);
        }
      }
    },
    [cancelPreviewRequest],
  );

  const syncLocation = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedView = embedded ? "mod" : viewFromLocation();
    setHandoffLocationId(
      requestedView === "mod" ? handoffFromLocation() : undefined,
    );
    setCopilotOpen(!embedded && requestedView === "mod" && copilotFromLocation());
    if (requestedView !== "mod") {
      cancelPreviewRequest();
      setPreviewMode(false);
      setPreview(undefined);
      setPreviewError(undefined);
      setPreviewLoading(false);
      setActiveView(requestedView);
      setSuiteSettingsDirectoryId(
        requestedView === "suite-settings" ? directoryFromLocation() : undefined,
      );
      return;
    }
    setActiveView("mod");
    setSuiteSettingsDirectoryId(undefined);
    const rawPreview = params.get("preview");
    if (rawPreview !== null) {
      void loadPreviewValue(rawPreview);
      return;
    }

    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setPreviewLoading(false);
    const selection = preferredMod(modulesRef.current);
    setSelectedId(selection?.moduleId);
    if (selection) rememberSelection(selection.moduleId);
  }, [cancelPreviewRequest, embedded, loadPreviewValue]);

  useEffect(() => {
    return () => eventBus.close();
  }, [eventBus]);

  useEffect(() => eventBus.subscribe(setLastEvent), [eventBus]);

  useEffect(() => {
    void loadRegistry();
    syncLocation();
    window.addEventListener("popstate", syncLocation);
    return () => {
      window.removeEventListener("popstate", syncLocation);
      cancelPreviewRequest();
    };
  }, [cancelPreviewRequest, loadRegistry, syncLocation]);

  const selectModule = (module: StoredMod, handoffId?: string) => {
    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setSelectedId(module.moduleId);
    setActiveView("mod");
    setSuiteSettingsDirectoryId(undefined);
    setHandoffLocationId(handoffId);
    if (!handoffId) {
      deliveringHandoffRef.current = undefined;
      setPendingHandoff(undefined);
      setHandoffError(undefined);
      setWikiActiveLinkId(undefined);
    }
    rememberSelection(module.moduleId);
    writeModLocation(module.moduleId, "push", handoffId);
  };

  const openAgentSettings = () => {
    openSettings("agent-settings");
  };

  const openInterfaceSettings = () => {
    openSettings("interface-settings");
  };

  const openStore = () => {
    openSettings("store");
  };

  const openSuiteSettings = (directoryId: string) => {
    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setActiveView("suite-settings");
    setCopilotOpen(false);
    setSuiteSettingsDirectoryId(directoryId);
    const url = new URL(window.location.href);
    url.searchParams.delete("preview");
    url.searchParams.delete("module");
    url.searchParams.delete("mod");
    url.searchParams.delete("copilot");
    url.searchParams.delete("handoff");
    url.searchParams.set("view", "suite-settings");
    url.searchParams.set("directory", directoryId);
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const openSettings = (view: Exclude<ShellView, "mod">) => {
    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setActiveView(view);
    setCopilotOpen(false);
    setSuiteSettingsDirectoryId(undefined);
    const url = new URL(window.location.href);
    url.searchParams.delete("preview");
    url.searchParams.delete("module");
    url.searchParams.delete("mod");
    url.searchParams.delete("directory");
    url.searchParams.delete("copilot");
    url.searchParams.delete("handoff");
    url.searchParams.set("view", view);
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const changeThemeMode = (mode: ThemeMode) => {
    setThemeMode(mode);
    saveThemeMode(mode);
  };

  const changeCategoryOverrides = (overrides: Record<string, string>) => {
    setCategoryOverrides(overrides);
    saveCategoryOverrides(overrides);
  };

  const changeNavigationPreferences = (
    preferences: SidebarNavigationPreferences,
  ) => {
    setNavigationPreferences(preferences);
    saveSidebarNavigationPreferences(preferences);
  };

  const retryPreview = () => {
    const rawPreview = new URLSearchParams(window.location.search).get(
      "preview",
    );
    if (rawPreview !== null) void loadPreviewValue(rawPreview);
  };

  const changeCopilotOpen = (open: boolean) => {
    if (embedded) return;
    setCopilotOpen(open);
    if (activeView === "mod" && !previewMode) writeCopilotLocation(open);
  };

  const selected = modules.find((module) => module.moduleId === selectedId);
  const sidebarNavigation = useMemo(
    () => compileSidebarNavigation(modules, categoryOverrides, navigationPreferences),
    [categoryOverrides, modules, navigationPreferences],
  );
  useEffect(() => {
    if (sidebarNavigation.preferences === navigationPreferences) return;
    setNavigationPreferences(sidebarNavigation.preferences);
    saveSidebarNavigationPreferences(sidebarNavigation.preferences);
  }, [navigationPreferences, sidebarNavigation.preferences]);
  const activeSuite = suiteSettingsDirectoryId
    ? sidebarNavigation.directoriesById.get(suiteSettingsDirectoryId)
    : undefined;
  const activeModule = previewMode ? preview : selected;
  const showEmpty =
    registryLoaded &&
    !registryLoading &&
    modules.length === 0 &&
    !previewMode &&
    !registryError;

  useLayoutEffect(() => {
    wikiRequestRef.current?.abort();
    wikiRequestRef.current = undefined;
    wikiContextKeyRef.current = "";
    setWikiContext(undefined);
    setWikiLinks([]);
    setWikiLoading(false);
    setWikiResolutionError(undefined);
  }, [activeModule?.moduleId, activeView, previewMode]);

  useEffect(() => () => wikiRequestRef.current?.abort(), []);

  const handleContextPublished = useCallback((context: ModPageContext) => {
    if (embedded && newmaHostIdentity && activeModule) {
      postNewmaHostContext({
        context,
        identity: newmaHostIdentity,
        modId: activeModule.moduleId,
      });
    }

    const nextWikiContext = context.wiki;
    if (!activeModule || previewMode || !nextWikiContext) {
      wikiRequestRef.current?.abort();
      wikiRequestRef.current = undefined;
      wikiContextKeyRef.current = "";
      setWikiContext(undefined);
      setWikiLinks([]);
      setWikiLoading(false);
      setWikiResolutionError(undefined);
      return;
    }

    const contextKey = `${activeModule.moduleId}:${JSON.stringify(nextWikiContext)}`;
    if (wikiContextKeyRef.current === contextKey) return;
    wikiContextKeyRef.current = contextKey;
    wikiRequestRef.current?.abort();
    const controller = new AbortController();
    wikiRequestRef.current = controller;
    setWikiContext(nextWikiContext);
    setWikiLoading(true);
    setWikiResolutionError(undefined);

    void resolveWikiLinks({
      sourceModId: activeModule.moduleId,
      context: nextWikiContext,
      limit: 5,
      signal: controller.signal,
    }).then((resolution) => {
      if (controller.signal.aborted) return;
      setWikiLinks(
        resolution.links.filter((link) =>
          modulesRef.current.some((module) => module.moduleId === link.targetModId),
        ),
      );
    }).catch((reason: unknown) => {
      if (
        controller.signal.aborted ||
        (typeof reason === "object" && reason !== null && "name" in reason && reason.name === "AbortError")
      ) return;
      setWikiLinks([]);
      setWikiResolutionError(
        reason instanceof Error ? reason.message : "关联研究暂不可用",
      );
    }).finally(() => {
      if (!controller.signal.aborted) setWikiLoading(false);
    });
  }, [activeModule, embedded, newmaHostIdentity, previewMode]);

  const openWikiLink = async (link: WikiLink) => {
    if (!activeModule || !wikiContext || wikiActiveLinkId) return;
    const target = modulesRef.current.find(
      (module) => module.moduleId === link.targetModId,
    );
    if (!target) {
      setHandoffError("关联 Mod 尚未安装或已停用");
      return;
    }

    setWikiActiveLinkId(link.id);
    setHandoffError(undefined);
    try {
      const handoff = await createWikiHandoff({
        userId: identity.userId,
        workspaceId: identity.workspaceId,
        sourceModId: activeModule.moduleId,
        targetModId: link.targetModId,
        entrypointId: link.entrypointId,
        context: wikiContext,
      });
      setPendingHandoff(handoff);
      deliveringHandoffRef.current = undefined;
      selectModule(target, handoff.id);
    } catch (reason) {
      setWikiActiveLinkId(undefined);
      setHandoffError(
        reason instanceof Error ? reason.message : "跨 Mod 切换失败",
      );
    }
  };

  const clearHandoffLocation = useCallback((handoffId: string) => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("handoff") !== handoffId) return;
    url.searchParams.delete("handoff");
    window.history.replaceState(
      null,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    );
    setHandoffLocationId(undefined);
  }, []);

  useEffect(() => {
    if (
      !handoffLocationId ||
      !selectedId ||
      pendingHandoff?.id === handoffLocationId ||
      activeView !== "mod" ||
      previewMode
    ) return;
    const controller = new AbortController();
    void getWikiHandoff({
      handoffId: handoffLocationId,
      userId: identity.userId,
      workspaceId: identity.workspaceId,
      signal: controller.signal,
    }).then((handoff) => {
      if (controller.signal.aborted) return;
      if (handoff.targetModId !== selectedId) {
        throw new Error("Wiki 交接目标与当前 Mod 不一致");
      }
      deliveringHandoffRef.current = undefined;
      setPendingHandoff(handoff);
      setHandoffError(undefined);
    }).catch((reason: unknown) => {
      if (
        controller.signal.aborted ||
        (typeof reason === "object" && reason !== null && "name" in reason && reason.name === "AbortError")
      ) return;
      setHandoffError(
        reason instanceof Error ? reason.message : "Wiki 交接已失效",
      );
    });
    return () => controller.abort();
  }, [
    activeView,
    handoffLocationId,
    handoffRetryNonce,
    identity.userId,
    identity.workspaceId,
    pendingHandoff?.id,
    previewMode,
    selectedId,
  ]);

  useEffect(() => {
    if (
      !pendingHandoff ||
      pendingHandoff.targetModId !== activeModule?.moduleId ||
      activeView !== "mod" ||
      previewMode ||
      deliveringHandoffRef.current === pendingHandoff.id
    ) return;
    const frame = moduleFrameRef.current;
    if (!frame) return;
    deliveringHandoffRef.current = pendingHandoff.id;
    let active = true;
    void frame.deliverHandoff(pendingHandoff).then(async () => {
      await deleteWikiHandoff({
        handoffId: pendingHandoff.id,
        userId: identity.userId,
        workspaceId: identity.workspaceId,
      }).catch(() => undefined);
      if (!active) return;
      clearHandoffLocation(pendingHandoff.id);
      setPendingHandoff(undefined);
      setWikiActiveLinkId(undefined);
      setHandoffError(undefined);
      deliveringHandoffRef.current = undefined;
    }).catch((reason: unknown) => {
      if (!active) return;
      deliveringHandoffRef.current = undefined;
      setHandoffError(
        reason instanceof Error ? reason.message : "目标 Mod 未能接收 Wiki 交接",
      );
    });
    return () => {
      active = false;
    };
  }, [
    activeModule?.moduleId,
    activeView,
    clearHandoffLocation,
    handoffRetryNonce,
    identity.userId,
    identity.workspaceId,
    pendingHandoff,
    previewMode,
  ]);

  const retryHandoff = () => {
    deliveringHandoffRef.current = undefined;
    setHandoffError(undefined);
    setHandoffRetryNonce((value) => value + 1);
  };

  return (
    <div className="shell-layout" data-embedded={embedded || undefined}>
      {!embedded ? (
        <Sidebar
          navigation={sidebarNavigation}
          selectedId={
            previewMode || activeView !== "mod" ? undefined : selectedId
          }
          onSelect={selectModule}
          onReload={() => void loadRegistry()}
          loading={registryLoading}
          agentSettingsActive={activeView === "agent-settings"}
          onOpenAgentSettings={openAgentSettings}
          interfaceSettingsActive={activeView === "interface-settings"}
          onOpenInterfaceSettings={openInterfaceSettings}
          storeActive={activeView === "store"}
          onOpenStore={openStore}
          suiteSettingsDirectoryId={
            activeView === "suite-settings" ? suiteSettingsDirectoryId : undefined
          }
          onOpenSuiteSettings={(directory) => openSuiteSettings(directory.id)}
          onNavigationPreferencesChange={changeNavigationPreferences}
        />
      ) : null}
      <main className="shell-content">
        {previewMode && preview ? (
          <div className="preview-banner">
            <Eye size={16} aria-hidden="true" />
            预览，尚未发布
          </div>
        ) : null}
        {registryError ? (
          <ErrorBanner
            message={registryError}
            onRetry={() => void loadRegistry()}
          />
        ) : null}
        {previewError ? (
          <ErrorBanner message={previewError} onRetry={retryPreview} />
        ) : null}
        {handoffError && pendingHandoff ? (
          <ErrorBanner message={handoffError} onRetry={retryHandoff} />
        ) : null}
        {activeView === "mod" && registryLoading && modules.length === 0 ? (
          <div className="content-state" role="status">
            <LoaderCircle className="spin" size={24} aria-hidden="true" />
            正在读取 Mod 列表…
          </div>
        ) : null}
        {activeView === "mod" && previewMode && previewLoading ? (
          <div className="content-state" role="status">
            <LoaderCircle className="spin" size={24} aria-hidden="true" />
            正在加载预览…
          </div>
        ) : null}
        {activeView === "mod" && showEmpty ? (
          <div className="content-state empty-state">
            <Boxes size={28} aria-hidden="true" />
            <strong>尚无已发布 Mod</strong>
            <span>发布 Mod 后，它会自动出现在左侧导航中。</span>
          </div>
        ) : null}
        {activeView === "agent-settings" ? (
          <Suspense
            fallback={(
              <div className="content-state" role="status">
                <LoaderCircle className="spin" size={24} aria-hidden="true" />
                正在加载 Agent 设置…
              </div>
            )}
          >
            <AgentSettings modules={modules} userId={identity.userId} />
          </Suspense>
        ) : activeView === "suite-settings" && activeSuite ? (
          <SuiteSettings
            suiteId={activeSuite.id}
            suiteLabel={activeSuite.label}
            modules={[
              ...activeSuite.modules,
              ...(activeSuite.settingsModule ? [activeSuite.settingsModule] : []),
            ].map((item) => item.module)}
            userId={identity.userId}
            workspaceId={identity.workspaceId}
            onOpenAgentSettings={openAgentSettings}
          />
        ) : activeView === "suite-settings" ? (
          <div className="content-state empty-state">
            <AlertTriangle size={28} aria-hidden="true" />
            <strong>项目不存在</strong>
            <span>该项目可能已被卸载或更名，请从左侧项目导航重新打开设置。</span>
          </div>
        ) : activeView === "store" ? (
          <ModStore onInstalled={loadRegistry} />
        ) : activeView === "interface-settings" ? (
          <InterfaceSettings
            modules={modules}
            themeMode={themeMode}
            onThemeModeChange={changeThemeMode}
            categoryOverrides={categoryOverrides}
            onCategoryOverridesChange={changeCategoryOverrides}
            navigationPreferences={navigationPreferences}
            onNavigationPreferencesChange={changeNavigationPreferences}
          />
        ) : activeModule ? (
          <div className="mod-workspace">
            <ModFrame
              key={`${activeModule.moduleId}@${activeModule.revision}`}
              ref={moduleFrameRef}
              manifest={activeModule.manifest}
              eventBus={eventBus}
              theme={resolvedTheme}
              userId={identity.userId}
              workspaceId={identity.workspaceId}
              embedded={embedded}
              copilotOpen={embedded ? false : copilotOpen}
              onToggleCopilot={
                embedded ? undefined : () => changeCopilotOpen(!copilotOpen)
              }
              onRequestCopilotOpen={
                embedded ? undefined : () => changeCopilotOpen(true)
              }
              onContextPublished={handleContextPublished}
              wikiSubjectName={wikiContext?.primarySubject.displayName}
              wikiLinks={wikiLinks}
              wikiLoading={wikiLoading}
              wikiActiveLinkId={wikiActiveLinkId}
              wikiError={wikiResolutionError ?? (!pendingHandoff ? handoffError : undefined)}
              onOpenWikiLink={(link) => void openWikiLink(link)}
            />
            {!embedded ? (
              <ModCopilot
                module={activeModule}
                open={copilotOpen}
                userId={identity.userId}
                workspaceId={identity.workspaceId}
                onClose={() => changeCopilotOpen(false)}
                onEditCompleted={() => moduleFrameRef.current?.reload()}
                onOpenAgentSettings={openAgentSettings}
                requestContext={() =>
                  moduleFrameRef.current?.requestContext("agent") ??
                  Promise.resolve(undefined)
                }
                invokeUiAction={(actionId, input) =>
                  moduleFrameRef.current?.invokeUiAction(actionId, input) ??
                  Promise.reject(new Error("当前 Mod 动作通道不可用"))
                }
              />
            ) : null}
          </div>
        ) : null}
        {!embedded && lastEvent ? (
          <div className="shell-event-log" aria-label="Mod 事件日志">
            <span>最近事件</span>
            <code>{eventSummary(lastEvent)}</code>
          </div>
        ) : null}
      </main>
    </div>
  );
}
