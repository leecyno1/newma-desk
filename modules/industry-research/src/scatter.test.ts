import { describe, expect, it } from "vitest";
import { industryLabel, scatterLayout } from "./scatter";
import type { Industry } from "./research";

describe("散点直接标签", () => {
  it("简称不混淆采矿与冶炼，不把电子大类叫半导体", () => {
    expect(industryLabel("有色金属矿采选业")).toBe("有色采矿");
    expect(industryLabel("有色金属冶炼和压延加工业")).toBe("有色冶炼");
    expect(industryLabel("计算机、通信和其他电子设备制造业")).toBe("计算机通信电子");
    expect(industryLabel("未知行业")).toBe("未知行业");
  });
  it.each([640, 1000, 1200])("%i宽度下密集同坐标标签互不重叠，且不挪动真实点", width => {
    const rows = Array.from({length: 41}, (_, i) => ({name: `行业${i}`, revenueYoy: 0, profitYoy: 0}) as Industry);
    const chart = scatterLayout(rows, width, width < 800 ? 680 : 520);
    expect(chart.points).toHaveLength(41);
    for (const [i, point] of chart.points.entries()) {
      expect(point.x).toBe(chart.centerX);
      expect(point.y).toBe(chart.centerY);
      expect(point.labelBox).not.toBeNull();
      const a = point.labelBox!;
      expect(a.x).toBeGreaterThanOrEqual(chart.bounds.left);
      expect(a.x + a.width).toBeLessThanOrEqual(chart.bounds.right);
      for (const other of chart.points.slice(i + 1)) {
        const b = other.labelBox!;
        expect(a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y).toBe(false);
      }
    }
  });
  it("过滤缺失坐标，不把缺失显示成零；空结果正常", () => {
    expect(scatterLayout([{name: "缺失", revenueYoy: 1, profitYoy: null} as Industry], 640, 680).points).toEqual([]);
    expect(scatterLayout([], 640, 680).points).toEqual([]);
  });
  it("分类筛选沿用同一搜索范围的坐标轴，点位置不跳变", () => {
    const a = {name: "双增", revenueYoy: 12, profitYoy: 15} as Industry;
    const b = {name: "大幅双降", revenueYoy: -90, profitYoy: -200} as Industry;
    const scope = [a, b];
    const full = scatterLayout(scope, 1000, 520);
    const filtered = scatterLayout([a], 1000, 520, scope);
    expect(filtered.extentX).toBe(full.extentX);
    expect(filtered.extentY).toBe(full.extentY);
    const original = full.points.find(point => point.row.name === a.name)!;
    expect(filtered.points[0]).toMatchObject({x: original.x, y: original.y});
  });
});
