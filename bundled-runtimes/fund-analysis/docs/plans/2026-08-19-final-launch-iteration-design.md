# 基金项目最终上线版本迭代设计（V2.1 → V3.0）

日期：2026-08-19
状态：已确认（含三处调整：砍"评价稳定性"维度；组合权重只做等权+自定义；回测只做基础版）

## 上线目标形态

本机生产化：launchd 常驻前后端 + 数据自动调度 + 每日备份，单用户（专业用户）自用。
不做认证/并发/HTTPS；不做适当性判断与销售规则；交易清单为研究输出，系统不执行任何交易。

## 现状基线（2026-08-18 实测）

- 基金份额 26,897；已分类 9,596（36%）；推荐就绪 1,074（4%）；可用同类组 45 个
- 调度器已建成但从未运行（logs/scheduled_update/ 无 runbook 记录）
- 组合构建零代码；地基已有：holding_similarity（重仓重叠）、FOF 穿透、asset_allocation、watchlist、candidate pools
- 评价方法论已有分类专属四维（收益/风险/风险调整/一致性）+ 评价历史 service + 任期排名
- 研究闭环 UI 已合拢（workbench 五 Tab）但未通电（无自动扫描喂数据）

## 里程碑结构

```
一期「评价落地 + 上线基座」                二期「研究闭环 + 组合构建」
M1 调度通电 + 本机生产化（1 周）           M4 组合构建 MVP（3-4 周）
M2 评价体系深化（2-3 周）                  M5 基础组合回测 + 监控 + 交易清单（2 周）
M3 覆盖攻坚（2 周，与 M2 并行）            M6 上线验收（1 周）
```

## M1 调度通电 + 本机生产化

1. scheduled_update.sh 注册主动扫描任务（daily bucket，依赖 backend 常驻）：
   - `research:signals-scan` → `curl -fsS http://127.0.0.1:8005/api/research-signals/scan`
   - `anomalies:scan` → `curl -fsS http://127.0.0.1:8005/api/anomalies/scan`
   - `watches:scan` → `curl -fsS -X POST http://127.0.0.1:8005/api/watches/scan`
2. 新增 scripts/backup_postgres.sh：每日 pg_dump 到 backups/（保留最近 14 份），注册 daily bucket
3. 新增 backend/frontend 生产化 launchd plist（uvicorn + `next start`，KeepAlive 自愈）
4. launchctl 加载 daily/weekly 调度与常驻服务，验证首个运行周期写入 runbook.jsonl

## M2 评价体系深化（砍掉"评价稳定性"，保留四项）

| 新能力 | 复用地基 | 增量 |
| --- | --- | --- |
| 风格漂移检测 | holding_style_snapshot 按季快照 | 时序对比算法 + 漂移分级 + 详情页展示 |
| 评价历史曲线 | fund_evaluation_history_service | 前端同类分位时间曲线 + 趋势解读 |
| 经理任期评价聚合 | tenure / 同类任期排名 | 经理维度综合评价卡片，跨产品风格一致性 |
| 持有体验维度 | drawdown_recovery_service | 纳入评价面板一等维度 |

## M3 覆盖攻坚（与 M2 并行）

推荐就绪 4% → 30%+：优先补齐 45 个有推荐能力同类组内的未就绪基金（browser-core backfill 按组轮询限速）；分类覆盖 36% → 70%。evidence-coverage 页增加每类缺口数与自动补齐进度。

## M4 组合构建 MVP（权重只做等权 + 自定义，不做风险平价）

```
目标配置(股债比/同类组权重)
  → 候选准入(推荐就绪池 + 评价门槛 + 纪要覆盖)
  → 权重方案(等权 / 自定义权重，含单基金上下限)
  → 组合穿透(重仓股重叠[holding_similarity] / 风格暴露聚合 / 净值相关性矩阵)
```

数据模型：Portfolio、PortfolioHolding、PortfolioTarget、PortfolioSnapshot。
前端：/portfolio 路由组（构建器）。
约束：候选必须来自推荐就绪池；穿透覆盖率不足显示残差；权重方案披露估计窗口。

## M5 基础组合回测 + 监控 + 交易清单

1. 基础回测：历史净值合成组合曲线、累计收益/最大回撤/与基准对比（复用 fund_aligned_comparison_service 对齐逻辑）；样本不足强制标注区间。不做归因、不做优化重跑。
2. 组合监控：权重偏离阈值告警（复用 watches 机制）、成分基金异动告警（复用 anomaly_scanner）、月度再平衡提示。
3. 交易清单：目标组合 vs 当前持仓差异 → 申赎建议清单（代码/方向/金额/份额），页面明示"研究输出，专业用户自行决策"。

## M6 上线验收

Playwright 桌面+390px 移动端验收、smoke:fund-research 全绿、性能验证、备份恢复演练一次、CHANGELOG v3.0、ADR-0004（定位演进：选基工具 → 专业基金研究工作台；交易清单属研究输出边界）。

## 风险与对策

1. Tushare 限流 → 按同类组轮询限速，优先 45 个有推荐能力组
2. 净值历史深度不足 → 强制披露样本区间，不外推
3. 范围蔓延 → 锚定 M1-M6 清单；不做实时估值、自动再平衡执行、多组合对比

## 交付节奏

总计 10-13 周；M1 后系统进入自动运转（数据每日自增），每个里程碑均为可独立验收版本。
