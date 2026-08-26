# API 职责清单

> 用于识别当前 Next.js API 与 FastAPI 路由的所有权、重复逻辑和迁移目标。

## 说明

- **Owner** 表示推荐的权威实现归属。
- **Current** 表示当前实现位置。
- **Target** 表示未来期望承载位置。
- **Risk** 表示重复实现、口径不一致或迁移复杂度。

## Next.js API Routes

| Endpoint | Current | Owner | Target | Risk | Notes |
|---|---|---|---|---|---|
| `/api/analysis` | Next.js | FastAPI | FastAPI | High | 列表查询应由研究后端统一提供。 |
| `/api/analysis/{id}` | Next.js | FastAPI | FastAPI | High | 详情与删除需统一到研究后端。 |
| `/api/analysis/generate` | Next.js | FastAPI | FastAPI | High | AI 生成应迁移到 Python 服务。 |
| `/api/funds` | Next.js | FastAPI | FastAPI | High | 基金列表与创建应统一口径。 |
| `/api/funds/{id}` | Next.js | FastAPI | FastAPI | High | 基金 CRUD 建议后端统一。 |
| `/api/funds/nav` | Next.js | FastAPI | FastAPI | Medium | 当前代理 Wind 服务，可保留为 BFF。 |
| `/api/managers` | Next.js | FastAPI | FastAPI | High | 基金经理 CRUD 建议迁移。 |
| `/api/managers/{id}` | Next.js | FastAPI | FastAPI | High | 基金经理详情应统一。 |
| `/api/reports` | Next.js | FastAPI | FastAPI | High | AI 报告列表应由研究后端统一。 |
| `/api/reports/{id}` | Next.js | FastAPI | FastAPI | High | 报告详情/删除应统一。 |
| `/api/reports/search` | Next.js | FastAPI | FastAPI | High | 语义搜索应由后端统一。 |
| `/api/reports/upload` | Next.js | FastAPI | FastAPI | High | 上传后解析、入库应归后端。 |
| `/api/scores` | Next.js | FastAPI | FastAPI | High | 评分必须由唯一权威引擎计算。 |
| `/api/screening` | Next.js | FastAPI | FastAPI | High | 筛选规则应后端统一。 |
| `/api/screening/templates` | Next.js | FastAPI | FastAPI | Medium | 模板 CRUD 可迁移到后端。 |
| `/api/screening/templates/{id}` | Next.js | FastAPI | FastAPI | Medium | 模板明细和更新可迁移。 |
| `/api/sync/wind` | Next.js | FastAPI | FastAPI | High | 同步任务应由 FastAPI 执行，Next.js 仅代理触发。 |

## FastAPI Routes

| Endpoint | Current | Owner | Target | Risk | Notes |
|---|---|---|---|---|---|
| `/api/reports/manager/{manager_id}` | FastAPI | FastAPI | FastAPI | Low | AI 报告主入口。 |
| `/api/attribution/fund/{wind_code}` | FastAPI | FastAPI | FastAPI | Low | 统一业绩归因权威接口。 |
| `/api/barra/exposure/{fund_code}` | FastAPI | FastAPI | Compatibility | Low | 旧兼容 Adapter，映射统一归因中的 Barra 证据。 |
| `/api/barra/risk-decomposition/{fund_code}` | FastAPI | FastAPI | Deprecated | Low | 无正式风险模型输入时不输出风险贡献、特异风险和 R²。 |
| `/api/barra/score/{fund_code}` | FastAPI | FastAPI | Deprecated | Low | Barra 只作解释证据，不生成基金评价分数。 |
| `/api/brinson/attribution/{fund_code}` | FastAPI | FastAPI | Compatibility | Low | 旧兼容 Adapter，默认基准来自基金分类目录。 |
| `/api/brinson/history/{fund_code}` | FastAPI | FastAPI | Deprecated | Low | 停止用一年收益复制季度历史；历史归因按季度现场运行。 |
| `/api/data-sync/funds/{wind_code}` | FastAPI | FastAPI | FastAPI | Low | 单基金同步。 |
| `/api/data-sync/managers/{manager_id}` | FastAPI | FastAPI | FastAPI | Low | 单经理同步。 |
| `/api/data-sync/batch` | FastAPI | FastAPI | FastAPI | Low | 批量同步任务。 |
| `/api/data-sync/batch/{task_id}` | FastAPI | FastAPI | FastAPI | Low | 批量任务查询。 |
| `/api/data-sync/batch/{task_id}` | FastAPI | FastAPI | FastAPI | Low | 批量任务删除。 |
| `/api/data-sync/funds/full` | FastAPI | FastAPI | FastAPI | Low | 全量基金同步。 |
| `/api/data-sync/stats` | FastAPI | FastAPI | FastAPI | Low | 同步统计。 |
| `/api/export/funds` | FastAPI | FastAPI | FastAPI | Low | 基金导出。 |
| `/api/export/screening-results` | FastAPI | FastAPI | FastAPI | Low | 筛选结果导出。 |
| `/api/export/report/{report_id}` | FastAPI | FastAPI | FastAPI | Low | 报告导出。 |
| `/api/funds/` | FastAPI | FastAPI | FastAPI | Low | 基金列表。 |
| `/api/funds/{wind_code}` | FastAPI | FastAPI | FastAPI | Low | 基金详情。 |
| `/api/funds/{wind_code}/nav` | FastAPI | FastAPI | FastAPI | Low | 净值序列。 |
| `/api/funds/{wind_code}/holdings` | FastAPI | FastAPI | FastAPI | Low | 持仓数据。 |
| `/api/funds/{wind_code}/nav-chart` | FastAPI | FastAPI | FastAPI | Low | 图表数据。 |
| `/api/managers/` | FastAPI | FastAPI | FastAPI | Low | 经理列表。 |
| `/api/managers/{manager_id}` | FastAPI | FastAPI | FastAPI | Low | 经理详情。 |
| `/api/managers/{manager_id}/reports` | FastAPI | FastAPI | FastAPI | Low | 经理关联报告。 |
| `/api/managers/{manager_id}/profile` | FastAPI | FastAPI | FastAPI | Low | 经理画像。 |
| `/api/managers/{manager_id}/profile/generate` | FastAPI | FastAPI | FastAPI | Low | 经理画像生成。 |
| `/api/managers/{manager_id}/score` | FastAPI | FastAPI | FastAPI | Low | 经理评分。 |
| `/api/managers/{manager_id}/morningstar` | FastAPI | FastAPI | FastAPI | Low | 晨星相关视图。 |
| `/api/reports/fund/{wind_code}` | FastAPI | FastAPI | FastAPI | Low | 基金 AI 报告。 |
| `/api/reports/manager/{manager_id}` | FastAPI | FastAPI | FastAPI | Low | 经理 AI 报告。 |
| `/api/reports/history` | FastAPI | FastAPI | FastAPI | Low | 报告历史。 |
| `/api/reports/{report_id}` | FastAPI | FastAPI | FastAPI | Low | 报告详情。 |
| `/api/research-reports/` | FastAPI | FastAPI | FastAPI | Low | 调研报告 CRUD。 |
| `/api/research-reports/{report_id}` | FastAPI | FastAPI | FastAPI | Low | 调研报告详情/更新/删除。 |
| `/api/research-reports/batch-import` | FastAPI | FastAPI | FastAPI | Low | 批量导入。 |
| `/api/research-reports/search/status` | FastAPI | FastAPI | FastAPI | Low | 搜索状态。 |
| `/api/research-reports/search/warmup` | FastAPI | FastAPI | FastAPI | Low | 检索预热。 |
| `/api/research-reports/search/similar` | FastAPI | FastAPI | FastAPI | Low | 语义相似搜索。 |
| `/api/scoring/fund/{wind_code}` | FastAPI | FastAPI | FastAPI | Low | 基金评分。 |
| `/api/scoring/fund/{wind_code}/recalculate` | FastAPI | FastAPI | FastAPI | Low | 基金评分重算。 |
| `/api/scoring/manager/{manager_id}` | FastAPI | FastAPI | FastAPI | Low | 经理评分。 |
| `/api/scoring/batch` | FastAPI | FastAPI | FastAPI | Low | 批量评分。 |
| `/api/scoring/leaderboard` | FastAPI | FastAPI | FastAPI | Low | 排行榜。 |
| `/api/scoring/rules` | FastAPI | FastAPI | FastAPI | Low | 评分规则。 |
| `/api/screening/templates` | FastAPI | FastAPI | FastAPI | Low | 模板列表。 |
| `/api/screening/template/{template_key}` | FastAPI | FastAPI | FastAPI | Low | 模板详情。 |
| `/api/screening/custom` | FastAPI | FastAPI | FastAPI | Low | 自定义筛选。 |
| `/api/screening/save` | FastAPI | FastAPI | FastAPI | Low | 保存筛选。 |
| `/api/screening/saved` | FastAPI | FastAPI | FastAPI | Low | 已保存筛选。 |
| `/api/screening/compare` | FastAPI | FastAPI | FastAPI | Low | 筛选比较。 |

## 迁移优先级

1. **高优先级**：评分、筛选、AI 报告、搜索、同步。
2. **中优先级**：基金/经理 CRUD 与模板 CRUD。
3. **低优先级**：仅页面级聚合、格式转换、前端展示辅助接口。

## 规则

- 新增核心业务接口默认归 FastAPI。
- Next.js API 不新增任何权威计算逻辑。
- 若接口已在两端同时存在，以 FastAPI 为准。
- 迁移期间保留兼容层，不直接破坏现有前端。
