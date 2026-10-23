export const SESSION_LANES = [
  { id: "attention", title: "待你处理", hint: "等待审批或补充信息" },
  { id: "running", title: "运行中", hint: "Agent 正在处理" },
  { id: "queued", title: "等待响应", hint: "已有待处理用户消息" },
  { id: "idle", title: "空闲", hint: "可返回原会话继续" },
  { id: "unknown", title: "状态未知", hint: "来源未提供明确状态" },
] as const;
export type SessionStatus = typeof SESSION_LANES[number]["id"];
export interface SessionCard {
  id: string;
  title: string;
  projectId: string;
  projectName: string;
  model: string;
  status: SessionStatus;
  attention: string;
  pinned: boolean;
  readOnly: boolean;
  updatedAt: string | null;
  url: string;
}
export interface SessionSnapshot {
  source: "newma-hermes";
  scope: string;
  fetchedAt: string;
  sessions: SessionCard[];
  truncated: boolean;
}
export function selectSessions(rows: SessionCard[], search: string, project: string, pinnedOnly: boolean) {
  const query = search.trim().toLocaleLowerCase();
  return rows.filter((row) => (!project || row.projectId === project) && (!pinnedOnly || row.pinned)
    && (!query || `${row.title} ${row.projectName} ${row.model}`.toLocaleLowerCase().includes(query)))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned)
      || (Date.parse(b.updatedAt || "") || 0) - (Date.parse(a.updatedAt || "") || 0)
      || a.id.localeCompare(b.id));
}
