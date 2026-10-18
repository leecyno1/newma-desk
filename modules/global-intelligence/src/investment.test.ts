import { describe, expect, it } from "vitest";
import { buildInvestmentTransmission } from "./investment";
import { normalizeGlobalIntelEvents, type GlobalIntelEvent, type GlobalIntelRoute, type GlobalIntelRouteImpact } from "./data";

const event: GlobalIntelEvent = { id: "report", title: "Shipping warning", category: "maritime", detail: "Test source warning", severity: "medium", source: "NGA", timestamp: "2026-10-13T00:00:00Z", sourceFreshness: "stale" };
const route: GlobalIntelRoute = { id: "channel", name: "运输通道", kind: "shipping", detail: "示意通道", path: [[0, 0], [10, 10]], exposure: { countries: [], commodities: ["原油"], industries: ["航运"], marketSignals: ["运费"] } };
const impact: GlobalIntelRouteImpact = { routeId: route.id, eventId: event.id, relation: "nearby", reasons: ["邻近"], distanceKm: 30, riskScore: 40, confidence: 0.4, sourceCount: 1, evidenceCount: 1, ageHours: 1 };

describe("investment transmission evidence boundaries", () => {
  it("keeps stale geographic association separate from confirmed disruption and market evidence", () => {
    const research = buildInvestmentTransmission(event, [route], [impact], []);
    expect(research?.evidenceGate).toContain("旧证据");
    expect(research?.pathways[0]).toMatchObject({ association: "地理邻近", commodities: ["原油"], observations: [] });
    expect(research?.pathways[0]?.invalidation).toContain("演练");
    expect(research?.semantics).toContain("不代表通道已中断");
  });
  it("does not invent asset impacts for unmatched events or treat future events as occurred", () => {
    const research = buildInvestmentTransmission({ ...event, sourceFreshness: "fresh", timestamp: "2030-01-01T00:00:00Z" }, [route], [], [], Date.parse("2026-10-14"));
    expect(research?.evidenceGate).toContain("未来日期");
    expect(research?.pathways).toEqual([]);
    expect(research?.gaps[0]).toContain("没有匹配");
    expect(buildInvestmentTransmission(undefined, [], [], [])).toBeNull();
  });
  it("does not turn cable operations warnings or a heuristic score into a high-severity cable outage", () => {
    const events = normalizeGlobalIntelEvents({ cable_health: { timestamp: "2026-10-14T00:00:00Z", corridors: { red_sea: { status_score: 3, status_label: "disrupted", relevant_warnings: [{ text_snippet: "CABLE OPERATIONS IN PROGRESS" }] } } } });
    const cable = events.find((item) => item.title.includes("光缆走廊"));
    expect(cable).toMatchObject({ severity: "medium", timestamp: "", timestampBasis: "unknown", sourceFreshness: "unknown" });
    expect(cable?.title).not.toContain("中断");
    expect(cable?.facts).toContainEqual({ label: "故障状态", value: "未核验；施工或相关警告不能证明中断" });
  });
});
