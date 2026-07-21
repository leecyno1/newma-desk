import { AlertTriangle, Boxes, Eye, LoaderCircle, RotateCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ModEvent } from "@vibedesk/contracts";

import {
  getModRevision,
  listMods,
  type StoredMod,
} from "./api/modules";
import { ModFrame } from "./components/ModuleFrame";
import { Sidebar } from "./components/Sidebar";
import { ShellEventBus } from "./events/ShellEventBus";

const ACTIVE_MOD_KEY = "vibedesk.activeMod";
const LEGACY_ACTIVE_MODULE_KEY = "vibe.shell.activeModule";
const PREVIEW_PATTERN = /^([a-z][a-z0-9-]{2,63})@([1-9]\d*)$/;

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
  const requested = params.get("mod") ?? params.get("module");
  const stored = storedSelection();
  return (
    mods.find((mod) => mod.moduleId === requested) ??
    mods.find((mod) => mod.moduleId === stored) ??
    mods[0]
  );
}

function writeModLocation(modId: string, mode: "push" | "replace") {
  const url = new URL(window.location.href);
  url.searchParams.delete("preview");
  url.searchParams.delete("module");
  url.searchParams.set("mod", modId);
  window.history[mode === "push" ? "pushState" : "replaceState"](
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

export function App() {
  const [eventBus] = useState(() => new ShellEventBus());
  const [lastEvent, setLastEvent] = useState<ModEvent>();
  const [modules, setModules] = useState<StoredMod[]>([]);
  const modulesRef = useRef<StoredMod[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const [registryError, setRegistryError] = useState<string>();
  const [previewMode, setPreviewMode] = useState(false);
  const [preview, setPreview] = useState<StoredMod>();
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string>();
  const previewRequestRef = useRef<AbortController | undefined>(undefined);
  const previewRequestSequenceRef = useRef(0);

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
      setSelectedId((current) => {
        const selection =
          rows.find((module) => module.moduleId === current) ??
          preferredMod(rows);

        if (
          selection &&
          !new URLSearchParams(window.location.search).has("preview")
        ) {
          rememberSelection(selection.moduleId);
          const params = new URLSearchParams(window.location.search);
          const requested = params.get("mod") ?? params.get("module");
          if (requested !== selection.moduleId) {
            writeModLocation(selection.moduleId, "replace");
          }
        }

        return selection?.moduleId;
      });
    } catch (reason) {
      setRegistryError(errorMessage(reason));
    } finally {
      setRegistryLoading(false);
    }
  }, []);

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
  }, [cancelPreviewRequest, loadPreviewValue]);

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

  const selectModule = (module: StoredMod) => {
    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setSelectedId(module.moduleId);
    rememberSelection(module.moduleId);
    writeModLocation(module.moduleId, "push");
  };

  const retryPreview = () => {
    const rawPreview = new URLSearchParams(window.location.search).get(
      "preview",
    );
    if (rawPreview !== null) void loadPreviewValue(rawPreview);
  };

  const selected = modules.find((module) => module.moduleId === selectedId);
  const activeModule = previewMode ? preview : selected;
  const showEmpty =
    registryLoaded &&
    !registryLoading &&
    modules.length === 0 &&
    !previewMode &&
    !registryError;

  return (
    <div className="shell-layout">
      <Sidebar
        modules={modules}
        selectedId={previewMode ? undefined : selectedId}
        onSelect={selectModule}
        onReload={() => void loadRegistry()}
        loading={registryLoading}
      />
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
        {registryLoading && modules.length === 0 ? (
          <div className="content-state" role="status">
            <LoaderCircle className="spin" size={24} aria-hidden="true" />
            正在读取 Mod 列表…
          </div>
        ) : null}
        {previewMode && previewLoading ? (
          <div className="content-state" role="status">
            <LoaderCircle className="spin" size={24} aria-hidden="true" />
            正在加载预览…
          </div>
        ) : null}
        {showEmpty ? (
          <div className="content-state empty-state">
            <Boxes size={28} aria-hidden="true" />
            <strong>尚无已发布 Mod</strong>
            <span>发布 Mod 后，它会自动出现在左侧导航中。</span>
          </div>
        ) : null}
        {activeModule ? (
          <ModFrame
            key={`${activeModule.moduleId}@${activeModule.revision}`}
            manifest={activeModule.manifest}
            eventBus={eventBus}
          />
        ) : null}
        {lastEvent ? (
          <div className="shell-event-log" aria-label="Mod 事件日志">
            <span>最近事件</span>
            <code>{eventSummary(lastEvent)}</code>
          </div>
        ) : null}
      </main>
    </div>
  );
}
