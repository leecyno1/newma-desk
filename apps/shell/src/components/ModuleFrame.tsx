import { ExternalLink, LoaderCircle, TriangleAlert } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  modEventSchema,
  type ModManifest,
} from "@vibedesk/contracts";

import type { ShellEventBus } from "../events/ShellEventBus";
import { resolveModUrl } from "../lib/moduleUrl";

interface ModFrameProps {
  manifest: ModManifest;
  eventBus: ShellEventBus;
}

function warnIgnoredMessage(reason: string) {
  if (import.meta.env.DEV && import.meta.env.MODE !== "test") {
    console.warn(`[ModFrame] ignored Mod message: ${reason}`);
  }
}

export function ModFrame({ manifest, eventBus }: ModFrameProps) {
  const resolution = useMemo(() => {
    try {
      return { src: resolveModUrl(manifest.entry), error: undefined };
    } catch (error) {
      return {
        src: undefined,
        error: error instanceof Error ? error.message : "Mod 地址配置无效",
      };
    }
  }, [manifest.entry]);
  const [frameState, setFrameState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const frameRef = useRef<HTMLIFrameElement>(null);

  useLayoutEffect(() => {
    setFrameState("loading");
    const frame = frameRef.current;
    if (!frame || !resolution.src) return;

    const expectedOrigin = new URL(resolution.src).origin;
    let registeredWindow: Window | null = null;

    const registerCurrentWindow = () => {
      if (registeredWindow) eventBus.unregister(registeredWindow);
      registeredWindow = frame.contentWindow;
      if (!registeredWindow) return;
      eventBus.register({
        moduleId: manifest.id,
        manifest,
        target: registeredWindow,
        origin: expectedOrigin,
      });
    };

    const handleLoad = () => {
      setFrameState("ready");
      registerCurrentWindow();
    };
    // Browser iframe error reporting is incomplete; this remains a
    // best-effort navigation hint rather than a module health protocol.
    const handleError = () => setFrameState("error");
    const handleMessage = (message: MessageEvent) => {
      const currentWindow = frame.contentWindow;
      if (
        !registeredWindow ||
        currentWindow !== registeredWindow ||
        message.source !== registeredWindow
      ) {
        warnIgnoredMessage("unexpected source window");
        return;
      }
      if (message.origin !== expectedOrigin) {
        warnIgnoredMessage("unexpected origin");
        return;
      }

      const parsed = modEventSchema.safeParse(message.data);
      if (!parsed.success) {
        warnIgnoredMessage("invalid envelope");
        return;
      }
      if (parsed.data.source !== manifest.id) {
        warnIgnoredMessage("source Mod mismatch");
        return;
      }
      if (!manifest.events.emits.includes(parsed.data.event)) {
        warnIgnoredMessage("undeclared emitted event");
        return;
      }

      eventBus.route(parsed.data, currentWindow ?? undefined);
    };

    frame.addEventListener("load", handleLoad);
    frame.addEventListener("error", handleError);
    window.addEventListener("message", handleMessage);
    return () => {
      frame.removeEventListener("load", handleLoad);
      frame.removeEventListener("error", handleError);
      window.removeEventListener("message", handleMessage);
      if (registeredWindow) eventBus.unregister(registeredWindow);
    };
  }, [eventBus, manifest, resolution.src]);

  if (resolution.error || !resolution.src) {
    return (
      <div className="frame-message frame-error" role="alert">
        <TriangleAlert size={20} aria-hidden="true" />
        <span>{resolution.error ?? "Mod 地址配置无效"}</span>
      </div>
    );
  }

  return (
    <section className="module-frame" aria-busy={frameState === "loading"}>
      <header className="frame-toolbar">
        <div>
          <strong>{manifest.name}</strong>
          <span>{manifest.version}</span>
        </div>
        <a href={resolution.src} target="_blank" rel="noreferrer">
          独立打开
          <ExternalLink size={14} aria-hidden="true" />
        </a>
      </header>
      {frameState === "loading" ? (
        <div className="frame-status" role="status">
          <LoaderCircle className="spin" size={18} aria-hidden="true" />
          正在加载 Mod…
        </div>
      ) : null}
      {frameState === "error" ? (
        <div className="frame-message frame-error" role="alert">
          <TriangleAlert size={18} aria-hidden="true" />
          Mod 页面可能未能加载，请尝试独立打开。
        </div>
      ) : null}
      <iframe
        ref={frameRef}
        title={manifest.name}
        src={resolution.src}
        sandbox="allow-scripts allow-forms allow-downloads allow-popups allow-same-origin"
        referrerPolicy="no-referrer"
        allow="clipboard-read; clipboard-write; fullscreen"
      />
    </section>
  );
}

// Compatibility export for code that still imports the former component name.
export const ModuleFrame = ModFrame;
