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


export function ArtifactBlock({ block, data }: ArtifactBlockProps) {
  const url = safeArtifactUrl(resolvePath(data, block.urlPath));
  const spec = block.specPath ? resolvePath(data, block.specPath) : undefined;
  const serializableSpec = spec !== undefined && spec !== null && typeof spec === "object"
    ? spec
    : undefined;

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
          src={url}
          title={block.title || `${block.renderer} artifact`}
          sandbox="allow-scripts allow-downloads"
          loading="lazy"
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
