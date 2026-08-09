import { useCallback, useEffect, useState } from "react";

import type { GatewayFetch } from "@newma-desk/mod-sdk";

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

function requestMessage(body: unknown, fallback: string) {
  if (
    typeof body === "object" && body !== null &&
    "detail" in body && typeof body.detail === "string"
  ) return body.detail;
  return fallback;
}

export function createMarketAlertClient(input: {
  baseUrl: string;
  userId: string;
  workspaceId: string;
  fetch?: GatewayFetch;
}): MarketAlertClient {
  const fetcher = input.fetch ?? globalThis.fetch.bind(globalThis);
  const baseUrl = input.baseUrl.replace(/\/$/, "");
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-User-Id": input.userId,
    "X-Workspace-Id": input.workspaceId,
  };
  const request = async <T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<T> => {
    const response = await fetcher(`${baseUrl}${path}`, {
      method,
      credentials: "omit",
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    if (!response.ok) {
      throw new MarketAlertRequestError(
        response.status,
        requestMessage(payload, `Market alert API returned ${response.status}`),
      );
    }
    return payload as T;
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
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [status, setStatus] = useState<"unavailable" | "loading" | "ready" | "error">(
    client ? "loading" : "unavailable",
  );

  const reload = useCallback(async () => {
    if (!client) {
      setAlerts([]);
      setStatus("unavailable");
      return [];
    }
    setStatus("loading");
    try {
      const items = await client.load();
      setAlerts(items);
      setStatus("ready");
      return items;
    } catch (reason) {
      setStatus("error");
      throw reason;
    }
  }, [client]);

  useEffect(() => {
    void reload().catch(() => undefined);
  }, [reload]);

  const createAlert = useCallback(async (input: PriceAlertCreate) => {
    if (!client) throw new Error("共享价格预警服务未连接");
    const alert = await client.create(input);
    setAlerts((current) => [alert, ...current.filter((item) => item.id !== alert.id)]);
    setStatus("ready");
    return alert;
  }, [client]);

  const updateAlert = useCallback(async (alertId: string, update: PriceAlertUpdate) => {
    if (!client) throw new Error("共享价格预警服务未连接");
    const alert = await client.update(alertId, update);
    setAlerts((current) => current.map((item) => item.id === alert.id ? alert : item));
    setStatus("ready");
    return alert;
  }, [client]);

  const deleteAlert = useCallback(async (alertId: string) => {
    if (!client) throw new Error("共享价格预警服务未连接");
    await client.delete(alertId);
    setAlerts((current) => current.filter((item) => item.id !== alertId));
    setStatus("ready");
  }, [client]);

  return { alerts, status, reload, createAlert, updateAlert, deleteAlert };
}
