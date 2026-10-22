import {describe,it,expect,vi} from 'vitest';
vi.mock('@/lib/vibedesk',()=>({waitForVibeDeskConfig:async()=>null,getVibeDeskConfig:()=>null,isVibeDeskEmbedded:false}));
import {convertFilingAmount,applyFilingCorrection,previewFilingCorrection,announcementRevisionHint,filingExcerptPassage,filingExcerptTarget,reviewFilingExcerpts,linkFilingExcerpt,parseFinancialValue,previewFinancialEvidence} from '../../bundled-runtimes/vibe-research/frontend/src/lib/earningsEvidence';
import {blankEarningsWorkbook,calculateVariance,earningsComparisonIssue,earningsDataStatus,hydrateEarningsWorkspace,persistEarningsWorkspace as persistStorage,type EarningsWorkspace} from '../../bundled-runtimes/vibe-research/frontend/src/lib/earningsWorkbench';
import type {AnnouncementText,EarningsPdfImport,Financials} from '../../bundled-runtimes/vibe-research/frontend/src/lib/api';
import {earningsResearchWorkbookSchema} from '../../packages/contracts/src/earnings';
import {appendPdfCapital,appendPdfCapitalNotes,appendPdfDiscussion,missingPdfDiscussion,workbookFromPdf,appendPdfRevenue,missingPdfRevenue} from '../../bundled-runtimes/vibe-research/frontend/src/lib/earningsPdfImport';

const facts=(overrides:Partial<Financials>={}):Financials=>({basis:'ytd',period:'2026-06-30',revenue:'123亿元',revenue_yoy:'5%',net_profit:null,net_profit_yoy:null,eps:'2元',bvps:null,roe:null,gross_margin:null,net_margin:null,op_cf_ps:null,...overrides});
const persistEarningsWorkspace=async(workspace:EarningsWorkspace)=>persistStorage(workspace,await hydrateEarningsWorkspace());
const draft=()=>{const d=blankEarningsWorkbook();d.security.symbol='600519';d.security.name='合成测试';d.fiscalPeriod.basis='ytd';return d};
const filingReading=(text:string):AnnouncementText=>({announcementId:'AN202608141827994407',symbol:'600519',title:'合成公告',date:'2026-08-15',url:'https://data.eastmoney.com/notices/detail/600519/AN202608141827994407.html',pdfUrl:null,text,segment:1,segmentCount:1,truncated:false,contentOrigin:'provider-transcription',retrievedAt:'2026-09-19T00:00:00Z'});
describe('financial evidence adoption',()=>{
  it('persists only selected discussion with physical pages without treating passages as metrics',async()=>{
    vi.stubGlobal('window',{location:{origin:'http://127.0.0.1:8911'}});
    const memory=new Map<string,string>();
    vi.stubGlobal('localStorage',{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v)});
    try{
      const document:EarningsPdfImport={reportId:'sample',name:'合成测试.pdf',security:{market:'CN',symbol:'600519',name:'示例',currency:'CNY'},periodEnd:'2024-12-31',basis:'annual',retrievedAt:'2026-09-19T00:00:00+00:00',pageCount:100,readPages:[1,2,3],warnings:[],
        candidates:[{id:'revenue',label:'营业收入',value:12,unit:'亿元',rawValue:'12',rawUnit:'亿元',page:2,excerpt:'营业收入 12',columnHeader:'2024年 2023年'}],
        discussion:[{id:'discussion:3',page:3,topics:['现金流'],text:'现金流量变动原因说明：回款增加。',truncated:true},
          {id:'excluded',page:2,topics:['风险披露'],text:'不选中原文',truncated:false}]};
      const workbook=workbookFromPdf(document,['revenue'],['discussion:3']);
      const textOnly=workbookFromPdf({...document,candidates:[]},[],['discussion:3']);
      expect(textOnly.metrics.every(metric=>metric.reported===null)).toBe(true);
      expect(textOnly.sourceMaterials).toHaveLength(1);
      expect(textOnly.sourceMaterials[0].discussion?.reportId).toBe(document.reportId);
      expect(earningsResearchWorkbookSchema.safeParse(textOnly).success).toBe(true);
      expect(()=>workbookFromPdf({...document,candidates:[]},[],['missing-id'])).toThrow('经营原文');
      expect(earningsResearchWorkbookSchema.safeParse(workbook).success).toBe(true);
      expect(workbook.sourceMaterials).toHaveLength(2);
      expect(workbook.sourceMaterials[1].excerpt).toBeUndefined();
      expect(workbook.operatingMetrics).toEqual([]);
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:workbook.updatedAt,workbooks:[workbook]});
      const saved=(await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials[1];
      expect(saved.discussion).toMatchObject({pdfPage:3,pdfPageCount:100,readPages:[1,2,3],truncated:true,text:'现金流量变动原因说明：回款增加。'});
      expect(saved.url).toContain('#page=3');
      expect(workbookFromPdf(document,['revenue']).sourceMaterials).toHaveLength(1);
      const old=workbookFromPdf(document,['revenue']);
      old.headline='已有研究判断';old.metrics[0].reported=13;old.metrics[0].internalEstimate=14;
      const original=structuredClone(old);
      const enriched=appendPdfDiscussion(old,document,['discussion:3']);
      expect(old).toEqual(original);
      expect(enriched.id).toBe(old.id);
      expect(enriched.metrics).toEqual(old.metrics);
      expect(enriched.headline).toBe('已有研究判断');
      expect(enriched.verification).toEqual(old.verification);
      expect(enriched.sourceMaterials[0]).toEqual(old.sourceMaterials[0]);
      expect(missingPdfDiscussion(enriched,document).map(row=>row.id)).toEqual(['excluded']);
      expect(()=>appendPdfDiscussion(enriched,document,['discussion:3'])).toThrow('不会重复');
      expect(()=>appendPdfDiscussion(old,{...document,reportId:'unlinked'},['discussion:3'])).toThrow('未关联');
      expect(()=>appendPdfDiscussion(old,{...document,periodEnd:'2023-12-31'},['discussion:3'])).toThrow('不一致');
      expect(()=>appendPdfDiscussion(old,{...document,security:{...document.security,symbol:'000001'}},['discussion:3'])).toThrow('不一致');
      const capital={...document,capitalCandidates:[{...document.candidates[0],id:'capital-share-capital',label:'股本',unit:'百万元'}]};
      const extended=appendPdfCapital(old,capital,['capital-share-capital']);
      expect(extended.metrics).toEqual(old.metrics);expect(extended.headline).toBe(old.headline);
      expect(extended.operatingMetrics[0]).toMatchObject({id:'capital-share-capital',reported:12,unit:'百万元'});
      expect(earningsResearchWorkbookSchema.safeParse(extended).success).toBe(true);
      expect(()=>appendPdfCapital(extended,capital,['capital-share-capital'])).toThrow('不会重复');
      expect(()=>appendPdfCapital(old,{...capital,periodEnd:'2023-12-31'},['capital-share-capital'])).toThrow('不一致');
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:extended.updatedAt,workbooks:[extended]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].operatingMetrics[0].reported).toBe(12);
      const balances: EarningsPdfImport = {...document, capitalCandidates: [
        {...document.candidates[0], id:'capital-inventory', label:'存货', value:0, rawValue:'0.00', unit:'百万元',
          basis:'instant', periodEnd:'2024-12-31', scope:'consolidated', columnHeader:'合并资产负债表 · 2024年12月31日 2023年12月31日'},
      ]};
      const withBalances=appendPdfCapital(extended,balances,['capital-inventory']);
      expect(withBalances.operatingMetrics.at(-1)).toMatchObject({reported:0,reportedBasis:'instant',periodEnd:'2024-12-31'});
      expect(withBalances.sourceMaterials.at(-1)).toMatchObject({basis:'instant',importedReport:{scope:'consolidated'}});
      expect(withBalances.fiscalPeriod.basis).toBe('annual');
      expect(earningsResearchWorkbookSchema.safeParse(withBalances).success).toBe(true);
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:withBalances.updatedAt,workbooks:[withBalances]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].operatingMetrics.at(-1)?.reportedBasis).toBe('instant');
      expect(()=>appendPdfCapital(withBalances,balances,['capital-inventory'])).toThrow('不会重复');
      for(const patch of [{basis:undefined},{periodEnd:'2023-12-31'},{scope:undefined}]) {
        expect(()=>appendPdfCapital(extended,{...balances,capitalCandidates:[{...balances.capitalCandidates![0],...patch}]},['capital-inventory'])).toThrow('期末余额');
      }
      const noteDocument={...document,capitalNotesReadPages:[1,2,3,80],capitalNotes:[
        {id:'capital-note:80:0',page:80,title:'31、租赁负债',topics:['债务与租赁'],text:'长期租赁负债 12 元',truncated:false},
        {id:'capital-note:80:1',page:80,title:'32、货币资金',topics:['现金与受限资金'],text:'货币资金 10 元',truncated:false}]};
      const withNotes=appendPdfCapitalNotes(extended,noteDocument,['capital-note:80:0']);
      expect(withNotes.sourceMaterials.at(-1)?.capitalNote).toMatchObject({pdfPage:80,title:'31、租赁负债',text:'长期租赁负债 12 元'});
      expect(withNotes.metrics).toEqual(extended.metrics);expect(withNotes.operatingMetrics).toEqual(extended.operatingMetrics);
      expect(withNotes.headline).toBe(extended.headline);
      expect(earningsResearchWorkbookSchema.safeParse(withNotes).success).toBe(true);
      expect(()=>appendPdfCapitalNotes(withNotes,noteDocument,['capital-note:80:0'])).toThrow('不重复');
      expect(appendPdfCapitalNotes(withNotes,noteDocument,['capital-note:80:1']).sourceMaterials).toHaveLength(withNotes.sourceMaterials.length+1);
      expect(()=>appendPdfCapitalNotes(extended,{...noteDocument,periodEnd:'2023-12-31'},['capital-note:80:0'])).toThrow('不一致');
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:withNotes.updatedAt,workbooks:[withNotes]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials.at(-1)?.capitalNote).toEqual(withNotes.sourceMaterials.at(-1)?.capitalNote);
      const revenueDocument:EarningsPdfImport={...document,revenueGroups:[{id:'business-revenue:9:product',dimension:'product',title:'主营业务分产品情况',scope:'main-business',currency:'CNY',unit:'亿元',page:9,columnHeader:'营业收入 营业成本',rows:[{label:'测试产品',value:8,rawValue:'800,000,000.00',rawUnit:'元',excerpt:'测试产品 800,000,000.00'}],total:null,skippedRows:0}]};
      const withRevenue=appendPdfRevenue(old,revenueDocument,['business-revenue:9:product']);
      expect(withRevenue.metrics).toEqual(old.metrics);expect(withRevenue.operatingMetrics).toEqual(old.operatingMetrics);expect(withRevenue.headline).toBe(old.headline);
      expect(withRevenue.sourceMaterials.at(-1)?.businessRevenue).toMatchObject({dimension:'product',pdfPage:9,rows:[{label:'测试产品',value:8}]});
      expect(earningsResearchWorkbookSchema.safeParse(withRevenue).success).toBe(true);
      expect(missingPdfRevenue(withRevenue,revenueDocument)).toEqual([]);
      expect(()=>appendPdfRevenue(withRevenue,revenueDocument,['business-revenue:9:product'])).toThrow('不重复');
      expect(()=>appendPdfRevenue(old,{...revenueDocument,periodEnd:'2023-12-31'},['business-revenue:9:product'])).toThrow('不一致');
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:withRevenue.updatedAt,workbooks:[withRevenue]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials.at(-1)?.businessRevenue).toEqual(withRevenue.sourceMaterials.at(-1)?.businessRevenue);
    }finally{vi.unstubAllGlobals()}
  });
  it('creates a separate sourced workbook from selected PDF candidates and preserves missing values',async()=>{
    vi.stubGlobal('window',{location:{origin:'http://127.0.0.1:8911'}});
    const memory=new Map<string,string>();
    vi.stubGlobal('localStorage',{getItem:(k:string)=>memory.get(k)??null,setItem:(k:string,v:string)=>memory.set(k,v)});
    try{
      const workbook=workbookFromPdf({reportId:'sample',name:'合成年报.pdf',security:{market:'CN',symbol:'600519',name:'示例',currency:'CNY'},periodEnd:'2024-12-31',basis:'annual',retrievedAt:'2026-09-19T00:00:00Z',pageCount:10,readPages:[1,2],warnings:['仅读取前两页'],candidates:[{id:'revenue',label:'营业收入',value:12,unit:'亿元',rawValue:'1,200,000,000',rawUnit:'元',page:2,excerpt:'营业收入 1,200,000,000',columnHeader:'2024年 2023年'}]},['revenue']);
      expect(earningsResearchWorkbookSchema.safeParse(workbook).success).toBe(true);
      expect(earningsDataStatus(workbook)).toMatchObject({present:1,missing:8,filingAdopted:1,comparable:0});
      expect(workbook.metrics[1].reported).toBeNull();
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:workbook.updatedAt,workbooks:[workbook]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials[0].importedReport?.rawValue).toBe('1,200,000,000');
    }finally{vi.unstubAllGlobals()}
  });
  it('derives current coverage separately from historical notes and adopted-source history',()=>{
    const {next:d}=previewFinancialEvidence(draft(),facts());
    d.gaps.push('净利润：旧采集缺失提示');
    const reading=filingReading('净利润 50 亿元。');
    const source=linkFilingExcerpt(d,reading,'net-profit',reading.text);d.sourceMaterials.push(source);
    const before=earningsDataStatus(d);
    const next=applyFilingCorrection(d,previewFilingCorrection(d,source.id,50,'公告补录',reading),reading);
    const after=earningsDataStatus(next);
    expect(after.missing).toBe(before.missing-1);
    expect(after.present).toBe(before.present+1);
    expect(after.filingAdopted).toBe(1);
    expect(after.rows.find(row=>row.metricId==='net-profit')).toMatchObject({origin:'filing-fill',comparisonIssue:'一致预期缺失'});
    expect(next.gaps).toEqual(d.gaps);
    const metric=next.metrics.find(item=>item.id==='net-profit')!;
    metric.reported=51;metric.sourceIds=[];
    expect(earningsDataStatus(next).filingAdopted).toBe(0);
    expect(earningsDataStatus(next).rows.find(row=>row.metricId===metric.id)?.origin).toBe('manual');
    expect(next.sourceMaterials[0].correction?.before).toBeNull();
  });
  it('shares precise comparison reasons and counts zero expectations as amount-comparable',()=>{
    const d=draft(),metric=d.metrics[0];
    expect(earningsComparisonIssue(metric)).toBe('实际值缺失');
    Object.assign(metric,{reported:50,consensus:0,reportedBasis:'ytd',consensusBasis:'quarter',periodEnd:'2026-06-30',consensusPeriodEnd:'2026-06-30'});
    expect(earningsComparisonIssue(metric)).toBe('实际与预期口径不同');
    expect(calculateVariance(metric).varianceVsConsensus.amount).toBeNull();
    metric.consensusBasis='ytd';metric.consensusPeriodEnd='2026-03-31';
    expect(earningsComparisonIssue(metric)).toBe('实际与预期报告期不同');
    metric.consensusPeriodEnd='2026-06-30';
    expect(calculateVariance(metric).varianceVsConsensus).toEqual({amount:50,percent:null,bps:null});
    expect(earningsDataStatus(d).comparable).toBe(1);
    expect(earningsDataStatus(d).rows[0].comparisonNote).toContain('一致预期为零');
  });
  it('fills a missing actual from filing evidence without manufacturing zero or relabelling old expectations',()=>{
    const {next:d}=previewFinancialEvidence(draft(),facts());
    const metric=d.metrics.find(item=>item.id==='net-profit')!;
    metric.consensus=40; // Legacy expectation has no period or basis.
    const reading=filingReading('本期归母净利润 50 亿元。');
    const source=linkFilingExcerpt(d,reading,metric.id,reading.text);d.sourceMaterials.push(source);
    const original=structuredClone(d);
    const candidate=previewFilingCorrection(d,source.id,50,'按公告补录缺失净利润',reading);
    expect(candidate).toMatchObject({before:null,after:50,operation:'fill'});
    const next=applyFilingCorrection(d,candidate,reading);
    const filled=next.metrics.find(item=>item.id===metric.id)!;
    expect(filled).toMatchObject({reported:50,reportedOrigin:'manual',periodEnd:'2026-06-30',reportedBasis:'ytd',reportedCurrency:'CNY',consensus:40,varianceVsConsensus:{amount:null,percent:null,bps:null}});
    expect(filled.sourceIds).toEqual([next.sourceMaterials[0].id]);
    expect(next.metrics.filter(item=>item.id!==metric.id)).toEqual(d.metrics.filter(item=>item.id!==metric.id));
    expect(earningsResearchWorkbookSchema.parse(next).sourceMaterials[0].correction?.before).toBeNull();
    expect(next.verification.latestPeriodChecked).toBe(false);
    expect(d).toEqual(original);
    expect(()=>previewFilingCorrection(d,source.id,50,'补录',null)).toThrow('先回读');
    d.fiscalPeriod.periodEnd='2026-09-30';
    expect(()=>previewFilingCorrection(d,source.id,50,'补录',reading)).toThrow('口径未对齐');
    d.fiscalPeriod.periodEnd='2026-06-30';metric.reported=0;
    expect(()=>previewFilingCorrection(d,source.id,50,'补录',reading)).toThrow('实际值已变化');
  });
  it('allows an explicit zero fill while retaining a null before-value',()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2026-06-30';
    const reading=filingReading('本期营业收入为零。');
    const source=linkFilingExcerpt(d,reading,'revenue',reading.text);d.sourceMaterials.push(source);
    const next=applyFilingCorrection(d,previewFilingCorrection(d,source.id,0,'公告明确披露零值',reading),reading);
    expect(next.sourceMaterials[0].correction).toMatchObject({before:null,after:0});
    expect(next.metrics[0].reported).toBe(0);
    expect(next.metrics[0].varianceVsConsensus.amount).toBeNull();
  });
  it('converts explicit CNY scales without treating separators, ratios or currencies as amounts',()=>{
    expect(convertFilingAmount({value:'1,100,000',unit:'万元',currency:'CNY'})).toBe(110);
    expect(convertFilingAmount({value:'3',unit:'万元',currency:'CNY'})).toBe(0.0003);
    expect(convertFilingAmount({value:'-12,345.67',unit:'元',currency:'CNY'})).toBe(-0.0001234567);
    expect(convertFilingAmount({value:'0',unit:'亿元',currency:'CNY'})).toBe(0);
    for(const value of ['1,10','1.1亿元','20%',''])expect(()=>convertFilingAmount({value,unit:'万元',currency:'CNY'})).toThrow();
  });
  it('shows nearby source context for the first normalized quote, not an inferred replacement',()=>{
    expect(filingExcerptPassage('单位：亿元\n营业收入\n 123 亿元。 上年同期 100 亿元。','营业收入 123 亿元。')).toEqual({prefix:'单位：亿元 ',quote:'营业收入 123 亿元。',suffix:' 上年同期 100 亿元。'});
    expect(filingExcerptPassage('123 亿元；123 亿元','123 亿元')?.prefix).toBe('');
    expect(filingExcerptPassage('甲'.repeat(250)+'123'+'乙'.repeat(250),'123')).toEqual({prefix:'…'+'甲'.repeat(240),quote:'123',suffix:'乙'.repeat(240)+'…'});
    expect(filingExcerptPassage('营业收入 110 亿元','营业收入 123 亿元')).toBeNull();
    expect(filingExcerptPassage('营业收入 123 亿元','  ')).toBeNull();
  });
  it('rereads only the saved security and location and compares text without changing evidence',()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2026-06-30';
    const document:AnnouncementText={announcementId:'AN202608141827994407',symbol:'600519',title:'合成报告',date:'2026-08-15',url:'https://data.eastmoney.com/notices/detail/600519/AN202608141827994407.html',pdfUrl:'https://pdf.dfcfw.com/report.pdf',text:'营业收入 123 亿元',truncated:false,pdfPage:6,pdfPageCount:100,contentOrigin:'pdf-text',retrievedAt:'2026-09-18T00:00:00Z'};
    const source=linkFilingExcerpt(d,document,'revenue',document.text);d.sourceMaterials=[source];
    const before=structuredClone(d);
    expect(filingExcerptTarget('600519',source)).toEqual({announcementId:document.announcementId,kind:'pdf',position:6});
    expect(filingExcerptTarget('000001',source)).toBeNull();
    expect(filingExcerptTarget('600519',{...source,url:'https://other.example/notices/detail/600519/AN202608141827994407.html'})).toBeNull();
    expect(reviewFilingExcerpts(d,{...document,text:'营业收入\n 123 亿元'})[0]).toMatchObject({textMatch:'found',attachmentChanged:false});
    expect(reviewFilingExcerpts(d,{...document,text:'收入 110 亿元',pdfUrl:'https://pdf.dfcfw.com/revised.pdf'})[0]).toMatchObject({textMatch:'not-found',attachmentChanged:true});
    expect(reviewFilingExcerpts(d,{...document,text:''})[0].textMatch).toBe('unavailable');
    expect(reviewFilingExcerpts(d,{...document,pdfPage:7})).toEqual([]);
    expect(reviewFilingExcerpts(d,null)).toEqual([]);
    expect(d).toEqual(before);
  });
  it('preserves PDF page provenance without confusing it with transcription segments',()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2026-06-30';d.fiscalPeriod.label='半年报';d.metrics[0].reported=123;
    const document:AnnouncementText={announcementId:'AN202608141827994407',symbol:'600519',title:'PDF 半年报',date:'2026-08-15',url:'https://data.eastmoney.com/notices/detail/600519/AN202608141827994407.html',pdfUrl:'https://pdf.dfcfw.com/report.pdf',text:'营业收入 123 亿元',truncated:false,pdfPage:6,pdfPageCount:100,contentOrigin:'pdf-text',retrievedAt:'2026-09-18T00:00:00Z'};
    const source=linkFilingExcerpt(d,document,'revenue',document.text);
    expect(source.excerpt).toMatchObject({pdfPage:6,pdfPageCount:100,pdfUrl:document.pdfUrl,contentOrigin:'pdf-text'});
    expect(source.excerpt?.segment).toBeUndefined();
    d.sourceMaterials=[source];
    expect(earningsResearchWorkbookSchema.safeParse(d).success).toBe(true);
    expect(()=>linkFilingExcerpt(d,{...document,pdfPage:undefined},'revenue',document.text)).toThrow('定位不完整');
    source.excerpt!.pdfPage=101;
    expect(earningsResearchWorkbookSchema.safeParse(d).success).toBe(false);
  });
  it('adopts one manually confirmed correction, preserves provenance and expectations, and persists the record',async()=>{
    const {next:d}=previewFinancialEvidence(draft(),facts());
    d.metrics[0].consensus=100;d.metrics[0].consensusBasis='ytd';d.metrics[0].consensusPeriodEnd='2026-06-30';
    const source={...d.sourceMaterials[0],id:'correction-filing',kind:'filing' as const,label:'半年报更正',excerpt:{text:'营业收入由123亿元更正为110亿元。',segment:1,metricId:'revenue',reportedValue:123,unit:'亿元',contentOrigin:'provider-transcription' as const,association:'user-linked' as const}};
    const reading=filingReading(source.excerpt.text);Object.assign(source,{url:reading.url});
    d.sourceMaterials.push(source);
    const original=structuredClone(d);
    const amountInput={value:'1,100,000',unit:'万元' as const,currency:'CNY' as const};
    const candidate=previewFilingCorrection(d,source.id,110,'按收入更正段核对采用',reading,amountInput);
    expect(()=>applyFilingCorrection(d,{...candidate,after:111},reading)).toThrow('输入金额');
    expect(d).toEqual(original);
    const next=applyFilingCorrection(d,candidate,reading,'2026-09-19T00:00:00Z');
    expect(next.metrics[0]).toMatchObject({reported:110,consensus:100,reportedOrigin:'manual',varianceVsConsensus:{amount:10}});
    expect(next.metrics.slice(1)).toEqual(d.metrics.slice(1));
    expect(next.sourceMaterials[0].correction).toMatchObject({before:123,after:110,previousSourceIds:d.metrics[0].sourceIds,evidenceSourceId:source.id,amountInput});
    expect(next.sourceMaterials.slice(1)).toEqual(d.sourceMaterials);
    expect(next.verification.latestPeriodChecked).toBe(false);
    expect(earningsResearchWorkbookSchema.parse(next).sourceMaterials[0].correction?.amountInput).toEqual(amountInput);
    const memory=new Map<string,string>();vi.stubGlobal('localStorage',{setItem:(k:string,v:string)=>memory.set(k,v),getItem:(k:string)=>memory.get(k)??null});
    try{await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:next.updatedAt,workbooks:[next]});expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials[0].correction).toEqual(next.sourceMaterials[0].correction)}finally{vi.unstubAllGlobals()}
  });
  it('refuses stale correction baselines, unit/period mismatches, and missing or unchanged values',()=>{
    const {next:d}=previewFinancialEvidence(draft(),facts());
    const source={...d.sourceMaterials[0],id:'filing',kind:'filing' as const,excerpt:{text:'收入更正',segment:1,metricId:'revenue',reportedValue:123,unit:'亿元',contentOrigin:'provider-transcription' as const,association:'user-linked' as const}};
    const reading=filingReading(source.excerpt.text);Object.assign(source,{url:reading.url});
    d.sourceMaterials.push(source);
    expect(()=>previewFilingCorrection(d,source.id,NaN,'更正',reading)).toThrow('有效');
    expect(()=>previewFilingCorrection(d,source.id,123,'更正',reading)).toThrow('相同');
    const candidate=previewFilingCorrection(d,source.id,0,'收入更正为零',reading);
    expect(applyFilingCorrection(d,candidate,reading).metrics[0].reported).toBe(0);
    d.headline='已编辑';expect(()=>applyFilingCorrection(d,candidate,reading)).toThrow('底稿已改变');
    source.excerpt.unit='万元';expect(()=>previewFilingCorrection(d,source.id,110,'更正',reading)).toThrow('口径未对齐');
    source.excerpt.unit='亿元';d.metrics[0].reported=124;expect(()=>previewFilingCorrection(d,source.id,110,'更正',reading)).toThrow('实际值已变化');
  });
  it('requires matching current reading at both correction preview and adoption',()=>{
    const {next:d}=previewFinancialEvidence(draft(),facts());
    const reading=filingReading('营业收入由123亿元更正为110亿元。');
    const source=linkFilingExcerpt(d,reading,'revenue',reading.text);d.sourceMaterials.push(source);
    expect(()=>previewFilingCorrection(d,source.id,110,'更正',null)).toThrow('先回读');
    expect(()=>previewFilingCorrection(d,source.id,110,'更正',{...reading,text:'本段不含该摘录'})).toThrow('未能匹配');
    const candidate=previewFilingCorrection(d,source.id,110,'更正',reading);
    expect(()=>applyFilingCorrection(d,candidate,null)).toThrow('先回读');
    expect(()=>applyFilingCorrection(d,candidate,{...reading,text:'本段不含该摘录'})).toThrow('未能匹配');
    expect(d.metrics[0].reported).toBe(123);
  });
  it('marks title revision hints without inferring a replacement relationship',()=>{
    expect(announcementRevisionHint('2026年半年度报告')).toBeNull();
    expect(announcementRevisionHint('关于2026年半年度报告的更正公告')).toBe('更正线索（仅标题）');
    expect(announcementRevisionHint('2026年半年度报告（修订版）')).toBe('修订/补充线索（仅标题）');
    expect(announcementRevisionHint('取消股东大会')).toBe('撤回/取消线索（仅标题）');
  });
  it('links only actually read excerpts without replacing financial provenance',async()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2026-06-30';d.fiscalPeriod.label='半年报';d.metrics[0].reported=123;
    const document:AnnouncementText={announcementId:'AN202608141827994407',symbol:'600519',title:'合成半年报',date:'2026-08-15',url:'https://data.eastmoney.com/notices/detail/600519/AN202608141827994407.html',pdfUrl:null,text:'本期营业收入 123 亿元。',truncated:false,segment:1,segmentCount:1,contentOrigin:'provider-transcription',retrievedAt:'2026-09-17T00:00:00Z'};
    const source=linkFilingExcerpt(d,document,'revenue','营业收入 123 亿元。');
    expect(source).toMatchObject({status:'available',asOf:'2026-08-15',periodEnd:'2026-06-30',excerpt:{reportedValue:123,association:'user-linked',contentOrigin:'provider-transcription'}});
    expect(d.metrics[0].sourceIds).toEqual([]);
    expect(d.verification.latestPeriodChecked).toBe(false);
    expect(()=>linkFilingExcerpt(d,document,'revenue','收入超过所有预期')).toThrow('当前已读取');
    expect(()=>linkFilingExcerpt(d,{...document,symbol:'000001'},'revenue','营业收入')).toThrow('证券');
    d.sourceMaterials=[source];
    expect(earningsResearchWorkbookSchema.safeParse(d).success).toBe(true);
    const memory=new Map<string,string>();
    vi.stubGlobal('localStorage',{setItem:(k:string,v:string)=>memory.set(k,v),getItem:(k:string)=>memory.get(k)??null});
    try {
      await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:d.updatedAt,workbooks:[d]});
      expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].sourceMaterials[0].excerpt).toEqual(source.excerpt);
    }finally{vi.unstubAllGlobals()}
  });
  it('does not infer units from magnitude or turn missing markers into zero',()=>{
    for(const raw of ['','--','暂无',null,'1.2至1.4亿',100000000,'123'])expect(parseFinancialValue(raw,'亿元')).toBeNull();
    expect(parseFinancialValue('0元','亿元')).toBe(0);
    expect(parseFinancialValue('1200万元','亿元')).toBeCloseTo(0.12,12);
    expect(parseFinancialValue('1.2万亿','亿元')).toBe(12000);
    expect(parseFinancialValue('-5%','%')).toBe(-5);
  });
  it('uses the actual provider and period, without claiming latest filing verification',()=>{
    const d=draft();d.fiscalPeriod={basis:'ytd',label:'2026 半年报',periodEnd:'2026-06-30',reportingTime:'unknown'};
    d.metrics[0].consensus=100;d.metrics[0].internalEstimate=105;
    const {next}=previewFinancialEvidence(d,facts(),'2026-09-16T00:00:00Z');
    expect(d.metrics[0].reported).toBeNull();
    expect(next.metrics[0]).toMatchObject({reported:123,consensus:100,internalEstimate:105,periodEnd:'2026-06-30',reportedCurrency:'CNY'});
    expect(next.sourceMaterials[0]).toMatchObject({retrievedAt:'2026-09-16T00:00:00Z',periodEnd:'2026-06-30',status:'available'});
    expect(next.sourceMaterials[0].asOf).toBeUndefined();
    expect(next.verification).toMatchObject({status:'partial',latestPeriodChecked:false});
    expect(next.metrics[0].varianceVsConsensus.amount).toBeNull(); // Legacy expectations are not silently relabelled.
    expect(earningsResearchWorkbookSchema.safeParse(next).success).toBe(true);
  });
  it('accepts the live THS numeric annual year without crossing report periods',()=>{
    const annual=draft();annual.fiscalPeriod={basis:'annual',label:'2025 年报',periodEnd:'2025-12-31',reportingTime:'unknown'};
    const result=previewFinancialEvidence(annual,facts({basis:'annual',period:2025,revenue:'1720.54亿'}),'2026-09-19T00:00:00Z');
    expect(result.period).toBe('2025-12-31');
    expect(result.next.metrics[0].reported).toBe(1720.54);
    annual.fiscalPeriod.periodEnd='2024-12-31';
    expect(()=>previewFinancialEvidence(annual,facts({basis:'annual',period:2025}))).toThrow('不同');
    expect(()=>previewFinancialEvidence(draft(),facts({period:2025}))).toThrow('有效报告期');
  });
  it('retains old values AND original provenance when the provider omits a value',()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2026-06-30';
    d.sourceMaterials=[{id:'old',label:'旧来源',kind:'user',asOf:'2026-08-01',status:'available'}];
    d.metrics[0]={...d.metrics[0],reported:90,sourceIds:['old'],asOf:'2026-08-01'};
    const {next}=previewFinancialEvidence(d,facts({revenue:null}));
    expect(next.metrics[0]).toEqual(d.metrics[0]);
    expect(next.sourceMaterials).toContainEqual(d.sourceMaterials[0]);
    expect(next.gaps.join(' ')).toContain('保留原值及原始来源');
  });
  it('rejects mismatched/unknown periods and non-CNY imports instead of mixing data',()=>{
    const d=draft();d.fiscalPeriod.periodEnd='2025-12-31';
    expect(()=>previewFinancialEvidence(d,facts())).toThrow('不同');
    expect(()=>previewFinancialEvidence(d,facts({period:null}))).toThrow('有效报告期');
    const unknown=draft();unknown.metrics[0].consensus=100;
    expect(()=>previewFinancialEvidence(unknown,facts())).toThrow('期末日期');
    const usd=draft();usd.security.currency='USD';
    expect(()=>previewFinancialEvidence(usd,facts())).toThrow('人民币');
  });
  it('persists new provenance and marks local-only save honestly',async()=>{
    const memory=new Map<string,string>();
    vi.stubGlobal('localStorage',{setItem:(k:string,v:string)=>memory.set(k,v),getItem:(k:string)=>memory.get(k)??null});
    try{
      const {next}=previewFinancialEvidence(draft(),facts());
      next.verification.status='verified';next.verification.latestPeriodChecked=true; // Legacy stored metadata must not be silently rewritten.
      expect(await persistEarningsWorkspace({schemaVersion:'newma-desk.earnings-research.v1',updatedAt:next.updatedAt,workbooks:[next]})).toMatchObject({mode:'local'});
      const restored=(await hydrateEarningsWorkspace()).workspace.workbooks[0];
      expect(restored.metrics[0].periodEnd).toBe('2026-06-30');
      expect(restored.fiscalPeriod.basis).toBe('ytd');
      expect(restored.metrics[0].reportedBasis).toBe('ytd');
      expect(restored.sourceMaterials[0].basis).toBe('ytd');
      expect(restored.sourceMaterials[0].retrievedAt).toBe(next.sourceMaterials[0].retrievedAt);
      expect(restored.verification.latestPeriodChecked).toBe(true);
    }finally{vi.unstubAllGlobals()}
  });
  it('uses upstream single-quarter data and rejects unknown, mismatched and unsupported bases',()=>{
    const d=draft();d.fiscalPeriod.basis='quarter';
    expect(()=>previewFinancialEvidence(d,facts())).toThrow('口径');
    expect(()=>previewFinancialEvidence(d,facts({basis:undefined}))).toThrow('口径');
    const {next}=previewFinancialEvidence(d,facts({basis:'quarter',revenue:'40亿元'}));
    expect(next.metrics[0]).toMatchObject({reported:40,reportedBasis:'quarter'});
    d.fiscalPeriod.basis='ttm';expect(()=>previewFinancialEvidence(d,facts())).toThrow('TTM');
    d.fiscalPeriod.basis=undefined;expect(()=>previewFinancialEvidence(d,facts())).toThrow('先选择');
  });
  it('compares only matching known bases and period ends',()=>{
    const m={...draft().metrics[0],reported:123,consensus:100,reportedBasis:'ytd' as const,consensusBasis:'ytd' as const,periodEnd:'2026-06-30',consensusPeriodEnd:'2026-06-30'};
    expect(calculateVariance(m).varianceVsConsensus.percent).toBe(23);
    expect(calculateVariance({...m,consensusBasis:'quarter'}).varianceVsConsensus.amount).toBeNull();
    expect(calculateVariance({...m,consensusBasis:undefined}).varianceVsConsensus.amount).toBeNull();
    expect(calculateVariance({...m,consensusPeriodEnd:'2026-12-31'}).varianceVsConsensus.amount).toBeNull();
    expect(calculateVariance({...m,reportedBasis:'annual',consensusBasis:'ttm'}).varianceVsConsensus.amount).toBeNull();
    expect(calculateVariance({...m,unit:'%',reported:21,consensus:20}).varianceVsConsensus.bps).toBe(100);
  });
});
