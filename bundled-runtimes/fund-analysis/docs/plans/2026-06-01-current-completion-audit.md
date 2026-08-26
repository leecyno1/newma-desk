# 基金研究投资分析引擎：当前完成度审计（2026-06-01）

## 一、当前已完成并有证据支持的部分

### 1. Sprint A 研究工作流前台闭环
已具备以下可交付能力：
- 全市场基金浏览器：搜索、筛选、排序、列表/卡片视图、加入候选池
- 基金池工作流：候选/观察/核心/淘汰状态流转
- 研究维护：编辑最新结论、下次复查日期、风险备注、证据 JSON
- 预警中心：创建规则、查看规则、启停规则、删除规则、触发扫描、处理事件
- 分析详情：自动加载、可信度/证据摘要展示

### 2. 后端基础能力
已具备以下后端能力：
- FundPool / PoolMember 的 schema、repo、route
- AlertRule / AlertEvent 的 schema、repo、route
- Alert scan service
- 数据可信度/分析基础设施的一部分（历史轮次已补）

### 3. 当前已通过的验证
#### 前端定向检查
- `app/(dashboard)/market/page.tsx`
- `app/(dashboard)/pools/page.tsx`
- `app/(dashboard)/alerts/page.tsx`
- `app/(dashboard)/analysis/[id]/page.tsx`

#### 后端语法 / import / deterministic smoke
- `backend/tests/fund_pools_route_import_smoke.py`
- `backend/tests/alerts_route_import_smoke.py`
- `backend/tests/alert_scan_smoke.py`
- `backend/tests/scoring_contract_smoke.py`
- `backend/tests/scoring_engine_metric_snapshot_smoke.py`

## 二、当前不能证明“项目已完成”的原因

### 1. PostgreSQL 不可用
当前环境证据：
- `pg_isready -h localhost -p 5432` 返回无响应
- Docker daemon 不可用

这意味着以下需要数据库的能力尚未得到有效验收：
- FundPoolRepo 真正写库/读库能力
- AlertRepo 真正写库/读库能力
- Alert scan 对真实数据的事件生成
- MetricSnapshot / ReportChunk / DataSourceSnapshot 等 repo 层联动

### 2. 缺少 DB-backed smoke / integration 证据
尚未完成或尚无有效结果的关键验证包括：
- `backend/tests/fund_pool_repo_smoke.py`
- `backend/tests/alert_repo_smoke.py`
- `backend/tests/data_snapshot_repo_smoke.py`
- `backend/tests/metric_snapshot_repo_smoke.py`
- `backend/tests/report_chunk_repo_smoke.py`

### 3. 缺少真实运行态页面联调证据
当前已有静态检查与 import smoke，但还没有以下强证据：
- 页面在真实后端/数据库可用时的交互截图或自动化点击验证
- 从市场页加入候选池后，在基金池页面真实可见
- 创建规则后扫描产生真实事件，再在预警中心流转处理

## 三、当前结论
当前状态可定义为：
- **功能开发已推进到较完整的 Sprint A 产品闭环**
- **但不能声称整个项目“完成”**
- 核心缺口不是代码空白，而是 **数据库运行条件与最终联调验收证据缺失**

## 四、下一步最小完成路径
要把项目从“功能基本齐”推进到“可证明完成”，推荐顺序如下：

1. 启动本地 PostgreSQL 或 Docker 数据库
2. 配置 `DATABASE_URL`
3. 运行 DB-backed smoke：
   - `backend/tests/fund_pool_repo_smoke.py`
   - `backend/tests/alert_repo_smoke.py`
   - `backend/tests/alert_scan_smoke.py`
   - `backend/tests/data_snapshot_repo_smoke.py`
   - `backend/tests/metric_snapshot_repo_smoke.py`
   - `backend/tests/report_chunk_repo_smoke.py`
4. 启动前后端并做页面联调
5. 如联调暴露问题，再做最后一轮修复与回归验证

## 五、可接受的当前定位
如果今天需要阶段性交付，可以将当前版本定义为：
- “基金研究投资分析引擎 Sprint A 功能版（待数据库联调验收）”

## 六、2026-06-01 追加推进记录（当前轮）
本轮继续推进了无需数据库即可完成的产品收尾项：
- 将根路由 `/` 调整为优先进入全市场浏览器，使“全市场基金浏览器”成为默认研究入口
- 重写 dashboard 首页，突出“全市场浏览器 → 基金池 → 预警中心”的研究主流程
- 同步 README 的产品定位与核心功能描述，使文档与当前实现一致

这类收尾能降低用户首次进入系统时的路径割裂感，但**不构成项目已完成的最终证据**。
最终完成仍然依赖：
- PostgreSQL / Docker 恢复可用
- DB-backed smoke 通过
- 前后端在真实写库条件下完成联调验收

## 七、2026-06-01 追加推进记录（交互闭环补丁）
本轮继续补齐“全市场浏览器 → 基金池”的离线可感知闭环：
- 全市场浏览器增加首次自动加载、成功提示横幅和错误提示横幅
- 加入候选池后，页面内可直接引导前往基金池继续研究
- 基金池页面增加首次自动加载、状态/保存成功提示和错误提示
- 基金池页面补上返回全市场浏览器入口，强化研究路径回环

以上改动提升了产品闭环体验与离线可验证性，但仍然不能替代真实数据库联调验收。

## 八、2026-06-01 追加推进记录（预警与分析体验补丁）
本轮继续补齐预警中心与分析详情页的体验闭环：
- 预警中心增加成功提示、错误提示、规则空态和事件空态
- 预警规则创建、启停、删除、阈值更新、扫描触发改为页面内反馈，不再依赖浏览器弹窗
- 分析详情页增加复制/下载成功反馈与错误反馈
- 分析详情页在报告缺失或接口失败时给出更明确的页面内提示

这提升了研究工作流的可感知性与操作反馈质量，但项目最终完成仍需数据库联调与真实验收证据。

## 九、2026-06-01 追加推进记录（基金列表与详情统一补丁）
本轮继续统一基金列表与基金详情页的研究入口体验：
- 基金列表增加“前往全市场浏览器”导流与空态引导
- 基金详情页增加“AI 分析”与“去全市场浏览器”双入口
- 基金详情页在详情缺失或接口失败时给出更明确的重试反馈
- 列表页与详情页都补上更一致的非数据库状态下操作路径提示

至此，前台研究闭环相关主要页面已完成一轮统一收尾；最终完成仍取决于数据库恢复后的真实联调与验收。

## 十、2026-06-01 追加推进记录（最终验收脚本与清单）
本轮补齐了数据库恢复后的最终验收入口：
- 新增一键 smoke 验收脚本 `scripts/run_completion_audit.sh`
- 新增最终联调与完成定义清单 `docs/plans/2026-06-01-final-validation-checklist.md`
- 将“恢复数据库后立即执行什么”从口头说明沉淀为可复用操作资产

这意味着：一旦 PostgreSQL / Docker 恢复，项目已具备立即进入最终验收模式的标准入口。
