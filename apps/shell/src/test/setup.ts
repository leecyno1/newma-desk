import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

const storage = new Map<string, string>();
const storageApi = {
  clear: () => storage.clear(),
  getItem: (key: string) => storage.get(key) ?? null,
  key: (index: number) => [...storage.keys()][index] ?? null,
  get length() {
    return storage.size;
  },
  removeItem: (key: string) => storage.delete(key),
  setItem: (key: string, value: string) => storage.set(key, String(value)),
} satisfies Storage;

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: storageApi,
});
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: storageApi,
});

const { server } = await import("./server");

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});
afterAll(() => server.close());
