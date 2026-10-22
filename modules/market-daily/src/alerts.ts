import { useCallback, useEffect, useRef, useState } from "react";
import { createStorageRequest, StorageAccessError, type StorageClientOptions } from "./storageAccess";

import type { SecurityRef } from "./types";

export interface PriceAlert {
  id: string;
  userId: string;
  workspaceId: string;
  security: SecurityRef;
  direction: "above" | "below";
  price: number;
  label: string;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PriceAlertCreate {
  security: SecurityRef;
  direction: PriceAlert["direction"];
  price: number;
  label?: string;
  enabled?: boolean;
}

export interface PriceAlertUpdate {
  direction?: PriceAlert["direction"];
  price?: number;
  label?: string;
  enabled?: boolean;
}

export interface MarketAlertClient {
  load(enabled?: boolean): Promise<PriceAlert[]>;
  create(alert: PriceAlertCreate): Promise<PriceAlert>;
  update(alertId: string, update: PriceAlertUpdate): Promise<PriceAlert>;
  delete(alertId: string): Promise<void>;
}

export class MarketAlertRequestError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "MarketAlertRequestError";
  }
}

export function createMarketAlertClient(input: StorageClientOptions): MarketAlertClient {
  const send = createStorageRequest(input);
  const request = async <T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<T> => {
    try {
      return await send<T>(method, path, body);
    } catch (error) {
      if (error instanceof StorageAccessError) throw new MarketAlertRequestError(error.status, error.message);
      throw error;
    }
  };
  const path = (alertId: string) =>
    `/api/market-alerts/${encodeURIComponent(alertId)}`;
  return {
    async load(enabled) {
      const query = enabled === undefined ? "" : `?enabled=${enabled}`;
      const result = await request<{ items: PriceAlert[] }>("GET", `/api/market-alerts${query}`);
      return result.items ?? [];
    },
    create: (alert) => request("POST", "/api/market-alerts", alert),
    update: (alertId, update) => request("PATCH", path(alertId), update),
    delete: async (alertId) => {
      await request("DELETE", path(alertId));
    },
  };
}

export function useMarketAlerts(client?: MarketAlertClient) {
  type Status = "unavailable" | "loading" | "ready" | "error";
  const [state, setState] = useState<{ client?: MarketAlertClient; alerts: PriceAlert[]; status: Status }>({
    client, alerts: [], status: client ? "loading" : "unavailable",
  });
  const current = useRef({ client });
  if (current.current.client !== client) current.current = { client };
  const generation = current.current;
  const mounted = useRef(true);
  const loadVersion = useRef(0);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; loadVersion.current++; };
  }, []);
  const isCurrent = useCallback(() => mounted.current && current.current === generation, [generation]);
  const assertCurrent = useCallback(() => {
    if (!isCurrent()) throw new Error("账户或页面已切换，旧预警结果未应用");
  }, [isCurrent]);

  const reload = useCallback(async () => {
    const version = ++loadVersion.current;
    if (!client) {
      setState({ client, alerts: [], status: "unavailable" });
      return [];
    }
    setState((old) => ({ client, alerts: old.client === client ? old.alerts : [], status: "loading" }));
    try {
      const items = await client.load();
      assertCurrent();
      if (version === loadVersion.current) setState({ client, alerts: items, status: "ready" });
      return items;
    } catch (reason) {
      if (isCurrent() && version === loadVersion.current) {
        setState({ client, alerts: [], status: "error" });
      }
      throw reason;
    }
  }, [assertCurrent, client, isCurrent]);

  useEffect(() => {
    void reload().catch(() => undefined);
  }, [reload]);

  const createAlert = useCallback(async (input: PriceAlertCreate) => {
    assertCurrent();
    if (!client) throw new Error("共享价格预警服务未连接");
    loadVersion.current++;
    const alert = await client.create(input);
    assertCurrent();
    setState((old) => ({ client, alerts: [alert, ...(old.client === client ? old.alerts : []).filter((item) => item.id !== alert.id)], status: "ready" }));
    return alert;
  }, [assertCurrent, client]);

  const updateAlert = useCallback(async (alertId: string, update: PriceAlertUpdate) => {
    assertCurrent();
    if (!client) throw new Error("共享价格预警服务未连接");
    loadVersion.current++;
    const alert = await client.update(alertId, update);
    assertCurrent();
    setState((old) => ({ client, alerts: (old.client === client ? old.alerts : []).map((item) => item.id === alert.id ? alert : item), status: "ready" }));
    return alert;
  }, [assertCurrent, client]);

  const deleteAlert = useCallback(async (alertId: string) => {
    assertCurrent();
    if (!client) throw new Error("共享价格预警服务未连接");
    loadVersion.current++;
    await client.delete(alertId);
    assertCurrent();
    setState((old) => ({ client, alerts: (old.client === client ? old.alerts : []).filter((item) => item.id !== alertId), status: "ready" }));
  }, [assertCurrent, client]);

  const visible = state.client === client ? state : { alerts: [], status: client ? "loading" as const : "unavailable" as const };
  return { ...visible, reload, createAlert, updateAlert, deleteAlert };
}
