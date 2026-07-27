import ReactMarkdown from "react-markdown";

import type { MarkdownBlock as MarkdownBlockContract } from "@newma-dock/contracts";

import { resolvePath } from "../resolvePath";

interface MarkdownBlockProps {
  block: MarkdownBlockContract;
  data: unknown;
}

export function MarkdownBlock({ block, data }: MarkdownBlockProps) {
  const content = resolvePath(data, block.contentPath);

  return (
    <section
      className="vv-view-block vv-markdown-block"
      data-block-id={block.id}
      data-vibe-block="markdown"
      data-vibe-block-id={block.id}
      data-vibe-content-path={block.contentPath}
    >
      {block.title ? <h2>{block.title}</h2> : null}
      {typeof content === "string" && content.length > 0 ? (
        <ReactMarkdown skipHtml>{content}</ReactMarkdown>
      ) : (
        <p className="vv-empty">—</p>
      )}
    </section>
  );
}
