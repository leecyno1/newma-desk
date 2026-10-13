import { Copy, Download } from "lucide-react";
import { useState, type ReactNode } from "react";

export function CopilotAnswerActions({ content, filename, children }: {
  content: string;
  filename: string;
  children?: ReactNode;
}) {
  const [copying, setCopying] = useState(false);
  const [manualCopy, setManualCopy] = useState(false);
  const [notice, setNotice] = useState("");

  async function copyAnswer() {
    setCopying(true);
    setNotice("");
    try {
      await navigator.clipboard.writeText(content);
      setManualCopy(false);
      setNotice("已复制全文");
    } catch {
      setManualCopy(true);
      setNotice("浏览器未允许自动复制。点击下方原文全选后手动复制，或下载文件。");
    } finally {
      setCopying(false);
    }
  }

  function downloadAnswer() {
    setNotice("");
    try {
      const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = `${filename.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 140) || "agent-answer"}.md`;
        document.body.append(link);
        link.click();
        link.remove();
        setNotice("已发起下载，仅含回答正文，不含附件");
      } finally {
        // Let the browser consume the object URL before releasing it.
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch {
      setNotice("下载未能发起，请重试或复制全文。");
    }
  }

  return (
    <>
      <div className="copilot-answer-actions">
        {children}
        {content.trim() ? <>
          <button type="button" className="copilot-message-toggle" disabled={copying} onClick={() => void copyAnswer()} title="复制完整 Markdown 原文，不受折叠影响">
            <Copy size={13} aria-hidden="true" />复制全文
          </button>
          <button type="button" className="copilot-message-toggle" onClick={downloadAnswer} title="下载完整回答正文，不含附件；不会写入财报底稿">
            <Download size={13} aria-hidden="true" />下载 Markdown
          </button>
        </> : null}
      </div>
      {notice ? <p className="copilot-answer-notice" role="status">{notice}</p> : null}
      {manualCopy ? <textarea
        className="copilot-answer-source"
        aria-label="手动复制完整回答"
        readOnly
        rows={6}
        value={content}
        onFocus={event => event.currentTarget.select()}
      /> : null}
    </>
  );
}
