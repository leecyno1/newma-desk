# Changelog

本项目的重要变更记录。历史版本（1.0.0 及以前的阶段总结）见 `docs/history/CHANGELOG.md`。

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
