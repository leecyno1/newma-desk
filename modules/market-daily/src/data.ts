import {
  createDataServiceClient,
  createUnifiedDataClient,
  type GatewayFetch,
} from "@newma-desk/mod-sdk";

import type {
  Adjustment,
  MarketDataSource,
  MarketEventFeed,
  MarketEventSourceStatus,
  MarketEvidenceEvent,
  MarketFilter,
  MarketOverview,
  MarketScanOrder,
  MarketScanResult,
  MarketScanSort,
  OhlcvResult,
  Quote,
  SearchResult,
  SecurityRef,
  Timeframe,
  TurnoverStock,
} from "./types";

interface DataEnvelope<T> {
  data: T;
}

function dataOf<T>(value: DataEnvelope<T>): T {
  return value.data;
}

function textField(value: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return "";
}

function timestampOf(value: string) {
  const parsed = Date.parse(value.replace(/\//g, "-"));
  return Number.isFinite(parsed) ? parsed : 0;
}

function evidenceId(source: string, timestamp: number, title: string) {
  const body = `${source}-${timestamp}-${title}`
    .toLocaleLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 96);
  return `${source}:${body || timestamp}`;
}

function normalizeAnnouncement(value: Record<string, unknown>): MarketEvidenceEvent | undefined {
  const title = textField(value, "title", "公告标题");
  const date = textField(value, "date", "noticeDate", "公告日期");
  const timestamp = timestampOf(date);
  if (!title || !timestamp) return undefined;
  const typeText = textField(value, "type", "公告类型");
  const isFundAnnouncement = Boolean(textField(value, "fundCode", "FUNDCODE")) || typeText.includes("基金公告");
  const isEarnings = !isFundAnnouncement && /年报|季报|半年报|业绩|财务报告|审计报告/.test(`${title}${typeText}`);
  return {
    id: evidenceId("announcement", timestamp, title),
    timestamp,
    type: isEarnings ? "earnings" : "announcement",
    title,
    detail: typeText || (isFundAnnouncement ? "基金公告" : "上市公司公告"),
    source: isFundAnnouncement ? "东方财富基金公告" : "东方财富公告",
    ...(textField(value, "url", "链接") ? { url: textField(value, "url", "链接") } : {}),
    evidenceId: evidenceId("announcement", timestamp, title),
  };
}

const CN_ETF_CODE = /^(?:159\d{3}|5(?:1\d|2[0-3]|6[0-3]|88)\d{3})$/;

type SecurityClassification = Pick<
  SecurityRef,
  "symbol" | "name" | "market" | "exchange" | "assetType" | "securityType"
>;

export function isOpenFundSecurity(security: SecurityClassification) {
  const assetType = security.assetType?.toLocaleLowerCase();
  if (assetType === "fund") return true;
  if (assetType === "etf") return false;
  const classification = `${security.securityType ?? ""} ${security.name}`;
  if (/ETF|交易型开放式/i.test(classification) || CN_ETF_CODE.test(security.symbol)) return false;
  return security.market === "CN"
    && (security.exchange === "OTC" || /基金|开放式/i.test(classification));
}

export function isEtfSecurity(
  security: SecurityClassification,
) {
  if (security.assetType?.toLocaleLowerCase() === "fund") return false;
  const classification = `${security.assetType ?? ""} ${security.securityType ?? ""} ${security.name}`;
  return /ETF|交易型开放式/i.test(classification)
    || (security.market === "CN" && CN_ETF_CODE.test(security.symbol));
}

function normalizeReport(value: Record<string, unknown>): MarketEvidenceEvent | undefined {
  const title = textField(value, "title", "reportTitle", "研报标题");
  const date = textField(value, "publishDate", "publish_date", "日期");
  const timestamp = timestampOf(date);
  if (!title || !timestamp) return undefined;
  const organization = textField(value, "orgSName", "orgName", "机构");
  const rating = textField(value, "emRatingName", "ratingName", "评级");
  const detail = [organization, rating].filter(Boolean).join(" · ") || "机构研究报告";
  return {
    id: evidenceId("research", timestamp, title),
    timestamp,
    type: "research",
    title,
    detail,
    source: organization || "东方财富研报",
    ...(textField(value, "pdfUrl", "url") ? { url: textField(value, "pdfUrl", "url") } : {}),
    evidenceId: evidenceId("research", timestamp, title),
  };
}

function normalizeNews(value: Record<string, unknown>): MarketEvidenceEvent | undefined {
  const title = textField(value, "新闻标题", "title", "标题");
  const date = textField(value, "发布时间", "publishTime", "date", "时间");
  const timestamp = timestampOf(date);
  if (!title || !timestamp) return undefined;
  const source = textField(value, "文章来源", "source", "来源") || "东方财富新闻";
  const url = textField(value, "新闻链接", "url", "链接");
  return {
    id: evidenceId("news", timestamp, title),
    timestamp,
    type: "news",
    title,
    detail: source,
    source,
    ...(url ? { url } : {}),
    evidenceId: evidenceId("news", timestamp, title),
  };
}

export function createMarketDataSource(input: {
  baseUrl: string;
  fetch?: GatewayFetch;
  invokeAction?<T = unknown>(
    actionId: string,
    actionInput?: Record<string, unknown>,
  ): Promise<T>;
}): MarketDataSource {
  const fixedClient = createDataServiceClient(input);
  const unifiedClient = input.invokeAction
    ? createUnifiedDataClient({ invokeAction: input.invokeAction })
    : undefined;
  const queryData = <T>(
    capabilityId: string,
    actionInput: Record<string, unknown>,
  ) => unifiedClient
    ? unifiedClient.query<T>(capabilityId, actionInput)
    : fixedClient.invoke<T>("market-data", capabilityId, actionInput);
  return {
    async search(query: string, market: MarketFilter) {
      const result = dataOf(
        await queryData<DataEnvelope<{ items: SearchResult[] }>>(
          "market.symbol-search",
          { query, market, limit: 16 },
        ),
      );
      return result.items ?? [];
    },
    async quotes(symbols: SecurityRef[]) {
      if (symbols.length === 0) return [];
      const result = dataOf(
        await queryData<DataEnvelope<{ items: Quote[] }>>(
          "market.quotes",
          { symbols: symbols.map((item) => `${item.market}:${item.symbol}`).join(",") },
        ),
      );
      return result.items ?? [];
    },
    async quote(security: SecurityRef) {
      const assetType = isOpenFundSecurity(security)
        ? "fund"
        : isEtfSecurity(security)
          ? "etf"
          : security.assetType;
      const result = dataOf(
        await queryData<DataEnvelope<Quote>>("market.quote", {
          symbol: security.symbol,
          market: security.market,
          ...(assetType ? { assetType } : {}),
        }),
      );
      return {
        ...result,
        name: result.name && result.name !== result.symbol ? result.name : security.name,
        ...(assetType ? { assetType } : {}),
        ...(security.securityType ? { securityType: security.securityType } : {}),
      };
    },
    async scan(
      market: MarketScanResult["market"],
      sort: MarketScanSort,
      order: MarketScanOrder = "desc",
      limit = 100,
    ) {
      return dataOf(
        await queryData<DataEnvelope<MarketScanResult>>("market.scan", {
          market,
          sort,
          order,
          limit,
        }),
      );
    },
    async ohlcv(
      security: SecurityRef,
      timeframe: Timeframe,
      adjustment: Adjustment,
    ) {
      const capability = timeframe.endsWith("m") || timeframe === "60m"
        ? "market.intraday"
        : "market.ohlcv";
      const assetType = isOpenFundSecurity(security)
        ? "fund"
        : isEtfSecurity(security)
          ? "etf"
          : security.assetType;
      return dataOf(
        await queryData<DataEnvelope<OhlcvResult>>(capability, {
          symbol: security.symbol,
          market: security.market,
          timeframe,
          limit: 420,
          adjust: assetType === "fund" ? "none" : (security.market === "CN" ? adjustment : "none"),
          ...(assetType ? { assetType } : {}),
        }),
      );
    },
    async overview() {
      return dataOf(
        await queryData<DataEnvelope<MarketOverview>>(
          "market.overview",
          {},
        ),
      );
    },
    async indices() {
      return dataOf(
        await queryData<DataEnvelope<Array<Record<string, unknown>>>>(
          "market.indices",
          {},
        ),
      );
    },
    async globalIndices() {
      return dataOf(
        await queryData<DataEnvelope<Array<Record<string, unknown>>>>(
          "market.global-indices",
          {},
        ),
      );
    },
    async turnoverTop() {
      const result = dataOf(
        await queryData<DataEnvelope<{ stocks?: TurnoverStock[] }>>(
          "market.turnover-top",
          {},
        ),
      );
      return result.stocks ?? [];
    },
    async events(security) {
      const asOf = new Date().toISOString();
      const isEtf = isEtfSecurity(security);
      const isFund = isOpenFundSecurity(security);
      if (security.market !== "CN") {
        return {
          items: [],
          asOf,
          sources: isEtf || isFund
            ? [
                { id: "announcements", label: "基金公告", status: "unsupported", count: 0 },
                ...(isEtf ? [{ id: "news" as const, label: "ETF资讯", status: "unsupported" as const, count: 0 }] : []),
              ]
            : [
                { id: "announcements", label: "公司公告", status: "unsupported", count: 0 },
                { id: "reports", label: "机构研报", status: "unsupported", count: 0 },
                { id: "news", label: "个股新闻", status: "unsupported", count: 0 },
              ],
        } satisfies MarketEventFeed;
      }
      type EventRequest = readonly [
        MarketEventSourceStatus["id"],
        string,
        string,
        Record<string, unknown>,
        (value: Record<string, unknown>) => MarketEvidenceEvent | undefined,
      ];
      const etfNameKeyword = security.name.split(/ETF|交易型开放式/i)[0]?.trim() || "";
      const normalizeCurrentEtfNews = (value: Record<string, unknown>) => {
        const event = normalizeNews(value);
        if (!event) return undefined;
        return event.title.includes(security.symbol)
          || (etfNameKeyword.length >= 2 && event.title.includes(etfNameKeyword))
          ? event
          : undefined;
      };
      const requests: EventRequest[] = isFund
        ? [["announcements", "基金公告", "market.announcements", { code: security.symbol, assetType: "fund" }, normalizeAnnouncement]]
        : isEtf
          ? [
            ["announcements", "基金公告", "market.announcements", { code: security.symbol, assetType: "etf" }, normalizeAnnouncement],
            ["news", "ETF资讯", "market.news", { code: security.symbol, limit: 30 }, normalizeCurrentEtfNews],
          ]
          : [
            ["announcements", "公司公告", "market.announcements", { code: security.symbol }, normalizeAnnouncement],
            ["reports", "机构研报", "market.reports", { code: security.symbol, pages: 2 }, normalizeReport],
            ["news", "个股新闻", "market.news", { code: security.symbol, limit: 30 }, normalizeNews],
          ];
      const settled: Array<{
        items: MarketEvidenceEvent[];
        status: MarketEventSourceStatus;
      }> = [];
      for (const [id, label, capability, inputData, normalize] of requests) {
        try {
          const rows = dataOf(await queryData<DataEnvelope<Array<Record<string, unknown>>>>(capability, inputData));
          const items = (Array.isArray(rows) ? rows : []).flatMap((row) => {
            const normalized = normalize(row);
            return normalized ? [normalized] : [];
          });
          settled.push({
            items,
            status: { id, label, status: items.length ? "ok" : "empty", count: items.length },
          });
        } catch (reason) {
          settled.push({
            items: [],
            status: {
              id,
              label,
              status: "unavailable",
              count: 0,
              error: reason instanceof Error ? reason.message : "数据源不可用",
            },
          });
        }
      }
      const deduplicated = new Map<string, MarketEvidenceEvent>();
      for (const event of settled.flatMap((item) => item.items)) deduplicated.set(event.id, event);
      return {
        items: [...deduplicated.values()].sort((left, right) => right.timestamp - left.timestamp),
        sources: settled.map((item) => item.status),
        asOf,
      } satisfies MarketEventFeed;
    },
  };
}

export function securityKey(security: Pick<SecurityRef, "market" | "symbol">) {
  return `${security.market}:${security.symbol}`;
}
