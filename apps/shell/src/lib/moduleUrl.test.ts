import { describe, expect, it } from "vitest";

import { resolveModuleUrl } from "./moduleUrl";

describe("resolveModuleUrl", () => {
  it("normalizes a local origin and preserves the entry trailing slash", () => {
    expect(
      resolveModuleUrl(
        { type: "static", url: "/modules/market-daily/" },
        "http://127.0.0.1:5891///",
        "http://localhost:5173",
      ),
    ).toBe("http://127.0.0.1:5891/modules/market-daily/");
  });

  it("returns an external HTTP URL unchanged", () => {
    expect(
      resolveModuleUrl(
        { type: "external", url: "https://example.com/app/?a=1" },
        "http://127.0.0.1:5891",
        "http://localhost:5173",
      ),
    ).toBe("https://example.com/app/?a=1");
  });

  it("rejects a same-origin local module server", () => {
    expect(() =>
      resolveModuleUrl(
        { type: "structured", url: "/modules/market-daily/" },
        "http://localhost:5173/path",
        "http://localhost:5173",
      ),
    ).toThrow("模块服务必须使用与 Web Shell 不同的 origin");
  });
});
