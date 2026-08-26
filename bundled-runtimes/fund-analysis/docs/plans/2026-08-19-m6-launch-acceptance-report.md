# M6 上线验收报告

日期：2026-08-19
结论：**通过**（附一项已修复的备份异常与防复发加固）

验收范围：上线迭代 M1（调度通电+本机生产化）/ M2（评价数据攻坚）/ M4（组合构建 MVP）/ M5（基础回测+监控+交易清单+ADR-0004）全量成果，对应设计文档 `2026-08-19-final-launch-iteration-design.md`。

## 1. launchd 常驻巡检 ✓

| 服务 | 状态 | 证据 |
|---|---|---|
| com.fund-analysis.backend（8005） | 正常 | PID 3312，运行 1h12m，KeepAlive 自愈在 M5 已实证（kill 25066 → 29654 自动拉起） |
| com.fund-analysis.frontend（3000） | 正常 | PID 29654，`next start` 生产构建，新路由（backtest/monitor/trade-list）200 |
| com.fund-analysis.scheduled_update.daily | 正常 | 工作日 18:15 触发，睡眠错过时唤醒补跑（今晨实证） |
| com.fund-analysis.scheduled_update.weekly | 正常 | 已注册（周日 20:00） |

API 健康抽查：backend `/api/health` 200、frontend `/` 200、`/portfolio` 200、`/recommendations` 200。

## 2. 调度全链路复查 ✓（含睡眠唤醒场景）

runbook（`logs/scheduled_update/runbook.jsonl`）完整记录 2026-08-19 06:19-06:20 唤醒补跑全过程：

1. 昨日 18:15 机器睡眠错过触发 → 今晨唤醒后 launchd 自动补跑
2. `ops:backup-postgres` 出现 `skipped_locked`（锁占用跳过）→ `failed`（pg_dump 版本回退失败）→ `ok`（30 秒后成功，24MB）三态记录
3. `research:signals-scan` / `anomalies:scan` / `watches:scan` 全部 ok
4. 评价快照积累任务运行正常（快照最新日期 2026-08-19，30 只无变化时不重写——去重机制符合设计）

调度体系在睡眠唤醒、锁竞争、工具版本异常三类真实扰动下均自愈或正确记录。

## 3. 备份恢复演练 ✓（发现并修复一项异常）

### 3.1 异常发现

今晨自动备份（`fund_analysis_20260819_062030.dump`）恢复验证时发现内容为旧时点状态：缺 `portfolios` 表（M4 已建）、评价快照 0 条、风格快照仅 6 条（均为 M2 攻坚前状态），而源库实际完整（portfolios=1、评价 30、风格 360）。socket 与 TCP 连接确认同一实例同一库，手动重新备份（10:01）内容完整——异常仅出现在唤醒补跑那一次 dump，疑似唤醒时序下的竞态。

### 3.2 处置

1. 删除异常 dump，保留经完整验证的备份
2. `backup_postgres.sh` 新增**备份内容自检**：dump 完成后 `pg_restore -l` 校验必须包含 `funds`/`fund_nav`/`portfolios` 三张关键表的 TABLE DATA，缺失即删除文件并返回失败（runbook 记 failed，不再静默产出不完整备份）
3. 双场景验证：完整备份通过自检 ✓；构造缺表 partial dump 被正确拒绝 ✓

### 3.3 恢复演练

`pg_restore` 到临时库 `fund_analysis_restore_test`，7 张关键表行数与源库完全一致：

| 表 | 源库 | 恢复库 |
|---|---|---|
| funds | 31,810 | 31,810 ✓ |
| fund_nav | 707,028 | 707,028 ✓ |
| fund_evaluation_snapshots | 30 | 30 ✓ |
| holding_style_snapshots | 360 | 360 ✓ |
| portfolios | 1 | 1 ✓ |
| portfolio_holdings | 3 | 3 ✓ |
| metric_snapshots | 116,198 | 116,198 ✓ |

备份→恢复链路可用；临时库已清理。

## 4. 数据盘点（2026-08-19）

- 基金总数 31,810；净值记录 707,028；滚动指标面板 116,198 条
- 评价快照 30 只基金（每日积累，连续性优先）；风格快照 194 只基金（360 条）
- 季报持仓覆盖 207 只基金；研究组合 1 个（3 只持仓，权重 100%）
- M3 覆盖攻坚由每日调度自动推进中（风格快照 359→360 的自然增长即为证据）

## 5. 功能验收 ✓

- 总验收 smoke **67 项全绿**（含 portfolio 扩展断言：准入推荐就绪口径、单只 ≤40%、等权/自定义来源限制、穿透覆盖率披露、回测样本不足拒答、监控不自动执行、交易清单边界声明、ADR-0004 定位）
- scope 守卫：组合优化/模拟/决策与投资决策禁令持续生效
- M5 三端点（回测/监控/交易清单）真实数据验证 + 浏览器 UI 验证通过（截图存档 `.playwright-cli/m5-portfolio-panels-full.png`）

## 6. 已知限制与运维建议

1. **备份目录当前仅 1 份有效备份**：每日调度自动积累，保留策略 14 份（已验证 prune 逻辑）。建议观察 3 天确认自然积累
2. **唤醒补跑竞态**（今晨异常的疑似根因）未完全定位：已用内容自检兜底；若 runbook 再现 `backup FAILED: dump 缺少关键表`，需进一步排查唤醒时序
3. 评价快照覆盖 30 只（占可分类基金少数）：推荐就绪率随每日积累提升，属 M3 长期任务，不影响现有功能
4. launchd frontend 每次代码更新后需 kill 让 KeepAlive 拉起新进程（`launchctl kickstart -k` 不会真正重启，P3005 惯例已记录在交接文档）

## 7. 迭代总结

| 里程碑 | 内容 | 提交 |
|---|---|---|
| M1 | 调度通电（mkdir 原子锁）+ launchd 生产化 + 每日备份 | d370ec7 |
| M2 | 评价数据攻坚（风格快照 359、评价历史 30、持仓 394 基金季度） | 7bd5251 |
| M4 | 组合构建 MVP（四表/准入/权重/穿透/前端） | 80f8301 |
| M5 | 基础回测 + 组合监控 + 交易清单 + ADR-0004 | c8a9dcb |
| M6 | 上线验收（本报告）+ 备份自检加固 | 本次提交 |

系统达成"完整功能 + 实际落地的评价体系、基金研究、组合构建"的上线目标，以本机生产形态（launchd 常驻 + 每日调度自动积累）持续运行。
