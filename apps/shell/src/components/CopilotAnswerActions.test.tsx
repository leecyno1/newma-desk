import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CopilotAnswerActions } from "./CopilotAnswerActions";

describe("CopilotAnswerActions", () => {
  const content = "## 财报分析\n\n| 收入 | 原值 |\n| --- | --- |\n| 收入 | 170,899,152,276.34元 |\n\n[来源](https://example.com/report.pdf#page=9)";

  it("copies the entire original Markdown", async () => {
    const user = userEvent.setup();
    render(<CopilotAnswerActions content={content} filename="earnings-answer" />);
    await user.click(screen.getByRole("button", { name: "复制全文" }));
    expect(await navigator.clipboard.readText()).toBe(content);
    expect(screen.getByRole("status")).toHaveTextContent("已复制全文");
  });

  it("offers selectable full text when clipboard permission is denied and allows retry", async () => {
    const user = userEvent.setup();
    const write = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"));
    render(<CopilotAnswerActions content={content} filename="earnings-answer" />);
    await user.click(screen.getByRole("button", { name: "复制全文" }));
    expect(screen.getByRole("status")).toHaveTextContent("浏览器未允许自动复制");
    const source = screen.getByRole("textbox", { name: "手动复制完整回答" }) as HTMLTextAreaElement;
    expect(source).toHaveValue(content);
    await user.click(source);
    expect(source.selectionStart).toBe(0);
    expect(source.selectionEnd).toBe(content.length);
    await user.click(screen.getByRole("button", { name: "复制全文" }));
    expect(await navigator.clipboard.readText()).toBe(content);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    write.mockRestore();
  });

  it("does not offer empty answer downloads", () => {
    render(<CopilotAnswerActions content=" " filename="earnings-answer" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
