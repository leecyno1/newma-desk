import type { AnnouncementText, Financials } from './api';
import { calculateVariance, EARNINGS_BASIS, type EarningsWorkbook, type EarningsSource, type FilingAmountInput } from './earningsWorkbench';

// The financials adapter returns THS display strings. Never infer money units from magnitude.
export function parseFinancialValue(raw:unknown,unit:string):number|null {
  if(typeof raw!=='string'&&typeof raw!=='number')return null;
  const match=String(raw).trim().replace(/,/g,'').match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(万亿元|万亿|亿元|亿|万元|万|元|%|％)?$/);
  if(!match)return null;
  const n=Number(match[1]),suffix=match[2]||'';
  if(!Number.isFinite(n))return null;
  if(unit==='亿元'){
    const exponent:Record<string,number>={'万亿元':4,'万亿':4,'亿元':0,'亿':0,'万元':-4,'万':-4,'元':-8};
    const value=suffix in exponent?Number(`${match[1]}e${exponent[suffix]}`):NaN;
    return Number.isFinite(value)?value:null;
  }
  if(unit==='%')return ['', '%','％'].includes(suffix)?n:null;
  if(unit==='元')return ['', '元'].includes(suffix)?n:null;
  return null;
}

export function convertFilingAmount(input:FilingAmountInput):number {
  const value=input.value.trim();
  if(value.length>100||!/^[-+]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d+)$/.test(value))throw new Error('请填写有效金额；千分位须每组三位，单位请单独选择');
  if(input.currency!=='CNY'||!['元','万元','亿元'].includes(input.unit))throw new Error('只支持人民币元、万元、亿元之间的换算，不进行汇率换算');
  const result=parseFinancialValue(`${value}${input.unit}`,'亿元');
  if(result===null)throw new Error('金额超出可处理范围');
  return result;
}

const mapping:Record<string,keyof Financials>={revenue:'revenue','revenue-yoy':'revenue_yoy','net-profit':'net_profit','net-profit-yoy':'net_profit_yoy',eps:'eps','gross-margin':'gross_margin','net-margin':'net_margin',roe:'roe','op-cf-ps':'op_cf_ps'};

export interface FilingReadFailure {
  announcementId: string;
  title: string;
  kind: 'pdf' | 'transcription';
  position: number;
  message: string;
  pdfUrl?: string;
}

export function filingExcerptTarget(symbol:string,source:EarningsSource) {
  if(source.kind!=='filing'||!source.excerpt||!source.url)return null;
  try {
    const url=new URL(source.url);
    const match=url.pathname.match(/^\/notices\/detail\/(\d{6})\/(AN\d{10,30})\.html$/);
    if(url.origin!=='https://data.eastmoney.com'||!match||match[1]!==symbol)return null;
    const kind=source.excerpt.contentOrigin==='pdf-text'?'pdf' as const:'transcription' as const;
    const position=kind==='pdf'?source.excerpt.pdfPage:source.excerpt.segment;
    if(!position||!Number.isInteger(position)||position<1||position>1000)return null;
    return {announcementId:match[2],kind,position};
  }catch{return null}
}

const normalizedExcerpt=(text:string)=>text.replace(/\s+/g,' ').trim();

export function filingExcerptPassage(text:string,excerpt:string) {
  const body=normalizedExcerpt(text),quote=normalizedExcerpt(excerpt);
  const start=quote?body.indexOf(quote):-1;
  if(start<0)return null;
  const end=start+quote.length;
  return {
    prefix:(start>240?'…':'')+body.slice(Math.max(0,start-240),start),quote,
    suffix:body.slice(end,end+240)+(end+240<body.length?'…':''),
  };
}

export function reviewFilingExcerpts(workbook:EarningsWorkbook,document:AnnouncementText|null) {
  if(!document||document.symbol!==workbook.security.symbol)return [];
  const text=normalizedExcerpt(document.text);
  return workbook.sourceMaterials.flatMap(source=>{
    if(source.correction)return [];
    const target=filingExcerptTarget(workbook.security.symbol,source);
    if(!target||target.announcementId!==document.announcementId||source.excerpt!.contentOrigin!==document.contentOrigin||target.position!==(document.contentOrigin==='pdf-text'?document.pdfPage:document.segment))return [];
    const textMatch=!text?'unavailable':filingExcerptPassage(text,source.excerpt!.text)?'found':'not-found';
    const attachmentChanged=document.contentOrigin==='pdf-text'&&source.excerpt!.pdfUrl?.split('#')[0]!==document.pdfUrl?.split('#')[0];
    return [{sourceId:source.id,...target,textMatch,attachmentChanged,
      status:(attachmentChanged?'PDF 链接已变化，请核对文件版本；':'')+(textMatch==='found'?'当前读取内容中找到已存摘录；仅文字匹配，不代表数值已核验。':textMatch==='unavailable'?'当前页未提取到文字，无法核对已存摘录。':'当前已读取内容中未找到已存摘录；可能为截断、提取或版本差异，不能据此认定公告更正。')}];
  });
}

export function announcementRevisionHint(title:string):string|null {
  if(/撤回|取消/.test(title))return '撤回/取消线索（仅标题）';
  if(/更正|修正/.test(title))return '更正线索（仅标题）';
  if(/修订|补充|更新版|更新后/.test(title))return '修订/补充线索（仅标题）';
  return null;
}

export function filingCorrectionReadiness(workbook:EarningsWorkbook,sourceId:string,document:AnnouncementText|null):string|null {
  const check=reviewFilingExcerpts(workbook,document).find(item=>item.sourceId===sourceId);
  if(!check)return '请先回读所选摘录所在的 PDF 页或转录分段，再生成修订对照。';
  if(check.attachmentChanged)return 'PDF 链接已变化，请核对版本并重新关联当前摘录，不能直接沿用旧来源修订。';
  if(check.textMatch!=='found')return '当前读取内容未能匹配所选摘录，请重新核对并关联后再修订。';
  return null;
}

export function previewFilingCorrection(workbook:EarningsWorkbook,sourceId:string,after:number,reason:string,document:AnnouncementText|null,amountInput?:FilingAmountInput) {
  const source=workbook.sourceMaterials.find(item=>item.id===sourceId);
  const metric=workbook.metrics.find(item=>item.id===source?.excerpt?.metricId);
  if(!source?.excerpt||source.kind!=='filing'||source.correction||!metric)throw new Error('请选择已关联的公告摘录');
  if(amountInput&&(metric.unit!=='亿元'||workbook.security.currency!=='CNY'||convertFilingAmount(amountInput)!==after))throw new Error('输入金额、单位与修订结果不一致，请重新生成对照');
  if(!Number.isFinite(after)||!reason.trim()||reason.trim().length>2000)throw new Error('请填写有效修订值和修改理由');
  if(metric.reported!==source.excerpt.reportedValue)throw new Error('实际值已变化，请重新核对并关联摘录');
  const {periodEnd,basis}=workbook.fiscalPeriod;
  const existingValueMismatch=metric.reported!==null&&(metric.periodEnd!==periodEnd||metric.reportedBasis!==basis||metric.reportedCurrency!==workbook.security.currency);
  if(!periodEnd||!basis||source.periodEnd!==periodEnd||source.basis!==basis||existingValueMismatch||source.excerpt.unit!==metric.unit)throw new Error('实际值、摘录与底稿的期间、币种或单位口径未对齐，请先核对');
  if(after===metric.reported)throw new Error('修订值与当前值相同，无需采用');
  if(workbook.sourceMaterials.length>=100)throw new Error('来源已达 100 项，请新建底稿整理证据');
  const readingIssue=filingCorrectionReadiness(workbook,sourceId,document);
  if(readingIssue)throw new Error(readingIssue);
  return {base:JSON.stringify(workbook),operation:metric.reported===null?'fill' as const:'revision' as const,sourceId,metricId:metric.id,label:metric.label,unit:metric.unit,before:metric.reported,after,reason:reason.trim(),periodEnd,basis,sourceLabel:source.label,excerpt:source.excerpt.text,...(amountInput?{amountInput:{...amountInput}}:{})};
}

export type FilingCorrectionPreview=ReturnType<typeof previewFilingCorrection>;

export function applyFilingCorrection(workbook:EarningsWorkbook,candidate:FilingCorrectionPreview,document:AnnouncementText|null,adoptedAt=new Date().toISOString()):EarningsWorkbook {
  if(JSON.stringify(workbook)!==candidate.base)throw new Error('底稿已改变，请重新生成修订对照');
  const checked=previewFilingCorrection(workbook,candidate.sourceId,candidate.after,candidate.reason,document,candidate.amountInput);
  const source=workbook.sourceMaterials.find(item=>item.id===checked.sourceId)!;
  const metric=workbook.metrics.find(item=>item.id===checked.metricId)!;
  const adopted:EarningsSource={...source,id:`correction:${globalThis.crypto.randomUUID()}`,status:'available',
    excerpt:{...source.excerpt!,reportedValue:checked.after},
    correction:{before:checked.before,after:checked.after,reason:checked.reason,adoptedAt,evidenceSourceId:source.id,previousSourceIds:[...metric.sourceIds],...(checked.amountInput?{amountInput:checked.amountInput}:{})}};
  return {...workbook,updatedAt:adoptedAt,mode:'reported',
    metrics:workbook.metrics.map(item=>item.id===metric.id?calculateVariance({...item,reported:checked.after,reportedOrigin:'manual',periodEnd:checked.periodEnd,reportedBasis:checked.basis,reportedCurrency:workbook.security.currency,sourceIds:[adopted.id],asOf:source.asOf}):item),
    sourceMaterials:[adopted,...workbook.sourceMaterials],
    verification:{...workbook.verification,status:'partial',latestPeriodChecked:false}};
}

export function linkFilingExcerpt(workbook: EarningsWorkbook, document: AnnouncementText, metricId: string, text: string): EarningsSource {
  if(workbook.security.market!=='CN'||workbook.security.symbol!==document.symbol)throw new Error('公告证券与底稿不一致');
  if(!workbook.fiscalPeriod.periodEnd||!workbook.fiscalPeriod.basis)throw new Error('请先确认底稿期末与财务口径');
  const metric=workbook.metrics.find(item=>item.id===metricId);
  if(!metric)throw new Error('请选择关联指标');
  if(document.contentOrigin==='pdf-text'&&(!document.pdfUrl||!Number.isInteger(document.pdfPage)||!document.pdfPage||!document.pdfPageCount||document.pdfPage>document.pdfPageCount))throw new Error('PDF 页定位不完整，请重新读取');
  const excerpt=text.trim();
  if(!excerpt||excerpt.length>2000||!normalizedExcerpt(document.text).includes(normalizedExcerpt(excerpt)))throw new Error('摘录须来自当前已读取分段，最多 2000 字；研究判断不要写入原文摘录');
  return {
    id:`filing:${document.announcementId}:${globalThis.crypto.randomUUID()}`,
    label:document.title,kind:'filing',url:document.url,
    ...(document.date?{asOf:document.date}:{}),retrievedAt:document.retrievedAt,
    periodEnd:workbook.fiscalPeriod.periodEnd,basis:workbook.fiscalPeriod.basis,status:'available',
    excerpt:{text:excerpt,
      ...(document.contentOrigin==='pdf-text'?{pdfPage:document.pdfPage,pdfPageCount:document.pdfPageCount,pdfUrl:document.pdfUrl!}:{segment:document.segment}),
      metricId,reportedValue:metric.reported,unit:metric.unit,contentOrigin:document.contentOrigin,association:'user-linked'},
  };
}

export function previewFinancialEvidence(workbook:EarningsWorkbook,financials:Financials|null,checkedAt=new Date().toISOString()){
  if(workbook.security.market.toUpperCase()!=='CN'||workbook.security.currency.toUpperCase()!=='CNY')throw new Error('当前财务摘要只支持 A 股人民币口径；其他市场请保留人工底稿，不能套用 A 股或研究快照数字。');
  const basis=workbook.fiscalPeriod.basis;
  if(!basis)throw new Error('请先选择财务口径；旧数据不会随选择自动确认口径。');
  if(basis==='ttm')throw new Error('TTM 暂不支持自动回填，请使用有明确口径的人工底稿；不以累计或单季替代。');
  if(financials?.basis!==basis)throw new Error('接口财务口径缺失或与底稿不一致，未更改底稿。');
  // THS 年度接口实际返回数字年份（如 2025），报告期/单季接口返回日期。
  // 只有明确的完整年度允许补为年末，不能给季度或累计数据猜测期末。
  const rawPeriod=String(financials?.period??'').trim();
  const period=basis==='annual'&&/^\d{4}$/.test(rawPeriod)?`${rawPeriod}-12-31`:rawPeriod;
  const periodTime=Date.parse(`${period}T00:00:00Z`);
  if(!period||!/^\d{4}-\d{2}-\d{2}$/.test(period)||!Number.isFinite(periodTime)||new Date(periodTime).toISOString().slice(0,10)!==period||period>checkedAt.slice(0,10))throw new Error('财务摘要缺少有效报告期或报告期晚于采集日，未更改底稿。');
  if(workbook.fiscalPeriod.periodEnd&&workbook.fiscalPeriod.periodEnd!==period)throw new Error(`接口报告期 ${period} 与底稿 ${workbook.fiscalPeriod.periodEnd} 不同，未跨期覆盖。请新建该期底稿。`);
  if(!workbook.fiscalPeriod.periodEnd&&(workbook.fiscalPeriod.label.trim()||workbook.metrics.some(m=>m.reported!==null||m.consensus!==null||m.internalEstimate!==null)))throw new Error(`接口报告期为 ${period}，请先填写并核对底稿期末日期，再刷新证据。`);
  const source:EarningsSource={id:`financials:${workbook.security.symbol}:${period}:${basis}:${checkedAt}`,label:`同花顺财务摘要 · ${workbook.security.symbol} · ${period} · ${EARNINGS_BASIS[basis]}`,kind:'company',periodEnd:period,basis,retrievedAt:checkedAt,status:'available'};
  const gaps:string[]=['财务摘要未提供原始公告披露日及最新公告核验，不能声称已核验最新财报。'];
  let updated=0;
  const rows=workbook.metrics.map(metric=>{
    const key=mapping[metric.id];
    const value=key?parseFinancialValue(financials?.[key],metric.unit):null;
    if(value===null){
      gaps.push(`${metric.label}：接口缺值或单位不明；${metric.reported===null?'保持缺失':'保留原值及原始来源，不视为本次已更新'}。`);
      return {id:metric.id,label:metric.label,before:metric.reported,after:metric.reported,unit:metric.unit,updated:false};
    }
    updated++;
    return {id:metric.id,label:metric.label,before:metric.reported,after:value,unit:metric.unit,updated:true};
  });
  if(!updated)throw new Error('没有可确认单位的财务数字，未更改底稿。');
  const next:EarningsWorkbook={...workbook,mode:'reported',fiscalPeriod:{...workbook.fiscalPeriod,label:workbook.fiscalPeriod.label||period,periodEnd:period},
    verification:{status:'partial',latestPeriodChecked:false,checkedAt,primarySourceIds:[source.id]},
    metrics:workbook.metrics.map((m,i)=>rows[i].updated?calculateVariance({...m,reported:rows[i].after,asOf:undefined,periodEnd:period,reportedBasis:basis,reportedCurrency:'CNY',reportedOrigin:'provider',sourceIds:[source.id]}):m),
    sourceMaterials:[source,...workbook.sourceMaterials],gaps:[...new Set([...workbook.gaps,...gaps])],updatedAt:checkedAt};
  return {next,rows,period,basis,checkedAt,gaps};
}
