import { useCallback, useEffect, useRef } from "react";

import type { ArtifactBlock as ArtifactBlockContract } from "@newma-desk/contracts";

import { serializeEmbeddedJson } from "../embeddedJson";
import { resolvePath } from "../resolvePath";


interface ArtifactBlockProps {
  block: ArtifactBlockContract;
  data: unknown;
}


function safeArtifactUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const base = globalThis.location?.origin || "https://module.local";
    const url = new URL(value, base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}


type ArtifactThemeMode = "light" | "dark";


function themedArtifactUrl(value: string): string {
  const url = new URL(value);
  url.searchParams.set("newmaTheme", "1");
  return url.toString();
}


function eventTheme(event?: Event): {
  mode?: ArtifactThemeMode;
  cssVars?: Record<string, unknown>;
} {
  const detail = (event as CustomEvent<unknown> | undefined)?.detail;
  if (!detail || typeof detail !== "object") return {};
  const value = detail as Record<string, unknown>;
  const appearance = value.appearance && typeof value.appearance === "object"
    ? value.appearance as Record<string, unknown>
    : undefined;
  const environment = value.environment && typeof value.environment === "object"
    ? value.environment as Record<string, unknown>
    : undefined;
  const candidate = value.mode ?? value.theme ?? appearance?.mode ?? environment?.theme;
  return {
    mode: candidate === "dark" || candidate === "light" ? candidate : undefined,
    cssVars: appearance?.cssVars && typeof appearance.cssVars === "object"
      ? appearance.cssVars as Record<string, unknown>
      : value.cssVars && typeof value.cssVars === "object"
        ? value.cssVars as Record<string, unknown>
        : undefined,
  };
}


function currentTheme(event?: Event): {
  mode: ArtifactThemeMode;
  cssVars: Record<string, string>;
} {
  const root = document.documentElement;
  const detail = eventTheme(event);
  const marker = root.dataset.theme ?? root.dataset.vibedeskTheme;
  const mode = detail.mode ?? (
    marker === "dark" || marker === "light"
      ? marker
      : root.classList.contains("dark") || getComputedStyle(root).colorScheme === "dark"
        ? "dark"
        : "light"
  );
  const cssVars = new Map<string, string>();
  const addVariables = (style: CSSStyleDeclaration) => {
    for (let index = 0; index < style.length; index += 1) {
      const name = style.item(index);
      if (!name.startsWith("--vibe-") && !name.startsWith("--newma-")) continue;
      const value = style.getPropertyValue(name).trim();
      if (value) cssVars.set(name, value);
    }
  };
  addVariables(getComputedStyle(root));
  addVariables(root.style);
  for (const [name, value] of Object.entries(detail.cssVars ?? {})) {
    if ((name.startsWith("--vibe-") || name.startsWith("--newma-")) &&
        typeof value === "string" && value.trim()) {
      cssVars.set(name, value.trim());
    }
  }
  return { mode, cssVars: Object.fromEntries(cssVars) };
}


export function ArtifactBlock({ block, data }: ArtifactBlockProps) {
  const safeUrl = safeArtifactUrl(resolvePath(data, block.urlPath));
  const url = safeUrl ? themedArtifactUrl(safeUrl) : null;
  const frameRef = useRef<HTMLIFrameElement>(null);
  const spec = block.specPath ? resolvePath(data, block.specPath) : undefined;
  const serializableSpec = spec !== undefined && spec !== null && typeof spec === "object"
    ? spec
    : undefined;
  const sendTheme = useCallback((event?: Event) => {
    if (!url || !frameRef.current?.contentWindow) return;
    frameRef.current.contentWindow.postMessage(
      { type: "newma:artifact-theme", ...currentTheme(event) },
      new URL(url).origin,
    );
  }, [url]);

  useEffect(() => {
    const forwardTheme = (event: Event) => sendTheme(event);
    window.addEventListener("newma:themechange", forwardTheme);
    window.addEventListener("vibedesk:theme", forwardTheme);
    const observer = new MutationObserver(() => sendTheme());
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "data-vibedesk-theme", "style"],
    });
    return () => {
      observer.disconnect();
      window.removeEventListener("newma:themechange", forwardTheme);
      window.removeEventListener("vibedesk:theme", forwardTheme);
    };
  }, [sendTheme]);

  return (
    <section
      className="vv-view-block vv-artifact-block"
      data-block-id={block.id}
      data-vibe-block="artifact"
      data-vibe-block-id={block.id}
      data-vibe-artifact-renderer={block.renderer}
      data-vibe-artifact-url-path={block.urlPath}
    >
      {block.title ? <h2>{block.title}</h2> : null}
      {url ? (
        <iframe
          ref={frameRef}
          src={url}
          title={block.title || `${block.renderer} artifact`}
          sandbox="allow-scripts allow-downloads"
          loading="lazy"
          onLoad={() => sendTheme()}
          style={{ width: "100%", height: block.height ?? 560, border: 0 }}
        />
      ) : (
        <p className="vv-empty">—</p>
      )}
      {serializableSpec ? (
        <script
          data-vibe-artifact-spec=""
          dangerouslySetInnerHTML={{
            __html: serializeEmbeddedJson(serializableSpec),
          }}
          type="application/json"
        />
      ) : null}
    </section>
  );
}
