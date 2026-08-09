import { BellRing, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import type { PriceAlert } from "./alerts";
import type { Quote, SecurityRef } from "./types";

export function MarketAlertCenter({
  alerts,
  security,
  quote,
  available,
  onCreate,
  onToggle,
  onDelete,
}: {
  alerts: PriceAlert[];
  security: SecurityRef;
  quote?: Quote;
  available: boolean;
  onCreate: (input: { direction: "above" | "below"; price: number; label: string }) => Promise<unknown>;
  onToggle: (alert: PriceAlert) => Promise<unknown>;
  onDelete: (alert: PriceAlert) => Promise<unknown>;
}) {
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [price, setPrice] = useState(quote?.price ? String(quote.price) : "");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPrice(quote?.price ? String(quote.price) : "");
    setLabel("");
    setError("");
  }, [quote?.price, security.market, security.symbol]);

  const currentAlerts = alerts.filter((alert) =>
    alert.security.market === security.market && alert.security.symbol === security.symbol,
  );
  const submit = async () => {
    const nextPrice = Number(price);
    if (!Number.isFinite(nextPrice) || nextPrice <= 0) {
      setError("请输入有效预警价格");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onCreate({ direction, price: nextPrice, label });
      setLabel("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警保存失败");
    } finally {
      setBusy(false);
    }
  };
  const runMutation = async (operation: () => Promise<unknown>) => {
    setError("");
    try {
      await operation();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预警操作失败");
    }
  };

  return (
    <details className="market-alert-center">
      <summary aria-label="价格预警中心" title="价格预警中心">
        <BellRing size={14} />
        <span>{alerts.filter((alert) => alert.enabled).length}</span>
      </summary>
      <div className="market-alert-popover">
        <header>
          <span><strong>价格预警</strong><small>Desk 跨 Mod 共享</small></span>
          <i>{security.market}:{security.symbol}</i>
        </header>
        <div className="market-alert-form">
          <select value={direction} onChange={(event) => setDirection(event.target.value as "above" | "below")} aria-label="预警方向">
            <option value="above">价格上穿</option>
            <option value="below">价格下穿</option>
          </select>
          <input type="number" min="0" step="any" value={price} onChange={(event) => setPrice(event.target.value)} aria-label="预警价格" placeholder="价格" />
          <input value={label} onChange={(event) => setLabel(event.target.value.slice(0, 80))} aria-label="预警备注" placeholder="备注（可选）" />
          <button type="button" disabled={!available || busy} onClick={() => void submit()}>{busy ? "保存中" : "添加"}</button>
        </div>
        {error ? <p className="market-alert-error">{error}</p> : null}
        <div className="market-alert-list">
          {currentAlerts.slice(0, 12).map((alert) => (
            <div key={alert.id} className="market-alert-row" data-enabled={alert.enabled}>
              <button type="button" className="market-alert-toggle" onClick={() => void runMutation(() => onToggle(alert))} aria-label={`${alert.enabled ? "停用" : "启用"} ${alert.label}`}>
                <i />
              </button>
              <span><strong>{alert.label}</strong><small>{alert.direction === "above" ? "上穿" : "下穿"} {alert.price}</small></span>
              <button type="button" className="market-alert-delete" onClick={() => void runMutation(() => onDelete(alert))} aria-label={`删除 ${alert.label}`}><Trash2 size={12} /></button>
            </div>
          ))}
          {!currentAlerts.length ? <p>当前标的尚无预警</p> : null}
        </div>
      </div>
    </details>
  );
}
