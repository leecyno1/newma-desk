# Newma-Desk Domain Context

## Mod Suite

围绕同一业务能力组织的一组相关 Mod 页面。Mod Suite 只声明一次完整项目身份、所属投资栏目、运行环境和共享能力；Suite Discovery 会把页面展开为独立 Mod，使现有权限、数据路由、Agent Context 与运行时隔离继续按页面生效。同一运行时可提供多个 Suite，但同一页面只能有一个主归属。

## Navigation Descriptor

导入项目提供给 Newma-Desk 的导航声明。它描述 Mod Suite 的所属栏目、完整项目分组、页面顺序、标签、图标和设置入口，不包含用户的拖拽、冻结、隐藏等个人偏好。

## Investment Column Identity

由 `navigation.project` 声明、并由同一 Mod Suite 的全部展开页面继承的稳定栏目身份。其 ID 必须属于十六个核心投研栏目或自定义项目；它决定一级导航归属，但不充当完整项目的设置、数据或 Agent 作用域。

## Complete Project Identity

由 Suite ID 和同 ID 的 `navigation.directory.id` 共同声明。它代表不可拆分的完整业务项目，是项目设置、统一数据路由和 Agent Workspace 的稳定作用域。同一 Suite 的所有页面必须继承相同栏目和完整项目身份；共享源码、端口或数据库不等于必须共用一个 Suite。

## Project Rail

Newma-Desk 左侧显示十六个核心栏目与用户自定义项目的中文方形短标。选择栏目后，二级 Project Panel 直接呈现该栏全部页面，并在底部提供栏目数据与能力设置。

## Suite Discovery

读取 Navigation Descriptor 并生成独立 Mod Manifest 的 Module。Git / 本地文件与 `.well-known/newma-desk-suite.json` HTTP 声明是该 Seam 上的不同 Adapter；旧 `.well-known/newma-dock-suite.json` 与 `.well-known/vibedesk-suite.json` 在兼容期作为回退入口。生成后的 Manifest 继续进入既有 Mod Registry。

## Mod Update Catalog

以 GitHub `main` 的明确 commit 为发布快照，统一提供目录同步、版本比较和项目级安装。Desk 校验完整商店与 Suite 后原子替换本地快照；Newma 宿主只调用 Desk Interface，不直接执行 Git、写插件目录或复制 Desk 业务代码。

## Navigation Compiler

把已发布 Mod Manifest、Suite 默认导航和 Preference Overlay 编译成 Desk 唯一导航树的 Module。一级栏目、二级完整项目分组、项目设置和当前路由都应读取同一份编译结果。

## Preference Overlay

只记录用户相对默认导航所做的变化，包括排序、冻结和栏目重命名。页面只能在所属完整项目内排序，不能移动到其他项目或栏目；已删除页面和项目的失效偏好由 Navigation Compiler 清理。

## External Mod Runtime

在 Newma-Desk 仓库之外运行、但由 Desk 注册、检查或在本地开发时启动的 Mod 运行环境。External Mod Runtime 可以包含一个或多个工作区、进程和 HTTP 入口；不可用时必须独立降级，不能影响 Desk 核心运行时。

## Integrated Domain Runtime

把第一方 Research / Trading Mod Suite 收敛到 Desk 核心交付物中的运行方式。该 Module 只暴露经过权限筛选的领域 Interface，复用 Desk Agent、模型设置、调度和确认能力；生产环境使用一套固定依赖，不加载嵌套工作区的虚拟环境，也不启动上游自带 Agent、频道或后台任务。

## Creator Studio Suite

Newma-Desk 中承载完整自媒体创作主链的 Mod Suite。它以状态看板为默认首页，以内容采集、选题 Brief、初稿生产、多通路转写、发布、复盘六个 Workflow Stage 作为纵向导航；审核、交付物、剪辑和发布操作属于具体 Workflow Node，不再形成独立业务页面。

## Workflow Stage

自媒体主链中的稳定纵向阶段。六个 Stage 只表达业务进程和阶段交付，不直接暴露脚本、目录或旧 Manifest 差异；每个 Stage 的内部步骤由横向 Workflow Node 表达。

## Workflow Node

Workflow Stage 内可独立运行、审核、反馈和转接的最小工作节点。Node 声明 Material Requirement、输出 Artifact、Gate、Action、可用 Capability Adapter 和 Editor Session；用户可从任意 Node 新建项目，但必须先满足该 Node 的 Material Requirement。

## Node Workspace

用户选择一个 Workflow Stage 和 Workflow Node 后进入的统一互动页面。它集中显示状态、输入素材、上游交付物、当前产物、参数、修改与反馈、审核、人工编辑、运行日志和下一节点转接，避免把同一节点的信息拆散到多个全局页面。

## Material Requirement

Workflow Node 对输入素材的结构化要求，包括类型、格式、是否必需以及允许来自人工上传或上游 Artifact Handoff。Node 在 Material Requirement 未满足时不得进入运行状态。

## Artifact Handoff

把上游 Workflow Node 的版本化 Artifact 作为下游 Material Requirement 输入的转接记录。它保存来源 Run、来源 Artifact、目标 Stage / Node 和匹配结果，只传递引用与版本，不复制媒体文件；人工修改上游后，受影响的下游交付物必须标记为 stale。

## Capability Adapter

在受控 Seam 上封装本地 CLI、Skill、外部项目、编辑器或发布连接器差异的 Adapter。前端只能按注册 ID 和声明参数调用，不能提交任意终端命令；CLI 检测、参数构造、输出解析和错误归一都留在 Adapter Implementation 内。

## Node Execution Adapter

把一个 Workflow Node 的结构化输入转换为真实执行、人工审核会话或编辑会话的 Adapter。每个 Node 只引用稳定 Executor ID；命令白名单、参数构造、运行时选择、日志和 Artifact 回写集中在 Creator Run Control Module 内，Agent 与可视化按钮共用同一 Interface。

## Creator Execution Job

Workflow Node 的持久化异步执行记录。Job 保存 Run、Node、Executor、结构化请求、进度、结果和取消状态；后台运行与 Run revision 原子衔接，应用重启后排队任务可恢复，已中断任务明确失败，不允许前端用本地状态伪装执行完成。

## Editor Session Runtime

人工编辑节点的受控运行 Module。它根据 Registry 只启动白名单 Editor Adapter，记录打开、保存、关闭和输出 Artifact；HTML Anything、HTML Video、公众号预览、分镜与粗剪审核等编辑器共享同一 Interface，未注册实现必须明确显示不可用。

## Collaborative Editing Session

Editor Session Runtime 中允许人工时间线操作与 Desk Agent 对话操作并存的会话形态。编辑器在会话期间掌握真实时间线，Creator Run Control 掌握任务、审核和交付物；两种入口必须调用编辑器同一命令层，不能各自维护工程副本。

## Edit Proposal

Agent 在隔离 Draft 中生成的可审核修改集合。Proposal 保存外部编辑会话 ID、摘要、影响范围、状态和审核时间；只有编辑器确认 applied 后才能继续保存工程与回写 Artifact，rejected 或 discarded 不改变正式时间线。

## Editor Project Binding

Newma Editor Session 与外部编辑器真实工程之间的稳定映射。绑定保存来源 Editor Adapter、外部 Project ID 和受信启动入口；人工时间线与 Agent 必须读取同一绑定，不能根据窗口数量或工程名称重复猜测。绑定不复制外部工程内容，工程仍由来源编辑器掌握。

## Publish Execution Module

发布阶段中“预检、明确确认、执行、回执验真”的深 Module。发布确认是一次性权限，进入 Creator Execution Job 队列即消费，失败重试必须重新确认；账号健康、阻塞项、平台回执和验真结果统一回写 Run 的 Publish State。

## Artifact Lineage

维护 Artifact 版本、内容摘要、父产物、生产 Job 和参数摘要的 Module。新版本不覆盖旧版本；已被 Handoff 消费的上游 Artifact 被替代后，Lineage 沿 Handoff 图递归把下游 Material、Artifact、Node 和 Handoff 标记为 stale，直到新的版本化 Handoff 恢复目标 Node。

## Creator Marketplace

Creator Studio Suite 内用于测试和选择仓库、Skills、模板、流水线、编辑器和发布连接器的业务超市。选择项先经过兼容性检查和演示，再保存为版本化预设；它不替代 Newma Mod Store，也不能直接修改生产注册表。

## Creator Template Lifecycle

模板从“剪辑前收藏并绑定节点”，到“剪辑中随时应用”，再到“剪辑完成后把已跑通工程保存为模板”的统一生命周期。Newma 保存模板引用、来源编辑器、版本、适用节点和参数；模板内容与媒体资产继续由来源编辑器管理，避免复制出第二套模板事实源。

## Organization Workflow

组织围绕一个明确目标执行的版本化协作流程。它不限定投研、投决或创作领域，由 Workflow Template、Workflow Run、Organization Workflow Node、Node Assignment、Delegation Grant、Workflow Artifact 和 Workflow Audit Ledger 共同描述；领域 Mod 只通过 Adapter 提供节点定义与执行能力。

## Workflow Matrix

Organization Workflow 的组织画布，由纵向 Workflow Lane 与横向 Workflow Matrix Stage 交叉形成坐标格。Matrix 负责总览、菜单和节点归类，DAG Edge 继续负责真实执行依赖；调整行列顺序只改变 A1、C4 等显示坐标，不能改变稳定 Node ID、授权、交付物谱系或审计记录。

## Workflow Lane

Workflow Matrix 的纵向业务域，也是工作流内部的二级模块。组织可以新增、命名和排序多个 Lane；被提升的成熟 Node 作为快捷入口显示在所属 Lane 中，但 Node 仍保留在画布原坐标。

## Workflow Matrix Stage

Workflow Matrix 的横向流程阶段，也是画布上方可切换的三级标签。Stage 用于按受理、执行、复核、决策、交付等阶段切换视图，不替代 DAG Edge，也不等同于 Creator Studio 的创作 Stage。

## Organization

拥有成员、服务器 Agent、Workflow Template、Workflow Run、授权关系和审计账本的稳定协作范围。Desk 本地模式暂以 Workspace ID 作为 Organization ID；未来组织目录 Adapter 可以替换身份来源，但不能改变工作流授权语义。

## Principal

可以承担责任、执行动作、审核或进行授权的组织主体。Principal 分为 human 和 server_agent；身份、责任、执行权与会话必须分开记录，切换实际执行者不能覆盖原责任人。

## Server Agent Principal

由组织登记的服务器 Agent 身份。它可以成为 Node Assignment 的责任人，也可以在自身权限范围内授予他人覆盖某个模板、运行、节点或职能；同一个 Agent 可以同时拥有多个 incoming 和 outgoing Delegation Grant。

## Workflow Template

组织可复用的工作流定义，保存有向无环节点图、职能角色、审核要求和交付物约定。Template 每次修改创建新版本；已经启动的 Workflow Run 固定引用启动时版本，不被后续编辑静默改写。

## Workflow Run

Workflow Template 某一版本的执行实例。Run 保存节点状态、责任快照、领取租约、数据版本、交付物版本和事件序列；并发命令必须携带 expected revision，过期命令不得覆盖当前状态。

## Organization Workflow Node

Organization Workflow 中最小的责任、执行、审核与交付范围。Node 可声明 task、review、gate 或 automation 类型、role key、前置节点、矩阵坐标、是否提升为 Lane 入口、是否需要审核和预期输出；Node 不依赖 Creator Studio 的创作 Stage。

## Node Assignment

Workflow Run 启动或运行中记录的节点责任分配。Assignment 分别保存 accountable principal 和 reviewer principal；Delegation Grant 只增加覆盖执行权，不能替换 Assignment 中的责任人。

## Responsibility Snapshot

一次节点动作发生时固化的责任人、实际执行者和授权来源。Workflow Audit Ledger 使用 Snapshot 解释“谁负责、谁实际做、凭什么做”，后续改派或撤销不能重写历史。

## Delegation Grant

Principal 把自己已有的部分动作授权给另一个 Principal 的版本化记录。Grant 支持 organization、template、run、node 和 role Scope、有效期、撤销、是否允许转授权及最大深度；子授权的 Scope、Action、期限和深度都不得超过父授权，撤销父授权必须级联使后代授权失效。

## Execution Claim

Principal 对 Organization Workflow Node 的短期独占领取记录。Claim 使用可到期 Lease 防止多人或多个 Agent 重复执行；Lease 到期、主动释放或节点提交后不再阻止其他已授权主体领取，Node Assignment 中的责任人保持不变。

## Node Data Revision

Organization Workflow Node 保存结构化输入、过程数据或阶段结论的不可覆盖版本。相同 slot key 的新写入创建新 revision，旧版本继续可审计；节点 Run revision 与数据 revision 分开记录。

## Workflow Artifact

Organization Workflow Node 产生的版本化交付物引用。Artifact 保存稳定 key、版本、生产者、内容或 URI、元数据和输入 Artifact ID；上游同 key 新版本替代旧版本后，仍引用旧版本的下游 Artifact 与 Node 标记为 stale。

## Workflow Audit Ledger

Organization Workflow 的追加式事件账本。每条事件保存组织、Run、事件类型、实际执行 Principal、accountable Principal、Delegation Grant、时间和最小载荷；它是权限调查、责任复盘与跨 Agent 协作验真的事实源。

## Notification Inbox

Creator Studio Suite 的统一消息入口。它聚合待审核 Gate、新交付物、阻塞 Node、发布失败和 Handoff 就绪事件，并在顶部计数器与动态通知中投影；真实状态仍由运行事件和快照提供，通知本身不是状态源。

## Runtime Descriptor

External Mod Runtime 的统一声明文件。它描述稳定 ID、工作区发现候选、环境变量、HTTP 入口和健康路径，不包含用户账号、密钥或个人绝对路径。Node 启动器与 Python Agent Gateway 分别通过自己的 Adapter 读取同一个 Runtime Descriptor。

## Runtime Certification

在真实 Desk 与 Mod 运行环境中执行的兼容验收。Manifest 中的等级只是声明；只有 health、embed、Bridge、响应式布局以及等级要求的 Agent Context 检查全部通过，才能获得对应认证等级。

## Evidence Ledger

个股研究中可追溯事实的统一账本。每条证据保留稳定 ID、来源、原字段、截止日期、单位、币种、置信度与数据缺口，研究结论和 Desk Agent 都只能引用账本中实际存在的证据。

## Market Research Adapter

把单一市场的数据来源归一为共同个股研究结构的 Adapter。A 股、港股与美股可以使用不同 Adapter，但必须产出同一组研究维度和 Evidence Ledger，而不是各自形成独立研究框架。

## Quarantined Pilot

默认关闭并受能力、环境变量、网络、存储和端口策略约束的外部项目试用运行时。Quarantined Pilot 通过验收前不属于默认 Mod，也不能获得真实交易、券商凭据或项目自带 Agent 能力。

## Pilot Extraction Adapter

把 Quarantined Pilot 的可复用输出压缩成 Desk 自有研究上下文或 Strategy Ledger 的 Adapter。它只提取白名单字段，删除投资建议、订单、凭据、任意策略代码与上游 Agent 信息；审计未通过时运行时拒绝调用。

## Strategy Ledger

纸面回测与量化实验的可复现账本。每条记录包含稳定 ID、策略模板及参数、Desk 数据窗口、收益与风险指标、归因、执行模式和来源；不保存真实订单、券商账户或可执行策略代码。

## Mod Storage Interface

由 Desk 提供给 Mod 的统一持久化 Interface。Mod 只声明存储模式、namespace、Schema 版本和容量，不接触数据库地址、凭据或表名；Desk 在用户、工作区、Mod 与 namespace 四个维度实施隔离，并通过 SQLite 或未来的 PostgreSQL Adapter 提供相同语义。

## Mod Data Continuity

Mod 在读取型页面中保留最后一次成功展示快照，并在后台刷新最新数据的标准行为。快照按用户、Workspace、Mod 和资源隔离；刷新期间旧数据继续可见，成功后替换，失败时明确标记为上次数据。它只用于显示连续性，不保存交易执行状态、凭据或一次性任务结果。

## Research Archive Index

由 Desk 从各研究 Mod 已有的 Desk Storage 文档中派生的统一研究档案索引。该 Module 只返回来源 Mod、档案 ID、标题、证券身份、状态、时间与标签等最小引用，不复制研究正文、财务明细、行情、新闻或上传文件；文件内容继续由独立 Blob Adapter 管理。

## Portfolio Research Coverage

把 Portfolio Ledger 当前持仓与 Research Archive Index 按市场和证券代码匹配后即时派生的研究覆盖视图。它只表达是否具备有效核心档案、支持档案、复核日期和来源引用，不复制研究正文、不持久化派生结果，也不产生持仓评分、仓位建议或交易信号。

## Mod Wiki Graph

由全部已发布 Mod 的 Wiki Profile、当前页面 Wiki Subject、研究意图、概念标签和数据能力即时派生的跨 Mod 连接图。它只保存身份与能力引用，不复制行情、新闻、财报或研究正文；新增或更新 Mod 后由 Resolver 自动重算。

## Wiki Subject

跨 Mod 共享的标准研究对象。股票、ETF 与开放式基金必须同时携带对象类型、市场和代码，并使用 `security:CN:300308`、`etf:CN:512010`、`fund:CN:003562` 这类 Canonical ID；名称只用于展示和消歧，不能替代标准身份。

## Wiki Profile

Manifest 1.1 中可选的机器可读声明，描述 Mod 支持的 Wiki Subject 类型、概念和可进入的研究意图。只有声明入口且真实接入 Wiki Handoff 的 Mod 才能成为可跳转目标。

## Wiki Handoff

用户点击顶部关联 Mod 后，由 Desk 创建的短期、用户与 Workspace 隔离的对象交接记录。Shell 只在目标 Mod 完成 Bridge 握手后投递，目标确认接收后消费；长参数 URL 不再承担跨 Mod 状态传递。
