import { useEffect, useState } from "react";
import { AlertCircle, GitCompareArrows, Loader2 } from "lucide-react";

import { GlassCard } from "@/components/ui/GlassCard";
import { api, type EquityResearchComparison } from "@/lib/api";


const METRICS = [
  ["pe", "PE", "x"],
  ["pb", "PB", "x"],
  ["revenueGrowthPct", "营收同比", "%"],
  ["netProfitGrowthPct", "净利同比", "%"],
  ["roePct", "ROE", "%"],
  ["netMarginPct", "净利率", "%"],
  ["cashConversionPct", "现金转化", "%"],
  ["debtRatioPct", "资产负债率", "%"],
] as const;

function format(value: number | null, unit: string) {
  if (value == null) return "—";
  const rendered = value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  return unit === "%" ? `${rendered}%` : `${rendered} ${unit}`;
}

export function EquityPeerComparison({ currentSymbol }: { currentSymbol: string }) {
  const [peers, setPeers] = useState("");
  const [result, setResult] = useState<EquityResearchComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPeers("");
    setResult(null);
    setError(null);
  }, [currentSymbol]);

  async function compare() {
    const symbols = Array.from(new Set([
      currentSymbol,
      ...peers.split(/[，,;；\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    ]));
    if (symbols.length < 2) {
      setError("请再输入至少 1 个同行证券代码");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await api.equityResearchComparison(symbols));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "同行比较失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <GlassCard className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <GitCompareArrows className="h-4 w-4 text-primary" /> 同行横向比较
          </h3>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground/70">
            使用与当前个股完全相同的标准字段比较 A/H/US 同行；原始币种金额不混算，只比较比例与结构指标。
          </p>
        </div>
        <span className="rounded-full border border-border/60 px-2 py-1 font-mono text-[9px] text-muted-foreground">
          基准 {currentSymbol}
        </span>
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          value={peers}
          onChange={(event) => setPeers(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void compare()}
          placeholder="输入同行代码，如 000858, 600809 或 MSFT, GOOG"
          className="min-w-0 flex-1 rounded-lg border border-border bg-card/80 px-3 py-2 text-xs outline-none placeholder:text-muted-foreground/60 focus:border-primary/50"
        />
        <button
          type="button"
          onClick={() => void compare()}
          disabled={loading}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-xs font-medium text-primary hover:bg-primary/25 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitCompareArrows className="h-3.5 w-3.5" />}
          开始比较
        </button>
      </div>

      {error && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" /> {error}
        </p>
      )}

      {result && result.rows.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-xl border border-border/60">
          <table className="min-w-[980px] w-full text-left text-xs">
            <thead className="bg-muted/30 text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 font-medium">证券</th>
                {METRICS.map(([, label]) => <th key={label} className="px-3 py-2.5 font-medium">{label}</th>)}
                <th className="px-3 py-2.5 font-medium">质量 / 增长 / 估值 / 韧性</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={`${row.identity.market}:${row.identity.symbol}`} className="border-t border-border/40">
                  <td className="px-3 py-3">
                    <p className="font-medium">{row.identity.name}</p>
                    <p className="font-mono text-[10px] text-muted-foreground">{row.identity.symbol} · {row.identity.market}</p>
                  </td>
                  {METRICS.map(([key, , unit]) => (
                    <td key={key} className="px-3 py-3 font-mono">{format(row.metrics[key], unit)}</td>
                  ))}
                  <td className="px-3 py-3 font-mono text-[10px] text-muted-foreground">
                    {["quality", "growth", "valuation", "resilience"]
                      .map((key) => row.scores[key] == null ? "—" : Math.round(row.scores[key] as number))
                      .join(" / ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result && result.errors.length > 0 && (
        <p className="mt-2 text-[10px] text-warning">
          未纳入：{result.errors.map((item) => `${item.symbol}（${item.message}）`).join("；")}
        </p>
      )}
    </GlassCard>
  );
}
