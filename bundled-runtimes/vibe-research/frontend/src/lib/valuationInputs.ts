import type { EarningsWorkbook } from "@/lib/earningsWorkbench";
import type { EquityResearchSnapshot } from "@/lib/api";
import { blankValuationModel, type ValuationModel } from "@/lib/valuationWorkbench";
import { waitForVibeDeskConfig } from "@/lib/vibedesk";
import { CAPITAL_FACT_IDS } from './earningsPdfImport';
import type { CapitalField } from './valuationReview';

export type SavedEarningsInput = Pick<EarningsWorkbook, "id" | "updatedAt" | "security" | "fiscalPeriod" | "mode" | "metrics" | "sourceMaterials"> & Partial<Pick<EarningsWorkbook, 'operatingMetrics'>>;

export function capitalNoteReferences(workbooks: SavedEarningsInput[], model: ValuationModel, field: CapitalField) {
  const topic = field === 'totalDebtM' ? '债务与租赁' : field === 'cashM' || field === 'excludedCashM' ? '现金与受限资金' : field === 'dilutedSharesM' ? '股本' : '';
  return workbooks.filter(workbook => workbook.mode === 'reported' && workbook.security.market === model.security.market
    && workbook.security.symbol === model.security.symbol && workbook.security.currency === model.security.currency
    && workbook.fiscalPeriod.basis === 'annual' && workbook.fiscalPeriod.periodEnd === model.asOf)
    .flatMap(workbook => workbook.sourceMaterials.filter(source => source.capitalNote?.topics.includes(topic)
      && source.capitalNote.text && source.capitalNote.contentOrigin === 'pdf-text' && source.capitalNote.confirmedAt
      && source.capitalNote.readPages.includes(source.capitalNote.pdfPage)
      && source.periodEnd === model.asOf && source.basis === 'annual' && ['available','verified'].includes(source.status))
      .map(source => ({workbookId: workbook.id, savedAt: workbook.updatedAt, source})));
}

export function capitalReferences(workbooks: SavedEarningsInput[], model: ValuationModel, field: CapitalField) {
  const relevant = field === 'dilutedSharesM' ? ['capital-share-capital']
    : field === 'cashM' || field === 'excludedCashM' ? ['capital-cash-funds', 'capital-customer-deposits']
    : field === 'totalDebtM' ? CAPITAL_FACT_IDS.filter(id => !['capital-share-capital', 'capital-cash-funds', 'capital-customer-deposits'].includes(id)) : [];
  return workbooks.filter(workbook => workbook.mode === 'reported' && workbook.security.market === model.security.market
    && workbook.security.symbol === model.security.symbol && workbook.security.currency === model.security.currency
    && workbook.fiscalPeriod.basis === 'annual' && workbook.fiscalPeriod.periodEnd === model.asOf)
    .flatMap(workbook => (workbook.operatingMetrics || []).filter(metric => relevant.includes(metric.id)
      && metric.reported !== null && Number.isFinite(metric.reported) && metric.unit === '百万元'
      && metric.reportedCurrency === model.security.currency && metric.periodEnd === model.asOf && metric.reportedBasis === 'annual')
      .flatMap(metric => {
        const source = workbook.sourceMaterials.find(source => metric.sourceIds.includes(source.id)
          && ['available', 'verified'].includes(source.status) && source.periodEnd === metric.periodEnd && source.basis === 'annual'
          && source.excerpt?.metricId === metric.id && source.excerpt.unit === metric.unit
          && source.importedReport?.columnHeader.includes('合并资产负债表')
          && source.excerpt.reportedValue === metric.reported);
        return source ? [{workbookId:workbook.id, savedAt:workbook.updatedAt, metric, source}] : [];
      }));
}

export function previewEarningsInput(workbook: SavedEarningsInput) {
  const metric = workbook.metrics.find(item => item.id === "revenue");
  const source = workbook.sourceMaterials.find(item => metric?.sourceIds.includes(item.id)
    && ["available", "verified"].includes(item.status)
    && item.excerpt?.metricId === "revenue" && item.excerpt.unit === metric.unit
    && item.periodEnd === metric.periodEnd && item.basis === metric.reportedBasis
    && ((item.importedReport && item.excerpt.reportedValue === metric.reported)
      || (item.correction && item.correction.after === metric.reported)));
  const factor = ({ "亿元": 100, "百万元": 1, "万元": 0.01, "元": 0.000001 } as Record<string, number>)[metric?.unit ?? ""];
  const period = workbook.fiscalPeriod?.periodEnd ?? "";
  const issues = [
    ...(!workbook.security?.symbol || !workbook.security?.name || !workbook.security?.market ? ["证券身份不完整"] : []),
    ...(workbook.mode !== "reported" || workbook.fiscalPeriod?.basis !== "annual" || metric?.reportedBasis !== "annual" ? ["仅采用完整年度实际收入，不将季度或累计数直接年化"] : []),
    ...(!/^\d{4}-\d{2}-\d{2}$/.test(period) || !Number.isFinite(Date.parse(period)) || metric?.periodEnd !== period ? ["收入期间与财报基期不一致"] : []),
    ...(workbook.security?.currency !== "CNY" || metric?.reportedCurrency !== "CNY" ? ["首版财报接入仅支持人民币，不自动换汇"] : []),
    ...(typeof metric?.reported !== "number" || !Number.isFinite(metric.reported) || metric.reported <= 0 ? ["缺少正数营业收入"] : []),
    ...(!factor ? ["收入金额单位尚不支持"] : []),
    ...(!source ? ["缺少与当前收入匹配的已采用财报原文，请先在财报研究中确认"] : []),
  ];
  return { issues, metric, source, period, revenueM: issues.length ? null : metric!.reported! * factor! };
}

export function valuationFromEarnings(workbook: SavedEarningsInput): ValuationModel {
  const preview = previewEarningsInput(workbook);
  if (preview.issues.length) throw new Error(preview.issues.join("；"));
  const model = blankValuationModel();
  const source = preview.source!;
  const sourceId = `earnings:${workbook.id}:revenue`;
  return {
    ...model,
    name: `${workbook.security.name} ${preview.period.slice(0, 4)} 年报估值草稿`,
    security: { ...workbook.security }, asOf: preview.period,
    historicals: [{ ...model.historicals[0]!, period: preview.period, revenue: preview.revenueM, sourceIds: [sourceId] }],
    scenarios: model.scenarios.map(scenario => ({ ...scenario,
      rationale: `模板假设，待研究确认：${scenario.rationale}`,
      drivers: scenario.drivers.map((driver, index) => ({ ...driver, year: Number(preview.period.slice(0, 4)) + index + 1 })),
    })),
    sourceMaterials: [{ id: sourceId, label: `${source.label} · 收入 ${preview.metric!.reported} ${preview.metric!.unit}`,
      asOf: preview.period, source: `财报底稿 ${workbook.id} · 保存 ${workbook.updatedAt}`, status: "available", ...(source.url ? { url: source.url } : {}) }],
    gaps: ["仅接入已确认的年度营业收入；三情景均为模板假设，不能视为公司指引或研究预测",
      "本模型以财报基期末为估值时点，尚未滚动至今日", "稀释股数、债务与现金须核验；市值÷股价不等于稀释股数",
      "EBIT、折旧摊销、资本开支与营运资本尚待核验；净利润和经营现金流不直接代替 EBIT 或 UFCF"],
  };
}

export async function loadSavedEarningsInputs(): Promise<SavedEarningsInput[]> {
  const config = await waitForVibeDeskConfig();
  if (!config) throw new Error("请在 Desk 中打开此页面，读取当前工作区已保存财报");
  const response = await fetch(`${config.apiOrigin}/api/research-archive/earnings-inputs`, {
    headers: { "X-User-Id": config.userId, "X-Workspace-Id": config.workspaceId },
  });
  if (!response.ok) throw new Error("财报底稿读取失败，请检查财报研究及本地服务后重试");
  return (await response.json()).workbooks;
}

export function hasValuationFacts(model: ValuationModel) {
  return model.historicals.some(row => row.revenue !== null) || model.sourceMaterials.length > 0
    || Object.keys(model.capitalEvidenceDrafts || {}).length > 0
    || [model.capitalInputs.currentPrice, model.capitalInputs.dilutedSharesM, model.capitalInputs.totalDebtM, model.capitalInputs.cashM,
      model.capitalInputs.excludedCashM, model.capitalInputs.nonOperatingAssetsM, model.capitalInputs.minorityInterestM, model.capitalInputs.otherClaimsM].some(value => typeof value === 'number');
}

export function applyMarketPrice(model: ValuationModel, snapshot: EquityResearchSnapshot): ValuationModel {
  if (snapshot.identity.symbol.toUpperCase() !== model.security.symbol.toUpperCase()
    || snapshot.identity.market !== model.security.market || snapshot.identity.currency !== model.security.currency) {
    throw new Error("行情证券或币种与模型不一致，未采用任何输入");
  }
  const evidence = snapshot.evidenceLedger.find(item => item.id === "valuation.price");
  const price = typeof evidence?.value === "number" ? evidence.value : Number(String(evidence?.value ?? "").replace(/,/g, ""));
  if (!evidence || !Number.isFinite(price) || price <= 0 || evidence.currency !== model.security.currency) {
    throw new Error("未取得币种明确的有效股价，保留原值");
  }
  return { ...model,
    capitalInputs: { ...model.capitalInputs, currentPrice: price, currentPriceAsOf: evidence.asOf?.slice(0, 10) || '' },
    sourceMaterials: [...model.sourceMaterials.filter(item => item.id !== evidence.id), {
      id: evidence.id, label: evidence.label, asOf: evidence.asOf || "待核验", source: evidence.source,
      status: "available", ...(evidence.url ? { url: evidence.url } : {}),
    }], updatedAt: new Date().toISOString(),
  };
}
