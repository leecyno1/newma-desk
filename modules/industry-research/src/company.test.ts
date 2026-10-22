import { describe, expect, it } from "vitest";
import { companyFor, safeSourceUrl, type CompanyWorkbook } from "./company";
import type { Industry, Snapshot } from "./research";
import type { BusinessRevenue } from '@newma-desk/contracts';
const report = {periodEnd: "2026-08-31"} as Snapshot;
const industry = {name: "煤炭开采和洗选业"} as Industry;
const workbook: CompanyWorkbook = {id: "book", updatedAt: "2026-10-18", mode: "reported", security: {name: "测试公司", symbol: "000001", market: "CN", currency: "CNY"},
  fiscalPeriod: {label: "2025年报", periodEnd: "2025-12-31", basis: "annual"},
  metrics: [{id: "revenue", label: "营业收入", unit: "亿元", reported: 100, reportedBasis: "annual", reportedCurrency: "CNY", periodEnd: "2025-12-31", sourceIds: ["pdf"]}],
  sourceMaterials: [{id: "pdf", label: "合成测试财报", kind: "filing", status: "available", url: "https://example.com/a.pdf#page=3", periodEnd: "2025-12-31", basis: "annual",
    excerpt: {metricId: "revenue", reportedValue: 100, unit: "亿元", contentOrigin: "pdf-text", pdfPage: 3}, importedReport: {confirmedAt: "2026-10-18"}}]};

describe("行业到公司只读核验", () => {
  it("主营收入按表展示组内占比，错期或未确认原文撤下结构而非外推公司收入", () => {
    const group: BusinessRevenue={reportId:'pdf',dimension:'product',title:'主营业务分产品情况',scope:'main-business',currency:'CNY',unit:'亿元',pdfPage:9,pdfPageCount:100,columnHeader:'营业收入 营业成本',rows:[{label:'测试产品',value:80,rawValue:'80',rawUnit:'亿元',excerpt:'测试产品 80'}],total:null,skippedRows:0,confirmedAt:'2026-10-19T00:00:00Z',contentOrigin:'pdf-text'};
    const source={...workbook.sourceMaterials[0]!,id:'revenue-group',businessRevenue:group};
    const book={...workbook,sourceMaterials:[...workbook.sourceMaterials,source]};
    const result=companyFor(report,industry,book,'人工关联',1)!;
    expect(result.revenueGroups[0]!.summary).toMatchObject({denominator:80,denominatorLabel:'已采用项目合计（非公司总收入）'});
    expect(result.rows[0]!.value).toBe(100);
    expect(result.revenueGroups[0]!.group?.pdfPage).toBe(9);
    for(const patch of [{periodEnd:'2024-12-31'},{status:'unavailable'},{businessRevenue:{...group,confirmedAt:''}},{businessRevenue:{...group,currency:'USD'}}]) {
      expect(companyFor(report,industry,{...book,sourceMaterials:[{...source,...patch}] as CompanyWorkbook['sourceMaterials']},'关联',1)!.revenueGroups[0]!.summary).toBeNull();
    }
  });
  it("期末余额须有合并证据，拒绝年度发生额、错期及缺失合并范围", () => {
    const book = structuredClone(workbook);
    book.metrics = [{...book.metrics[0]!, id: "capital-inventory", reported: 0, reportedBasis: "instant"}];
    book.sourceMaterials = [{...book.sourceMaterials[0]!, basis: "instant",
      excerpt: {...book.sourceMaterials[0]!.excerpt!, metricId: "capital-inventory", reportedValue: 0},
      importedReport: {confirmedAt: "2026-10-19", scope: "consolidated"}}];
    const inventory = (value: CompanyWorkbook) => companyFor(report, industry, value, "合并报表核验", 1)!.rows.find(row => row.id === "capital-inventory")!;
    expect(inventory(book)).toMatchObject({value: 0, basis: "期末余额", state: "已采用PDF证据，非审计确认"});
    for (const change of [{reportedBasis: "annual"}, {periodEnd: "2024-12-31"}]) {
      expect(inventory({...book, metrics: [{...book.metrics[0]!, ...change}]}).value).toBeNull();
    }
    expect(inventory({...book, sourceMaterials: [{...book.sourceMaterials[0]!, importedReport: {confirmedAt: "2026-10-19"}}]}).value).toBeNull();
    expect(inventory({...book, sourceMaterials: [{...book.sourceMaterials[0]!, basis: "annual"}]}).value).toBeNull();
  });
  it("未确认关联或财务失效不输出公司证据", () => {
    expect(companyFor(report, industry, workbook, "", 1)).toBeNull();
    expect(companyFor(null, industry, workbook, "关联理由", 1)).toBeNull();
    expect(companyFor(report, undefined, workbook, "关联理由", 1)).toBeNull();
  });
  it("保留PDF证据，跨期不计算传导，现金流与缺项不补造", () => {
    const result = companyFor(report, industry, workbook, "人工业务关联", 4)!;
    expect(result.periodAligned).toBe(false);
    expect(result.timingNote).toContain("不计算增速差");
    expect(result.rows[0]).toMatchObject({value: 100, state: "已采用PDF证据，非审计确认"});
    expect(result.rows.find(row => row.id === "operating-cash-flow")?.value).toBeNull();
    expect(result.rows.find(row => row.id === "operating-cash-flow")?.issues).toEqual(["实际值缺失或重复"]);
    expect(companyFor(report, industry, {...workbook, metrics:[{...workbook.metrics[0]!, reported:null, reportedBasis:undefined, reportedCurrency:undefined, sourceIds:[]}]}, "关联", 4)!.rows[0]!.issues).toEqual(["实际值缺失或重复"]);
    expect(result.relation.boundary).toContain("不是官方");
    expect(result.sourceRevision).toBe(4);
  });
  it("单位、期间、币种、来源与实际口径不满足时停止使用数值", () => {
    for (const patch of [{reportedBasis: "quarter"}, {periodEnd: "2026-06-30"}, {reportedCurrency: "USD"}, {sourceIds: []}, {reported: null}]) {
      const result = companyFor(report, industry, {...workbook, metrics: [{...workbook.metrics[0]!, ...patch}]}, "关联", 1)!;
      expect(result.rows[0]?.value).toBeNull();
    }
    expect(companyFor(report, industry, {...workbook, mode: "preview"}, "关联", 1)?.rows[0]?.value).toBeNull();
    const duplicated = {...workbook, metrics: [...workbook.metrics, ...workbook.metrics]};
    expect(companyFor(report, industry, duplicated, "关联", 1)?.rows[0]?.value).toBeNull();
  });
  it("同日单季不能当累计比较，未采用来源不冒称原文确认", () => {
    expect(companyFor({...report, periodEnd: "2025-12-31"}, industry, workbook, "关联", 1)?.periodAligned).toBe(true);
    const quarter = {...workbook, fiscalPeriod: {...workbook.fiscalPeriod, basis: "quarter"}};
    expect(companyFor({...report, periodEnd: "2025-12-31"}, industry, quarter, "关联", 1)?.periodAligned).toBe(false);
    const provider = {...workbook, sourceMaterials: [{...workbook.sourceMaterials[0]!, importedReport: undefined, excerpt: undefined}]};
    expect(companyFor(report, industry, provider, "关联", 1)?.rows[0]?.state).toBe("底稿记录，待核对原文");
    expect(safeSourceUrl("javascript:alert(1)")).toBeNull();
  });
});
