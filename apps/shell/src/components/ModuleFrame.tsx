import { ExternalLink, LoaderCircle, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ModuleManifest } from "@vibe-visualization/contracts";

import { resolveModuleUrl } from "../lib/moduleUrl";

interface ModuleFrameProps {
  manifest: ModuleManifest;
}

export function ModuleFrame({ manifest }: ModuleFrameProps) {
  const resolution = useMemo(() => {
    try {
      return { src: resolveModuleUrl(manifest.entry), error: undefined };
    } catch (error) {
      return {
        src: undefined,
        error: error instanceof Error ? error.message : "模块地址配置无效",
      };
    }
  }, [manifest.entry]);
  const [frameState, setFrameState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    setFrameState("loading");
    const frame = frameRef.current;
    if (!frame) return;

    const handleLoad = () => setFrameState("ready");
    const handleError = () => setFrameState("error");
    frame.addEventListener("load", handleLoad);
    frame.addEventListener("error", handleError);
    return () => {
      frame.removeEventListener("load", handleLoad);
      frame.removeEventListener("error", handleError);
    };
  }, [resolution.src]);

  if (resolution.error || !resolution.src) {
    return (
      <div className="frame-message frame-error" role="alert">
        <TriangleAlert size={20} aria-hidden="true" />
        <span>{resolution.error ?? "模块地址配置无效"}</span>
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
          正在加载模块…
        </div>
      ) : null}
      {frameState === "error" ? (
        <div className="frame-message frame-error" role="alert">
          <TriangleAlert size={18} aria-hidden="true" />
          模块页面加载失败，请稍后重试或独立打开。
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
