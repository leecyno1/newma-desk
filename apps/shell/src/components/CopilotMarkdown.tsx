import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useId } from "react";

/** Render Agent text only; never enable raw HTML or fetch inline remote images. */
export function CopilotMarkdown({ content }: { content: string }) {
  const citationPrefix = `copilot-${useId()}-`;
  return (
    <div className="copilot-message-body copilot-markdown">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        remarkRehypeOptions={{clobberPrefix: citationPrefix, footnoteLabel: "注释", footnoteBackLabel: "返回引用"}}
        components={{
          a: ({ node: _node, href, children, ...props }) => href ? (
            <a {...props} href={href} target={href.startsWith("#") ? undefined : "_blank"} rel="noopener noreferrer">
              {children}
            </a>
          ) : <span>{children}</span>,
          img: ({ alt }) => <span className="copilot-image-placeholder">[图片：{alt || "请查看交付物"}]</span>,
          table: ({ children }) => (
            <>
              <div className="copilot-table-hint">宽表可横向滚动</div>
              <div className="copilot-table-scroll" role="region" aria-label="分析表格，可横向滚动" tabIndex={0}>
                <table>{children}</table>
              </div>
            </>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
