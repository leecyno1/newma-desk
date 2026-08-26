import fs from "node:fs";
import path from "node:path";

const frontendRoot = path.resolve(__dirname, "../../../..");

function read(relativePath: string): string {
  return fs.readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

describe("chart code splitting", () => {
  it("keeps chart series out of the shared ECharts runtime", () => {
    const runtime = read("src/lib/echarts.ts");

    expect(runtime).not.toContain('from "echarts/charts"');
    expect(runtime).not.toContain('from "echarts/components"');
    expect(runtime).toContain('from "echarts/renderers"');
  });

  it("does not force ECharts into one manual vendor chunk", () => {
    const config = read("vite.config.ts");

    expect(config).not.toContain('"vendor-charts"');
    expect(config).toContain('"echarts-core": ["echarts/core"]');
  });

  it("keeps chart-capable pages behind lazy routes", () => {
    const router = read("src/router.tsx");

    for (const page of ["RunDetail", "Compare", "Correlation", "AlphaZoo"]) {
      expect(router).toContain(`import("@/pages/${page}")`);
    }
  });

  it.each([
    ["src/pages/Correlation.tsx", "@/components/charts/CorrelationMatrix"],
    ["src/pages/Compare.tsx", "@/components/charts/EquityChartOverlay"],
    ["src/pages/RunDetail.tsx", "@/components/charts/CandlestickChart"],
    ["src/pages/RunDetail.tsx", "@/components/charts/EquityChart"],
    ["src/pages/AlphaZoo.tsx", "@/components/charts/AlphaThemeChart"],
    ["src/components/chat/RunCompleteCard.tsx", "@/components/charts/MiniEquityChart"],
  ])("lazy-loads %s chart dependency %s", (consumerPath, chartModule) => {
    const consumer = read(consumerPath);

    expect(consumer).toContain("lazy(");
    expect(consumer).toContain(`import("${chartModule}")`);
  });
});
