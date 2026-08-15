export const STATUS_LABELS: Record<string, string> = {
  pending: "待开始",
  queued: "排队中",
  running: "执行中",
  waiting_user: "待审核",
  changes_requested: "待修改",
  blocked: "已阻塞",
  failed: "失败",
  succeeded: "已完成",
  skipped: "已跳过",
  stale: "已过期",
  superseded: "已被替代",
  active: "当前版本",
  ready: "已就绪",
  needs_material: "缺素材",
  manual: "人工素材",
  upstream: "上游素材",
  cancelled: "已取消",
};

export function statusLabel(status?: string) {
  return STATUS_LABELS[status || "pending"] || status || "未知";
}

export function statusTone(status?: string) {
  if (status === "succeeded") return "success";
  if (status === "running" || status === "queued") return "active";
  if (status === "waiting_user" || status === "changes_requested") return "review";
  if (status === "failed" || status === "blocked" || status === "stale") return "danger";
  if (status === "skipped" || status === "cancelled" || status === "superseded") return "muted";
  if (status === "active" || status === "ready") return "success";
  return "pending";
}

export function formatTime(value?: string) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
