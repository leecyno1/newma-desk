# 供应链瓶颈研究合同

`analysis.industry-chain` 是独立 `instock-industry-chain` Module 的确定性 Action。Newma-Desk 负责数据访问、Agent 编排和证据采集；InStock 只校验点时产业链拓扑、计算关键节点与瓶颈候选优先级、登记 Snapshot，并把结果交给页面或其他 Web 客户端。

## 权威文件

- 输入 JSON Schema：`integrations/newma-desk/schemas/industry-chain-research-packet.schema.json`
- 非真实数据示例：`integrations/newma-desk/examples/supply-chain-research.packet.json`
- HTTP：`POST /api/v1/industry-chain/research`
- Action：`analysis.industry-chain`
- 兼容 HTTP：`POST /api/v1/rotations/supply-chain-research`（仅旧 Adapter）

`integrations/newma-desk/schemas/supply-chain-research-packet.schema.json` 仅保留给 `schema_version=1.0` 的迁移兼容，不是新接入的合同来源。

示例文件只用于合同与联调验证，所有名称、证据和评分均不构成真实供应链研究。

## 研究包语义

2.0 研究包可以只保留可追溯的节点与关系，`layers=[]`、`candidates=[]` 表示证据不足，不要求凑瓶颈评级。结果为 partial，缺少评级的节点分数为 null、不会进入关键节点排序；无瓶颈层的候选仍按悬空引用拒绝。1.0 依靠瓶颈层生成拓扑，仍至少需要一层。输入 notes 以未核验研究说明保留到结果、历史与页面 Context；模型联网失败或资料缺口不能在展示时丢失。

规范研究包使用 `schema_version=2.0`，并明确 `theme`、`market`、`as_of` 和 `chain` 拓扑；引擎仍兼容 `schema_version=1.0`，但会标记为 legacy。`as_of` 是研究的点时截止日；任何 `evidence.observed_at` 晚于该日期都会被拒绝。

处理顺序固定为：

1. 校验证据 ID、来源引用、强度和日期。
2. 根据需求压力、卡点严重度、供应商集中度、扩产难度和替代难度排序稀缺层。
3. 在所属稀缺层得分基础上，根据业务暴露纯度、估值错位、催化时点、财务韧性和证据质量排序候选。
4. 扣除融资稀释、治理、地缘、流动性、炒作、会计质量、周期性和替代设计风险。
5. 输出证伪条件、证据覆盖、限制项和稳定 Snapshot。

评分字段全部使用 `0..5`。字段必须完整且不能出现未知键；证据引用必须指向当前研究包中的真实证据 ID。没有 strong 或 medium 证据的候选会被强制降为 `early_lead`、`confidence=low`。两个以上 strong 证据只有来自至少两个不同 `source_ref` 时才能形成 `confidence=high`；同源强证据会触发来源集中限制并把结果标记为 `data_state=partial`。

## 页面适配器

`/mods/industry-chain` 暴露只读页面适配器 `window.InStockIndustryChainResearch`：

```js
// 让页面通过已授权 Desk Action 执行；未嵌入 Desk 时只回退到同一附属运行时 API。
await window.InStockIndustryChainResearch.analyze(researchPacket);

// 宿主或同页组件已经取得 Action 成功结果时，直接渲染。
window.InStockIndustryChainResearch.acceptActionResult(actionResult);

// 清除当前显示，不删除服务端 Snapshot。
window.InStockIndustryChainResearch.clear();
```

同页组件也可派发 `instock:industry-chain-result` DOM 事件，`detail` 为完整 Action 响应或其中的 `data`。该接口属于 InStock 页面适配层，不扩展 Newma-Desk Bridge Protocol，也不要求 Desk 新增事件类型。

页面初始状态是“请输入主题开始研究”。完整链路为：定义主题 → Agent 整理来源、关系主张与初步评级 → InStock 校验结构、引用和日期 → 按固定权重形成研究排序。Agent 提供评级与候选，并非“不评分、不选股”；引擎未联网核验来源真实性，也未核验原文是否支持关系主张。页面最多展开前 20 家候选，完整数组保留在 Action 返回值。Desk Context 包含关系、前 40 条来源（超限时标记 evidenceTruncated）及快照摘要，不重复传输快照中的完整来源目录。

导入成功或切换历史结果会同步主题、市场和截止日。修改条件、清空、导入失败会清除结果和上下文；清空或切换历史后，旧请求返回不能覆盖当前显示。执行期间锁定输入。错误引用交由引擎拒绝，不允许前端静默删除节点、关系或候选来掩盖错误。

## 输出边界

引擎 2.3.0 / 模组 0.22.0 起，`candidates` 可以为空。没有直接证据支持当前市场的公司候选时，保留关系和层研究，输出 `top_candidate=null`、`candidate_count=0`、`no_supported_company_candidates`，`data_state=partial`；不以虚构证券填满结构。数据服务、模块动作与规范/兼容 JSON Schema 采用相同约束。

采集按宿主初始化信息路由：`runtime.aiExecution=host` 时，通过已握手 Bridge 的 `vibedesk:copilot-open` 转交 newma；本地模式继续调用授权配置提供的 Agent gateway。0.29.0 起可使用协商后的结果回传协议；旧宿主继续显示等待结果并提供手动 JSON 导入。请求不能自动解释为已接收、已完成或已核验。原文取证能力仍需独立验收。

`priority_score` 是版本化研究优先级启发式，不是收益预测、目标价、择时分或买卖信号。`calibrated_backtest=false` 是强制输出。调用方应同时展示：

- `data_state` 与 `limitations`
- `confidence` 与 `evidence_summary`
- `penalty_score`
- `invalidation`
- `snapshot.snapshot_id`

引擎 2.1.0 起，返回 `evidence` 原始主张目录及 `verification`（scope=structure_references_dates，sources_verified=false，ratings_origin=input_packet）。`data_state=complete` 只说明未触发既定降级规则，不表示事实完备或已核实。页面统一显示“结构校验通过 · 来源及主张待核验”。证据强度和置信等级仍源于输入标注，不是独立核验结论。

`snapshot.result.evidence` 保留 chain、sources、layers、candidates，以便下游追溯。旧历史缺少来源目录时明确提示重新导入，不捏造原文。HTTP(S) 引用可点击，文档标识及其他协议仅作为文本显示。关系方向只表示输入关系，不推断依赖比例、价格弹性或因果传导。若需原样复现输入，仍应保留原始研究包；快照不代替原始文件归档。

## 财报主营材料交接（模块 0.20.0 / 引擎 2.2.0）

行业景气通过现有 Desk `modSearch` 仅传源模块、底稿/原表 ID、保存版本和用户/工作区标识。目标页点击读取时复用只读 `/api/research-archive/industry-inputs`，不新增副本存储，不修改原件。跨用户/工作区交接拒绝；底稿或来源移除不回退其他公司；版本变化提示重新核对。

材料选择只接受实际年度、同币种/期间、已采用 PDF 主营表，用户选择具体项目，保留原值、单位、归一化金额、原页摘录及物理页码。不计算依赖比例，不跨产品/地区/渠道混加。

原件尚无可靠披露日期字段，因此不把报告期末或上传日当成点时可见日。用户须确认该表版本的披露日期；早于报告期末、晚于今天或研究截止日时拒绝。确认只在本次会话有效，刷新、切换原表或工作区会撤下确认和旧研究结果。

## 关系人工复核（模块 0.21.0）

复用 Desk `relation-reviews` 用户工作区命名空间，文档 `records` 为 `{schemaVersion:1,entries:[]}`，通过会话授权访问并使用 `expectedRevision` 处理并发。记录追加保存，最多 200 条，可导出；不覆盖旧意见、不自动删除。独立页缺少宿主授权时不能保存。

每条记录包含复核者、时间、快照 ID、关系目标、意见及直接原文。目标保留主题、市场、截止日、两端节点、关系、关键性及引用字段。最新意见仅在完整目标一致且引用目录不缺失时适用；否则为 `needs-review`。支持与反驳必须提供直接来源、日期、定位和摘录，证据不足可以只记录待补材料。所有意见都需要人工确认，资料日期不能晚于研究截至日或今天。

Desk 上下文 `selection.relationshipReviews.selectedReview/relations` 仅包含已保存意见与适用性，不传未保存人工意见草稿。0.26.0 起另设 `agentSuggestion` 表示本次辅助请求与待采纳建议，不得混作已保存结论。关系卡片显示复核状态，反证突出提示。复核不改变引擎评分或 `sources_verified=false`，不能被解释为独立事实认证。

采集任务获得 `companyMaterial` 和固定 `suppliedEvidence`。返回研究包中 `desk-main-business` 被原始事实覆盖，不能由 Agent 改写数值、来源或强度；强度为 `unverified`（未独立核验）。`source_type=user-adopted-filing-row` 不能作为链路或瓶颈层证据，引擎明确拒绝，而不是删掉引用后继续排名。它可用于公司业务事实，关系仍须补直接来源。旧导入包不自动绑定当前材料；页面上下文分别显示待交接材料与本次研究实际使用材料。

## 公开来源正文读取（模块 0.23.0）

Desk 提供 `POST /api/mods/{module_id}/sources/read`，请求为 `{url, quote?, asOf?}`。使用当前 Mod session、实例绑定、已发布版本及 `analysis.read` 权限，不是匿名网页代理。仅支持公开 HTTP(S) 的 80/443 端口，验证 DNS 地址并固定连接 IP，每次跳转重新检查；不转发调用者凭证、代理环境或远端 Cookie。读取限制为 20 秒、2 MB 响应和 60000 字提取文本。

`status` 区分 `readable`、`not_found`、`restricted`、`unsupported`、`unreadable`、`blocked`、`too_large`、`unavailable`、`timeout`、`redirect_limit`。0.23.0 只提取 HTML / 纯文本；0.24.0 增加下述 PDF 文字层读取。需执行 JavaScript 才能显示的内容不能宣称已读取。全文区不明确时 `extractionScope=page`，需要人工检查混入内容；正文截断显式标记。

`publishedAt` 只取网页日期元数据，未识别时为 null，不用 `checkedAt` 代替披露日期。`afterCutoff` 指已识别日期是否晚于研究截止日，未知为 null。可选 `quoteMatch` 仅做空白归一化后的逐字匹配，不判断语义、关系、因果或真实性；始终 `claimVerified=false`，失败访问也不能推出主张为假。

页面最多展开前 120 段，明确展示上限；逐字匹配使用全部已提取文本。关系段落可带入对应人工复核草稿，清空日期与确认，并恢复“证据不足”，由用户核对后明确保存。长于 2000 字的段落不自动截断带入，要求人工摘录；截止日之后的原文不提供历史复核带入操作。

`selection.sourceChecks` 提供本次会话的访问状态；`selection.sourceDocument` 提供最近请求成功读取来源的最多 6000 字摘录及来源、日期、截断标记、不可信文本边界，失败或待读取时为 null。网页内容是待分析数据，不是 Agent 指令。切换研究或用户工作区时清空并取消未完成读取，旧响应不能覆盖新结果。访问状态不单独持久化，只有用户明确保存的复核记录保留摘录；不自动修改评分或引擎核验标记。

### PDF 页段读取（模块 0.24.0）

同一端点增加 `pageStart`（1-based，默认 1，最大 10000）、`pageCount`（默认/最大 10）。PDF 响应上限为 20 MB，HTML / 纯文本仍为 2 MB；接受 `application/pdf` 或 `application/octet-stream` 且以 `%PDF-` 开头的文件。声明 PDF 但返回脚本不视作 PDF，更不执行脚本绕过站点限制。

复用 pypdf 的 layout 文字层提取，每个文本块保留 `page`、`locator` 和原文；物理页不是印刷页码，表格列与脚注仍需打开原页核对。结果含 `documentType=pdf`、`pageCount`、`readPages`、`partialDocument`、`nextPage`、`textLayerMissingPages`。新增状态 `encrypted`、`no_text`、`page_out_of_range` 分别表示加密、所选页无可提取文字、起始页越界。无文字层可能是空白或扫描页，不认定无证据；未实施 OCR。

解析在独立子进程中最多执行 15 秒，取消/超时终止回收；整个请求原有 20 秒上限仍有效。Linux 子进程地址空间上限为 1.5 GB。文本提取最多 60000 字，显示最多 120 块，正文/页段不完整均明确提示。PDF 创建/修改元数据不作为披露日期，`publishedAt` 和 `afterCutoff` 保持 null，由人工核对披露时间。

翻页替换当前来源文本和上下文，不合并成已审全文。`sourceChecks` 与 `sourceDocument` 携带页段范围，原文摘录含物理页定位。逐字匹配仅覆盖已提取页段，同页分块不插入新空白；摘录存在不等于语义支持。人工复核带入同样不保存、不确认、不改评分。

## 已采用财报原文复用（模块 0.25.0）

`GET /api/mods/{module_id}/sources/archive` 以有效 Mod session 确定用户、工作区、实例和发布版本，需要 `analysis.read`。只读投影已有 `earnings-workbench/earnings-workbench/workbooks`，不信任自由填写的身份请求头，不新建文件库，原 `industry-inputs` 信息范围不变。

返回 `{revision, materials}`，仅包含 reported 底稿中 available / verified 且已采用的 discussion / capitalNote PDF 文字层页段。保留底稿 ID/更新时间、来源 ID、证券、期间、原始来源、reportId、物理页/总页数、原文、采用时间与截断状态。这是保存的摘录，不是重新读取整份 PDF；采用时间不作为披露日期。

选定关系后可带入最多 2000 字的逐字摘录；不能把原文中不存在的推断当摘录。带入后默认“证据不足”，清空日期与确认。披露日期不能早于报告期末或晚于研究截止日。保存前再次读取归档，比较材料身份、证券/期间、页码、来源、文本、版本与截断状态；变化、移除或失败则不保存、保留草稿。

复核记录可选 `archiveSource` 保留来源快照，旧记录继续兼容。有归档关联的意见只有材料已成功读取且一致才属于 `current-human-opinion`，否则 `needs-review`；仅针对本次读取版本，不是实时监控。手动修改摘录、来源或页码必须仍与归档一致，否则需明确移除关联并清空证据后填写其他材料。

`selection.relationshipReviews.archivedMaterials` 暴露读取状态、版本、选定原文及非指令边界。切换研究清除原文选择；切换工作区清空目录并丢弃旧请求。归档不自动形成关系判断，不改变引擎评分；只有明确确认、保存的人工意见进入复核历史。

## 原文支持度辅助判断（模块 0.26.0）

复用已有 Agent gateway，默认使用用户配置的 `batch` 路由和 `memoryScope=task`，不新增模型内核。请求只含主题、市场、截止日、两端主体、关系主张、来源/披露日期/定位、最多 2000 字摘录及唯一 requestId；不携带人工判断作为证据，不自动检索或全文取证。提示明确原文是不可信数据，并要求不调用工具；这不是对所有 CLI 的绝对工具隔离保证。

借鉴 [FEVER](https://fever.ai/dataset/fever.html) 的支持/反驳/信息不足分类，返回 `schemaVersion=1,requestId,verdict,explanation,checks,citations,gaps`。主体、方向、时期、主张范围均匹配且有支持引文才可返回 supported；同主体、同时期且有明确冲突与反证引文才可返回 contradicted。缺失事实应为 insufficient。新增用户可核对的 `claimAsOf`（主张对应日），默认研究截止日，不能晚于 asOf。代码保守拒绝 `sourceDate < claimAsOf` 的反证结论；较早日期的否定不能证明后来仍未发生。此规则不代替摘录所述时期、披露日期或主张日期的人工核对，也不能覆盖全部时间语义。

每条引用须对应输入中的连续原文，请求标识须一致；验证返回结构、维度一致性和引文存在，不保证语义判断正确。0.27.0 起匹配仅兼容空白与 ASCII/英文直弯单双引号，实际返回和保存的引文还原为源文本；数字、正负号、词语、中文引号替换等不放宽。错误返回进入可修正的 JSON 面板，保留当前任务，不自动重跑；人工导入/编辑标记为 `execution.resultEntry=manual-json`。网络观察中断保留已知 taskId，可继续查看同一任务；创建响应丢失提示先检查任务，避免盲目重试。

newma 挂载模式仅发送宿主请求，不回退本地 CLI。0.26.0 / 0.27.0 需要用户粘贴 JSON；0.28.0 增加下述可选回传。“请求已发送”不表示“判断完成”。输入或工作区变化撤下建议，并请求取消已知本地任务；取消结果仍需在任务页核对。迟到返回不能覆盖新输入。

明确点击“将建议带入草稿”才填写意见与依据，且取消人工确认勾选。保存仍须人工确认并通过现有归档刷新/并发检查。可选 `agentAssistance` 保存绑定输入、建议、执行来源与时间；输入变化不再沿用旧来源标记。人工后续修改可与建议不同，最终决定以人工意见为准。不自动提高证据等级、不改分、不标记来源已核实。

## 人工决定与辅助返回对照（模块 0.27.0）

已保存意见新增展开对照，分别呈现人工决定/依据、采用的辅助建议/引用/缺口、主张与资料日期、任务/适配器/模型（有记录时）和带入时间。只比较 verdict 是否一致，不把文字编辑当作判断改变。人工改变 verdict 但仍原样保留系统生成的模型理由时，要求修改判断依据后才允许保存。

本地完成任务保留 `originalResponse={raw,truncated,receivedAt}`，最多 24000 字符，超长明确标注截断；无论是否通过 JSON 校验，都不覆盖原始返回。用户修正并采用的 `result` 与原始返回分列，手动导入标记仍保留。新增 `acceptedAt` 和 `appliedAt` 分别表示本页校验/带入时间，不冒充模型生成时间。旧记录没有原始返回时明确缺失；newma 手动导入不能独立确认为宿主模型原话。

辅助来源需通过结构、引用及人工记录绑定校验；不完整或不匹配时显示来源不可用，但保留人工意见，不把整个工作区当空库。页面上下文提供 `selectedReview.assistanceComparison`，区分 same-decision/human-overridden/unavailable/none；不重复携带最多 24000 字原始返回，只给保留状态与时间。原始返回仍可在页面展开和记录导出中追溯。

真实材料样例位于 `tests/fixtures/industry-chain/asml-euv-2022.json`。来自 ASML 2022-03-30 文章的少量摘录，覆盖采购关系、未披露份额/排他性、计划与已完成交付；仅评价所给片段，不证明历史网页版本未变或当前供应关系。样例期望不等于模型已达到稳定准确率。

## 可选 newma 辅助判断回传（模块 0.28.0）

Desk 与宿主协商 `agent-result-v1`，模组声明 `agent-result`。只有双方支持时 init.runtime 才包含 `resultMessage=vibedesk:agent-result`；其他宿主沿用手动导入。0.28.0 只接通原文辅助判断，主题采集在 0.29.0 接入。

自动返回仍通过原有业务请求、输入绑定、引用匹配和支持度校验，不自动保存。`execution.mode=newma` 与 `originalResponse.origin=newma` 区分宿主原始回复；人工导入继续标记 manual-json。等待中修改输入、切换工作区、停止或先手动导入后，迟到的自动返回不能覆盖当前结果。停止等待不意味着取消宿主任务。

默认宿主观察 180 秒，模组等待 190 秒；超时保留手动导入入口，明确任务状态未知，不自动重试、不回退本地。真实 newma 宿主尚未对接；Desk 侧通过模拟父宿主 + 实际 Desk + 实际 InStock 嵌套页面验收，不能视作真实模型运行。

## 主题采集与原任务恢复（模块 0.29.0）

- 支持自动回传的宿主返回研究包后，继续校验请求主题、市场、截止日、引用与结构；固定财报业务事实仍以原始 suppliedEvidence 为准，不允许模型改写。旧宿主手动导入路径保留，不调用本地 CLI。
- 本地采集保留任务标识。轮询失败或等待超时进入 pending，可“继续查看原任务”；不会取消并重建任务。创建响应丢失或 5xx 时进入 unknown，不推测任务不存在；须先核对任务，再显式解除本页等待。
- “停止采集等待”仅停止观察，不取消已创建任务。创建响应晚到时仍可取得同一任务号并继续查看。切换输入、来源或工作区会撤下旧状态并提示旧任务未取消；刷新页面后的恢复尚不支持，需在 Agent 任务页核对。
- 自动输出格式或身份不符时保留返回文本，提示修正后导入，不引导盲目重跑。手动导入本次采集结果仍须匹配主题/市场/截止日；先完成手动导入后，迟到自动回复无效。
- 上下文 selection.collectionTask 提供执行模式、任务号、请求条件和状态，不携带请求凭证；用户/工作区缺失时不回退到默认身份启动任务。
- 自动采集结果仍仅为结构通过、事实待核验，不提升来源强度或替代人工复核。

## 刷新恢复与任务归属（模块 0.30.0）

- “刷新后找回采集任务”读取当前用户、工作区、模组与采集能力的最近 20 条记录。选中后使用同一个任务号继续观察；已完成任务直接重新校验原返回，不创建模型任务，不在浏览器另存研究材料或凭证。
- 恢复的是创建时的主题、市场、截止日和财报材料快照，页面及 Agent 上下文明确标为历史任务。不会自动确认当前财报材料、提升证据强度或修改原件；修改条件会撤下恢复状态。
- 服务端创建任务时独立持久化用户/工作区归属，不能以提示词上下文中的工作区冒充归属。列表、详情、事件流及取消均核对归属。Copilot 查询/取消同步携带创建时身份。
- 旧任务数据保留，但没有可信归属的旧记录不自动认领，任务查询返回 404。既有客户端调用新建任务的详情/事件/取消接口时，必须携带与创建一致的 X-User-Id / X-Workspace-Id；默认本地身份只对应默认本地任务。
- 这是现有可信本地网关的工作区隔离，不是新增登录鉴权。身份头仍依赖可信调用方；对外多租户部署必须另由认证入口绑定身份，不能直接信任公网传入的身份头。
- newma 历史任务查询尚无协议，提示到宿主查原任务并导入，不会自动回退本地。40 项页面回归覆盖刷新、原任务续看、历史材料标识、错误用途拒绝、工作区切换与宿主不回退。

## 候选关联证据检查（模块 0.31.0）

- 候选区直接展示关联反证、证据不足、意见失效、尚未复核、记录不可用和无关联关系。汇总基于候选 layer_id → layer.node_id → 与节点直接相连的关系，不跨多跳传播风险，也不将同一主题的所有公司视作受影响。
- 只使用当前证据版本匹配的最新已保存人工意见；未保存草稿和 Agent 建议不计入支持数。引用变化则待复核，读取失败则不可判断，不保留绿色状态。即便所有直接关联关系获人工支持，也不等于公司暴露已核实或形成投资结论。
- 每张候选卡可展开逐条检查并进入对应关系复核。原优先级评分、排名、证据强度不变。Agent 上下文 selection.relationshipReviews.candidateChecks 提供相同的状态、关系清单与人工支持计数。
- 参考 [Anthropic thesis-tracker](https://github.com/anthropics/financial-services/tree/main/plugins/vertical-plugins/equity-research/skills/thesis-tracker) 将反证与正向证据同等跟踪；沿用既有存储/复核体系，无新依赖。
- 重新读取 ASML 官方 [Making EUV: from lab to fab](https://www.asml.com/en/company/stories/2022/making-euv-lab-to-fab)，新增“EUV 无需高真空”的明确反证测试。官网引文真实，测试候选/评级为合成数据；验证的是人工意见进入候选提示的链路，不是模型语义准确率或真实证券结论。

## 公司档案交接与人工复核（产业链 0.33.0 / 公司档案 0.20.0）

- A 股候选携带快照、证券代码和截止日进入公司档案。Desk 内通过现有受校验导航消息留在同一个宿主、工作区；只放行产业链到公司档案这一跨套件路径，不开放任意模组跳转。独立运行仍打开独立公司页，没有工作区会话时不读取私人意见。
- 公司档案复用证券快照中的直接关系与原文目录。人工意见通过 `POST /api/mods/instock-stock-research/sources/chain-reviews` 单独读取，不污染共享快照或计算评分。接口要求本模组当前版本、实例绑定且具有 `analysis.read` 的会话，只使用签名用户/工作区，不接受请求指定其他身份。
- 请求仅提供主题、市场和直接关系两端；接口仅返回这些关系最新追加的已保存人工记录及其所需的当前归档页段，不返回其他研究或模型原始回复。与页面相同的公共匹配逻辑核对完整关系、引用、日期和归档版本。JSON 对象字段顺序不影响版本一致性。
- 公司页展示反证、证据不足、未复核和旧意见待复核，引用原文、定位、日期和人工理由可展开；归档读取失败不能沿用旧归档意见。切换工作区、换证券和读取失败撤下旧意见，迟到返回不得重新填入。
- `data.relationshipReviews` 向 Agent 提供相同的工作区读取状态、记录版本、直接关系和人工意见。人工支持不证明公司暴露成立，关系反证不等于财务受损；无多跳传播，无自动交易或评分修改。
