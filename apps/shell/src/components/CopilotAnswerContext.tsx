import type { CopilotAnswerContext as AnswerContext } from "../lib/copilotAnswerContext";

const sourceLabels = {structured: "结构化页面", "dom-html": "页面 HTML", visual: "页面截图", manifest: "仅 Mod 基础信息"};
const basisLabels: Record<string, string> = {annual: "年度", quarter: "单季", ytd: "年初至今累计", ttm: "滚动十二个月", unknown: "待确认"};

export function CopilotAnswerContext({ record }: { record?: AnswerContext }) {
  if (!record) return <p className="copilot-answer-context-missing">历史回答未记录分析对象</p>;
  const identity = record.source === "structured"
    ? [record.subject || record.viewTitle, record.fiscalPeriod || record.periodEnd].filter(Boolean).join(" · ")
    : `${sourceLabels[record.source]} · ${record.viewTitle || "对象未确认"}`;
  return <details className="copilot-answer-context">
    <summary>分析对象：{identity || "未提供"}</summary>
    <dl>
      <dt>取证时间</dt><dd><time dateTime={record.capturedAt}>{new Date(record.capturedAt).toLocaleString("zh-CN", {hour12: false})}</time></dd>
      <dt>取证方式</dt><dd>{sourceLabels[record.source]}</dd>
      {record.source === "structured" ? <>
        {record.periodEnd ? <><dt>报告期末</dt><dd>{record.periodEnd}</dd></> : null}
        {record.basis ? <><dt>财务口径</dt><dd>{basisLabels[record.basis] || record.basis}</dd></> : null}
        {record.workbookId ? <><dt>底稿编号</dt><dd>{record.workbookId}</dd></> : null}
      </> : null}
    </dl>
    <p>记录本次提交的页面身份，不代表底稿已保存或数据已核验；不是财务数据快照。</p>
  </details>;
}
