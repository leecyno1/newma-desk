import type { GraphArtifactInput } from "@/lib/artifacts";
import { getVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export interface IndustryEvidence {
  id: string;
  target: string;
  title: string;
  url: string;
  locator: string;
  excerpt: string;
  publishedAt: string;
  nextReview: string;
  judgment: "supports" | "refutes" | "unclear";
  note: string;
  recordedAt: string;
  reviewRequired?: { targetLabel: string; reason: string };
}
export interface IndustryVersion {
  number: number;
  basedOn: number | null;
  savedAt: string;
  provenance: string;
  spec: GraphArtifactInput;
  evidence: IndustryEvidence[];
}
export interface IndustryBook {
  schemaVersion: "newma-desk.industry-map.v1";
  sectorKey: string;
  versions: IndustryVersion[];
}
export interface IndustryDocument { revision: number; value: IndustryBook }
export interface IndustrySourceCheck {
  evidenceId: string;
  status: string;
  sourceUrl: string;
  finalUrl?: string;
  checkedAt?: string;
  publishedAt?: string | null;
  quoteMatch: string;
  claimVerified: false;
  documentType?: string;
  readPages?: number[];
  nextPage?: number | null;
  pageCount?: number;
  partialDocument?: boolean;
  truncated?: boolean;
  paragraphs: Array<{ locator: string; text: string }>;
}
export const evidenceJudgments = { supports: "支持", refutes: "反证", unclear: "证据不足" } as const;

export function industryTargets(spec: GraphArtifactInput) {
  const labels = new Map(spec.nodes.map((node) => [node.id, node.label]));
  return [
    ...spec.nodes.map((node) => ({ key: "node:" + node.id, label: "环节 · " + node.label })),
    ...spec.edges.map((edge) => ({
      key: JSON.stringify(["edge", edge.source, edge.target, edge.label || "", edge.kind || "flow"]),
      label: (labels.get(edge.source) || edge.source) + " → " + (labels.get(edge.target) || edge.target) + " · " + (edge.label || "未说明关系"),
    })),
  ];
}
export function evidenceLink(value: string): string | null {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
function validDate(value: string) {
  return !value || (/^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value);
}
export function evidenceError(item: IndustryEvidence, spec: GraphArtifactInput): string | null {
  if (item.reviewRequired && (typeof item.reviewRequired.targetLabel !== "string" || !item.reviewRequired.targetLabel || typeof item.reviewRequired.reason !== "string" || !item.reviewRequired.reason)) return "待复核记录缺少原对象说明。";
  if (!item.reviewRequired && !industryTargets(spec).some((target) => target.key === item.target)) return "请指定图谱中的节点或关系。";
  if (![item.id, item.title, item.locator, item.excerpt, item.note, item.url, item.publishedAt, item.nextReview, item.recordedAt].every((field) => typeof field === "string")) return "证据记录格式不完整。";
  if (!item.title.trim() || !item.locator.trim() || !item.excerpt.trim()) return "请填写来源名称、页码／段落和原文摘录。";
  if (item.title.length > 160 || item.locator.length > 240 || item.excerpt.length > 4000 || item.note.length > 2000 || item.url.length > 2000) return "证据内容过长，请缩短摘录或说明。";
  if (item.url && !evidenceLink(item.url)) return "来源链接只接受不含账号密码的 HTTP(S) 地址。";
  if (!validDate(item.publishedAt) || !validDate(item.nextReview)) return "请使用有效日期。";
  if (!Object.keys(evidenceJudgments).includes(item.judgment)) return "请选择人工判断类型。";
  return null;
}
export function evidenceTiming(item: IndustryEvidence, today = new Date().toISOString().slice(0, 10)) {
  if (item.reviewRequired) return "待人工复核（见记录说明）";
  if (item.publishedAt > today) return "资料日期晚于当前日期";
  if (item.nextReview && item.nextReview <= today) return "到期复核";
  if (!item.publishedAt) return "资料日期未知";
  return "待人工核验";
}
export function evidenceCoverage(spec: GraphArtifactInput, evidence: IndustryEvidence[]) {
  const targets = industryTargets(spec);
  const current = evidence.filter((item) => !item.reviewRequired);
  const covered = targets.filter((target) => current.some((item) => item.target === target.key)).length;
  const conflicting = targets.filter((target) => {
    const items = current.filter((item) => item.target === target.key);
    return items.some((item) => item.judgment === "supports") && items.some((item) => item.judgment === "refutes");
  }).length;
  return { targets: targets.length, recordedTargets: covered, missingTargets: targets.length - covered, conflictingTargets: conflicting, due: current.filter((item) => evidenceTiming(item) === "到期复核").length, needsReview: evidence.length - current.length };
}

/** Retain the original record when its node or directed relationship changes. */
export function reviseIndustryStructure(version: IndustryVersion, spec: GraphArtifactInput): IndustryVersion {
  const changedNodes = new Set(version.spec.nodes.filter((before) => {
    const after = spec.nodes.find((node) => node.id === before.id);
    return !after || before.label !== after.label || before.subtitle !== after.subtitle || before.group !== after.group || before.kind !== after.kind;
  }).map((node) => node.id));
  const oldTargets = industryTargets(version.spec);
  const newTargets = new Set(industryTargets(spec).map((target) => target.key));
  const affected = new Set<string>();
  for (const id of changedNodes) affected.add("node:" + id);
  version.spec.edges.forEach((edge, index) => {
    const key = oldTargets[version.spec.nodes.length + index].key;
    if (!newTargets.has(key) || changedNodes.has(edge.source) || changedNodes.has(edge.target)) affected.add(key);
  });
  return { ...version, spec, evidence: version.evidence.map((item) => item.reviewRequired || !affected.has(item.target) ? item : {
    ...item, reviewRequired: { targetLabel: oldTargets.find((target) => target.key === item.target)?.label || item.target, reason: "节点含义或关联关系已修改／移除；原记录保留，不计当前覆盖。" },
  }) };
}

export function industryStructureError(spec: GraphArtifactInput): string | null {
  if (!spec.title.trim() || spec.title.length > 160) return "请填写图谱标题（最多 160 字）。";
  if (spec.nodes.length < 2 || spec.nodes.length > 80) return "至少建立 2 个节点后才能预览和保存，最多 80 个。";
  if (spec.nodes.some((node) => !node.label.trim() || node.label.length > 120 || (node.subtitle?.length ?? 0) > 600 || (node.group?.length ?? 0) > 80)) return "请补齐节点名称，检查名称、说明和分组长度。";
  const ids = new Set(spec.nodes.map((node) => node.id));
  if (ids.size !== spec.nodes.length || spec.nodes.some((node) => !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(node.id))) return "节点标识重复或无效。";
  if (spec.edges.length > 160 || spec.edges.some((edge) => !ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target || (edge.label?.length ?? 0) > 120)) return "关系需连接两个不同的现有节点，最多 160 条。";
  const keys = industryTargets(spec).slice(spec.nodes.length).map((target) => target.key);
  if (new Set(keys).size !== keys.length) return "存在重复关系，请修改或移除重复项。";
  return null;
}
export function emptyIndustryBook(sectorKey: string): IndustryBook {
  return { schemaVersion: "newma-desk.industry-map.v1", sectorKey, versions: [] };
}

export function validateIndustryBook(value: IndustryBook, sectorKey: string): void {
  if (!value || value.schemaVersion !== "newma-desk.industry-map.v1" || value.sectorKey !== sectorKey || !Array.isArray(value.versions) || value.versions.length > 20) throw new Error("工作区图谱格式或主题不匹配，未采用。");
  for (const [index, version] of value.versions.entries()) {
    const spec = version?.spec;
    if (version.number !== index + 1 || (version.basedOn !== null && (!Number.isInteger(version.basedOn) || version.basedOn < 1 || version.basedOn >= version.number))
      || typeof version.provenance !== "string" || typeof version.savedAt !== "string"
      || !spec || spec.moduleId !== "industry-map" || typeof spec.title !== "string"
      || !Array.isArray(spec.nodes) || spec.nodes.length < 2 || spec.nodes.length > 80 || !Array.isArray(spec.edges) || spec.edges.length > 160
      || (spec.sources !== undefined && (!Array.isArray(spec.sources) || !spec.sources.every((source) => typeof source === "string")))
      || (spec.sourceText !== undefined && typeof spec.sourceText !== "string")) throw new Error("工作区图谱版本不完整，未采用。");
    const ids = new Set(spec.nodes.map((node) => node?.id));
    if (ids.size !== spec.nodes.length || spec.nodes.some((node) => !node || typeof node.id !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(node.id) || typeof node.label !== "string"
      || (node.subtitle !== undefined && typeof node.subtitle !== "string") || (node.group !== undefined && typeof node.group !== "string"))
      || spec.edges.some((edge) => !edge || !ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target || (edge.label !== undefined && typeof edge.label !== "string"))) throw new Error("图谱节点或关系无效，未采用。");
    if (!Array.isArray(version.evidence) || version.evidence.length > 80 || new Set(version.evidence.map((item) => item?.id)).size !== version.evidence.length
      || version.evidence.some((item) => !item || evidenceError(item, spec))) throw new Error("图谱证据记录无效，未采用。");
  }
}

export function industryStorageAvailable(config = getVibeDeskConfig(), write = false) {
  return Boolean(config?.moduleId === "industry-map" && config.accessToken && config.instanceId && config.storageGateway
    && config.permissions?.includes("storage.read") && (!write || config.permissions.includes("storage.write")));
}
function storageConfig(write = false): VibeDeskConfig {
  const config = getVibeDeskConfig();
  if (!config || !industryStorageAvailable(config, write)) throw new Error("请在已授权的 Desk 工作区中打开；未启用私人本地降级存储。");
  return config;
}
function headers(config: VibeDeskConfig) {
  return { Authorization: "Bearer " + config.accessToken, "X-Newma-Desk-Instance-Id": config.instanceId!, "Content-Type": "application/json" };
}
function endpoint(config: VibeDeskConfig, sectorKey: string) {
  return config.storageGateway + "/industry-maps/" + encodeURIComponent(sectorKey);
}
export async function readIndustryBook(sectorKey: string, signal: AbortSignal): Promise<IndustryDocument> {
  const config = storageConfig();
  const response = await fetch(endpoint(config, sectorKey), { headers: headers(config), signal });
  if (response.status === 404) return { revision: 0, value: emptyIndustryBook(sectorKey) };
  if (!response.ok) throw new Error("工作区读取失败（HTTP " + response.status + "），未载入任何其他账户或本地备份。");
  const result = await response.json() as IndustryDocument;
  validateIndustryBook(result.value, sectorKey);
  if (!Number.isInteger(result.revision) || result.revision < 1) throw new Error("存储修订号无效。");
  return result;
}
export async function writeIndustryBook(document: IndustryDocument, value: IndustryBook, signal: AbortSignal): Promise<IndustryDocument> {
  const config = storageConfig(true);
  validateIndustryBook(value, document.value.sectorKey);
  if (new TextEncoder().encode(JSON.stringify(value)).length > 500 * 1024) throw new Error("版本记录超过容量，请先导出；没有自动删除历史版本。");
  const response = await fetch(endpoint(config, value.sectorKey), {
    method: "PUT", headers: headers(config), signal,
    body: JSON.stringify({ expectedRevision: document.revision, value }),
  });
  if (response.status === 409) throw new Error("保存冲突：其他窗口已更新。当前草稿仍在；请导出后重新读取，未覆盖对方版本。");
  if (!response.ok) throw new Error("保存未确认（HTTP " + response.status + "）。请保留草稿并重新读取核对，勿重复提交。");
  const result = await response.json() as IndustryDocument;
  validateIndustryBook(result.value, value.sectorKey);
  if (!Number.isInteger(result.revision) || result.revision <= document.revision) throw new Error("保存修订号异常，请重新读取核对。");
  return result;
}

export async function readIndustrySource(item: IndustryEvidence, signal: AbortSignal, pageStart = 1): Promise<IndustrySourceCheck> {
  const config = storageConfig();
  if (!config.permissions?.includes("analysis.read")) throw new Error("缺少来源读取权限，请刷新模组后重试。");
  if (!evidenceLink(item.url)) throw new Error("请先补充可读取的公开原文链接。");
  if (item.excerpt.length > 2000) throw new Error("逐字核对最多 2000 字，请先缩短摘录；不会截断后冒充完整核对。");
  const url = config.storageGateway!.replace(/\/storage\/?$/, "/sources/read");
  const response = await fetch(url, { method: "POST", headers: headers(config), signal,
    body: JSON.stringify({ url: item.url, quote: item.excerpt, pageStart, pageCount: 10 }) });
  if (!response.ok) throw new Error("原文读取失败（HTTP " + response.status + "），未作核验结论。");
  const result = await response.json() as IndustrySourceCheck;
  return { ...result, evidenceId: item.id, claimVerified: false };
}
