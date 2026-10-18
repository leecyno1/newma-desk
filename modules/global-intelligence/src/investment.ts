import type { GlobalIntelEvent, GlobalIntelMarketReaction, GlobalIntelRoute, GlobalIntelRouteImpact } from "./data";

/** Research associations, not portfolio exposure or a buy/sell recommendation. */
export function buildInvestmentTransmission(
  event: GlobalIntelEvent | undefined,
  routes: GlobalIntelRoute[],
  impacts: GlobalIntelRouteImpact[],
  reactions: GlobalIntelMarketReaction[],
  now = Date.now(),
) {
  if (!event) return null;
  const sourceTime = Date.parse(event.timestamp);
  const evidenceGate = event.sourceFreshness === "stale" ? "旧证据 · 当前有效性待核验"
    : sourceTime > now ? "未来日期 · 不能视为已发生"
    : event.sourceFreshness !== "fresh" || !Number.isFinite(sourceTime) ? "时间或新鲜度未知 · 待核验"
    : "来源可用 · 因果关系仍待验证";
  const pathways = impacts.filter((impact) => impact.eventId === event.id).flatMap((impact) => {
    const route = routes.find((item) => item.id === impact.routeId);
    if (!route) return [];
    return [{
      routeId: route.id, route: route.name,
      association: impact.relation === "mentioned" ? "文本提及" : impact.relation === "nearby" ? "地理邻近" : "规则匹配",
      reasons: impact.reasons,
      commodities: route.exposure?.commodities ?? [],
      industries: route.exposure?.industries ?? [],
      validationIndicators: route.exposure?.marketSignals ?? [],
      observations: reactions.filter((reaction) => reaction.routeId === route.id),
      hypothesis: route.kind === "pipeline" ? "若供应实际受限，可能影响能源供给、价差及下游成本。"
        : route.kind === "shipping" ? "若运力或航道实际受限，可能影响运费、交付周期及库存成本。"
        : route.kind === "cable" ? "若通信设施确有故障，可能影响跨境网络服务及运营成本。"
        : "若航线运营实际受限，可能影响航空运力、客货收益及替代运输。",
      invalidation: "若运营方确认正常、公告只是施工或演练，或关联位置不在实际通道，须撤销中断假设；单次价格波动不能证明因果关系。",
    }];
  });
  return {
    eventId: event.id, title: event.title, evidenceGate,
    source: event.source, sourceTime: event.timestamp, collectedAt: event.collectedAt ?? null,
    semantics: "基于现有通道规则的研究假设；不代表通道已中断、真实持仓暴露或交易建议。市场观测是相关性线索，不是因果确认。",
    pathways,
    gaps: pathways.length ? ["尚未匹配用户持仓及对冲头寸", "需要运营状态和独立来源验证"]
      : ["当前没有匹配的通道证据，不能据此推导资产影响", "请先核验原始事件及具体受影响对象"],
  };
}
