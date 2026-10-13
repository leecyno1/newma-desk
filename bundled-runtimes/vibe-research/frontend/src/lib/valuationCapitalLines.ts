import type {CapitalField} from './valuationReview';

export interface CapitalLineItem {
  id: string;
  label: string;
  amountM: number | null;
  treatment: 'add' | 'deduct' | 'exclude';
  locator: string;
  reason: string;
}

export const LINE_TREATMENTS = {add:'纳入合计',deduct:'从已纳入金额扣除',exclude:'仅记录，不计入'};
export const supportsCapitalLines = (field: CapitalField) => ['totalDebtM','cashM','excludedCashM'].includes(field);

export function summarizeCapitalLines(items: CapitalLineItem[], field: CapitalField, cashBasis = 'adjusted') {
  const issues: string[] = [];
  if (!supportsCapitalLines(field)) issues.push('此项暂不支持明细归集');
  if (!items.length || items.length > 12) issues.push('请填写 1–12 项明细；零值也须有明确项目和依据');
  if (!items.some(row => row.treatment === 'add')) issues.push('至少有一项纳入合计；零债务须显式录入零及依据');
  for (const [index,row] of items.entries()) {
    if (!row.label.trim() || !row.locator.trim() || !row.reason.trim()) issues.push(`第 ${index+1} 项缺少名称、来源定位或处理理由`);
    if (row.amountM === null || !Number.isFinite(row.amountM) || row.amountM < 0) issues.push(`第 ${index+1} 项金额须为非负数，缺失不等于零`);
    if (!Object.prototype.hasOwnProperty.call(LINE_TREATMENTS,row.treatment)) issues.push(`第 ${index+1} 项处理方式无效`);
  }
  if (field === 'cashM' && cashBasis === 'gross' && items.some(row => row.treatment === 'deduct')) {
    issues.push('原始现金余额不能在本表扣除；请在“需剔除现金”中记录，以免重复扣减');
  }
  const included = items.reduce((sum,row)=>sum+(row.treatment==='add'?(row.amountM??0):0),0);
  const deducted = items.reduce((sum,row)=>sum+(row.treatment==='deduct'?(row.amountM??0):0),0);
  const total = Math.round((included-deducted)*1e8)/1e8;
  if (!Number.isFinite(total) || total < 0) issues.push('明细合计不得为负数或无效数值');
  return {total:issues.length?null:total,included,deducted,issues};
}

export function normalizeCapitalLines(value: unknown): CapitalLineItem[] {
  if (!Array.isArray(value) || value.length > 12) return [];
  // Never silently discard a bad row and confirm the remaining partial total.
  if (value.some(row=>!row || typeof row!=='object' || !['id','label','locator','reason'].every(key=>typeof row[key]==='string')
    || !Object.prototype.hasOwnProperty.call(LINE_TREATMENTS,row.treatment) || (row.amountM!==null && (typeof row.amountM!=='number' || !Number.isFinite(row.amountM)))
    || row.label.length>160 || row.locator.length>240 || row.reason.length>500 || row.id.length>80)) return [];
  return value.map(row=>({...row}));
}
