import { Filter, Plus, RefreshCw, Save, SlidersHorizontal, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { MarketDataSource, MarketId, Quote, SecurityRef } from "../types";
import { securityKey } from "../data";
import {
  WORKSPACE_SECURITIES,
  formatCompact,
  formatPrice,
  movement,
  signed,
} from "./shared";
import {
  SCANNER_TEMPLATES,
  cloneScannerExpression,
  createScannerCondition,
  evaluateScannerExpression,
  type SavedScannerExpression,
  type ScannerExpression,
  type ScannerField,
  type ScannerOperator,
} from "./scannerExpressions";

type ScannerPreset = "all" | "momentum" | "volume" | "value" | "custom";
const SAVED_EXPRESSIONS_KEY = "vibedesk.market-scanner.expressions.v1";

const FIELD_LABELS: Record<ScannerField, string> = {
  changePct: "涨跌幅 %",
  volumeRatio: "量比",
  amount: "成交额",
  pe: "PE",
  pb: "PB",
};

const OPERATOR_LABELS: Record<ScannerOperator, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
};

function loadSavedExpressions(): SavedScannerExpression[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SAVED_EXPRESSIONS_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.name === "string" && item.expression) : [];
  } catch {
    return [];
  }
}

function scannerSignal(quote: Quote) {
  if ((quote.changePct ?? 0) >= 3 && (quote.volumeRatio ?? 0) >= 1.4) return "放量走强";
  if ((quote.changePct ?? 0) >= 1.5) return "趋势向上";
  if ((quote.pe ?? 999) > 0 && (quote.pe ?? 999) <= 25) return "估值观察";
  if ((quote.changePct ?? 0) <= -3) return "波动风险";
  return "持续跟踪";
}

export function ScannerWorkspace({
  dataSource,
  security,
  onSelectSecurity,
  refreshNonce,
  onContextChange,
}: {
  dataSource: MarketDataSource;
  security: SecurityRef;
  onSelectSecurity: (security: SecurityRef) => void;
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [preset, setPreset] = useState<ScannerPreset>("all");
  const [expression, setExpression] = useState<ScannerExpression>(() => cloneScannerExpression(SCANNER_TEMPLATES.all));
  const [expressionName, setExpressionName] = useState("我的扫描条件");
  const [savedExpressions, setSavedExpressions] = useState<SavedScannerExpression[]>(loadSavedExpressions);
  const [activeSavedId, setActiveSavedId] = useState("");
  const [market, setMarket] = useState<MarketId | "ALL">("ALL");
  const [minimumChange, setMinimumChange] = useState(-10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void Promise.allSettled([
      dataSource.quotes(WORKSPACE_SECURITIES),
      dataSource.turnoverTop(),
    ]).then(async ([quoteResult, turnoverResult]) => {
      if (!active) return;
      const seedQuotes = quoteResult.status === "fulfilled" ? quoteResult.value : [];
      const known = new Set(seedQuotes.map(securityKey));
      const extraRefs: SecurityRef[] = turnoverResult.status === "fulfilled"
        ? turnoverResult.value.slice(0, 20).flatMap((item) => {
            const symbol = String(item.code || item.symbol || "").trim();
            if (!symbol || known.has(`CN:${symbol}`)) return [];
            return [{ symbol, name: item.name || symbol, market: "CN" as const }];
          })
        : [];
      const extras = extraRefs.length ? await dataSource.quotes(extraRefs).catch(() => []) : [];
      if (!active) return;
      setQuotes([...seedQuotes, ...extras]);
      if (quoteResult.status === "rejected" && !extras.length) setError("扫描行情暂时不可用");
    }).finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [dataSource, refreshNonce]);

  const filtered = useMemo(() => [...quotes]
    .filter((quote) => market === "ALL" || quote.market === market)
    .filter((quote) => (quote.changePct ?? -Infinity) >= minimumChange)
    .filter((quote) => evaluateScannerExpression(quote, expression))
    .sort((left, right) => (right.changePct ?? -Infinity) - (left.changePct ?? -Infinity)), [expression, market, minimumChange, quotes]);

  useEffect(() => {
    onContextChange({
      preset,
      market,
      minimumChange,
      expression,
      activeSavedExpression: savedExpressions.find((item) => item.id === activeSavedId)?.name ?? null,
      savedExpressionCount: savedExpressions.length,
      resultCount: filtered.length,
      leaders: filtered.slice(0, 8).map((quote) => ({
        symbol: quote.symbol,
        name: quote.name,
        market: quote.market,
        changePct: quote.changePct ?? null,
        signal: scannerSignal(quote),
      })),
    });
  }, [activeSavedId, expression, filtered, market, minimumChange, onContextChange, preset, savedExpressions]);

  const applyPreset = (next: Exclude<ScannerPreset, "custom">) => {
    setPreset(next);
    setActiveSavedId("");
    setExpression(cloneScannerExpression(SCANNER_TEMPLATES[next]));
  };

  const updateExpression = (next: ScannerExpression) => {
    setPreset("custom");
    setExpression(next);
  };

  const persistSaved = (next: SavedScannerExpression[]) => {
    setSavedExpressions(next);
    window.localStorage.setItem(SAVED_EXPRESSIONS_KEY, JSON.stringify(next));
  };

  const saveExpression = () => {
    const cleanName = expressionName.trim() || "未命名扫描条件";
    const current = savedExpressions.find((item) => item.id === activeSavedId);
    const record: SavedScannerExpression = {
      id: current?.id ?? globalThis.crypto?.randomUUID?.() ?? `expression-${Date.now()}`,
      name: cleanName,
      expression: cloneScannerExpression(expression),
      updatedAt: new Date().toISOString(),
    };
    persistSaved([record, ...savedExpressions.filter((item) => item.id !== record.id)]);
    setActiveSavedId(record.id);
    setExpressionName(record.name);
  };

  const deleteSavedExpression = () => {
    if (!activeSavedId) return;
    persistSaved(savedExpressions.filter((item) => item.id !== activeSavedId));
    setActiveSavedId("");
  };

  return (
    <div className="scanner-workspace">
      <section className="scanner-filter-rail" aria-label="扫描条件">
        <div className="workspace-section-title">
          <span><SlidersHorizontal size={14} />扫描条件</span>
          <small>{filtered.length} 个候选</small>
        </div>
        <div className="scanner-preset-list" role="group" aria-label="扫描预设">
          {([
            ["all", "全部标的", "不过滤信号"],
            ["momentum", "趋势走强", "涨幅不低于 1.5%"],
            ["volume", "量能活跃", "量比或成交额靠前"],
            ["value", "估值观察", "0 < PE ≤ 30"],
          ] as const).map(([id, label, description]) => (
            <button type="button" key={id} aria-pressed={preset === id} onClick={() => applyPreset(id)}>
              <Filter size={13} />
              <span><strong>{label}</strong><small>{description}</small></span>
            </button>
          ))}
        </div>
        <div className="scanner-expression-builder">
          <div className="scanner-expression-toolbar">
            <select
              aria-label="已保存扫描表达式"
              value={activeSavedId}
              onChange={(event) => {
                const saved = savedExpressions.find((item) => item.id === event.target.value);
                setActiveSavedId(event.target.value);
                if (!saved) return;
                setPreset("custom");
                setExpressionName(saved.name);
                setExpression(cloneScannerExpression(saved.expression));
              }}
            >
              <option value="">组合表达式</option>
              {savedExpressions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            <button type="button" aria-label="删除已保存表达式" disabled={!activeSavedId} onClick={deleteSavedExpression}><Trash2 size={12} /></button>
          </div>
          <div className="workspace-segment scanner-logic" role="group" aria-label="表达式逻辑">
            <button type="button" aria-pressed={expression.logic === "all"} onClick={() => updateExpression({ ...expression, logic: "all" })}>全部满足</button>
            <button type="button" aria-pressed={expression.logic === "any"} onClick={() => updateExpression({ ...expression, logic: "any" })}>任一满足</button>
          </div>
          <div className="scanner-condition-list">
            {expression.conditions.map((condition) => (
              <div key={condition.id} className="scanner-condition-row">
                <select aria-label="条件字段" value={condition.field} onChange={(event) => updateExpression({ ...expression, conditions: expression.conditions.map((item) => item.id === condition.id ? { ...item, field: event.target.value as ScannerField } : item) })}>
                  {(Object.keys(FIELD_LABELS) as ScannerField[]).map((field) => <option key={field} value={field}>{FIELD_LABELS[field]}</option>)}
                </select>
                <select aria-label="条件运算符" value={condition.operator} onChange={(event) => updateExpression({ ...expression, conditions: expression.conditions.map((item) => item.id === condition.id ? { ...item, operator: event.target.value as ScannerOperator } : item) })}>
                  {(Object.keys(OPERATOR_LABELS) as ScannerOperator[]).map((operator) => <option key={operator} value={operator}>{OPERATOR_LABELS[operator]}</option>)}
                </select>
                <input aria-label="条件值" type="number" value={condition.value} onChange={(event) => updateExpression({ ...expression, conditions: expression.conditions.map((item) => item.id === condition.id ? { ...item, value: Number(event.target.value) } : item) })} />
                <button type="button" aria-label="删除条件" onClick={() => updateExpression({ ...expression, conditions: expression.conditions.filter((item) => item.id !== condition.id) })}><Trash2 size={11} /></button>
              </div>
            ))}
          </div>
          <button type="button" className="scanner-add-condition" onClick={() => updateExpression({ ...expression, conditions: [...expression.conditions, createScannerCondition()] })}><Plus size={12} />增加条件</button>
          <div className="scanner-save-expression">
            <input aria-label="表达式名称" value={expressionName} onChange={(event) => setExpressionName(event.target.value)} />
            <button type="button" onClick={saveExpression}><Save size={12} />保存</button>
          </div>
        </div>
        <label className="workspace-field">
          <span>市场</span>
          <select value={market} onChange={(event) => setMarket(event.target.value as MarketId | "ALL")}>
            <option value="ALL">全部市场</option>
            <option value="CN">A 股</option>
            <option value="HK">港股</option>
            <option value="US">美股</option>
          </select>
        </label>
        <label className="workspace-field">
          <span>最低涨跌幅 <em>{minimumChange.toFixed(1)}%</em></span>
          <input type="range" min="-10" max="10" step="0.5" value={minimumChange} onChange={(event) => setMinimumChange(Number(event.target.value))} />
        </label>
        <p className="workspace-help">扫描结果来自共享行情服务与当前工作区标的，不产生自动买卖建议。</p>
      </section>

      <section className="scanner-results" aria-label="扫描结果">
        <div className="workspace-section-title">
          <span>候选标的</span>
          <small>按涨跌幅排序</small>
        </div>
        <div className="scanner-table" role="table">
          <div className="scanner-row scanner-head" role="row">
            <span>市场 / 标的</span><span>最新</span><span>涨跌幅</span><span>成交额</span><span>PE / PB</span><span>扫描信号</span>
          </div>
          {filtered.map((quote) => (
            <button
              type="button"
              className="scanner-row"
              data-selected={securityKey(quote) === securityKey(security)}
              role="row"
              key={securityKey(quote)}
              onClick={() => onSelectSecurity(quote)}
            >
              <span className="scanner-security"><i>{quote.market}</i><strong>{quote.name}</strong><small>{quote.symbol}</small></span>
              <span>{formatPrice(quote.price, quote.market === "HK" ? 3 : 2)}</span>
              <span className={movement(quote.changePct)}>{signed(quote.changePct)}</span>
              <span>{formatCompact(quote.amount)}</span>
              <span>{formatPrice(quote.pe)} / {formatPrice(quote.pb)}</span>
              <span><em className={`scanner-signal ${movement(quote.changePct)}`}>{scannerSignal(quote)}</em></span>
            </button>
          ))}
          {loading ? <div className="workspace-empty"><RefreshCw className="spin" size={16} />正在扫描行情…</div> : null}
          {!loading && error ? <div className="workspace-empty workspace-error">{error}</div> : null}
          {!loading && !error && filtered.length === 0 ? <div className="workspace-empty">当前条件没有匹配标的</div> : null}
        </div>
      </section>
    </div>
  );
}
