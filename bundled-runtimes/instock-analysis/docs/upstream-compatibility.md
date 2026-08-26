# 上游兼容与更新策略

最后审计：2026-08-12。

## InStock

- 集成基线：`myhhub/stock` 的 `origin/master`，提交 `b6e0ca2268cfbadd02f5ed052159c187b6670231`。
- 2026-08-05 已执行 `git fetch --prune origin`；当前 `codex/czsc-integration` 与该基线仍为 `0 ahead / 0 behind`，没有待合入的上游提交。
- 后续只挑选与分析内核、安全修复或依赖兼容有关的变更；上游 Docker、MySQL 抓取、旧站点和交易服务不会重新进入 Newma-Desk 附属运行时。

## CZSC

- 生产依赖固定为稳定版 `czsc==0.10.12`。
- 官方主分支与 PyPI 预发布版已进入 `1.0.0rc8`，核心迁移为 Rust/PyO3，并删除 `czsc.signals` Python 命名空间，属于破坏性升级。
- 2026-08-05 查询 PyPI，最新可安装版本仍为 `1.0.0rc8`，尚无 1.0 稳定版；官方 `master` HEAD 为 `9ab62854f6bfab8515115b942baf4deb0f06185c`。
- `rs-czsc` 最新版本仍为项目已认证的 `0.1.26.post260402`，无需更新约束快照。
- 隔离探针已确认 `1.0.0rc8` 的 `RawBar`、`CZSC`、`finished_bis`、`fx_list`、`ubi`、笔字段与 `ZS.is_valid` 可以支撑当前结构分析。
- 七组现有官方规则已经接入 `generate_czsc_signals` Rust registry Adapter。`0.10.12` 使用 `czsc.signals-v0.10`，`1.0.0rc8` 使用 `czsc.rust-registry-v1`，二者都输出相同的项目合同。
- Analysis Module 将 CZSC 运行兼容信息放入 `engine.compatibility`。只有旧 Python 信号与 Rust registry 都不存在时，才降级为 structure-only，并在页面明确显示降级状态。

## 1.0 正式升级门槛

只有同时满足以下条件才更新生产依赖：

1. CZSC 发布 1.0 正式稳定版，不跟随 RC 自动升级。
2. 在 1.0 正式版上重新验证现有 Rust registry Adapter 与七组官方信号映射。
3. Python 全量测试、Snapshot 合同、批量扫描和三个 Mod 页面全部通过。
4. 使用真实 Newma-Desk 数据完成单标的、批量、轮动和稳健性实验烟测。
5. 更新 Suite 版本并重新执行 Newma-Desk Level 2 合同与运行认证。

## 当前认证证据

- Suite `0.17.0` 已适配 Newma-Desk 的投资栏目规范：`project=quant-research`、`directory=instock-suite`，共交付 11 个 Desk 原生 Module 与 13 个主要 Action。
- 2026-08-12 已完成 `160` 项 Python 全量测试与 `14/14` 在线发布检查；12 个主要 Action 均通过真实 Newma-Desk 数据调用。
- `instock-czsc` 与 `instock-rotation` 已通过 Newma-Desk Level 2 运行认证。
- 市场概览与技术策略信号已完成真实数据、暗色主题、Bridge 握手、Agent Context 和 320px 无文档横向溢出验收，不再依赖上游 MySQL 旧页面。
- `instock-stock-candidates` 使用 Desk 最新成交活跃池、前复权日线与 `research.equity-comparison` 批量财务比较完成两阶段预筛和财务重排，缺失项回退 `research.equity-snapshot`；正式 Level 2 认证等待宿主导入 Suite。
- `instock-stock-research` 使用 Desk 股票快照、公告、研报、新闻与项目 CZSC 结构完成项目侧预认证；正式 Level 2 认证等待宿主导入 Suite。
- `instock-strategy-validation` 使用 Desk 前复权日线完成点时信号执行、成本与样本外验证的项目侧预认证；正式 Level 2 认证等待宿主导入 Suite。
- `instock-event-flow` 使用宿主结构化事件包完成去重、时效和证券级异常归并的项目侧预认证；正式 Level 2 认证等待宿主导入 Suite。
- `instock-research-book` 使用宿主研究组合包与 Snapshot 引用完成暴露和风险汇总的项目侧预认证；正式 Level 2 认证等待宿主导入 Suite。
- `instock-industry-chain` 已通过 Suite 编译、真实 API、Bridge 握手与 320px 嵌入预认证；正式 Level 2 认证等待宿主导入 Suite，不要求修改 Desk 代码或商店。
- Desk 行业排名暂时为空时，轮动按公开合同将行业因子中性化；市场概览则使用成交额活跃样本的行业涨跌中位数并明确标记样本口径。两者都不伪造全市场行业数据。
- `scripts/newma_release_check.py --report` 现在记录 UTC 生成时间、Suite 版本、当前提交、`origin/master` 提交和工作区脏状态，避免报告脱离源码上下文。
