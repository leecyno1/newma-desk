import { describe, expect, it } from "vitest";

import { sidebarGroupTone, sidebarGroupTones } from "./sidebarGroupTheme";

describe("sidebarGroupTone", () => {
  it("uses fixed semantic tones for built-in Mod groups", () => {
    expect(sidebarGroupTone("今日")).toBe("orange");
    expect(sidebarGroupTone("市场")).toBe("blue");
    expect(sidebarGroupTone("研究")).toBe("violet");
    expect(sidebarGroupTone("量化")).toBe("cyan");
    expect(sidebarGroupTone("交易")).toBe("red");
    expect(sidebarGroupTone("Deepsee")).toBe("green");
    expect(sidebarGroupTone("连接与设置")).toBe("slate");
  });

  it("assigns a stable palette tone to user-defined groups", () => {
    const firstTone = sidebarGroupTone("我的关注");

    expect(sidebarGroupTones).toContain(firstTone);
    expect(sidebarGroupTone(" 我的关注 ")).toBe(firstTone);
    expect(sidebarGroupTone("我的策略")).not.toBe(firstTone);
  });
});
