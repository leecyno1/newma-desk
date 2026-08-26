# 架构说明

更新时间：2026-08-18。本文描述当前主干架构；历史架构文档见 `docs/history/`。

## 系统定位

独立基金研究工作台：基金数据库 -> 浏览与比较 -> 分类评价 -> 经理纪要研究 -> 业绩归因 -> AI 现场分析 -> 研究工作流闭环（队列 -> 论点 -> 监控 -> 复盘 -> 模式识别）。产品边界见 `CONTEXT.md` 与 ADR-0002/0003。

## 运行拓扑

| 组件 | 地址 | 职责 |
| --- | --- | --- |
| Next.js 前端 | `127.0.0.1:3000` | 全部业务页面、Desk Adapter 页面、`app/api/*` 后端转发 |
| FastAPI 后端 | `127.0.0.1:8005` | 业务服务层、数据同步、AI 分析、健康检查 `/api/health` |
| PostgreSQL | 仓库内 `.data/postgres/` | 基金、评价、归因、纪要、经理、论点等结构化主数据 |
| MongoDB | docker `fund_mongo` | AI 分析历史记录（缺失时自动降级） |
| Redis | docker `fund_redis:6380` | 缓存（缺失时回退内存缓存） |
| Qdrant | docker `fund_qdrant` | 调研纪要语义检索（模型懒加载） |

`3001` 属于 Orchestra，本项目不得占用。

## 前端结构

```
app/
├── (dashboard)/          # 独立应用业务页面（唯一业务实现）
│   ├── discover/         # 基金浏览器（默认入口）
│   ├── compare/          # 同类比较（单同类组）
│   ├── evaluation/       # 评价与分类
│   ├── research/         # 调研纪要 + /research/pending 待确认收件箱
│   ├── analysis/         # AI 分析、业绩归因、分析历史
│   ├── workbench/        # 研究工作台（队列/论点/监控/异动/复盘）
│   ├── theses/           # 投资论点
│   ├── evidence-coverage/# 数据健康与证据覆盖
│   ├── market/           # 全市场研究库
│   └── *_redirect 页      # 旧路由薄重定向（legacyResearchRedirect.ts）
├── (desk)/mod/fund-research/  # Desk Adapter：复用 (dashboard) 业务页面
└── api/                  # Next 转发层 -> FastAPI
```

- 壳组件：`components/shell/FundWorkspaceShell.tsx`（导航注册表 `fund-workspace-navigation.ts`）
- 简版导航：`components/navigation/AppNavigation.tsx`
- 旧路由兼容：`lib/research-platform/routes.ts` 的 `canonicalResearchHref` / merged 映射

## 后端结构

```
backend/
├── main.py               # FastAPI 入口，路由注册
├── service_registry.py   # 数据源(Tushare)、缓存、Mongo 注册
├── routes/               # HTTP 路由层（30+ 路由文件）
├── services/             # 业务服务层（70+ 服务文件）
├── repositories/         # PostgreSQL 数据访问层
├── lib/                  # barra/brinson 等纯计算库
├── scripts/              # 数据同步脚本（npm run funds:* / research:* 调用）
└── tests/                # smoke 测试
```

关键服务：`fund_research_snapshot_service`（统一研究快照）、`fund_evaluation_service`（同类评价）、`performance_attribution_service`（归因）、`local_research_folder_service`（本地纪要库）、研究工作流服务（theses/queue/watches/anomaly/postmortem/decision_support/signals）。

## 数据同步与调度

- 薄调度器：`scripts/scheduled_update.sh`（flock 非重入锁、runbook.jsonl 运行记录、脱敏日志、`--dry-run/--only/--bucket`）
- launchd 模板：`scripts/launchd/*.plist`
- 数据源：Tushare（`TUSHARE_TOKEN`）+ IMA 云端纪要（本地 `../ima知识库/`）

## 验证

```bash
npm run doctor
npx tsc --noEmit
npm run build
PYTHONPATH=backend .venv/bin/python -c "import main"
npm run smoke:fund-research   # 总验收（含静态检查 + 运行时断言）
```
