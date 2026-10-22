import type { GraphArtifactInput } from "@/lib/artifacts";
import { industryTargets, type IndustryEvidence } from "@/lib/industryWorkspace";

export const HBM_GRAPH: GraphArtifactInput = {
  moduleId: "industry-map",
  title: "HBM 技术结构与工艺观察",
  subtitle: "公开技术资料示例 · 结构与候选路线分开，不是企业供货图",
  nodes: [
    { id: "dram-dies", label: "DRAM 裸片", group: "存储芯片", kind: "component", subtitle: "多颗裸片垂直堆叠；不据此推断厂商产量或良率" },
    { id: "interconnect", label: "TSV 与微凸点互连", group: "互连工艺", kind: "component", subtitle: "Micron FAQ 描述的堆叠连接方式，不代表所有代际永久采用同一工艺" },
    { id: "hbm-stack", label: "HBM 堆叠存储", group: "存储集成", kind: "component", subtitle: "带宽、容量与功耗需按代际及具体型号比较" },
    { id: "processor", label: "CPU／GPU", group: "计算芯片", kind: "component", subtitle: "与 HBM 在系统级封装内集成；未指定客户、订单或采购份额" },
    { id: "sip", label: "中介层与系统级封装", group: "封装集成", kind: "infrastructure", subtitle: "此示例采用 Micron FAQ 的硅中介层描述；不等于所有封装路线或某一家封装服务" },
    { id: "workloads", label: "AI／高性能计算需求", group: "应用方向", kind: "market", subtitle: "产品面向的工作负载方向，不代表当期需求增速或收入预测" },
    { id: "hybrid", label: "混合键合（候选路线）", group: "工艺观察", kind: "external", subtitle: "SK hynix 技术文章称 HBM 采用时点仍不确定；不能据此认定全面量产或设备订单兑现" },
  ],
  edges: [
    { source: "dram-dies", target: "hbm-stack", label: "裸片垂直堆叠", kind: "flow" },
    { source: "interconnect", target: "hbm-stack", label: "堆叠裸片互连", kind: "dependency" },
    { source: "hbm-stack", target: "sip", label: "通过中介层集成", kind: "flow" },
    { source: "processor", target: "sip", label: "与 HBM 并置集成", kind: "flow" },
    { source: "hbm-stack", target: "workloads", label: "面向 AI／HPC 工作负载", kind: "flow" },
    { source: "hybrid", target: "hbm-stack", label: "候选工艺，采用时点未定", kind: "risk" },
  ],
  sources: ["Micron · High-bandwidth memory (HBM) · 产品页与 FAQ", "SK hynix Newsroom · Tech Note: Hybrid Bonding · 作者技术观点"],
  sourceText: `资料读取日：2026-10-19（不是全部资料的发布日期，也不是实时更新承诺）。

范围：HBM 的存储堆叠、互连、系统封装与工作负载方向；混合键合单独作为候选路线。不是设备／材料／测试的完整产业链，也不包含企业供应关系。

阅读边界：Micron 产品页未识别发布日期，存在滚动更新和营销表述；SK hynix Newsroom 技术文章是作者观点，不是订单、交付或量产公告。TSMC CoWoS 页面本轮遇到访问验证，未采纳其内容。未将厂商竞争性性能数字或预测当作独立行业统计。

投资研究待办（研究问题，不是事实结论）：
1. 需求兑现：核对客户平台认证、实际出货、单平台 HBM 配置与库存，不能用 AI 热度替代订单。
2. 供给瓶颈：分别跟踪裸片良率、堆叠良率、封装／测试吞吐；不能把技术复杂度直接等同于长期紧缺。
3. 利润传导：检查具体代际的售价、成本、产品组合与资本开支；带宽提高不直接等于利润增长。
4. 工艺切换：跟踪混合键合的可靠性、成本、设备成熟度及客户认证；文章展望不能证明供应商收入兑现。
下一站为产业链证据及公司财报模块；本页不计算目标价或自动推荐证券。`,
  metadata: { sectorKey: "hbm", artifactRole: "base", baseVersion: "2026-10-19.1", evidenceStatus: "source-linked-not-user-reviewed" },
};

const micron = "https://www.micron.com/products/memory/hbm";
const notes = [
  { title: "Micron HBM FAQ · 垂直堆叠", url: micron, publishedAt: "", locator: "What is high-bandwidth memory (HBM)? · 网页提取段落 153（位置可能随更新变化）", excerpt: "HBM stacks multiple DRAM dies vertically atop an optional base die.", note: "支持此结构描述；不证明厂商产量、良率或当前供需缺口。" },
  { title: "Micron HBM FAQ · 堆叠互连", url: micron, publishedAt: "", locator: "What is high-bandwidth memory (HBM)? · 网页提取段落 154", excerpt: "They are interconnected using thousands of through-silicon vias (TSVs) and microbumps", note: "支持 FAQ 描述的互连方式；不能推出所有后续代际都沿用微凸点。" },
  { title: "Micron HBM FAQ · 中介层集成", url: micron, publishedAt: "", locator: "How does HBM differ from traditional DDR5 memory? · 网页提取段落 158", excerpt: "HBM is integrated directly into a system-in-package (SiP) alongside the CPU or GPU via a silicon interposer", note: "支持此封装示意，不证明某家封装厂的供应份额，也不等于所有工艺路线。" },
  { title: "Micron HBM FAQ · 计算与存储并置", url: micron, publishedAt: "", locator: "How does HBM differ from traditional DDR5 memory? · 网页提取段落 158", excerpt: "alongside the CPU or GPU via a silicon interposer", note: "本条与中介层引用来自同一段，不能视为独立交叉证据；未指定客户型号或订单。" },
  { title: "Micron HBM · 工作负载方向", url: micron, publishedAt: "", locator: "Built for AI and high-performance computing · 网页提取段落 142", excerpt: "Micron’s HBM portfolio is designed to deliver the bandwidth, capacity, and power efficiency needed for demanding AI and high-performance computing (HPC) workloads.", note: "是厂商产品定位，不是市场规模、当期出货或盈利预测。" },
  { title: "SK hynix Tech Note · 混合键合采用时点", url: "https://news.skhynix.com/en/tech-note-series-ep2/", publishedAt: "2026-08-25", locator: "Hybrid Bonding Powers AI Advancement — HBM Adoption Still “In Progress” · 网页提取段落 31", excerpt: "The timing of hybrid bonding adoption in HBM remains uncertain due to several practical constraints.", note: "作者技术观点明确保留采用时点不确定性；不能改写为 HBM 已全面量产采用。发布日期取页面可见日期，不以读取日替代。" },
];
const targets = industryTargets(HBM_GRAPH).slice(HBM_GRAPH.nodes.length);
/** Public reading notes, never inherited as a user's completed review. */
export const HBM_REFERENCES: IndustryEvidence[] = notes.map((note, index) => ({
  ...note, id: "hbm-reference-" + (index + 1), target: targets[index].key, judgment: "unclear", nextReview: "", recordedAt: "2026-10-19",
  reviewRequired: { targetLabel: targets[index].label, reason: "预置公开资料引用，尚未由当前工作区用户复核；仅为研究线索。" },
}));
