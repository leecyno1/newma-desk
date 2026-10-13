# Changelog

本项目的重要变更记录。历史版本（1.0.0 及以前的阶段总结）见 `docs/history/CHANGELOG.md`。

## [2.2.2] - 2026-09-21

覆盖 2026-09-20/21 的 UAT 遗留缺口闭环（五项，`18f68a6`…`8961e96`）、冒烟测试基线全绿恢复（`819983d` + `42c749b`）与 09-22 追加的详情页研究画像边界清理（`e9fbab5`）、服务重启上线与经理任期补数。**最终冒烟批量验收 121/121 全绿。**

### Fixed

- **净值口径与 lineage 全链路统一**（09-20 `18f68a6`）：`get_fund_nav` 与 `get_fund_performance` 的口径列选择加有限正数过滤——adj_nav 列若只剩 0/负值/inf 的"假活"值，不再被误选为业绩口径，按 adj>accum>unit 顺延到首个真实可用列；逐行守卫拦截非有限净值（NaN/Inf 不落库不进序列）；输出守卫让 `unit_nav`/`adjusted_nav` 非有限时置 None。生产库抽查证实复权口径可中和分红跳空（019510.OF 单位净值区间收益 -2.90% vs 复权 -0.58%）。顺带纠正 `fund_nav_dedup_smoke` 自始写反的降序断言（实现自始 ASC，前端 NavChart 按返回顺序绘图需要升序）。
- **分红数据接入复权计算闭环**（09-20 `6f192c6`）：新增 `GET /api/funds/{code}/dividends`（本地 `fund_dividends` 优先，缺失回退 tushare `fund_div`，从未分红返回空列表并带 source lineage）——此前 530 基金 4764 条分红事件只写不读，复权链路缺最后一环。
- **基金池成员标识混用归一**（09-20 `bd66f86`）：系统审计确认 UUID/代码混写的唯一真实缺口是 `add_fund_to_pool`——修复为入库统一归一为 wind_code（经 funds 表反查），存在性检查用别名集合（wind_code/UUID/原始值）去重，同一基金的两种历史别名不再重复入池；生产库仅 4 条测试残留，无需回填。
- **启动 DDL 无锁超时**（09-20 `b7904d3`）：`init_database` 建表前置 `SET LOCAL lock_timeout = '5s'`——ALTER 需 ACCESS EXCLUSIVE 锁，若被长读事务阻塞（此前真实观测过启动卡死），5 秒后放弃而非无限等待；语句全部幂等，读事务结束后下次调用自然补齐。Redis/Mongo/Qdrant 降级路径核实已内建且有冒烟覆盖，无需改动。
- **前端 UAT 四项展示缺陷**（09-21 `8961e96`）：① 比较页快照请求补 `include_attribution=true&live_attribution=false`（复用已存归因证据 history_reused，不触发现场计算），归因证据不再恒显"尚未运行"占位；② 纪要证据层级优先读 `evidence_scope`（fund_specific/manager_level），基金级/经理级标签不再落入"其他"；③ 短样本仅缺滚动窗口时回撤轨迹照常展示（派生序列服务短样本分支补 `history_start/end`，前端另有 fallback）；④ 年度图同年各基金净值截止日不一致时不再直接并柱（新纯函数模块 `compare/yearlyChartData.ts`：只保留多数截止日组，并列取最新），表头显式披露截止日区间，YTD 单元格标注"截至 日期"。

- **真实数据缺口已闭环**（09-22）：`fund_manager_detail_smoke` 曾因 `managerAssessment` 需 ≥1 在管任期 `performance_snapshot=available` 而红（全库 84962 条任期仅 29 条 available）。注意 `GET /api/data-sync/managers/{id}` 只 upsert 经理与基金基础信息、**不写任期绩效快照**；正确入口是 `backend/scripts/sync_fund_manager_tenure.py --manager-id`（`FundManagerTenureSyncService.sync_manager`，实时 Tushare 净值+基准落库）。对张仲维执行后 6 条在管任期全部 available（16233 净值点、6304 基准点），smoke 转绿。

### Changed

- **最后一处 MongoDB 依赖移除（09-24/25 `172bbd2`，用户确认）**：`scoring.py` 的 scores 集合读写（评分历史恒空、旁路写入恒跳过，从未产生真实效果）删除后顺势彻底清除——`service_registry` 删 `get_db` 连接器与重试状态、`init_services` 删 `mongo_db` 参数；`local_research_folder_repo` 删零消费者的 Mongo 版 repo 类（约 200 行）；`managers.py` 死解包与 `main.py` 启动探测块清理；`recalculate` 的 `save_to_db` 参数与其撒谎的 `"saved"` 返回移除（明示落库由评价快照管线负责）；删 `service_registry_mongo_retry_smoke`、`.env.example` Mongo 段。**后端运行栈收敛为 PostgreSQL + 本地缓存，零 Docker / 零 Mongo / 零 Qdrant，批次 151/151 全绿。**
- **报告链路去 Docker 化：读写全部归一 PostgreSQL**（09-23/24，用户确认 Docker 从来不是需求）：① `/api/research-reports` 的 POST/PUT/DELETE 从 MongoDB 改写为 PG（`PostgresLocalResearchFolderRepo`，新增 `delete_report` 与 `embedding_status`/`embedding_source` 两列幂等 ALTER）——修复"上传报告写 Mongo、列表读 PG 互不相通"的存储割裂，上传后立即可检索（闭环实测通过）；② AI 报告 `/api/reports/history` 从读 Mongo（从未运行、恒返回空）改为读 PG，报告历史首次真实可用（000390.OF 实测返回 1 条）；详情路由删除 Mongo 兜底，非法/未知 ID 统一 404；③ AI 报告生成管线中三处吞错的 Mongo 读（基金纪要、经理纪要、经理画像）改为 PG repo 等价方法，删除三处旁路 Mongo 复制；④ 快照服务删除 Mongo 优先分支（PG 唯一来源）；⑤ 删除四个零消费者的 Qdrant 孤儿端点（`batch-import`/`search/status`/`search/warmup`/`search/similar`）、`vector_db_service.py`（零引用）与对应 3 个冒烟（其一为假绿：端点吞 Qdrant 异常返回空）；⑥ 删除 `docker-compose.yml` 与 README Docker 段（脚手架遗留，从未是部署方式）；⑦ `reports_mongo_degrade_smoke` 改写为守护 PG 语义。**后端批次 152/152 全绿且不再依赖 Docker**。
- **后端冒烟基线恢复**（09-22 `42a7e32`）：后端批次 136 过/19 败 → **152 过/3 败**。16 项修复：12 个测试补 sys.path 注入头（直接运行时 `import services` 失败的整族）；`advanced_investment` 与 `comparison_matrix` 两个冒烟改为从 `metric_snapshots` 动态选基（原硬编码 `000002.OF`/`000007.OF` 不在本地库）；`attribution_repo` 由 SQLite 内存库改为真实 PG 夹具 + finally 清理（repo SQL 为 PG 方言 `::text`/`jsonb`，SQLite 无法承载，沿用池身份冒烟先例）；`standardized_classification_adapter` 测试桩补 `limit` 关键字参数（接口已扩展，桩签名漂移）。剩余 3 项（`research_reports_crud`/`vector_db`/`semantic_warmup`）为 Docker 环境依赖：报告写路径走 MongoDB、向量检索走 Qdrant，daemon 未运行时必然失败，已在交接文档标注启动方式。
- **基金详情页研究画像边界确认与死代码清理**（09-22 `e9fbab5`，用户确认）：删除 `FundDetailClient.tsx`（357KB、零引用——e3478bb 切换 SimpleFundDetailClient 后仅剩 11 个冒烟的源码锚点在维持假绿）与其唯一调用者 `app/api/funds/[id]/route.ts`（每次请求预取销售规则告警/同类分位/买前证据却无人渲染）。购买门禁 UI 不复活：购买路径在 /market、/analysis/fund、/evidence-coverage 与正式研究复核报告（服务端硬门禁）中提供；11 个冒烟守护迁移至现行边界（详情页禁购买入口、类别专属评价方法卡、同类样本门禁、专业评分就绪才渲染、材料证据与 review-events 反向守护重定向），删除 `fund_detail_research_semantics_smoke`（全部断言守护死组件专属文案）。`local_real_flow_smoke` 的详情步骤同步改走现行流程（/funds/{code} 页面 + research-snapshot，buyEvidence 由 compare-matrix 步骤逐基金验证）。
- **服务重启上线**（09-22，用户授权）：后端 `launchctl kickstart` 加载全部新代码（分红端点实测本地源返回、派生序列带真实起止日）；前端 bootout → `next build` → bootstrap（从 `~/Library/LaunchAgents/` 加载，从仓库路径 bootstrap 报 error 5）。浏览器 DOM 级验证 #29 修复真实生效：两只测试基金 2026 年净值截止日不同（9/18 vs 9/11），新逻辑不再并柱、表头披露"各基金净值截止日不同（2026-09-11 ~ 2026-09-18）"、逐基金"截至"标注显示，控制台零错误。
- **3000 端口抢占夺回**（09-22）：前端停服构建期间被 newma-desk `dev-stack.mjs`（自有 LaunchAgent `com.newma.desk.dev`）的 fund-analysis **dev 模式捆绑副本**抢占 3000——与此前 8005 被抢占同款冲突。按既定解法只杀占用端口的子进程树（不动 dev-stack 本体，它还管 8011/8788/3001 等其他项目端口），立即 kickstart 本项目前端夺回端口；隐患仍在：本项目前端任何停服窗口都可能再次被抢占。
- **冒烟测试基线全绿恢复**（09-21 `819983d` + `42c749b`）：批量跑 `scripts/*.mjs` 发现 22 个失败，经三组并行甄别确认为 21 个历史重构漏同步的陈旧断言 + 1 个真实数据缺口，全部处理后批量验收通过。修复模式遵循 5077473 确立的"边界语义不变，仅换锚文本"惯例：锚点跟随 `/sales-rules → /evidence-coverage` 路由归一与 `MATERIAL_EVIDENCE_VALIDATION_FAILED` 错误码改名、discover 三层组件拆分、`buy-evidence → research-evidence` 与 `pre-purchase-report → research-review-report` 实现搬家（原路径只剩转发 stub）、净值 adj 优先口径、同类样本下限分类化（`category_specific_peer_metric_proxy`）。两个 smoke 按现行边界改写：`manager_buy_before_evidence`（经理页纯研究视角禁购买入口 + "补充名下基金材料"引导必须落到逐基金核验页 + 经理分析报告购买口径完整保留）、`fund_pool_sales_rule_gate`（自建 rejected 夹具 → 测 409 门禁 → DELETE 自清理，不再依赖历史残留池数据）。5 个 smoke 补进 acceptance staticChecks 接线（其"被收录"断言此前从未成立）。

### Removed

- **`wind_service_no_implicit_mock_smoke` 删除**（09-21 `42c749b`）：守护对象 `backend/services/wind_service.py` 与 `backend/wind_service/` 已随 16a0ad8（v2.0.0 四代合并）作为一代 Wind 死资产删除，该 smoke 为漏网；"数据层不得隐式 mock"的守护由 Tushare `strict_no_mock=True`（`real_data_sync_strict_gate_smoke`）与 `style_exposure_no_mock_smoke` 等现行 smoke 承担。顺带清理 `backend/wind_service/__pycache__` 孤儿字节码残骸。

## [2.2.1] - 2026-09-11

修复上线迭代遗留的调度环境缺陷，并重建项目上下文记忆（历史 quest 归档 + 交接文档校正）。

### Fixed

- **launchd 极简 PATH 导致调度任务长期失败**（09-11 `629be0a`）：launchd 启动进程时 PATH 仅 `/usr/bin:/bin:/usr/sbin:/sbin`，不含 `/opt/homebrew/bin`，而 `npm`/`node`/`psql`/`pg_dump` 全在该目录。后果是自 2026-08-19 上线起每个调度日固定 5 个任务失败——4 个 daily + 4 个 weekly 同步任务 `exit=127`，`ops:backup-postgres` **静默 `exit=1`**（`command -v pg_dump` 在 `set -euo pipefail` 下命令替换失败即退出，连一行错误都不打印），连续 22 天无成功备份。三处修复：
  - `scripts/scheduled_update.sh` 与 `scripts/backup_postgres.sh` 顶部补全 Homebrew PATH（`/opt/homebrew/bin`、`/usr/local/bin`）后 `export`，不在 plist 写死环境，终端与调度共用同一脚本；
  - `backup_postgres.sh` 的 `pg_dump`/`pg_restore` 回退赋值改为 `command -v ... || true`，二进制缺失时打印含 `PATH` 的明确错误再 `exit 1`，杜绝静默失败；
  - `package.json` 中 13 个脚本由裸 `python` 改为 `.venv/bin/python`——macOS 与 launchd 都没有 `python` 命令，这是 PATH 修好后暴露的第二层 127（与 `update_fund_*.sh` 既有的解释器候选约定一致）。
- **M6 验收方法论缺口**：原验收全程在终端手工执行（shell 自带 homebrew PATH），因此完全掩盖了上述缺陷——`runbook.jsonl` 显示 20 次 18:15 调度时点 20/20 全败，只有两个非调度时点的手工执行成功。修复后用 `launchctl kickstart -k gui/$(id -u)/com.fund-analysis.scheduled_update.daily` 在**真实调度环境**验证：9 个 daily 任务 8 个 ok，含备份产出 `fund_analysis_20260911_234226.dump`（约 35MB，`pg_restore -l` 关键表自检通过）与两个曾 127 的 npm 补数任务；`research:sync-manager-identities` 补跑 ok（96s），`manager_profiles` 127→130。weekly bucket 另抽样补跑 `funds:sync-product-profiles -- --limit 100` ok（125s，`requested=100` / `failed=0`，资产配置与持有人结构真实写入），确认 weekly 路径同样恢复；剩余三个重量级 weekly 任务留给周日 20:00 定时器。`research:sync-ima` 一度被服务端拒绝（`skill auth failed`），09-12 复核后确认**不是本地凭证失效**：用户提供的 clientId/apiKey 与 `~/.config/ima/` 中 08-14 起在用的那组逐字节相同（md5 一致），同一组凭证 09-11 23:42 被拒、09-12 08:03 通过，属 IMA 服务端授权状态问题；用户在 IMA 侧重新授权后经调度脚本执行 ok（30s，226 份纪要全部命中云端同名文件，新增 0 / 失败 0）。**至此 9 个 daily 任务全绿。**

### Added

- **历史 quest 恢复归档**：2026-09-08 Qoder IDE 的 `cli_ws_migration` 只迁移工作区产物、未导入会话正文，导致本项目历史 quest 从 IDE 列表消失。新增只读恢复脚本 `../.quest-recovery/export.py`（仅读 CLI transcript、仅写 `restored/`、不触碰 Qoder 数据库），导出 12 个 quest 为可读 Markdown 并生成 `INDEX.md`；脚本具备幂等性（重跑前清理上一批归档，避免会话行数增长导致 tag 变化后残留过期文件）。

### Changed

- **`QODER_HANDOFF.md` 校正过期结论**：第 8 节由「尚无统一编排层，建议实现 `scheduled_update.sh`」改为「已于 M1 落地，不要再重复实现」，并新增 8.1 记录调度真实状态；第 2 节补充 launchd 常驻形态、端口归属排查、极简 PATH 与手工兜底启动；第 5.1 节补充只读核实的数据现状与备份还原点；第 11 节 M1 改为已达成、M3 解除阻塞、M6 标注验收方法论教训，优先级重排为「核对 weekly 定时器首次全自动运行结果」居首（原首项 IMA 授权已于 09-12 关闭）；新增第 13 节记录 quest 恢复的根因与归档位置。

## [2.2.0] - 2026-09-10

覆盖 2026-08-19 下午至 2026-09-10 的迭代：AI 报告链路打通、LLM 换用 MiniMax-M3、UAT 修复、投研信息密度重构、数据层关联加固与报告导出。

### Added

- **AI 报告前端闭环**（08-19 `93caf62`）：报告 Markdown 渲染、经理名可点击链接、生成入口集成，经理研究链路最后一公里打通。
- **LLM 综合分析接入 MiniMax-M3**（08-19 `3ebd6e4`）：openai-compatible 协议，四件套配置在 `.env.local`（`LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL`）；`GET /api/reports/ai-health` 校验配置状态。
- **组合目标配置 UI + 基金详情页 AI 报告入口**（08-20 `341df7e`）。
- **报告详情页导出 Word / PDF**（09-10 `105454e`）：纯前端零新依赖，复用已渲染的 `.report-markdown` HTML——Word 走 msword Blob + UTF-8 BOM（中文不乱码），PDF 走 `window.print()` + `@media print`（仅打印正文、表格与标题避免跨页）。绕开后端无 PDF 库与 `export.py` 的 `report_id` 兼容局限。

### Fixed

- 全功能自测暴露的四处缺陷（08-19 `92d5aa7`）。
- UAT 反馈五项：组合监控误报、基准静默缺失、评分联动（08-19 `e2029da`）。
- MiniMax-M3 接入伴随的经理报告数据错配与 `<think>` 段泄漏（08-19 `3ebd6e4`）。
- 定向补数暴露的分类基准映射两处缺陷：映射排序必须 `updated_at` 优先于 `effective_from`（08-20 `e6b13da`）。
- **数据层关联加固收尾**（09-08 `7d88375`）：`holdings` / `factor_exposures` / `performance_attributions` 补 `fund_id`（经 `wind_code` 反查 `funds.id::text`）与 `updated_at`，新增 3 个唯一索引，三个 repository 的 `ON CONFLICT` 与索引精确配套；`managers.updated_at` 设默认 `NOW()`。同时**回退** `research_reports.id` / `report_id` 的 UUID→TEXT 改动——`local_research_folder_repo.py` 硬编码 `CAST(:report_id AS UUID)`，而 `CREATE TABLE IF NOT EXISTS` 不会迁移已存在表的列类型，改 TEXT 会造成代码定义与生产库不一致并触发 `operator does not exist: text = uuid`。
- **AI 报告防重 + 标题去 ID 尾巴 + UAT 遗留核实**（09-09 `eb741d2`）：清理存量重复 16 行（29→13，每组保留最新，已全表备份），加唯一约束 `(target_type, target_id, report_type)`，`_save_report_to_postgres` 改为 upsert 覆盖式；经理复合 id「名|性别|学历」在详情/列表 API 增加 `displayTargetId` 用于展示美化，`targetId` / `managerId` 保留原值以维持跳转键完整。核实结论：任期 `fund_code`/`manager_id` 零空值零孤儿（已消解）；经理证据为空的根因是 `manager_profiles` 覆盖率仅 1.8%（127/7218），属数据覆盖天花板而非缺陷。

### Changed

- **去除全部页面宣传性大标题**（08-19 `5077473`）：h1 + 副标题 + eyebrow 移除以回归投研平台信息密度；实体内容标题（基金名、经理名、公司名、报告标题）与紧凑形式的边界语义（如「仅同类比较」）保留。
- **同步至 Newma-Desk**（08-22 `82ee4f3`）。

### Removed

- **Barra `factor_exposures` 死表依赖清理**（09-10 `198fdd1`）：清空生产库测试残留（`000001.OF` 手填示例 10 行 + `SMOKE.FACTOR.REPO` 冒烟数据 2 行，全表 12 行已备份为还原点），表结构保留；`backend/routes/funds.py` 移除对死表的 `get_exposures` 查询与未使用的 `factor_repo` 引用，`barra_exposure` 字段保留空对象以维持接口契约。真实风格暴露源为 `holding_style_snapshots`。

## [2.1.0] - 2026-08-19

### Added — 上线迭代 M1/M2/M4/M5（设计见 `docs/plans/2026-08-19-final-launch-iteration-design.md`）

- **M1 调度通电与本机生产化**：`scheduled_update.sh` 修复 macOS 无 flock 的根因（mkdir 原子锁 + PID 陈旧检测）；新增 `backup_postgres.sh` 每日备份（自动匹配 PG 大版本）；launchd 常驻模板（backend 8005 / frontend 3000，KeepAlive 自愈，工作日 18:15 / 周日 20:00 调度）。
- **M2 评价数据攻坚**：`save_evaluation_snapshots.py` 每日评价快照积累（连续性优先选基，已入 30+ 只）；风格快照 359 条、持仓覆盖 394 基金季度；风格漂移链路首次真实产出。
- **M4 组合构建 MVP**：Portfolio/Target/Holding/Snapshot 四表迁移；准入推荐就绪校验、等权/自定义权重（单只 ≤40%）、三合一穿透（重仓股重叠/风格暴露加权聚合/净值相关性）；`/portfolio` 构建器页面 + 8 转发路由。
- **M5 基础回测 + 组合监控 + 交易清单 + ADR-0004**：以当前权重回看历史的解释性回测（累计/年化/回撤/波动 + 分类映射基准对比 + 样本不足拒答 + SVG 净值曲线）；组合监控（同类组目标偏离阈值 5% + 成分风格漂移 + 再平衡提示）；交易清单（目标 vs 当前持仓差异 → 申赎建议研究输出，不落库不执行）；`ADR-0004` 定位演进（选基工具 → 专业基金研究工作台，交易清单属研究输出边界）。
- **M6 上线验收**：launchd 巡检/调度睡眠唤醒补跑验证/备份恢复演练（7 表行数一致）全通过（报告见 `docs/plans/2026-08-19-m6-launch-acceptance-report.md`）；发现唤醒补跑时序下备份内容为旧时点的异常，`backup_postgres.sh` 新增关键表内容自检（`pg_restore -l` 校验 funds/fund_nav/portfolios，缺失即失败）防复发。

### Changed

- `fund_research_scope_smoke` 禁令语义演进：移除对 `api/portfolio` 的全局禁止，保留组合优化/模拟/决策与投资决策禁令（与 ADR-0004 对齐）。
- `portfolio_construction_smoke` 扩展覆盖 M5 回测/监控/清单边界断言；总验收 67 项全绿。

## [2.0.0] - 2026-08-18

### Removed — 四代合并去重

- 删除旧独立前端 `frontend/` 整目录（迁移参考使命完成，业务实现已全部由根目录 Next.js 承载）。
- 删除一代 Wind 数据链路：`backend/wind_service/`、`services/wind_service.py`、`service_registry` 的 Wind 分支与 `get_wind_service()`。数据源统一为 Tushare。
- 删除一代筛选/评分前端链路：`/screening`、`/sync` 完整页面，`app/api/screening`、`app/api/scores`、`app/api/sync/wind` 转发路由，`backend/routes/screening.py`，`lib/scoring.ts`、`lib/wind.ts`、`lib/score/`。
- 删除 backend 根目录运行残留：`batch_sync*` 日志、`restart_8005.log`、`generated_reports/`、`init_system.py`、`check_progress.py`、`test_vector_db.py`、`final_report.md`、`VECTOR_DB_SETUP.md`。
- 归档一代/二代文档至 `docs/history/`：PROGRESS、CHANGELOG(旧)、ARCHITECTURE(旧)、DEPLOYMENT、DOCKER、FAQ、FINAL_SUMMARY、PHASE4/5_SUMMARY、FIXES_SUMMARY、PROJECT_COMPLETE、SUMMARY。

### Changed

- 工作区壳「数据与方法」入口与基金详情净值刷新指引从 `/sync` 改指 `/evidence-coverage`（数据健康页承接调度 runbook 与待确认计数）。
- 旧路由（investor-selection / sales-rules / alerts / pools / rankings / overview）保留薄重定向页，历史 AI 分析报告中的旧链接经 `canonicalResearchHref` 映射到新研究平台页面。
- 更新静态 smoke 断言以匹配页面删除后的现实；修复 `professional_fund_research_architecture_smoke` 中断言 AppNavigation 的历史失效（layout 已使用 FundWorkspaceShell）。
- 重写 `ARCHITECTURE.md` 为当前主干架构；更新 `README.md` 移除 `frontend/` 迁移参考说明。

### Preserved — 前代有效资产

- 二代语义搜索链路（Qdrant + SentenceTransformer 懒加载 + warmup 端点）、Mongo AI 分析历史（含降级）、Redis 缓存回退、`backend/scripts/start_backend.sh` 解释器选择。
- 一代评分引擎 `scoring_engine`（AI 分析内部使用，不对外输出跨类别综合评分）。
- 三代证据驱动核心与四代研究工作流闭环全部保留。

## [1.0.0] - 2026-04-18

见 `docs/history/CHANGELOG.md`。
