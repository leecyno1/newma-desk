import { useEffect, useState } from "react";
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
              <small className="artifact-modal-path" title={path}>{path}</small>
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
              {data.suffix === ".md" || data.suffix === ".txt" ? (
                <pre className="artifact-preview-text">{data.content}</pre>
              ) : data.suffix === ".json" ? (
                <pre className="artifact-preview-json">{(() => {
                  try { return JSON.stringify(JSON.parse(data.content || ""), null, 2); }
                  catch { return data.content || ""; }
                })()}</pre>
              ) : data.suffix === ".html" || data.suffix === ".htm" ? (
                <div className="artifact-preview-html-wrap">
                  <details>
                    <summary>查看渲染 HTML（点击展开）</summary>
                    <iframe
                      className="artifact-preview-iframe"
                      srcDoc={data.content}
                      sandbox="allow-same-origin"
                      title="HTML 预览"
                    />
                  </details>
                  <pre className="artifact-preview-text">{data.content}</pre>
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
