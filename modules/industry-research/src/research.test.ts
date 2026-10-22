import { describe, expect, it } from "vitest";
import { changeFor, contextFor, fmt, historyFor, migrationFor, publicationsFor, researchQuestions, rowsFor, type History, type Industry, type Snapshot } from "./research";

const row: Industry = {name: "测试煤炭", revenue: 200, revenueYoy: 10, cost: 150, costYoy: 4, profit: 30, profitYoy: 20, profitMargin: 15, costRatio: 75, quadrant: "expansion", raw: {}};
const data = {rows: [row, {...row, name: "测试电子", profitYoy: null, quadrant: "unknown"}], limitations: ["累计不是单月"], periodEnd: "2026-08-31", publishedAt: "2026-09-28", fetchedAt: "2026-10-18T01:00:00Z", freshness: "unknown"} as Snapshot;
describe("行业证据展示", () => {
  it("缺失不显示为零，排序保持缺失在最后", () => {
    expect(fmt(null)).toBe("—"); expect(fmt(0, "%")).toBe("0.0%");
    expect(rowsFor(data, "", "all", "profitYoy").map(r => r.name)).toEqual(["测试煤炭", "测试电子"]);
  });
  it("筛选保留不可比行业，不伪造象限", () => {
    expect(rowsFor(data, "电子", "unknown", "profitYoy")).toHaveLength(1);
    expect(rowsFor(data, "煤炭", "unknown", "profitYoy")).toHaveLength(0);
  });
  it("上下文只携带可见表格、选择与明确对照，不在失败后保留旧证据", () => {
    const context = contextFor(data, [row], row, [row], {query: "煤炭"}, "ready", "");
    expect(context.data.asOf).toBe("2026-08-31");
    expect(context.data.summary?.visibleRows).toEqual([row]);
    expect(context.data.summary?.growthStructure).toMatchObject({scopeCount: 1, plottedCount: 1, counts: {expansion: 1, unknown: 0}});
    const failed = contextFor(null, [], undefined, [], {}, "failed", "源不可用");
    expect(failed.selection).toEqual({}); expect(failed.data.asOf).toBeUndefined();
    expect(failed.data.summary?.publication).toBeNull();
    expect(failed.data.summary?.growthStructure).toBeNull();
    expect(failed.data.summary?.operations).toBeNull();
  });
  it("电子大类明确禁止外推半导体", () => {
    expect(researchQuestions("计算机、通信和其他电子设备制造业").join()).toContain("不能直接外推为半导体");
  });
});

it("经营质量背景沿用所选报告，独立于行业分类，随数据失效清空", () => {
  const operations: NonNullable<Snapshot["operations"]> = {status: "ready", scope: "全国及工业三大门类", rows: [], periodEnd: data.periodEnd, sourceUrl: "test", publishedAt: data.publishedAt, reason: "", boundary: "不能外推细分行业"};
  const snapshot = {...data, operations};
  expect(contextFor(snapshot, [row], row, [], {}, "ready", "").data.summary?.operations).toEqual(operations);
  expect(contextFor(data, [row], row, [], {}, "ready", "").data.summary?.operations).toBeNull();
});

const current = {...data, sourceUrl: "current", rows: [row], taxonomy: "工业", unit: "亿元 / %"};
const prior = {...current, period: "2026年1—7月", periodEnd: "2026-07-31", publishedAt: "2026-08-27", sourceUrl: "prior", rows: [{...row, revenueYoy: 0, profitYoy: 12}]};
describe("全行业累计同比变化", () => {
  it("区分增长水平与改善方向，零边界有效，缺失不当持平或退出双增", () => {
    const rows: Industry[] = [
      {...row, name: "进入", revenueYoy: 2, profitYoy: 3},
      {...row, name: "退出", revenueYoy: -1, profitYoy: -2, quadrant: "contraction"},
      {...row, name: "分化", revenueYoy: 3, profitYoy: 0, quadrant: "boundary"},
      {...row, name: "持平", revenueYoy: 1, profitYoy: 1},
      {...row, name: "缺失", revenueYoy: 1, profitYoy: null, quadrant: "unknown"},
      {...row, name: "仍负增长", revenueYoy: -2, profitYoy: -1, quadrant: "contraction"},
    ];
    const base = {...prior, rows: rows.map(r => ({...r, revenueYoy: r.name === "进入" ? 0 : r.name === "仍负增长" ? -3 : 1,
      profitYoy: r.name === "仍负增长" ? -2 : 1}))};
    const report = {...current, rows};
    const result = migrationFor(report, [report, base], rows);
    expect(result).toMatchObject({scopeCount: 6, comparableCount: 5, entered: 1, exited: 2,
      counts: {improving: 2, weakening: 1, mixed: 1, flat: 1, unknown: 1}, previous: {sourceUrl: "prior"}});
    expect(result.rows.find(r => r.name === "缺失")).toMatchObject({revenueYoyPp: 0, profitYoyPp: null, direction: "unknown", transition: "无法完整比较"});
    expect(result.rows.find(r => r.name === "仍负增长")).toMatchObject({direction: "improving", currentState: "contraction", transition: "未跨越双增边界"});
  });
  it("缺期、修订歧义和分类变更不形成广度结论", () => {
    for (const publications of [[current], [current, prior, {...prior, sourceUrl: "duplicate"}], [current, {...prior, taxonomy: "其他"}]]) {
      expect(migrationFor(current, publications, current.rows)).toMatchObject({comparableCount: 0, entered: 0, exited: 0, previous: null, counts: {unknown: 1}});
    }
    expect(migrationFor(current, [current, prior], [])).toMatchObject({scopeCount: 0, comparableCount: 0, rows: []});
  });
  it("Agent沿用搜索范围，不受象限过滤影响，刷新失败后撤下", () => {
    const history = {publications: [current, prior], errors: [], scope: "测试"} as unknown as History;
    const context = contextFor(current, [], undefined, [], {quadrant: "contraction"}, "ready", "", history, "ready", "", history.publications);
    expect(context.data.summary?.migration).toEqual(migrationFor(current, history.publications, current.rows));
    expect(contextFor(current, [], undefined, [], {query: "不存在"}, "ready", "", history, "ready", "", history.publications).data.summary?.migration).toMatchObject({scopeCount: 0});
    expect(contextFor(current, [], undefined, [], {}, "ready", "", null, "failed", "读取失败", [current]).data.summary?.migration).toBeNull();
    expect(contextFor(null, [], undefined, [], {}, "loading", "", history, "ready", "", history.publications).data.summary?.migration).toBeNull();
  });
});
describe("累计同比历史比较", () => {
  it("相邻累计期按百分点计算，零值有效且不同于单月增速", () => {
    expect(changeFor(current, [current, prior], row.name)).toMatchObject({revenueYoyPp: 10, profitYoyPp: 8, previousSourceUrl: "prior"});
    expect(historyFor([current, prior], row.name)[1]!.change.profitYoyPp).toBeNull();
  });
  it("缺月、跨年、分类差异、同一期多版本以及后发修订均不强行比较", () => {
    for (const other of [
      {...prior, periodEnd: "2026-06-30"}, {...prior, periodEnd: "2025-07-31"},
      {...prior, taxonomy: "申万"}, {...prior, unit: "万元"}, {...prior, publishedAt: "2026-10-01"},
    ]) expect(changeFor(current, [current, other], row.name).profitYoyPp).toBeNull();
    expect(changeFor(current, [current, prior, {...prior, sourceUrl: "revision"}], row.name).reason).toContain("多份发布");
    expect(changeFor(current, [current, {...current, sourceUrl: "revision"}, prior], row.name).revenueYoyPp).toBeNull();
  });
  it("缺失、不匹配和不可比不补零，仍保留可比指标", () => {
    expect(changeFor(current, [current, {...prior, rows: []}], row.name).revenueYoyPp).toBeNull();
    expect(changeFor(current, [current, {...prior, rows: [{...row, revenueYoy: null}]}], row.name)).toMatchObject({revenueYoyPp: null, profitYoyPp: 0});
    expect(historyFor([prior], "不存在")[0]!.profitYoy).toBeNull();
  });
  it("同URL按采集时间去重，不将历史发布称为原始时点快照", () => {
    const history = {publications: [{...current, fetchedAt: "2026-10-18T02:00:00Z"}, prior], errors: [], scope: "现时读取"} as unknown as History;
    const publications = publicationsFor(current, history);
    expect(publications).toHaveLength(2);
    expect(publications[0]!.fetchedAt).toBe("2026-10-18T02:00:00Z");
    const ctx = contextFor(prior, [row], row, [], {}, "ready", "", history, "ready", "", publications);
    expect(ctx.data.asOf).toBe("2026-07-31");
    expect(ctx.data.summary?.history).toMatchObject({points: expect.any(Array)});
    const failed = contextFor(null, [], undefined, [], {}, "failed", "源不可用", history, "ready", "", publications);
    expect(failed.data.summary?.history).toMatchObject({points: [], currentChange: null});
    const historyFailed = contextFor(current, [row], row, [], {}, "ready", "", null, "failed", "历史不可用", [current]);
    expect(historyFailed.data.summary?.history).toMatchObject({points: [], currentChange: null, status: "failed"});
  });
});
