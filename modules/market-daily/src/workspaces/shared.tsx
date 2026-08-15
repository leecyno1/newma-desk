import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { MarketDataSource, MarketFilter, Quote, SearchResult, SecurityRef } from "../types";
import { isEtfSecurity, isOpenFundSecurity, securityKey } from "../data";

export const WORKSPACE_SECURITIES: SecurityRef[] = [
  { symbol: "600519", name: "贵州茅台", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "688981", name: "中芯国际", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "300308", name: "中际旭创", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "002463", name: "沪电股份", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "300750", name: "宁德时代", market: "CN", exchange: "SZ", currency: "CNY" },
  { symbol: "600406", name: "国电南瑞", market: "CN", exchange: "SH", currency: "CNY" },
  { symbol: "00700", name: "腾讯控股", market: "HK", exchange: "HKEX", currency: "HKD" },
  { symbol: "AAPL", name: "Apple", market: "US", exchange: "NASDAQ", currency: "USD" },
  { symbol: "NVDA", name: "NVIDIA", market: "US", exchange: "NASDAQ", currency: "USD" },
  { symbol: "TSLA", name: "Tesla", market: "US", exchange: "NASDAQ", currency: "USD" },
];

export const EVENT_TIMELINE_ETFS: SecurityRef[] = [
  { symbol: "510300", name: "沪深300ETF", market: "CN", exchange: "SH", currency: "CNY", assetType: "etf", securityType: "ETF" },
  { symbol: "510050", name: "上证50ETF", market: "CN", exchange: "SH", currency: "CNY", assetType: "etf", securityType: "ETF" },
  { symbol: "159915", name: "创业板ETF", market: "CN", exchange: "SZ", currency: "CNY", assetType: "etf", securityType: "ETF" },
  { symbol: "588000", name: "科创50ETF", market: "CN", exchange: "SH", currency: "CNY", assetType: "etf", securityType: "ETF" },
];

const DEFAULT_WORKSPACE_SECURITY: SecurityRef = {
  symbol: "600519",
  name: "贵州茅台",
  market: "CN",
  exchange: "SH",
  currency: "CNY",
};

export function useDeskTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  });
  useEffect(() => {
    const root = document.documentElement;
    const update = () => {
      setTheme(root.dataset.theme === "dark" ? "dark" : "light");
    };
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

export function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function formatPrice(value: unknown, digits = 2) {
  const parsed = numberValue(value);
  return parsed === undefined
    ? "—"
    : new Intl.NumberFormat("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(parsed);
}

export function formatCompact(value: unknown) {
  const parsed = numberValue(value);
  if (parsed === undefined) return "—";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(parsed);
}

export function signed(value: unknown, suffix = "%") {
  const parsed = numberValue(value);
  if (parsed === undefined) return "—";
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(2)}${suffix}`;
}

export function movement(value: unknown) {
  const parsed = numberValue(value);
  return parsed === undefined || parsed === 0 ? "flat" : parsed > 0 ? "up" : "down";
}

export function quoteSummary(quote?: Quote) {
  if (!quote) return {};
  return {
    symbol: quote.symbol,
    name: quote.name,
    market: quote.market,
    price: quote.price ?? null,
    changePct: quote.changePct ?? null,
    amount: quote.amount ?? null,
    pe: quote.pe ?? null,
    pb: quote.pb ?? null,
    ...(quote.assetType === "fund" ? {
      fundType: quote.fundType ?? null,
      fundCompany: quote.fundCompany ?? null,
      fundManager: quote.fundManager ?? null,
      navDate: quote.navDate ?? null,
      cumulativeNav: quote.cumulativeNav ?? null,
      subscribeStatus: quote.subscribeStatus ?? null,
      redeemStatus: quote.redeemStatus ?? null,
    } : {}),
  };
}

export function SecuritySearch({
  dataSource,
  onSelect,
}: {
  dataSource: MarketDataSource;
  onSelect: (security: SecurityRef) => void;
}) {
  const [query, setQuery] = useState("");
  const [market, setMarket] = useState<MarketFilter>("ALL");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const clean = query.trim();
    if (!clean) {
      setResults([]);
      setLoading(false);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void dataSource.search(clean, market)
        .then((items) => active && setResults(items))
        .catch(() => active && setResults([]))
        .finally(() => active && setLoading(false));
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [dataSource, market, query]);

  const open = Boolean(query.trim());
  return (
    <div className="workspace-security-search">
      <Search size={14} aria-hidden="true" />
      <input
        aria-label="搜索证券"
        placeholder="代码、公司、ETF 或基金"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <select aria-label="搜索市场" value={market} onChange={(event) => setMarket(event.target.value as MarketFilter)}>
        <option value="ALL">全部</option>
        <option value="CN">A股 / 基金</option>
        <option value="HK">港股</option>
        <option value="US">美股</option>
      </select>
      {open ? (
        <button type="button" aria-label="清除搜索" onClick={() => setQuery("")}><X size={13} /></button>
      ) : null}
      {open ? (
        <div className="workspace-search-results" role="listbox">
          {loading ? <p>正在搜索…</p> : null}
          {!loading && results.length === 0 ? <p>没有匹配标的</p> : null}
          {results.map((item) => (
            <button
              type="button"
              key={`${securityKey(item)}:${item.assetType || item.exchange || "security"}`}
              onClick={() => {
                onSelect(item);
                setQuery("");
              }}
            >
              <span>{isOpenFundSecurity(item) ? "基金" : isEtfSecurity(item) ? "ETF" : item.market}</span>
              <strong>{item.name}</strong>
              <small>{item.symbol} · {item.exchange || item.market}</small>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function useStoredSecurity(modId: string) {
  return useMemo(() => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(`vibedesk.${modId}.security.v1`) || "null") as SecurityRef | null;
      if (parsed && parsed.symbol && ["CN", "HK", "US"].includes(parsed.market)) return parsed;
    } catch {
      // Ignore malformed local workspace state.
    }
    return WORKSPACE_SECURITIES[0] ?? DEFAULT_WORKSPACE_SECURITY;
  }, [modId]);
}
