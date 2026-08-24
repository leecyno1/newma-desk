import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArtifactPreviewModal } from "./ArtifactPreviewModal";

afterEach(() => {
  cleanup();
});

describe("ArtifactPreviewModal", () => {
  it("renders Markdown products as readable content and keeps source collapsed", async () => {
    const fetchPreview = vi.fn(async () => ({
      path: "/tmp/research.md",
      exists: true,
      mime: "text/markdown",
      encoding: "text",
      suffix: ".md",
      size: 180,
      content: [
        "# 研究报告",
        "",
        "**核心判断**：AI 资本开支正在改变融资方式。",
        "",
        "> 这是需要用户审核的结论。",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        "| 配售规模 | 800 亿港元 |",
        "",
        "[查看来源](https://example.com)",
        "",
        "<script>window.__unsafe = true</script>",
      ].join("\n"),
    }));

    render(
      <ArtifactPreviewModal
        path="/tmp/research.md"
        label="研究报告"
        onClose={vi.fn()}
        fetchPreview={fetchPreview}
      />,
    );

    expect(await screen.findByRole("heading", { name: "研究报告" })).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("这是需要用户审核的结论。")).toBeTruthy();
    expect(screen.getByText("查看原始 Markdown")).toBeTruthy();
    expect(screen.getByRole("link", { name: "查看来源" }).getAttribute("target")).toBe("_blank");
    expect(document.querySelector("script")).toBeNull();
  });
});
