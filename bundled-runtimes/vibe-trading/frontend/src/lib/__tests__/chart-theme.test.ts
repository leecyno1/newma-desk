import { getChartTheme } from "../chart-theme";

describe("getChartTheme", () => {
  beforeEach(() => {
    const root = document.documentElement;
    root.className = "light";
    root.dataset.theme = "light";
    root.lang = "zh-CN";
    root.removeAttribute("style");
    root.style.setProperty("--success", "142 76% 36%");
    root.style.setProperty("--danger", "0 73% 42%");
    root.style.setProperty("--info", "157 19% 30%");
    root.style.setProperty("--warning", "36 91% 33%");
    root.style.setProperty("--financial-positive", "#dc2626");
    root.style.setProperty("--financial-negative", "#16a34a");
    root.style.setProperty("--chart-series-1", "#a87432");
    root.style.setProperty("--chart-series-2", "#3f7667");
    root.style.setProperty("--chart-series-3", "#8f6b50");
    root.style.setProperty("--chart-correlation-negative-strong", "#315a4a");
    root.style.setProperty("--chart-correlation-neutral", "#f4efe3");
    root.style.setProperty("--chart-correlation-positive-strong", "#9a5d25");
  });

  it("uses Newma series colors while preserving Chinese financial colors", () => {
    const theme = getChartTheme();

    expect(theme.upColor).toBe("#dc2626");
    expect(theme.downColor).toBe("#16a34a");
    expect(theme.seriesColors.slice(0, 3)).toEqual([
      "#a87432",
      "#3f7667",
      "#8f6b50",
    ]);
    expect(theme.correlationColors).toContain("#f4efe3");
    expect(theme.seriesColors.join(" ")).not.toMatch(
      /#(?:2563eb|3b82f6|60a5fa|6366f1|8b5cf6|a855f7)/i,
    );
  });

  it("invalidates the cached palette when the Desk theme changes", () => {
    const light = getChartTheme();
    const root = document.documentElement;
    root.className = "dark";
    root.dataset.theme = "dark";
    root.style.setProperty("--chart-series-1", "#c89a5a");
    root.style.setProperty("--chart-series-2", "#70a596");

    const dark = getChartTheme();

    expect(dark).not.toBe(light);
    expect(dark.seriesColors.slice(0, 2)).toEqual(["#c89a5a", "#70a596"]);
  });

  it("refreshes a customized appearance without requiring a mode change", () => {
    const original = getChartTheme();
    document.documentElement.style.setProperty("--chart-series-1", "#8d5e25");

    const customized = getChartTheme();

    expect(customized).not.toBe(original);
    expect(customized.seriesColors[0]).toBe("#8d5e25");
  });
});
