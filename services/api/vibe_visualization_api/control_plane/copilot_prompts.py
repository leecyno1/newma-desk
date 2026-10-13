from typing import Any


Lens = dict[str, str]


SPECIALIZED_PROFILES_BY_ID = {
    "catalyst-calendar": "catalyst-calendar",
    "macro-monitor": "macro-monitor",
    "seven-cycle-research": "cycle-research",
    "thesis-tracker": "thesis-tracker",
    "earnings-workbench": "earnings-workbench",
    "peer-comparison": "peer-comparison",
    "valuation-workbench": "valuation-workbench",
    "research-memo": "research-memo",
    "idea-funnel": "idea-funnel",
    "news-radar": "news",
    "fed-rates": "macro",
}

SPECIALIZED_PROFILES_BY_NAME = {
    "催化剂日历": "catalyst-calendar",
    "宏观观察": "macro-monitor",
    "周期叠加": "cycle-research",
    "投资逻辑": "thesis-tracker",
    "财报研究": "earnings-workbench",
    "同业比较": "peer-comparison",
    "预测与估值": "valuation-workbench",
    "研究备忘录": "research-memo",
    "研究机会池": "idea-funnel",
    "新闻与舆情": "news",
    "联储加息": "macro",
}

PROJECT_PROFILES = {
    "global-intelligence": "global",
    "fundamentals": "macro",
    "policy-intelligence": "policy",
    "capital-flow": "capital",
    "market-surface": "market",
    "industry-research": "research",
    "equity-research": "research",
    "fund-research": "fund",
    "professional-fund-research": "fund",
    "asset-allocation": "portfolio",
    "quant-research": "quant",
    "trading": "trading",
    "risk-management": "risk",
    "strategy-research": "strategy",
    "investment-committee": "decision",
    "creator-studio": "creator",
    "deepsee": "deepsee",
    "workflow-center": "workflow",
    "workflow-center-suite": "workflow",
}

GROUP_PROFILES = {
    "全球": "global",
    "宏观": "macro",
    "政策": "policy",
    "资金": "capital",
    "市场": "market",
    "行业": "research",
    "公司": "research",
    "基金": "fund",
    "配置": "portfolio",
    "量化": "quant",
    "交易": "trading",
    "投决": "decision",
    "策略": "strategy",
    "风险": "risk",
    "创作": "creator",
    "深瞳": "deepsee",
    "工作流": "workflow",
}

CATEGORY_PROFILES = {
    "event": "global",
    "research": "research",
    "market": "market",
    "quant": "quant",
    "trading": "trading",
    "decision": "decision",
    "creator": "creator",
    "deepsee": "deepsee",
    "workflow": "workflow",
    "system": "settings",
}


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return str(value or "").strip()


def _copilot_profile(manifest: dict[str, Any]) -> str:
    navigation = _mapping(manifest.get("navigation"))
    project = _mapping(navigation.get("project"))
    if navigation.get("role") == "settings":
        return "settings"

    module_id = _text(manifest.get("id")).lower()
    name = _text(manifest.get("name"))
    specialized = SPECIALIZED_PROFILES_BY_ID.get(module_id)
    if specialized:
        return specialized
    specialized = SPECIALIZED_PROFILES_BY_NAME.get(name)
    if specialized:
        return specialized

    project_profile = PROJECT_PROFILES.get(_text(project.get("id")).lower())
    if project_profile:
        return project_profile
    group_profile = GROUP_PROFILES.get(_text(navigation.get("groupLabel")))
    if group_profile:
        return group_profile

    for prefix, profile in (
        ("policy-", "policy"),
        ("capital-", "capital"),
        ("fund-", "fund"),
        ("workflow-", "workflow"),
        ("creator-", "creator"),
        ("deepsee-", "deepsee"),
        ("orchestra-", "decision"),
    ):
        if module_id.startswith(prefix):
            return profile

    return CATEGORY_PROFILES.get(
        _text(manifest.get("category")).lower(),
        "general",
    )


DOMAIN_LENSES: dict[str, Lens] = {
    "idea-funnel": {
        "evidence": "核验筛选条件、证券身份、报告期、市场与同业口径；区分量化信号、主题判断、催化剂、反方证据和研究推断，并保留来源与截至日期。",
        "risk": "重点检查样本偏差、筛选条件过拟合、拥挤交易、陈旧数据、把相关性当因果、只记录支持证据、没有可观察催化剂或证伪条件的问题。",
        "extension": "补充更长周期财务、估值、同业、产业链、公司公告、新闻舆情、所有权与拥挤度、催化剂和反方证据，说明它们如何改变候选优先级。",
        "validation": "至少覆盖搜索条件、来源、双向假设、支持与挑战信号、研究优先级评分、催化剂、风险、证伪条件、研究任务、交接目标，以及流程总览中的到期复核、陈旧来源和档案缺口。",
    },
    "research-memo": {
        "evidence": "逐条区分已报告事实、管理层指引、市场一致预期和研究推断；核验每个关联档案 ID、来源、截至日期、新鲜度与冲突证据，不要把底层档案复制成无来源摘要。",
        "risk": "重点检查结论先行但证据不足、引用档案陈旧或缺失、三情景概率失真、估值输出被误当确定性结论、反方证据缺失，以及逻辑断点不可观察的问题。",
        "extension": "按需补充投资逻辑、财报、同业、估值、催化剂、产业链、宏观和新闻证据，并说明新增信息增强、削弱还是不改变哪一项判断。",
        "validation": "至少覆盖研究边界、执行结论、关联档案、关键驱动、三情景、差异认知、催化剂、反方风险、逻辑断点、监控指标、来源缺口和版本变化。",
    },
    "valuation-workbench": {
        "evidence": "将历史事实、管理层指引、研究假设和模型计算分开；核验收入基期、EBIT、折旧摊销、资本开支、营运资本、债务、现金、稀释股数及每项来源和截至日期。",
        "risk": "重点检查单位与币种错位、WACC 资本结构、终值增长高于折现率、终值占比过高、情景层级反常、负利润或周期高点外推，以及把模型输出误当确定性结论的风险。",
        "extension": "补充更长周期三表数据、财报与附注、管理层指引、同业经营和估值区间、无风险利率、Beta、债务成本及行业稳态假设。",
        "validation": "至少覆盖历史基期来源、三情景驱动、WACC 组成、UFCF 计算、EV 到股权价值桥接、终值占比、5×5 敏感性中心格、情景层级和缺失输入。",
    },
    "peer-comparison": {
        "evidence": "先审计业务模式、地区、客户、产品结构、财年、币种和指标定义是否真正可比；所有公司数字必须保留来源、报告期、单位和覆盖缺口。",
        "risk": "重点识别混入非纯业务公司、财年错位、会计口径差异、并购或一次性项目、负利润导致倍数失真，以及把相关性误当因果的风险。",
        "extension": "补充行业特定经营指标、竞争定位、护城河、市场份额、战略变化和能解释估值溢价或折价的证据。",
        "validation": "至少覆盖同业选择理由与例外、统一期间和币种、5–10 个关键指标、缺失值、最大/75分位/中位/25分位/最小统计、来源、口径和数据缺口。",
    },
    "earnings-workbench": {
        "evidence": "先核验最新报告期、披露日期、原始财报和管理层材料，再比较实际、内部预期和一致预期；所有关键数字必须保留来源与截至日期。",
        "risk": "重点检查一次性项目、会计口径、基数、季节性、并购与汇率影响，以及指引是否发生维持、上调、下调、撤回或口径变化。",
        "extension": "补充更长周期财务、公司特定经营指标、公告、电话会、研报与新闻，并说明新增证据如何改变预测假设和投资逻辑支柱。",
        "validation": "至少覆盖报告期核验、实际与预期差、差异驱动、利润率和经营指标、当前与上次指引、预测修订、Thesis 影响、来源、新鲜度和数据缺口。",
    },
    "thesis-tracker": {
        "evidence": "逐项核验核心论点、支柱、反方证据、来源、截至日期、新鲜度、可信度和信息缺口；不得只统计支持性证据。",
        "risk": "重点检查论点是否可证伪、证伪条件是否可观察、风险是否已经触发，以及确信度变化是否有新增证据支持。",
        "extension": "补充更长时间区间的行情与财务、公司公告、新闻、宏观与产业链证据，并明确新增信息增强、削弱还是不改变哪个支柱。",
        "validation": "至少覆盖 3–5 个支柱与风险、证据引用、催化剂关联、更新日志、下次复盘日期、证伪状态和 Desk Storage 持久化。",
    },
    "catalyst-calendar": {
        "evidence": "按重要性、紧迫度和证据质量排序，区分已确认日期事件与不确定观察窗；核验原始来源、日期变更、更新时间和覆盖缺口。",
        "risk": "逐项对照原始假设、确认条件、失效条件与实际结果；将过期来源、日期漂移、事件取消和观察窗未兑现列为风险。",
        "extension": "补充财报预期与历史财务、公司公告、新闻舆情、行业事件和相关宏观背景，但不得把周期概率解释成精确转折日期。",
        "validation": "至少覆盖确定日期与观察窗分类、来源和证据编号、日期变更、新鲜度、确认/失效状态、结果归档与公司/行业/宏观覆盖缺口。",
    },
    "macro-monitor": {
        "evidence": "核验指标发布机构、统计口径、发布日期、修订值、新鲜度和聚合源与原始源的差异；不要把陈旧数据当成当前状态。",
        "risk": "重点检查增长、价格和流动性信号是否分化，识别数据修订、预期差、事件聚集与跨地区传导失效风险。",
        "extension": "补充官方原始数据、利率与汇率、就业、信用、贸易、商品和政策背景，并解释其向行业和资产的传导路径。",
        "validation": "至少覆盖指标值与前值、发布时间、新鲜度、证据编号、经济事件时区、来源降级、修订风险和缺失地区或指标。",
    },
    "cycle-research": {
        "evidence": "先核验当前视图、时间范围、历史或预测图层、聚焦轨道、坐标轴、归一化和校准状态，再区分页面字段、图形读取与研究推断。",
        "risk": "重点检查不同周期信号背离、样本窗口敏感、视觉误读、预测区间被当成确定路径、数据校准失效和跨资产映射过度。",
        "extension": "补充各周期轨道的原始指标、校准方法、历史相似阶段、跨资产表现和能够确认或证伪拐点判断的后续数据。",
        "validation": "至少覆盖 2D/3D 状态、时间范围、历史/预测图层、聚焦轨道、图形快照、数据源、校准结果、切换操作和空数据降级。",
    },
    "fund": {
        "evidence": "先核验基金代码、名称、类型、币种、净值日期、业绩区间、比较基准、分红复权、持仓报告期和数据来源；区分基金披露事实、穿透计算和研究推断。",
        "risk": "重点检查净值或持仓滞后、基准错配、幸存者偏差、风格漂移、集中度、流动性、回撤、申赎冲击、费用以及把短期排名外推为长期能力的问题。",
        "extension": "补充基金经理与任职区间、规模和份额变化、费用、持仓穿透、行业与因子暴露、业绩归因、同类基金和基准对照；不要套用产业链公司分析模板。",
        "validation": "至少覆盖基金身份、净值与持仓日期、复权和基准口径、区间收益、回撤、风险调整收益、规模份额、费用、来源和空数据状态。",
    },
    "workflow": {
        "evidence": "核验工作流版本、节点、连线、过程参数、输入输出、负责人、授权范围、运行状态、上下文和交付物；箭头必须作为可配置过程读取，不能只看节点标题。",
        "risk": "重点检查断链、环路、孤立节点、参数未映射、权限越界、多人覆盖冲突、重复执行、重试不幂等、上下文分叉、交付物丢失和审计链不完整。",
        "extension": "补充模板复用、版本差异、审批门、SLA、失败恢复、人工接管、跨 Agent 授权、共同上下文合并、交付物归档和可观测性。",
        "validation": "至少覆盖节点增删改、连线和过程参数、保存重载、版本、授权、并发编辑、运行恢复、交付物持久化、审计记录和失败状态。",
    },
    "policy": {
        "evidence": "优先核验原始政策文件、发布机构、文号、发布日期、生效日期、适用对象、关键条款和官方附件；区分原文、执行细则、历史类比和 AI 解读。",
        "risk": "重点检查文件真伪、版本替换、适用范围误读、地方与中央口径差异、执行细则缺失、时点错配和把政策目标直接等同于实际效果。",
        "extension": "补充官方答记者问、配套细则、历史政策、执行数据、受影响主体和传导路径，并标明仍待确认的实施条件。",
        "validation": "至少覆盖原文可访问性、文号与机构、发布日期和生效日、条款引用、版本、影响对象、AI 分析失败降级和来源追溯。",
    },
    "creator": {
        "evidence": "核验创作简报、输入素材、素材权利、目标平台、受众、阶段、版本、生成参数、人工修改和最终交付物；不要把占位素材当成已完成作品。",
        "risk": "重点检查事实错误、来源缺失、版权和肖像权、品牌偏差、平台规格不符、版本覆盖、生成失败、发布误操作和交付物不可复现。",
        "extension": "补充素材清单、分镜、文案版本、品牌规范、平台适配、审核意见、发布计划、效果数据和复用模板。",
        "validation": "至少覆盖素材导入、阶段流转、版本保存、预览导出、规格、字幕与音画、权限、审核、失败恢复和交付物归档。",
    },
    "decision": {
        "evidence": "核验议题、对象、参会角色、证据包、正反观点、假设、表决、决议、负责人、截止时间和版本；区分讨论意见与最终决策。",
        "risk": "重点检查证据缺口、角色缺席、观点重复、共识偏差、利益冲突、未解决异议、决议不可执行、责任人缺失和会后审计断点。",
        "extension": "补充反方席位、风险复核、情景分析、待办、条件触发、复盘日期、决议变更和关联研究交接。",
        "validation": "至少覆盖议程、证据引用、角色权限、发言与表决、决议生成、待办交接、版本、审计和复盘闭环。",
    },
    "capital": {
        "evidence": "先区分真实成交、持仓、申赎、融资融券、龙虎榜、估算主力资金和模型信号；核验标的、市场、日期、频率、币种、单位、来源和覆盖范围。",
        "risk": "重点检查把估算流量当真实资金、数据空窗、跨市场时区错位、重复计数、敞口穿透不足、集中度、流动性、杠杆、回撤和权限越界。",
        "extension": "补充资金来源说明、组合穿透、行业与因子暴露、压力测试、限额、预警、处置流程、交易流水和数据缺口。",
        "validation": "至少覆盖标的输入、数据源与真实性标记、日期频率、空数据、刷新、组合敞口、限额预警、处置闭环和审计记录。",
    },
    "news": {
        "evidence": "核验每条新闻的真实标题、原始来源、发布时间、语言、正文或摘要、聚类依据和多源合并关系；分类标签不能替代标题。",
        "risk": "重点检查无标题记录、聚类误合并、转载重复、时间错位、来源失效、情绪误判、传闻当事实、单一来源和待核验线索被忽略。",
        "extension": "补充原文、交叉来源、时间线、传播范围、来源分歧、相关对象和后续确认信号。",
        "validation": "至少覆盖标题提取、去重聚类、来源与时间、正文可用性、情绪、待核验状态、刷新和空标题降级显示。",
    },
    "deepsee": {
        "evidence": "核验渠道、账号或联系人、同步时间、消息时间、会话范围、聚合规则、来源链接和数据新鲜度；区分原始消息、摘要和 AI 推断。",
        "risk": "重点检查同步中断、重复消息、联系人错配、跨账号串线、隐私泄露、权限越界、摘要丢失语境和群发误触。",
        "extension": "补充同步状态、渠道覆盖、联系人关系、主题聚类、待处理事项、授权范围和留痕策略。",
        "validation": "至少覆盖连接、同步、去重、搜索筛选、联系人映射、权限、隐私、群发确认、错误恢复和审计。",
    },
    "quant": {
        "evidence": "重点核验样本区间、基准、复权、信号时点、交易成本，以及是否存在前视偏差、幸存者偏差或数据泄漏。",
        "risk": "重点检查过拟合、容量、流动性、滑点、极端行情、参数敏感性和样本外失效风险。",
        "extension": "补充样本外测试、分层归因、参数稳定性、容量约束和不同市场状态下的表现。",
        "validation": "至少覆盖确定性测试、样本外或回放验证、边界条件、交易成本与关键回归检查。",
    },
    "trading": {
        "evidence": "核验账户、标的、委托、成交、持仓、资金、费用、时间戳和券商回报，明确模拟、待确认与真实执行状态。",
        "risk": "重点检查重复下单、部分成交、撤单失败、状态回退、价格或数量越界、持仓与资金不一致、费用漏记和对账断点。",
        "extension": "补充执行质量、滑点、成交率、订单生命周期、资金占用、日终对账、异常处置和人工确认记录。",
        "validation": "至少覆盖标的输入、订单创建到终态、部分成交与撤单、持仓资金联动、强确认、失败恢复、回放和审计。",
    },
    "market": {
        "evidence": "重点核验行情源、时间戳、交易时段、币种、复权方式、价格口径和跨数据源一致性。",
        "risk": "重点检查数据延迟、停牌或低流动性、公司行动、异常点和跨市场口径差异。",
        "extension": "补充量价结构、市场宽度、相对强弱、事件催化和同类资产对照。",
        "validation": "至少覆盖数据源可用性、时间与复权口径、空数据、异常行情和刷新链路。",
    },
    "research": {
        "evidence": "将事实、计算、推断和假设分开，核验来源、发布日期、统计口径、引用链和不同来源之间的一致性。",
        "risk": "重点寻找产业链传导断点、竞争替代、需求证伪、政策变化、估值约束和催化不兑现风险。",
        "extension": "补充产业链上下游、关键公司、可跟踪指标、催化日历和能够证伪当前观点的信号。",
        "validation": "至少覆盖来源可追溯性、关键数字复算、关系链完整性、反例与过期信息检查。",
    },
    "strategy": {
        "evidence": "核验候选范围、筛选条件、证券身份、信号时点、研究理由、证伪条件和来源，区分观察名单、研究结论与交易动作。",
        "risk": "重点检查筛选偏差、信号陈旧、条件漂移、重复暴露、拥挤度、反方证据缺失和把观察对象误当推荐标的。",
        "extension": "补充基本面、估值、技术结构、行业暴露、催化剂、反方证据和下一次复核条件。",
        "validation": "至少覆盖标的增删、筛选条件、来源与时点、证伪条件、跨 Mod 交接、持久化、空状态和权限边界。",
    },
    "portfolio": {
        "evidence": "核验资产池、预期收益、协方差、基准、约束、目标权重、再平衡规则、数据日期和模型假设，区分输入、计算结果与人工判断。",
        "risk": "重点检查模型敏感性、权重集中、相关性突变、流动性、汇率、杠杆、约束冲突、换手和交易成本。",
        "extension": "补充风险贡献、情景压力、历史区间、基准对照、约束变化、再平衡成本和模型稳定性。",
        "validation": "至少覆盖权重合计、约束满足、输入日期、模型复算、情景结果、再平衡、空数据和持久化。",
    },
    "risk": {
        "evidence": "核验持仓与穿透敞口、限额、集中度、回撤、流动性、杠杆、压力测试、预警状态、责任人和处置记录。",
        "risk": "重点检查限额未生效、穿透遗漏、行情陈旧、压力场景失真、预警重复或漏报、处置超时和授权越界。",
        "extension": "补充多层限额、情景库、风险归因、流动性分层、预警升级、人工接管、处置闭环和审计记录。",
        "validation": "至少覆盖限额设置与触发、组合穿透、压力测试、预警确认、升级处置、恢复条件、权限和审计。",
    },
    "macro": {
        "evidence": "核验指标发布机构、统计口径、发布日期、修订值、新鲜度和聚合源与原始源的差异；不要把陈旧数据当成当前状态。",
        "risk": "重点检查增长、价格和流动性信号是否分化，识别数据修订、预期差、事件聚集与跨地区传导失效风险。",
        "extension": "补充官方原始数据、利率与汇率、就业、信用、贸易、商品和政策背景，并解释其向行业和资产的传导路径。",
        "validation": "至少覆盖指标值与前值、发布时间、新鲜度、证据编号、经济事件时区、来源降级、修订风险和缺失地区或指标。",
    },
    "global": {
        "evidence": "核验事件原始来源、发生与发布时间、地点、对象、状态、证据编号和多源一致性，区分已确认事实、传闻、模型推演与人工判断。",
        "risk": "重点检查误报、重复事件、地理或时间错位、来源失效、单一来源、状态未更新和把情景推演当成已发生事实。",
        "extension": "补充官方来源、地区时间线、关联主体、跨市场传导、后续确认信号和相互冲突的证据。",
        "validation": "至少覆盖来源、时间地点、对象身份、去重、事件状态、刷新、新鲜度、跨源核验和空数据降级。",
    },
    "settings": {
        "evidence": "核验配置来源、默认值、生效范围、环境覆盖顺序、权限和依赖服务状态。",
        "risk": "重点检查错误配置、敏感信息暴露、权限越界、环境冲突和不可逆操作。",
        "extension": "补充健康检查、配置继承、迁移兼容、故障恢复和最小权限方案。",
        "validation": "至少覆盖配置解析、默认与覆盖优先级、权限、失败降级和重启后的持久化结果。",
    },
    "general": {
        "evidence": "核验数据来源、更新时间、统计口径、缺失值和交叉一致性。",
        "risk": "同时寻找反方证据、边界条件、依赖项和可能失效的假设。",
        "extension": "补充当前页面没有覆盖、但会显著改变结论的信息维度。",
        "validation": "给出可复现的检查步骤、实际结果和仍未覆盖的验证范围。",
    },
}
def _build_catalyst_calendar_prompt_groups(
    scope: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "understand",
            "label": "日历研判",
            "suggestions": [
                {
                    "id": "summary",
                    "intent": "summary",
                    "label": "总览 · 梳理未来关键催化",
                    "prompt": f"请基于{scope}，按重要性、紧迫度和证据质量梳理未来催化。明确区分已确认日期事件与不确定观察窗，列出时间、影响对象、来源、新鲜度、可信度和当前状态，并指出最需要优先跟踪的三项。不要给出买卖建议。",
                },
                {
                    "id": "evidence",
                    "intent": "evidence",
                    "label": "证据 · 核验日期、来源与覆盖",
                    "prompt": f"请基于{scope}做日历证据审计：核验每项事件的原始来源、证据编号、发布日期、最新更新时间和可信度，识别日期变更、陈旧来源、重复记录与缺失字段，并分别检查公司、行业和宏观事件是否存在明显覆盖缺口。",
                },
            ],
        },
        {
            "id": "judge",
            "label": "条件与复盘",
            "suggestions": [
                {
                    "id": "risk",
                    "intent": "risk",
                    "label": "条件 · 对照确认与失效信号",
                    "prompt": f"请基于{scope}，逐项对照原始催化假设、确认条件、失效条件和已记录的实际结果。指出哪些事件仍有效、哪些需要降级或作废，以及下一条能够确认或证伪判断的可观察证据。",
                },
                {
                    "id": "scenario",
                    "intent": "scenario",
                    "label": "观察窗 · 推演事件前后路径",
                    "prompt": f"请基于{scope}，为高重要性事件推演兑现、延迟和失效三种路径，说明传导链、应观察的数据与结论如何变化。Circle/周期叠加输出只能作为概率观察窗，不得转换成精确转折日期或确定性预测。",
                },
            ],
        },
        {
            "id": "advance",
            "label": "补充与跟踪",
            "suggestions": [
                {
                    "id": "extension",
                    "intent": "extension",
                    "label": "延伸 · 补全财务、公告与新闻",
                    "prompt": f"请围绕{scope}中的重点催化补充当前页面之外的证据，包括财报预期与历史财务、公司公告、新闻舆情、产业链事件和相关宏观数据。说明新增信息的来源、新鲜度、可信度，以及它会增强、削弱还是不改变原假设。",
                },
                {
                    "id": "next-step",
                    "intent": "next-step",
                    "label": "跟踪 · 形成滚动更新清单",
                    "prompt": f"请把{scope}转化为滚动跟踪清单：按本周、未来 30 天和更长期观察窗分组，为每项给出优先级、下次核验时间、所需数据、确认条件、失效条件和归档标准；同时标出需要补录或刷新来源的项目。",
                },
            ],
        },
    ]


def _build_macro_monitor_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "understand",
            "label": "宏观状态",
            "suggestions": [
                {
                    "id": "summary",
                    "intent": "summary",
                    "label": "总览 · 判断增长、价格与流动性",
                    "prompt": f"请基于{scope}和页面 decisionReview，分别判断增长、价格和流动性的已观测状态，列出支撑证据、反证、待补缺口与下一次复议事件。引用数据期、可核实的发布日期、来源及证据编号；发布日期缺失时直说未知。数据时效覆盖率不是判断正确概率，流动性 assessment 不是预测；不要直接给出资产买卖建议。",
                },
                {
                    "id": "evidence",
                    "intent": "evidence",
                    "label": "证据 · 核验口径、修订与来源",
                    "prompt": f"请对{scope}做宏观证据审计：检查发布机构、统计口径、发布日期、前值与修订值、数据新鲜度，以及聚合源和原始源之间可能存在的差异。按严重程度列出陈旧指标、缺失地区和必须回到官方来源复核的项目。",
                },
            ],
        },
        {
            "id": "judge",
            "label": "事件与传导",
            "suggestions": [
                {
                    "id": "risk",
                    "intent": "risk",
                    "label": "日历 · 梳理未来高影响事件",
                    "prompt": f"请基于{scope}，按时间和重要性梳理未来经济事件，比较前值、预期和已公布值，识别事件聚集、时区、日期调整与预期差风险，并指出每项事件最直接影响的宏观变量。",
                },
                {
                    "id": "scenario",
                    "intent": "scenario",
                    "label": "传导 · 推演超预期、符合与低预期",
                    "prompt": f"请为{scope}中的重点指标或事件构建超预期、符合预期和低于预期三种条件式情景：先核对实际值与预期值的单位、口径和来源冲突，再说明可能影响利率、汇率、信用、商品与行业景气的路径和反证。混合日频/月频数据不得外推成五日预测，情景不是交易指令。",
                },
            ],
        },
        {
            "id": "advance",
            "label": "补充与跟踪",
            "suggestions": [
                {
                    "id": "extension",
                    "intent": "extension",
                    "label": "延伸 · 补齐官方数据与跨市场证据",
                    "prompt": f"请围绕{scope}补充官方原始数据和跨市场证据，优先覆盖就业、信用、贸易、利率、汇率和商品；说明来源、截至日期、可信度，以及新增证据会增强、削弱还是不改变当前宏观状态判断。",
                },
                {
                    "id": "next-step",
                    "intent": "next-step",
                    "label": "跟踪 · 形成未来两周更新清单",
                    "prompt": f"请把{scope}转化为未来两周的宏观跟踪清单，按立即复核、等待发布和条件触发分组，为每项给出时间、所需数据、官方来源、预期差观察点、更新标准和停止跟踪条件。",
                },
            ],
        },
    ]


def _build_cycle_research_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "read-view",
            "label": "当前曲面",
            "suggestions": [
                {
                    "id": "cycle-view-summary",
                    "intent": "summary",
                    "label": "读图 · 说明当前视图与周期状态",
                    "prompt": f"请基于{scope}读取当前真实视图。先明确 2D/3D、时间范围、历史或预测图层、聚焦轨道和可见曲线，再总结当前周期状态与主要背离。页面没有提供的数据必须标记为未知，不得用 Manifest 或模型记忆补齐。",
                },
                {
                    "id": "cycle-evidence-audit",
                    "intent": "evidence",
                    "label": "证据 · 核验轨道、坐标与校准",
                    "prompt": f"请对{scope}做图形与数据证据审计：逐项核验轨道名称、坐标轴、时间窗口、归一化、历史/预测边界、数据源和校准状态，并区分结构化页面字段、视觉快照读取与研究推断。",
                },
            ],
        },
        {
            "id": "judge-cycle",
            "label": "背离与路径",
            "suggestions": [
                {
                    "id": "cycle-divergence",
                    "intent": "risk",
                    "label": "背离 · 找出冲突与误读风险",
                    "prompt": f"请基于{scope}识别各周期轨道之间的一致、领先、滞后和背离关系，重点指出样本窗口敏感、视觉误读、校准失效、预测区间被当成确定路径和跨资产映射过度的风险。",
                },
                {
                    "id": "cycle-scenarios",
                    "intent": "scenario",
                    "label": "路径 · 推演延续、收敛与反转",
                    "prompt": f"请基于{scope}构建周期延续、背离收敛和方向反转三条条件路径。每条说明先变化的轨道、需要观察的原始指标、确认或证伪条件及对跨资产判断的影响；不得把图中预测层解释成确定性时间点。",
                },
            ],
        },
        {
            "id": "advance-cycle",
            "label": "补证与跟踪",
            "suggestions": [
                {
                    "id": "cycle-extension",
                    "intent": "extension",
                    "label": "补证 · 连接原始指标与历史样本",
                    "prompt": f"请围绕{scope}补充各轨道对应的原始指标、校准方法、历史相似阶段和跨资产表现。逐项说明来源、截至日期、与当前图形的对应关系，以及新增证据会增强、削弱还是不改变当前判断。",
                },
                {
                    "id": "cycle-next-step",
                    "intent": "next-step",
                    "label": "跟踪 · 形成下一轮校准清单",
                    "prompt": f"请把{scope}转化为下一轮校准与跟踪清单：列出需要刷新的轨道、原始数据、校准检查、关键切换视图、确认条件、失效条件和复核时间，并优先处理当前页面已显示的数据缺口或异常状态。",
                },
            ],
        },
    ]


def _build_thesis_tracker_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "understand",
            "label": "逻辑校验",
            "suggestions": [
                {
                    "id": "summary",
                    "intent": "summary",
                    "label": "完整性 · 判断逻辑是否仍成立",
                    "prompt": f"请基于{scope}判断当前投资逻辑是否仍然完整且可证伪。先重述核心论点，再逐项评估支柱、证伪风险、催化剂和最新更新，说明哪些增强、削弱或不改变判断，并明确当前确信度是否与证据一致。不要给出买卖或仓位建议。",
                },
                {
                    "id": "evidence",
                    "intent": "evidence",
                    "label": "计分卡 · 核验每个支柱的证据",
                    "prompt": f"请对{scope}做支柱计分卡审计：逐项比较原始预期、当前状态、趋势与关联证据，核验来源、截至日期、新鲜度和可信度；区分事实、推断与假设，并指出没有证据支撑或证据已经陈旧的支柱。",
                },
            ],
        },
        {
            "id": "judge",
            "label": "反证与情景",
            "suggestions": [
                {
                    "id": "risk",
                    "intent": "risk",
                    "label": "反证 · 寻找缺失的证伪证据",
                    "prompt": f"请站在反方视角审视{scope}：检查每项证伪条件是否具体、可观察、可按时更新，主动寻找当前档案未记录的反例与冲突证据。按影响和紧迫度列出最可能推翻核心论点的信号，并说明应从哪里核验。",
                },
                {
                    "id": "scenario",
                    "intent": "scenario",
                    "label": "条件 · 对照强化、削弱与证伪路径",
                    "prompt": f"请基于{scope}构建强化、削弱和证伪三条条件路径。每条路径说明会先变化的支柱、需要出现的可观察数据、相关催化剂、结论如何调整，以及什么条件下应将逻辑标记为已证伪；不得转换为价格或买卖预测。",
                },
            ],
        },
        {
            "id": "advance",
            "label": "复盘与跟踪",
            "suggestions": [
                {
                    "id": "extension",
                    "intent": "extension",
                    "label": "延伸 · 补充财务、公告、新闻与宏观",
                    "prompt": f"请围绕{scope}主动补充当前页面之外的研究证据，包括更长时间区间的行情与财务数据、公司公告、新闻舆情、行业与产业链变化、相关宏观指标。每条新增证据都要给出来源、截至时间、可信度，并标明增强、削弱还是不改变哪个支柱。",
                },
                {
                    "id": "next-step",
                    "intent": "next-step",
                    "label": "复盘 · 生成下一轮核验清单",
                    "prompt": f"请把{scope}转化为下一轮复盘清单：按立即核验、催化剂前后更新、季度复盘和条件触发分组，为每项给出所需数据、原始来源、关联支柱或风险、完成标准、下次核验时间和停止跟踪条件。优先补齐页面已声明的信息缺口。",
                },
            ],
        },
    ]


def _build_earnings_workbench_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "preview",
            "label": "财报前准备",
            "suggestions": [
                {
                    "id": "consensus-snapshot",
                    "intent": "summary",
                    "label": "预期 · 建立一致预期快照",
                    "prompt": f"请基于{scope}准备财报前研究底稿。先核验最新待披露报告期、披露日期和原始来源，再汇总收入、利润、利润率、每股收益及公司特定经营指标的内部预期与一致预期。逐项给出来源、截至日期、口径和缺口，不得依赖模型记忆补齐数字，也不要给出评级或买卖建议。",
                },
                {
                    "id": "metrics-to-watch",
                    "intent": "evidence",
                    "label": "指标 · 找出公司特定观察点",
                    "prompt": f"请围绕{scope}识别本次财报最重要的公司特定经营指标。结合历史财务、公告、研报和新闻，说明每项指标为什么重要、当前预期、领先信号、来源与截至日期，以及高于、符合或低于预期分别意味着什么。",
                },
            ],
        },
        {
            "id": "reported",
            "label": "结果与预期差",
            "suggestions": [
                {
                    "id": "variance-analysis",
                    "intent": "scenario",
                    "label": "复盘 · 解释 Beat / Miss 驱动",
                    "prompt": f"请基于{scope}做财报后预期差分析：先核对实际、内部预期和一致预期的期末、币种、累计/单季/年度/TTM 及会计口径，仅明确一致时计算金额、百分比或基点差异。未知或不一致时列为待核对，不得自行换算或声称超预期；内部预期为人工研究输入，必须单独核验。尚未采用的候选不属于实际值，公告列表不等于原文已核验。再依据已读取的证据解释销量、价格、结构、成本、费用、汇率、并购、税率或一次性项目的影响；不能把推测当成已证实驱动。所有关键数字注明来源和截至日期；缺少一致预期时必须明确标记。",
                },
                {
                    "id": "guidance-change",
                    "intent": "risk",
                    "label": "指引 · 对比当前与上次口径",
                    "prompt": f"请基于{scope}逐项比较管理层当前指引与上次指引，识别维持、上调、下调、撤回及口径变化。结合电话会或公告解释变化原因，指出最重要的经营假设、可观察验证指标和数据缺口，不要把管理层表述直接当作已验证事实。",
                },
            ],
        },
        {
            "id": "update",
            "label": "指引与逻辑更新",
            "suggestions": [
                {
                    "id": "estimate-revision",
                    "intent": "extension",
                    "label": "修订 · 更新预测假设与估值输入",
                    "prompt": f"请结合{scope}和更长周期财务数据，列出需要修订的收入、利润率、费用率、每股收益和其他关键预测。按旧值、新值、期间、调整原因、来源与截至日期组织，并区分财报事实、管理层指引和研究假设；不要生成评级、目标价或交易动作。",
                },
                {
                    "id": "thesis-impact",
                    "intent": "next-step",
                    "label": "逻辑 · 判断增强、削弱或证伪",
                    "prompt": f"请把{scope}中的财报证据映射到投资逻辑：逐项说明它增强、削弱、不改变或证伪了哪个核心支柱或风险，并给出证据编号、来源和截至日期。最后形成下一期跟踪清单，包含指标、确认条件、证伪条件、下一次核验时间和仍缺少的数据。",
                },
            ],
        },
    ]


def _build_peer_comparison_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "scope",
            "label": "同业与口径",
            "suggestions": [
                {
                    "id": "peer-audit",
                    "intent": "evidence",
                    "label": "同业 · 审计谁真正可比",
                    "prompt": f"请基于{scope}审计同业集合。逐家公司检查业务模式、产品、客户、区域、规模和资本结构，说明为什么是直接同业、相邻对手或新进入者；标记不应纳入、只能部分可比或需要单独调整的公司。不要为了扩大样本强行保留差异过大的公司。",
                },
                {
                    "id": "period-audit",
                    "intent": "validation",
                    "label": "口径 · 核验报告期、币种与定义",
                    "prompt": f"请对{scope}做数据口径审计：核验每家公司报告期、财年结束日、币种、单位、会计定义、并购与一次性项目。逐项列出来源、截至日期和覆盖缺口；缺失值保持 N/A，不得用模型记忆或无来源估算静默填补。",
                },
            ],
        },
        {
            "id": "benchmark",
            "label": "指标与差异",
            "suggestions": [
                {
                    "id": "benchmark-metrics",
                    "intent": "summary",
                    "label": "指标 · 提炼最有解释力的比较",
                    "prompt": f"请基于{scope}围绕当前研究问题选择 5–10 个最重要指标，比较目标公司与同业的增长、利润率、资本效率、现金质量和估值。引用目标值、同业中位数与 25/75 分位，并指出数据覆盖率和异常值；不要堆砌与问题无关的指标。",
                },
                {
                    "id": "premium-discount",
                    "intent": "scenario",
                    "label": "估值 · 解释溢价或折价来源",
                    "prompt": f"请基于{scope}解释目标公司相对同业估值溢价或折价可能由哪些经营事实驱动。区分增长、利润率、现金转化、资产负债、业务纯度与风险差异，并给出能够确认或证伪每个解释的后续指标；不得直接得出高估、低估或买卖结论。",
                },
            ],
        },
        {
            "id": "strategy",
            "label": "竞争与跟踪",
            "suggestions": [
                {
                    "id": "moat-map",
                    "intent": "risk",
                    "label": "竞争 · 比较护城河与脆弱点",
                    "prompt": f"请基于{scope}比较目标公司与同业的网络效应、转换成本、规模经济、品牌/专利/数据等无形资产。分别说明当前状态、变化轨迹、难以复制的优势、难以修复的脆弱点和证据来源，避免把单一财务指标直接等同于护城河。",
                },
                {
                    "id": "thesis-update",
                    "intent": "next-step",
                    "label": "跟踪 · 映射投资逻辑与更新清单",
                    "prompt": f"请把{scope}的同业差异映射到投资逻辑：说明哪些证据增强、削弱或不改变核心支柱，哪些差距是当前状态、哪些正在改善或恶化。最后形成滚动跟踪清单，包含指标、来源、更新频率、确认条件、证伪条件和仍缺少的数据。",
                },
            ],
        },
    ]


def _build_valuation_workbench_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "inputs",
            "label": "假设与口径",
            "suggestions": [
                {
                    "id": "input-audit",
                    "intent": "evidence",
                    "label": "基期 · 审计历史与资本输入",
                    "prompt": f"请基于{scope}审计模型输入。先查看 reviewStatus 与 capitalEvidence，区分人工关联原文、输入变化后失效的确认和独立核验；用户粘贴摘录不代表系统已读取或审计原文。将历史事实、管理层指引和研究假设分开，逐项核验收入基期、EBIT 率、折旧摊销、资本开支、营运资本、有息债务（非负债合计）、可归属现金、稀释股数、币种、单位、来源和截至日期；缺失值保持缺失，不得用无来源数字静默补齐。",
                },
                {
                    "id": "scenario-review",
                    "intent": "summary",
                    "label": "情景 · 检查悲观、基准与乐观驱动",
                    "prompt": f"请基于{scope}审查三种经营情景。先检查当前基期、预测年份是否连续，以及 reviewStatus 中假设是否已确认；其他情景不能继承当前情景的确认。比较逐年收入增长、EBIT 率、税率、D&A、CapEx 和 ΔNWC 假设，说明每条路径的业务依据、与历史及同业是否一致，以及乐观、基准、悲观的 FCF 层级是否合理。不要把模板参数当作研究结论，也不要把情景名称当作概率结论。",
                },
            ],
        },
        {
            "id": "valuation",
            "label": "估值与敏感性",
            "suggestions": [
                {
                    "id": "wacc-bridge",
                    "intent": "validation",
                    "label": "WACC · 复核资本成本与价值桥接",
                    "prompt": f"请基于{scope}复核 WACC 与估值桥接：先检查 reviewStatus.ready，若缺失或未就绪，只解释现金流试算、计算口径与待核验项，不得绕过页面确认计算每股价值或目标价。输入与确认完整时，检查无风险利率、Beta、权益风险溢价、债务成本、税率和资本结构权重，再复算显式期 FCF 现值、终值、企业价值、净债务、股权价值和每股价值。核对 equityBridgePolicy：经营 EV 减有息债务，加可用现金与未纳入经营预测的非经营资产价值，再扣少数股东权益价值及其他优先权益。现金按 cashBasis 处理：adjusted 为已调整净额，不重复扣 excludedCashM；gross 才从现金余额扣剔除额。少数权益须匹配合并预测范围，账面值不是估值；其他索偿勿与债务、现金扣减或稀释股数重计，调整项缺失不能填零。先检查 priceComparisonIssue 与 currentPriceAsOf；股价日期缺失或与估值基期不同，不得自行计算上涨空间或模型差异百分比。财报资本参考仅是原始会计项目：股本金额不是稀释股数，货币资金不是可归属现金，不得把空白借款当零。人工确认不等于正式估值意见。",
                },
                {
                    "id": "sensitivity",
                    "intent": "scenario",
                    "label": "敏感性 · 找出最主要的估值驱动",
                    "prompt": f"请基于{scope}分析 WACC × 终值增长 5×5 敏感性矩阵。先检查 reviewStatus.ready；尚未确认或矩阵为空时，说明原因与需要补齐的依据，不自行填造矩阵。已就绪时确认中心格与当前基准假设完全一致，并识别价值对折现率、终值增长、收入增长和 EBIT 率最敏感的区间。解释变化原因，但不得把模型差异直接转换为买卖建议。",
                },
            ],
        },
        {
            "id": "audit",
            "label": "审计与更新",
            "suggestions": [
                {
                    "id": "model-risk",
                    "intent": "risk",
                    "label": "风险 · 寻找错误精度与失效条件",
                    "prompt": f"请站在模型审计者角度检查{scope}：重点识别终值增长不合理、终值占比过高、周期高点外推、利润率缺少经营依据、单位或币种错位、稀释股数遗漏、债务现金口径错误和缺失来源。按严重程度列出必须修正、需要警示和可以接受的简化。",
                },
                {
                    "id": "model-update",
                    "intent": "next-step",
                    "label": "更新 · 形成下一轮预测修订清单",
                    "prompt": f"请把{scope}转化为下一轮模型更新清单。结合财报研究、同业比较和投资逻辑，列出需要刷新或补录的历史财务、经营指标、资本结构、宏观利率和行业稳态假设，并说明每项来源、更新频率、触发条件、完成标准及会影响哪个情景或估值输入。",
                },
            ],
        },
    ]


def _build_research_memo_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "synthesis",
            "label": "结论与证据",
            "suggestions": [
                {
                    "id": "memo-summary",
                    "intent": "summary",
                    "label": "收敛 · 形成高密度研究结论",
                    "prompt": f"请基于{scope}先给研究结论，再用核心论点、关键争议、差异认知、市场可能遗漏和逻辑断点解释判断。逐项引用已关联的投资逻辑、财报、同业、估值、催化剂或产业链档案；未核验内容必须明确标记，不要输出买卖评级、仓位或个性化建议。",
                },
                {
                    "id": "memo-evidence",
                    "intent": "evidence",
                    "label": "审计 · 核验来源与引用档案",
                    "prompt": f"请审计{scope}中的证据链：逐条区分已报告事实、管理层指引、市场一致预期和研究推断，检查来源、截至日期、新鲜度、关联 Mod 与档案 ID。列出陈旧、缺失、互相冲突和无法回溯的判断，并给出优先补证清单。",
                },
            ],
        },
        {
            "id": "challenge",
            "label": "反方与情景",
            "suggestions": [
                {
                    "id": "memo-risk",
                    "intent": "risk",
                    "label": "反方 · 主动挑战核心论点",
                    "prompt": f"请站在反方研究员角度挑战{scope}：寻找当前备忘录没有覆盖的冲突证据、竞争变化、周期、监管、技术替代、执行、会计质量和估值风险。为每项给出领先预警信号与可观察的逻辑断点，并说明它会削弱或证伪哪一项结论。",
                },
                {
                    "id": "memo-scenario",
                    "intent": "scenario",
                    "label": "情景 · 校验悲观、基准与乐观路径",
                    "prompt": f"请校验{scope}的悲观、基准和乐观情景：检查概率是否合计 100%，经营路径是否由关键驱动支持，触发条件是否可观察，并把估值结论追溯到估值工作台对应情景。指出情景层级反常、错误精度和需要重新设定的假设。",
                },
            ],
        },
        {
            "id": "update",
            "label": "补充与版本",
            "suggestions": [
                {
                    "id": "memo-extension",
                    "intent": "extension",
                    "label": "延伸 · 补齐当前页面之外的研究",
                    "prompt": f"请围绕{scope}的核心争议补充当前页面之外的数据：更长周期财务、公司公告、电话会、同业经营与估值、产业链、宏观、新闻舆情和未来催化剂。说明每项来源与截至日期，以及它会增强、削弱还是不改变当前判断。",
                },
                {
                    "id": "memo-version",
                    "intent": "next-step",
                    "label": "更新 · 形成下一版备忘录清单",
                    "prompt": f"请把{scope}转化为下一版更新清单：按立即补证、等待披露、持续监控和条件触发分组，列出负责人所需数据、来源 Mod 或外部来源、完成标准、复核时间和停止条件；最后总结本版相对上一版新增、删除和改变了哪些判断。",
                },
            ],
        },
    ]


def _build_idea_funnel_prompt_groups(scope: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "screen",
            "label": "筛选与排序",
            "suggestions": [
                {
                    "id": "idea-screen-audit",
                    "intent": "evidence",
                    "label": "筛选 · 审计候选为何入池",
                    "prompt": f"请审计{scope}的搜索条件和入池依据：检查市场、行业、主题、市值范围、量化规则、来源、截至日期和同业口径。逐项说明哪些条件真正提高研究价值，哪些可能造成样本偏差、过拟合或重复暴露；筛选结果只是候选，不得直接写成投资结论。",
                },
                {
                    "id": "idea-rank",
                    "intent": "summary",
                    "label": "排序 · 比较当前机会池候选",
                    "prompt": f"请基于{scope}比较候选的相关性、证据质量、认知新颖度、催化清晰度、可证伪性和研究成本。先列最值得优先研究的候选及原因，再指出评分与证据不一致、重复主题暴露和暂缓研究的项目；不要输出买卖、目标价或仓位建议。",
                },
                {
                    "id": "idea-workflow-audit",
                    "intent": "validation",
                    "label": "流程 · 定位卡点与过期档案",
                    "prompt": f"请审计{scope}的研究流程总览：按复核到期、任务逾期、来源陈旧和档案缺口排序，检查机会池、投资逻辑、财报、同业、估值与研究备忘录是否衔接。逐项说明卡点、所需证据、下一研究入口和完成标准，不得把覆盖完整度解释为投资结论。",
                },
            ],
        },
        {
            "id": "challenge",
            "label": "双向假设",
            "suggestions": [
                {
                    "id": "idea-two-sided",
                    "intent": "scenario",
                    "label": "假设 · 同时强化正反研究路径",
                    "prompt": f"请基于{scope}分别重写最强的初始假设和反方假设。每一侧都给出传导链、当前证据、缺失证据、可观察指标与能够证伪自身的条件，并判断当前信息是否足以进入短名单或仍应留在初筛。",
                },
                {
                    "id": "idea-counter-evidence",
                    "intent": "risk",
                    "label": "反证 · 搜索被忽略的冲突证据",
                    "prompt": f"请站在反方研究员角度检查{scope}：寻找拥挤度、估值溢价、增长减速、利润率压力、库存与应收、客户集中、竞争、技术替代、监管和会计质量风险。按影响和可验证性排序，并说明每项会挑战哪一条假设。",
                },
            ],
        },
        {
            "id": "advance",
            "label": "补证与交接",
            "suggestions": [
                {
                    "id": "idea-extension",
                    "intent": "extension",
                    "label": "补证 · 扩展页面之外的数据",
                    "prompt": f"请围绕{scope}的研究问题补充页面之外的数据，包括更长周期财务与行情、财报公告、同业比较、估值区间、产业链、新闻舆情、所有权与拥挤度、催化剂和宏观变量。说明来源、截至日期，以及每项信息会提高、降低还是不改变研究优先级。",
                },
                {
                    "id": "idea-handoff",
                    "intent": "next-step",
                    "label": "交接 · 形成深度研究任务包",
                    "prompt": f"请把{scope}整理为深度研究交接包：明确下一步进入投资逻辑、财报研究、同业比较、预测与估值或研究备忘录中的哪一个 Mod；列出必须完成的任务、所需数据、来源、完成标准、截止时间、停止条件和交接档案名称。",
                },
                {
                    "id": "idea-rolling-review",
                    "intent": "next-step",
                    "label": "调度 · 形成滚动复核清单",
                    "prompt": f"请把{scope}转化为轻量滚动复核清单：按立即处理、本周处理、等待披露和条件触发分组，列出对象、来源 Mod、到期原因、需要刷新的数据、负责人下一动作、完成标准与复核日期；优先消除陈旧来源、逾期任务和断裂的档案引用。",
                },
            ],
        },
    ]


def build_mod_copilot_prompt_groups(
    manifest: dict[str, Any], mode: str = "ask"
) -> list[dict[str, Any]]:
    name = str(manifest.get("name") or manifest.get("id") or "当前")[:80]
    scope = (
        f"当前「{name}」Mod 的页面上下文（包括已选对象、筛选条件、时间范围、"
        "可见数据、数据新鲜度和可用操作）"
    )
    profile = _copilot_profile(manifest)
    lens = DOMAIN_LENSES[profile]

    if mode == "edit":
        return [
            {
                "id": "modify",
                "label": "修改与优化",
                "suggestions": [
                    {
                        "id": "modify-function",
                        "intent": "modification",
                        "label": "修改 · 修复数据或交互问题",
                        "prompt": f"请基于{scope}，复现并定位当前问题的根因，直接完成最小且完整的修复。保留现有标准接口和兼容行为，说明改动文件、关键取舍与影响范围。",
                    },
                    {
                        "id": "modify-experience",
                        "intent": "modification",
                        "label": "修改 · 优化信息层级与操作路径",
                        "prompt": f"请基于{scope}，找出影响理解效率和操作效率的结构问题，直接优化信息层级、状态反馈、空态与关键操作路径；避免增加重复功能，并说明修改前后的差异。",
                    },
                ],
            },
            {
                "id": "verify",
                "label": "验证与回归",
                "suggestions": [
                    {
                        "id": "verify-targeted",
                        "intent": "validation",
                        "label": "验证 · 运行针对性检查并给证据",
                        "prompt": f"请针对当前 Mod 运行最小充分的验证，不要只给判断。{lens['validation']}报告执行的检查、实际结果、失败项、未覆盖范围和复现方式。",
                    },
                    {
                        "id": "verify-regression",
                        "intent": "validation",
                        "label": "验证 · 对比修改前后并排查回归",
                        "prompt": f"请对当前 Mod 做修改前后对比与回归检查，验证核心数据链路、主要交互、错误状态和与 Desk 标准协议的兼容性；发现问题时直接修复并重新验证。{lens['validation']}",
                    },
                ],
            },
        ]

    if profile == "idea-funnel":
        return _build_idea_funnel_prompt_groups(scope)

    if profile == "research-memo":
        return _build_research_memo_prompt_groups(scope)

    if profile == "valuation-workbench":
        return _build_valuation_workbench_prompt_groups(scope)

    if profile == "peer-comparison":
        return _build_peer_comparison_prompt_groups(scope)

    if profile == "earnings-workbench":
        return _build_earnings_workbench_prompt_groups(scope)

    if profile == "thesis-tracker":
        return _build_thesis_tracker_prompt_groups(scope)

    if profile == "catalyst-calendar":
        return _build_catalyst_calendar_prompt_groups(scope)

    if profile == "macro-monitor":
        return _build_macro_monitor_prompt_groups(scope)

    if profile == "cycle-research":
        return _build_cycle_research_prompt_groups(scope)

    return [
        {
            "id": "understand",
            "label": "提炼与核验",
            "suggestions": [
                {
                    "id": "summary",
                    "intent": "summary",
                    "label": "总结 · 提炼核心结论与依据",
                    "prompt": f"请基于{scope}，输出一份高密度摘要：先给核心结论，再列支撑证据、关键变化、重要不确定性和用户最需要关注的三件事。不要脱离当前页数据泛泛而谈。",
                },
                {
                    "id": "evidence",
                    "intent": "evidence",
                    "label": "证据 · 核验数据、口径与推断",
                    "prompt": f"请基于{scope}做证据审计：把关键陈述拆分为事实、计算、推断和假设，逐条指出依据、缺失、冲突与可信度。{lens['evidence']}最后给出优先核验清单。",
                },
            ],
        },
        {
            "id": "judge",
            "label": "风险与推演",
            "suggestions": [
                {
                    "id": "risk",
                    "intent": "risk",
                    "label": "风险 · 寻找反例与失效条件",
                    "prompt": f"请站在反方视角审视{scope}：列出最可能被忽略的风险、反例、失效条件和领先预警信号，并按影响程度与发生可能性排序。{lens['risk']}",
                },
                {
                    "id": "scenario",
                    "intent": "scenario",
                    "label": "情景 · 推演乐观、基准与悲观路径",
                    "prompt": f"请基于{scope}构建乐观、基准、悲观三种情景。每种情景说明核心假设、传导路径、可观察指标、触发条件与结论变化，并指出当前页面数据更接近哪一种及原因。",
                },
            ],
        },
        {
            "id": "advance",
            "label": "延伸与行动",
            "suggestions": [
                {
                    "id": "extension",
                    "intent": "extension",
                    "label": "延伸 · 补全关联对象与跟踪指标",
                    "prompt": f"请从{scope}向外延伸分析，但保持与当前结论直接相关。{lens['extension']}按“为什么相关、需要补什么、从哪里验证、会怎样改变结论”组织结果。",
                },
                {
                    "id": "next-step",
                    "intent": "next-step",
                    "label": "下一步 · 形成可执行研究清单",
                    "prompt": f"请把{scope}转化为下一步行动清单：区分立即核验、持续跟踪和条件触发三类任务，为每项给出优先级、所需数据、完成标准、更新频率和停止条件。",
                },
            ],
        },
    ]


def build_mod_copilot_prompts(
    manifest: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "ask": build_mod_copilot_prompt_groups(manifest, "ask"),
        "edit": build_mod_copilot_prompt_groups(manifest, "edit"),
    }
