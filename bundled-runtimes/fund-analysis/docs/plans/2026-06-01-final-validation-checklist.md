# 基金研究投资分析引擎：最终验收清单（2026-06-01）

## 1. 数据库恢复条件
- PostgreSQL 已启动
- `DATABASE_URL` 已配置
- 若使用 Docker，Docker daemon 已恢复可用

## 2. 一键 smoke 验收
在项目根目录执行：

```bash
./scripts/run_completion_audit.sh
```

该脚本会依次验证：
- `backend/tests/fund_pool_repo_smoke.py`
- `backend/tests/alert_repo_smoke.py`
- `backend/tests/data_snapshot_repo_smoke.py`
- `backend/tests/metric_snapshot_repo_smoke.py`
- `backend/tests/report_chunk_repo_smoke.py`
- `backend/tests/alert_scan_smoke.py`

## 3. 前台联调验收
### 全市场浏览器
- 能加载基金列表
- 能筛选/排序
- 能将基金加入候选池

### 基金池工作流
- 能看到刚加入的基金
- 能修改状态
- 能保存结论、风险备注、证据 JSON、下次复查日期

### 预警中心
- 能创建规则
- 能启停/删除规则
- 能触发扫描
- 能看到新事件并更新状态

### 分析与基金详情
- 分析详情能加载报告内容
- 基金详情能加载基础信息、可信度、评分与报告摘要

## 4. 完成定义
只有当：
- DB-backed smoke 全部通过
- 前后台联调闭环通过
- 关键页面在真实数据条件下可用

才可以将项目标记为“完成”。
