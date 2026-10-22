# 宏观流动性：完整月份比较验收（2026-10-22）

阶段记录：PMI主源及Research固定源码、Desk集成已在后续修复，最新状态见 `research-integration-acceptance-2026-10-22.md`。下文保留当时验收结果，不代表最新缺口。

## 修正与源码

唯一主源：`/Volumes/PSSD/Projects/newma-desk-projects/vibe-research`。本轮限定本地提交 `64e077b`，仅5个宏观代码/测试文件；既有股票、行情及交接文件改动保留。未推送或远端部署。

- 月频数据按月末统计截止日过滤，排除尚未结束的当月（含当月最后一天）；展示期间为 YYYY-MM，不再用月初衡量新鲜度。
- 新增 frequency/dateBasis/periodEnd；月末不是已核验发布日期，也不是完整历史点时证据。只有未完成当月的来源返回缺失，不填0。
- 日频 SHIBOR、两融保留实际观测日。页面区分月频/日频、显示金额单位、聚合来源链接与统计说明；小幅变动0.0002个百分点不再被舍入为0.00。
- 来源明确为 AkShare 接入的东方财富/金十/同花顺聚合数据，不冒充已直接核验央行或交易所公告；未新增数据服务或权限。

## 实际验证

- 原生后端：`VR_DISABLE_BACKGROUND_TASKS=1 PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q`，374通过，11项live默认未选，3个既有弃用警告。其中宏观58通过。
- 原生前端：`npm test -- --reporter=dot`，229通过。新增页面测试覆盖频率、金额单位、来源链接、小幅变动及Agent Context的月末口径。
- `build:standalone` / `build:desk` 均通过，产物隔离在 `/tmp/desk-macro-acceptance-20261022-ijCD4o/standalone` 与 `desk`，未覆盖正式dist。
- 真实公开数据复测：流动性9/9；M2为2026-09、7.2%，asOf=2026-09-30、ageDays=22；股票融资9月627.81亿元，对比8月451.29亿元，变化+176.52亿元；10月224.84亿元未完成值被排除。SHIBOR隔夜为10月22日1.2612%，变化+0.0002个百分点。
- 原生源码API18964与编译前端15964使用隔离数据目录、禁用后台调度。IAB实际打开 `/macro-monitor`，核心10/10、流动性9/9；点击刷新后回读月份、来源和金额正确，按钮恢复可用。聚合值未经官方原件独立复核。
- 独立页明确显示Crucix仅在Desk集成模式可用，本次未验证其采集。未调用模型、未读取正式持仓或私人资料。
- Desk镜像只人工合并本轮四个宏观源文件/后端测试；新增`tests/unit/macro-liquidity.test.tsx`并纳入`vitest.research.config.ts`。Desk宏观58项、页面1项均通过，后端与页面文件和主源一致，既存api.ts其他改动保留。

## 发布边界与下一步

正式8911/5888及其他业务服务未重启；本轮不改变运行目录，不更新整个Research共同同步基线。Research仍有既存股票候选未收口，不能用64e077b冒充整个dirty工作树已固定。Desk集成源码尚未提交；需要随Research定向集成候选审核，不能打包整个工作区。

本轮没有重做Desk内嵌点击、真实newma宿主或模型回答验收。受控Chrome空白已由用户手动最小页正常显示排除为业务阻塞；不再重复该排查。后续完成配套候选后由主发布会话部署，再验实际入口与Context。PMI主源Tushare列不匹配仍由东财正常降级，需另轮修复，不能写成所有宏观来源均无故障。
