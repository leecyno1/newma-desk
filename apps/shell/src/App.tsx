import { AlertTriangle, Boxes, Eye, LoaderCircle, RotateCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getModuleRevision,
  listModules,
  type StoredModule,
} from "./api/modules";
import { ModuleFrame } from "./components/ModuleFrame";
import { Sidebar } from "./components/Sidebar";
import { ShellEventBus } from "./events/ShellEventBus";

const ACTIVE_MODULE_KEY = "vibe.shell.activeModule";
const PREVIEW_PATTERN = /^([a-z][a-z0-9-]{2,63})@([1-9]\d*)$/;

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "模块加载失败";
}

function storedSelection(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_MODULE_KEY);
  } catch {
    return null;
  }
}

function rememberSelection(moduleId: string) {
  try {
    window.localStorage.setItem(ACTIVE_MODULE_KEY, moduleId);
  } catch {
    // A blocked storage backend must not prevent module navigation.
  }
}

function preferredModule(modules: StoredModule[]): StoredModule | undefined {
  const requested = new URLSearchParams(window.location.search).get("module");
  const stored = storedSelection();
  return (
    modules.find((module) => module.moduleId === requested) ??
    modules.find((module) => module.moduleId === stored) ??
    modules[0]
  );
}

function writeModuleLocation(moduleId: string, mode: "push" | "replace") {
  const url = new URL(window.location.href);
  url.searchParams.delete("preview");
  url.searchParams.set("module", moduleId);
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
  const [modules, setModules] = useState<StoredModule[]>([]);
  const modulesRef = useRef<StoredModule[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const [registryError, setRegistryError] = useState<string>();
  const [previewMode, setPreviewMode] = useState(false);
  const [preview, setPreview] = useState<StoredModule>();
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
      const rows = await listModules();
      modulesRef.current = rows;
      setModules(rows);
      setRegistryLoaded(true);
      setSelectedId((current) => {
        const selection =
          rows.find((module) => module.moduleId === current) ??
          preferredModule(rows);

        if (
          selection &&
          !new URLSearchParams(window.location.search).has("preview")
        ) {
          rememberSelection(selection.moduleId);
          const requested = new URLSearchParams(window.location.search).get(
            "module",
          );
          if (requested !== selection.moduleId) {
            writeModuleLocation(selection.moduleId, "replace");
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
        setPreviewError("预览地址无效，请使用 module-id@revision。");
        return;
      }

      const moduleId = match[1];
      const revision = match[2];
      if (!moduleId || !revision) return;

      const controller = new AbortController();
      previewRequestRef.current = controller;
      setPreviewLoading(true);

      try {
        const result = await getModuleRevision(
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
    const selection = preferredModule(modulesRef.current);
    setSelectedId(selection?.moduleId);
    if (selection) rememberSelection(selection.moduleId);
  }, [cancelPreviewRequest, loadPreviewValue]);

  useEffect(() => {
    return () => eventBus.close();
  }, [eventBus]);

  useEffect(() => {
    void loadRegistry();
    syncLocation();
    window.addEventListener("popstate", syncLocation);
    return () => {
      window.removeEventListener("popstate", syncLocation);
      cancelPreviewRequest();
    };
  }, [cancelPreviewRequest, loadRegistry, syncLocation]);

  const selectModule = (module: StoredModule) => {
    cancelPreviewRequest();
    setPreviewMode(false);
    setPreview(undefined);
    setPreviewError(undefined);
    setSelectedId(module.moduleId);
    rememberSelection(module.moduleId);
    writeModuleLocation(module.moduleId, "push");
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
            正在读取模块注册表…
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
            <strong>尚无已发布模块</strong>
            <span>发布模块后，它会自动出现在左侧导航中。</span>
          </div>
        ) : null}
        {activeModule ? (
          <ModuleFrame
            key={`${activeModule.moduleId}@${activeModule.revision}`}
            manifest={activeModule.manifest}
            eventBus={eventBus}
          />
        ) : null}
      </main>
    </div>
  );
}
