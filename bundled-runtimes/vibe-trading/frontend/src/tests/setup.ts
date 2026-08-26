import "@testing-library/jest-dom/vitest";

// ── Global mocks for jsdom ───────────────────────────────────

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, String(value));
  }
}

// Node 25 exposes an incomplete global localStorage unless
// --localstorage-file is configured. Pin tests to a deterministic jsdom-safe
// implementation before i18n or application modules read language/auth state.
const testLocalStorage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: testLocalStorage,
});
if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: testLocalStorage,
  });
}

// Initialize i18n after storage is ready so `useTranslation()` resolves real
// strings and defaults to English when no preference is stored.
await import("../i18n");

// jsdom doesn't implement ResizeObserver (ECharts + layout components need it)
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// jsdom doesn't implement matchMedia
if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
