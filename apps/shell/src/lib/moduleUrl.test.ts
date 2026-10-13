import { describe, expect, it } from "vitest";

import { resolveModUrl } from "./moduleUrl";

describe("resolveModUrl", () => {
  it("does not silently send a remote browser to its own loopback", () => {
    expect(() => resolveModUrl(
      { type: "static", url: "/mods/market-daily/" }, "", "https://desk.example",
    )).toThrow("VITE_MOD_ORIGIN");
    expect(() => resolveModUrl(
      { type: "static", url: "/mods/market-daily/" }, "http://127.0.0.1:5891", "https://desk.example",
    )).toThrow("远程 Mod 不能使用本机地址");
  });

  it("uses the configured separate HTTPS origin in a remote browser", () => {
    expect(resolveModUrl(
      { type: "static", url: "/mods/market-daily/" }, "https://mods.example", "https://desk.example",
    )).toBe("https://mods.example/mods/market-daily/");
  });

  it("keeps the development fallback on the actual local machine", () => {
    expect(resolveModUrl(
      { type: "static", url: "/mods/market-daily/" }, "", "http://localhost:5888",
    )).toBe("http://127.0.0.1:5891/mods/market-daily/");
  });

  it("normalizes a local origin and preserves the entry trailing slash", () => {
    expect(
      resolveModUrl(
        { type: "static", url: "/mods/market-daily/" },
        "http://127.0.0.1:5891///",
        "http://localhost:5173",
      ),
    ).toBe("http://127.0.0.1:5891/mods/market-daily/");
  });

  it("returns an external HTTP URL unchanged", () => {
    expect(
      resolveModUrl(
        { type: "external", url: "https://example.com/app/?a=1" },
        "http://127.0.0.1:5891",
        "http://localhost:5173",
      ),
    ).toBe("https://example.com/app/?a=1");
  });

  it("rejects a same-origin local Mod server", () => {
    expect(() =>
      resolveModUrl(
        { type: "structured", url: "/mods/market-daily/" },
        "http://localhost:5173/path",
        "http://localhost:5173",
      ),
    ).toThrow("Mod 服务必须使用与 Newma-Desk 不同的 origin");
  });

  it("rejects a same-origin external entry", () => {
    expect(() =>
      resolveModUrl(
        { type: "external", url: "http://localhost:5173/embedded" },
        "http://127.0.0.1:5891",
        "http://localhost:5173",
      ),
    ).toThrow("Mod 页面必须使用与 Newma-Desk 不同的 origin");
  });
});
