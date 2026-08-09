# Newma-Desk Domain Context

## Mod Suite

由同一个导入项目提供的一组相关 Mod 页面。Mod Suite 只声明一次完整项目身份、所属投资栏目、运行环境和共享能力；Suite Discovery 会把页面展开为独立 Mod，使现有权限、数据路由、Agent Context 与运行时隔离继续按页面生效，但不得改变项目边界。

## Navigation Descriptor

导入项目提供给 Newma-Desk 的导航声明。它描述 Mod Suite 的所属栏目、完整项目分组、页面顺序、标签、图标和设置入口，不包含用户的拖拽、冻结、隐藏等个人偏好。

## Investment Column Identity

由 `navigation.project` 声明、并由同一 Mod Suite 的全部展开页面继承的稳定栏目身份。其 ID 必须属于十四个核心投研栏目或 `other`；它决定一级导航归属，但不充当完整项目的设置、数据或 Agent 作用域。

## Complete Project Identity

由 Suite ID 和同 ID 的 `navigation.directory.id` 共同声明。它代表不可拆分的完整来源项目，是项目设置、统一数据路由和 Agent Workspace 的稳定作用域。同一 Suite 的所有页面必须继承相同栏目和完整项目身份。

## Project Rail

Newma-Desk 左侧只显示十四个核心投研栏目与“其他”的中文方形短标。选择栏目后，二级 Project Panel 按完整来源项目分组，呈现项目名称、全部页面和项目设置入口。

## Suite Discovery

读取 Navigation Descriptor 并生成独立 Mod Manifest 的 Module。Git / 本地文件与 `.well-known/newma-desk-suite.json` HTTP 声明是该 Seam 上的不同 Adapter；旧 `.well-known/newma-dock-suite.json` 与 `.well-known/vibedesk-suite.json` 在兼容期作为回退入口。生成后的 Manifest 继续进入既有 Mod Registry。

## Navigation Compiler

把已发布 Mod Manifest、Suite 默认导航和 Preference Overlay 编译成 Desk 唯一导航树的 Module。一级栏目、二级完整项目分组、项目设置和当前路由都应读取同一份编译结果。

## Preference Overlay

只记录用户相对默认导航所做的变化，包括排序、冻结和栏目重命名。页面只能在所属完整项目内排序，不能移动到其他项目或栏目；已删除页面和项目的失效偏好由 Navigation Compiler 清理。

## External Mod Runtime

在 Newma-Desk 仓库之外运行、但由 Desk 注册、检查或在本地开发时启动的 Mod 运行环境。External Mod Runtime 可以包含一个或多个工作区、进程和 HTTP 入口；不可用时必须独立降级，不能影响 Desk 核心运行时。

## Integrated Domain Runtime

把第一方 Research / Trading Mod Suite 收敛到 Desk 核心交付物中的运行方式。该 Module 只暴露经过权限筛选的领域 Interface，复用 Desk Agent、模型设置、调度和确认能力；生产环境使用一套固定依赖，不加载嵌套工作区的虚拟环境，也不启动上游自带 Agent、频道或后台任务。

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

## Research Archive Index

由 Desk 从各研究 Mod 已有的 Desk Storage 文档中派生的统一研究档案索引。该 Module 只返回来源 Mod、档案 ID、标题、证券身份、状态、时间与标签等最小引用，不复制研究正文、财务明细、行情、新闻或上传文件；文件内容继续由独立 Blob Adapter 管理。

## Portfolio Research Coverage

把 Portfolio Ledger 当前持仓与 Research Archive Index 按市场和证券代码匹配后即时派生的研究覆盖视图。它只表达是否具备有效核心档案、支持档案、复核日期和来源引用，不复制研究正文、不持久化派生结果，也不产生持仓评分、仓位建议或交易信号。
