import { earningsResearchWorkbookSchema } from '@newma-desk/contracts/earnings';
import { valuationModelSchema } from '@newma-desk/contracts/valuation';
import { blankEarningsWorkbook, type EarningsWorkbook } from './earningsWorkbench';
import { blankValuationModel, calculateValuationModel, type ValuationModel } from './valuationWorkbench';
import { CAPITAL_FIELDS, stageCapitalEvidence, type CapitalField, type CapitalEvidenceInput } from './valuationReview';
import { getVibeDeskConfig, isVibeDeskEmbedded } from './vibedesk';

export type ResearchBackupKind = 'earnings' | 'valuation';
export interface ResearchBackupRow {
  id: string;
  title: string;
  identity: string;
  asOf: string;
  updatedAt: string;
  record: EarningsWorkbook | ValuationModel;
  capitalEditor?: { field: CapitalField; input: CapitalEvidenceInput };
}
export interface ResearchBackup {
  kind: ResearchBackupKind;
  rows: ResearchBackupRow[];
  warnings: string[];
  raw: string;
}
export const BACKUP_MAX_BYTES = 10 * 1024 * 1024;
const text = earningsResearchWorkbookSchema.shape.headline;
// Drafts can have blank labels: importing is not permission to save or verify them.
const earningsShape = earningsResearchWorkbookSchema.shape;
const earningsDraftSchema = earningsResearchWorkbookSchema.extend({
  security: earningsShape.security.extend({market:text,symbol:text,name:text,currency:text}),
  fiscalPeriod: earningsShape.fiscalPeriod.extend({label:text}),
  operatingMetrics: earningsShape.operatingMetrics.element.extend({label:text,unit:text}).array().max(50),
  guidance: earningsShape.guidance.element.extend({label:text,period:text,unit:text}).array().max(30),
  scenarios: earningsShape.scenarios.element.extend({condition:text,operatingPath:text,researchResponse:text}).array().length(3),
  estimateRevisions: earningsShape.estimateRevisions.element.extend({label:text,period:text,unit:text,reason:text}).array().max(30),
  thesisImpacts: earningsShape.thesisImpacts.element.extend({summary:text}).array().max(30),
  gaps: text.array().max(30),
});
const valuationShape = valuationModelSchema.innerType().shape;
const valuationDraftSchema = valuationModelSchema.innerType().extend({
  name:text,
  security:valuationShape.security.extend({market:text,symbol:text,name:text,currency:text}),
  scenarios:valuationShape.scenarios.element.innerType().array().length(3),
  gaps:text.array().max(30),
});
function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
function checkLinks(value: unknown) {
  if(Array.isArray(value)){value.forEach(checkLinks);return;}
  if(!record(value))return;
  for(const [key,item] of Object.entries(value)) {
    if((key==='url'||key==='pdfUrl')&&typeof item==='string'&&item&&!/^https?:\/\//i.test(item))throw new Error('备份的来源链接必须使用 HTTP 或 HTTPS，未打开链接或改动底稿。');
    if(typeof item==='object')checkLinks(item);
  }
}
function parseRow(value: unknown, kind: ResearchBackupKind): ResearchBackupRow {
  const parsed = kind === 'earnings' ? earningsDraftSchema.safeParse(value) : valuationDraftSchema.safeParse(value);
  if (!parsed.success) {
    const field = parsed.error.issues[0]?.path.join('.') || '文档';
    throw new Error(`备份结构不符合${kind==='earnings'?'财报':'估值'}格式（${field}），未修改当前草稿。原文件仍保留。`);
  }
  const row = parsed.data as EarningsWorkbook | ValuationModel;
  checkLinks(row);
  if (kind === 'valuation' && new Set((row as ValuationModel).scenarios.map(item=>item.id)).size!==3) throw new Error('估值备份必须各有一份悲观、基准和乐观情景。');
  if (kind === 'earnings') {
    const workbook = row as EarningsWorkbook;
    const expected = blankEarningsWorkbook().metrics.map(item=>item.id);
    if(workbook.metrics.length!==expected.length || !expected.every(id=>workbook.metrics.filter(item=>item.id===id).length===1)) throw new Error('财报核心指标缺失或重复，未截断或替换原数据。');
  }
  return { id:row.id, title:kind==='earnings'?row.security.name || '未命名公司':(row as ValuationModel).name || '未命名模型',
    identity:`${row.security.market}:${row.security.symbol} · ${row.security.currency}`,
    asOf:kind==='earnings'?(row as EarningsWorkbook).fiscalPeriod.label || '报告期待确认':(row as ValuationModel).asOf,
    updatedAt:row.updatedAt, record:row };
}

export function parseResearchBackup(raw: string, kind: ResearchBackupKind): ResearchBackup {
  if (new Blob([raw]).size > BACKUP_MAX_BYTES) throw new Error('备份超过 10MB，请分拆后读取；未修改当前草稿。');
  let data: unknown;
  try { data=JSON.parse(raw); } catch { throw new Error('不是有效的 JSON 备份，原文件及当前草稿均未改动。'); }
  if (!record(data)) throw new Error('未识别的备份格式。');
  const schema = kind==='earnings'?'newma-desk.earnings-research.v1':'newma-desk.valuation-workbench.v1';
  const one = kind==='earnings'?'workbook':'model', many=kind==='earnings'?'workbooks':'models';
  const values = Object.prototype.hasOwnProperty.call(data,one) ? [data[one]]
    : data.schemaVersion===schema && Array.isArray(data[many]) ? data[many] as unknown[] : null;
  if(!values || values.length>100) throw new Error('请选择本页导出的草稿或旧档案备份，最多 100 份。');
  const rows=values.map(value=>parseRow(value,kind));
  if(new Set(rows.map(row=>row.id)).size!==rows.length)throw new Error('备份包含重复档案编号，请先核对；没有合并或覆盖。');
  const warnings=['备份归属与时效未核验；恢复为新草稿，不覆盖同名或同编号档案。原文文件不包含在 JSON 中，旧链接须在当前工作区重新核对。'];
  if(kind==='earnings' && (data.pendingEvidence || data.correction || data.pendingUpload)) {
    warnings.push('备份还含未采用的刷新、修订或上传候选：不自动写入实际值，可在下方查看或下载原始内容，回原文重新核对后再采用。');
  }
  if(kind==='valuation' && data.unsavedCapitalEditor!=null) {
    const editor=data.unsavedCapitalEditor;
    if(!record(editor) || !CAPITAL_FIELDS.includes(editor.field as CapitalField))throw new Error('未暂存资本编辑的字段不受支持；原始备份未改动。');
    const field=editor.field as CapitalField;
    const schema=valuationShape.capitalEvidenceDrafts.unwrap().shape[field]!.unwrap().shape.input;
    const parsed=schema.safeParse(editor.input);
    if(!parsed.success)throw new Error('未暂存资本编辑格式异常，未舍弃这部分内容；请核对原始备份。');
    checkLinks(parsed.data);
    if(rows.length!==1)throw new Error('未暂存资本编辑必须对应单个模型。');
    rows[0].capitalEditor={field,input:parsed.data};
    warnings.push('未暂存资本编辑将恢复为待核验编辑，不改变已录入金额；情景确认需重新完成。');
  }
  return {kind,rows,warnings,raw};
}

/** Called only from an explicit user click; never enumerate another workspace's caches. */
export function readLegacyResearchBackup(kind: ResearchBackupKind, scoped: boolean): ResearchBackup {
  const config=getVibeDeskConfig();
  let key=`newma-desk.${kind==='earnings'?'earnings-workbench':'valuation-workbench'}.v1`;
  if(scoped) {
    if(kind!=='valuation'||!config?.userId||!config.workspaceId||config.moduleId!=='valuation-workbench'||!config.accessToken||!config.permissions?.includes('storage.read'))throw new Error('请先连接当前估值工作区，再读取对应旧缓存。');
    key+=`:${encodeURIComponent(config.userId)}:${encodeURIComponent(config.workspaceId)}`;
  } else if(isVibeDeskEmbedded&&!config)throw new Error('Desk 身份尚未确认，请稍后重试。');
  let raw: string | null;
  try { raw=localStorage.getItem(key); } catch { throw new Error('浏览器不允许读取旧备份；可以选择已导出的 JSON 文件。'); }
  if(raw===null)throw new Error('此浏览器、此站点没有这类旧备份。其他设备或旧网址的备份不会自动发现，请从原处导出 JSON。');
  return parseResearchBackup(raw,kind);
}

export function recoverEarningsBackup(row: ResearchBackupRow): EarningsWorkbook {
  const original=structuredClone(row.record as EarningsWorkbook), fresh=blankEarningsWorkbook();
  return {...original,id:fresh.id,createdAt:fresh.createdAt,updatedAt:fresh.updatedAt,
    verification:{...original.verification,status:'unverified',latestPeriodChecked:false},
    sourceMaterials:original.sourceMaterials.map(source=>({...source,status:'stale'})),
  };
}
export function recoverValuationBackup(row: ResearchBackupRow): ValuationModel {
  const original=structuredClone(row.record as ValuationModel),fresh=blankValuationModel();
  let model:ValuationModel={...original,id:fresh.id,createdAt:fresh.createdAt,updatedAt:fresh.updatedAt,
    scenarios:original.scenarios.map(({review: _review,...scenario})=>scenario),
    sourceMaterials:original.sourceMaterials.map(source=>({...source,status:'stale'})),
  };
  if(row.capitalEditor)model=stageCapitalEvidence(model,row.capitalEditor.field,row.capitalEditor.input);
  return calculateValuationModel(model);
}
