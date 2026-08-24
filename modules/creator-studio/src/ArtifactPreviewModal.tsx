import { useEffect, useState, type ReactNode } from "react";
import { X, FileText, FileJson, ImageIcon, Film, Music, FolderOpen, Download, AlertCircle } from "lucide-react";

interface PreviewData {
  path: string;
  exists: boolean;
  mime?: string;
  encoding?: string;
  content?: string;
  entries?: Array<{ name: string; is_dir: boolean; size: number }>;
  size?: number;
  truncated?: boolean;
  suffix?: string;
  hint?: string;
  error?: string;
}

interface Props {
  path: string;
  label?: string;
  onClose: () => void;
  fetchPreview: (path: string) => Promise<PreviewData>;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function typeIcon(mime?: string, suffix?: string) {
  if (mime?.startsWith("image/")) return <ImageIcon size={16} />;
  if (mime?.startsWith("video/")) return <Film size={16} />;
  if (mime?.startsWith("audio/")) return <Music size={16} />;
  if (suffix === ".json") return <FileJson size={16} />;
  if (mime === "inode/directory") return <FolderOpen size={16} />;
  return <FileText size={16} />;
}

type JsonRecord = Record<string, unknown>;

const JSON_LABELS: Record<string, string> = {
  basis: "筛选依据",
  note: "说明",
  recommended_count: "推荐数量",
  total: "总数",
  count: "数量",
  signal: "热点信号",
  why_recommended: "推荐理由",
  one_line_judgment: "核心判断",
  core_proposition: "核心命题",
  reader_payoff: "读者价值",
  counterargument: "反方观点",
  evidence_needed: "待补证据",
  logic_chain: "逻辑链",
};

function jsonLabel(key: string): string {
  return JSON_LABELS[key] || key.replaceAll("_", " ");
}

function objectArrayFromJson(value: unknown): JsonRecord[] {
  if (Array.isArray(value)) return value.filter((item): item is JsonRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item));
  if (!value || typeof value !== "object") return [];
  const record = value as JsonRecord;
  for (const key of ["topic_cards", "topics", "recommended_topics", "items", "events", "clusters", "records", "results"]) {
    const candidate = record[key];
    if (Array.isArray(candidate)) return candidate.filter((item): item is JsonRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item));
  }
  return [];
}

function JsonProductPreview({ content }: { content: string }) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return <pre className="artifact-preview-json">{content}</pre>;
  }
  const record = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as JsonRecord : undefined;
  const summary = record?.summary && typeof record.summary === "object" && !Array.isArray(record.summary)
    ? record.summary as JsonRecord
    : undefined;
  const items = objectArrayFromJson(parsed);

  return (
    <div className="product-json-preview">
      {summary ? (
        <dl className="product-json-summary">
          {Object.entries(summary).map(([key, value]) => (
            <div key={key}><dt>{jsonLabel(key)}</dt><dd>{Array.isArray(value) ? value.join("、") : String(value ?? "")}</dd></div>
          ))}
        </dl>
      ) : null}
      {items.length ? (
        <div className="product-json-grid">
          {items.map((item, index) => {
            const id = String(item.topic_id || item.id || item.rank || index + 1);
            const title = String(item.title || item.name || item.headline || item.label || `第 ${index + 1} 项`);
            const score = item.score ?? item.priority;
            const primary = item.one_line_judgment || item.why_recommended || item.summary || item.description || item.signal;
            const secondary = item.core_proposition || item.reader_payoff;
            const details = ["signal", "logic_chain", "counterargument", "evidence_needed", "reader_payoff"]
              .filter((key) => item[key] != null && item[key] !== primary && item[key] !== secondary);
            return (
              <article key={`${id}-${index}`}>
                <header>
                  <span>{id}</span>
                  {score != null ? <b>{String(score)} 分</b> : null}
                  {item.recommended ? <em>推荐</em> : null}
                </header>
                <h3>{title}</h3>
                {primary ? <p>{String(primary)}</p> : null}
                {secondary ? <small>{String(secondary)}</small> : null}
                {details.length ? (
                  <details>
                    <summary>查看论据与补充</summary>
                    {details.map((key) => (
                      <div key={key}><strong>{jsonLabel(key)}</strong><p>{Array.isArray(item[key]) ? (item[key] as unknown[]).join(" → ") : String(item[key])}</p></div>
                    ))}
                  </details>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : record ? (
        <dl className="product-json-summary report">
          {Object.entries(record)
            .filter(([key]) => !["schema_version", "run_id", "generated_at", "summary"].includes(key))
            .map(([key, value]) => (
              <div key={key}><dt>{jsonLabel(key)}</dt><dd>{typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "")}</dd></div>
            ))}
        </dl>
      ) : null}
      <details className="product-json-source">
        <summary>查看原始数据文件</summary>
        <pre className="artifact-preview-json">{JSON.stringify(parsed, null, 2)}</pre>
      </details>
    </div>
  );
}

function safeLinkHref(href: string): string {
  return /^(https?:\/\/|mailto:|\/|#)/i.test(href.trim()) ? href.trim() : "#";
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const pattern = /(\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      nodes.push(<a key={key} href={safeLinkHref(link[2])} target="_blank" rel="noreferrer">{link[1]}</a>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function isTableDivider(line: string): boolean {
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function MarkdownDocument({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  const startsBlock = (line: string, next = "") => (
    !line.trim()
    || /^(#{1,6})\s+/.test(line)
    || /^>\s?/.test(line)
    || /^([-*+]\s+|\d+\.\s+)/.test(line)
    || /^```/.test(line.trim())
    || /^\s*<[^>]+>/.test(line)
    || (line.includes("|") && isTableDivider(next))
  );

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim() || /^\s*<[^>]+>/.test(line)) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const children = renderInlineMarkdown(heading[2], `h-${index}`);
      if (level === 1) blocks.push(<h1 key={index}>{children}</h1>);
      else if (level === 2) blocks.push(<h2 key={index}>{children}</h2>);
      else if (level === 3) blocks.push(<h3 key={index}>{children}</h3>);
      else if (level === 4) blocks.push(<h4 key={index}>{children}</h4>);
      else if (level === 5) blocks.push(<h5 key={index}>{children}</h5>);
      else blocks.push(<h6 key={index}>{children}</h6>);
      index += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      const start = index;
      const language = line.trim().slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(<pre key={start}><code className={language ? `language-${language}` : undefined}>{code.join("\n")}</code></pre>);
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const start = index;
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <table key={start}>
          <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{renderInlineMarkdown(cell, `th-${start}-${cellIndex}`)}</th>)}</tr></thead>
          <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{renderInlineMarkdown(cell, `td-${start}-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }

    if (/^>\s?/.test(line)) {
      const start = index;
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={start}>{renderInlineMarkdown(quote.join(" "), `quote-${start}`)}</blockquote>);
      continue;
    }

    const unordered = /^[-*+]\s+/.test(line);
    const ordered = /^\d+\.\s+/.test(line);
    if (unordered || ordered) {
      const start = index;
      const items: string[] = [];
      const itemPattern = unordered ? /^[-*+]\s+(.+)$/ : /^\d+\.\s+(.+)$/;
      while (index < lines.length) {
        const item = lines[index].match(itemPattern);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      const children = items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineMarkdown(item, `li-${start}-${itemIndex}`)}</li>);
      blocks.push(ordered ? <ol key={start}>{children}</ol> : <ul key={start}>{children}</ul>);
      continue;
    }

    const start = index;
    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && !startsBlock(lines[index], lines[index + 1] || "")) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={start}>{renderInlineMarkdown(paragraph.join(" "), `p-${start}`)}</p>);
  }

  return <>{blocks}</>;
}

function MarkdownProductPreview({ content }: { content: string }) {
  return (
    <div className="product-markdown-wrap">
      <article className="product-markdown-preview">
        <MarkdownDocument content={content} />
      </article>
      <details className="product-markdown-source">
        <summary>查看原始 Markdown</summary>
        <pre className="artifact-preview-text">{content}</pre>
      </details>
    </div>
  );
}

export function ArtifactPreviewModal({ path, label, onClose, fetchPreview }: Props) {
  const [data, setData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [copyState, setCopyState] = useState("");

  useEffect(() => {
    setLoading(true);
    fetchPreview(path)
      .then(setData)
      .catch((err) => setData({ path, exists: false, error: err?.message || "加载失败" }))
      .finally(() => setLoading(false));
  }, [path, fetchPreview]);

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(path);
      setCopyState("✓ 已复制路径");
      setTimeout(() => setCopyState(""), 1500);
    } catch {
      setCopyState("复制失败");
    }
  };

  const filename = path.split("/").pop() || path;

  return (
    <div className="artifact-modal-backdrop" onClick={onClose}>
      <div className="artifact-modal" onClick={(e) => e.stopPropagation()}>
        <div className="artifact-modal-header">
          <div className="artifact-modal-title">
            {typeIcon(data?.mime, data?.suffix)}
            <div>
              <strong>{label || filename}</strong>
              <small className="artifact-modal-path" title={path}>{filename}</small>
            </div>
          </div>
          <div className="artifact-modal-actions">
            {data?.exists && (
              <>
                <span className="artifact-modal-meta">
                  {data.mime} · {formatSize(data.size || 0)}
                  {data.truncated && " · 已截断"}
                </span>
                <button className="text-button" onClick={copyPath}>{copyState || "复制路径"}</button>
              </>
            )}
            <button className="icon-button" onClick={onClose} title="关闭">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="artifact-modal-body">
          {loading && <div className="artifact-modal-loading">加载中…</div>}

          {!loading && data && !data.exists && (
            <div className="artifact-modal-error">
              <AlertCircle size={16} />
              <span>{data.error || "文件不存在"}</span>
            </div>
          )}

          {!loading && data?.exists && data.encoding === "directory" && (
            <div className="artifact-modal-dir">
              <div className="artifact-dir-count">共 {data.entries?.length ?? 0} 项</div>
              <ul className="artifact-dir-list">
                {data.entries?.map((e) => (
                  <li key={e.name} className={e.is_dir ? "dir" : "file"}>
                    <span>{e.is_dir ? "📁" : "📄"} {e.name}</span>
                    {!e.is_dir && <small>{formatSize(e.size)}</small>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!loading && data?.exists && data.encoding === "text" && (
            <>
              {data.suffix === ".md" || data.suffix === ".markdown" ? (
                <MarkdownProductPreview content={data.content || ""} />
              ) : data.suffix === ".txt" ? (
                <pre className="artifact-preview-text">{data.content}</pre>
              ) : data.suffix === ".json" ? (
                <JsonProductPreview content={data.content || ""} />
              ) : data.suffix === ".html" || data.suffix === ".htm" ? (
                <div className="artifact-preview-html-wrap">
                  <iframe
                    className="artifact-preview-iframe"
                    srcDoc={data.content}
                    sandbox="allow-same-origin"
                    title="HTML 预览"
                  />
                  <details>
                    <summary>查看 HTML 源文件</summary>
                    <pre className="artifact-preview-text">{data.content}</pre>
                  </details>
                </div>
              ) : (
                <pre className="artifact-preview-text">{data.content}</pre>
              )}
            </>
          )}

          {!loading && data?.exists && data.encoding === "base64" && (
            <>
              {data.mime?.startsWith("image/") && (
                <img
                  className="artifact-preview-image"
                  src={`data:${data.mime};base64,${data.content}`}
                  alt={filename}
                />
              )}
              {data.mime?.startsWith("video/") && (
                <video
                  className="artifact-preview-video"
                  src={`data:${data.mime};base64,${data.content}`}
                  controls
                />
              )}
              {data.mime?.startsWith("audio/") && (
                <audio
                  className="artifact-preview-audio"
                  src={`data:${data.mime};base64,${data.content}`}
                  controls
                />
              )}
            </>
          )}

          {!loading && data?.exists && data.encoding === "binary" && (
            <div className="artifact-modal-binary">
              <Download size={20} />
              <p>{data.hint || "文件为二进制，不支持内联预览。"}</p>
              <p><small>类型: {data.mime} · 大小: {formatSize(data.size || 0)}</small></p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
