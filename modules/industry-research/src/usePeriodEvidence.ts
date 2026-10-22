import { useEffect, useState } from "react";

export function usePeriodEvidence<T extends {periodEnd: string}>(kind: "production" | "prices" | "capacity", periodEnd?: string, sourceKey?: string) {
  const [request, setRequest] = useState(0);
  const [result, setResult] = useState<{key: string; data: T | null; status: string; error: string}>({key: "", data: null, status: "idle", error: ""});
  const key = `${kind}|${periodEnd ?? ""}|${sourceKey ?? ""}`;
  const label = {production: "生产", prices: "价格", capacity: "产能"}[kind];
  useEffect(() => {
    if (!request || !periodEnd) return;
    const controller = new AbortController();
    setResult({key, data: null, status: "loading", error: ""});
    void fetch(`/api/industry-research/${kind}?period=${periodEnd.slice(0, 7)}${request > 1 ? "&refresh=true" : ""}`, {signal: controller.signal})
      .then(async response => {const body = await response.json(); if (!response.ok) throw new Error(body.detail || `${label}证据读取失败`); return body as T;})
      .then(data => {if (!controller.signal.aborted) {
        if (data.periodEnd !== periodEnd) throw new Error(`${label}报告期不一致，未使用其他期间证据`);
        setResult({key, data, status: "ready", error: ""});
      }})
      .catch(reason => {if (!controller.signal.aborted) setResult({key, data: null, status: "failed", error: reason instanceof Error ? reason.message : `${label}证据读取失败`});});
    return () => controller.abort();
  }, [request, periodEnd, key, kind, label]);
  // Clear evidence synchronously on a period change, before the new effect runs.
  const visible = periodEnd && result.key === key ? result : {data: null, status: request && periodEnd ? "loading" : "idle", error: ""};
  function load() {setResult({key, data: null, status: "loading", error: ""}); setRequest(value => value + 1);}
  return {...visible, load};
}
