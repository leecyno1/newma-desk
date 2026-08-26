# 选基助手

面向普通用户的独立基金浏览、分类、评价、归因和候选推荐工具。Newma Desk 只是可选宿主，不是本项目的运行前提。

## 核心功能

1. 基金数据库：同步基金档案、净值、指标、经理和持仓。
2. 找基金：搜索基金、查看净值曲线、同类评价、上涨/下跌市场表现和多基金比较。
3. 调研库：连接本地纪要文件夹，按基金经理归档并提取可引用标签。
4. 综合基金数据库：合并基础数据、同类评价、纪要标签和数据质量。
5. 业绩归因：Barra 风格/风险暴露、Brinson 行业归因，以及明确标注的净值行为补充解释。
6. AI 分析：用户现场运行，读取评价、归因和纪要，保存分析历史。
7. 标签推荐：按类别和风格返回不超过十只候选基金。
8. 基金组合：设置目标权重，查看组合诊断、回测、偏离监控和交易清单。

不包含交易执行、购买金额、个人适当性、观察池晋级和投资决策。

LLM 不可用时，AI 分析只生成基于真实评价、归因和纪要的规则化摘要；调研库不会把普通关键词冒充已确认风格。

## 独立运行入口

- 前端：仓库根目录 Next.js，`http://127.0.0.1:3000`
- 后端：`backend/main.py`，`http://127.0.0.1:8005`
- 后端健康检查：`GET /api/health`

`3001` 属于 Orchestra，本项目不得占用或发布到该端口。

## Desk 适配包

- 描述文件：`desk/suite.json`
- 数据能力：`desk/data-service.json`
- 发现入口：`GET /.well-known/newma-desk-suite.json`
- 格式检查：`npm run desk:check`

适配包把本项目作为一个完整基金项目接入 Desk，六个页面属于同一个 Suite。项目不会自行发布到 Newma 控制面，也不会写入 `desk-mods`；只有人工验收后才进入宿主仓库。

## 本地启动

环境要求：Node.js 20+、Python 3.11+、PostgreSQL。

```bash
# 1. 启动并初始化本地 PostgreSQL
./scripts/start-local-postgres.sh

# 2. 启动 FastAPI
./backend/scripts/start_backend.sh

# 3. 另开终端启动正式前端
npm install
npm run dev
```

本地 PostgreSQL 默认保存在仓库的 `.data/postgres/`，不会再因系统清理 `/private/tmp` 而丢失基金库。项目虚拟环境 `.venv` 会被数据同步和后端启动脚本优先使用。

已有真实基金基础数据后，生成标准分类和同类评价样本：

```bash
./scripts/update_fund_classification.sh --apply
./scripts/update_fund_ranking_metrics.sh --peer-evaluation-coverage --limit 100
```

类别评价补齐会按同类组轮询，并同时覆盖 `.OF` 场外基金与 `.SH/.SZ` 交易所 ETF 代表份额。

同步产品介绍、完整费率、资产配置、持有人结构和公开重仓债券结构：

```bash
npm run funds:sync-product-profiles -- --limit 20
npm run funds:sync-bond-holdings -- --limit 20
```

债券结构只统计定期报告公开展示的重仓债券，并展示其占全部债券仓位的覆盖率，不冒充完整组合。

补齐某位基金经理现任产品的同类同任期可比样本：

```bash
./scripts/update_fund_ranking_metrics.sh \
  --manager-tenure-peer-coverage \
  --manager-id '基金经理规范ID' \
  --limit 30
```

全量刷新基金经理目录和真实任职关系：

```bash
npm run funds:sync-manager-universe
```

该同步直接读取 Tushare `fund_manager` 全量目录，只保留本地基金库中存在的产品关系；基金公司来自管理人字段或本地基金档案，不使用托管人字段代替。

补齐某位基金经理现任产品的基金级分类内评价：

```bash
./scripts/update_fund_ranking_metrics.sh \
  --manager-evaluation-coverage \
  --manager-id '基金经理规范ID' \
  --limit 30
```

按偏股、平衡、偏债 FOF 轮询补齐公开底层基金穿透：

```bash
./scripts/update_fund_ranking_metrics.sh \
  --fof-lookthrough-coverage \
  --peer-target-per-group 5 \
  --limit 15
```

FOF 只有在净值指标齐全、且最新公开底层基金至少 5 只并覆盖净值至少 20% 时，才进入可评价基金库。

`start-local-postgres.sh` 默认不导入演示基金；只有显式设置 `SEED_COMPLETION_SAMPLE=1` 才导入验收样本。

打开：

- 找基金：`http://127.0.0.1:3000/discover`
- AI 分析：`http://127.0.0.1:3000/analysis`
- 业绩归因：`http://127.0.0.1:3000/analysis/advanced`
- 标签推荐：`http://127.0.0.1:3000/recommendations`

## 基金经理纪要库

- 本地目录：仓库同级的 `ima知识库/`
- 云端目录：IMA 中的「ima知识库」，按年份保存原始纪要
- 增量同步：`npm run research:sync-ima`

IMA 凭证可通过 `IMA_OPENAPI_CLIENTID`、`IMA_OPENAPI_APIKEY` 环境变量传入，也可保存在本机 `~/.config/ima/`，不写入仓库。同步时会跳过云端已有文件，只上传新增纪要。

## Docker

```bash
docker compose up -d --build
```

Docker 使用仓库根目录 Next.js 应用和 `backend/main.py`。

## 数据原则

- 基金必须先分类，再做同类评价。
- 不用短期收益冠军直接推荐。
- 不用模拟数据或名称猜测冒充持仓、风格和归因。
- Barra 因子库未接入时，只展示持仓行业暴露。
- Brinson 持仓披露不足时，明确显示覆盖率和残差。
- 净值行为解释不得标记为 Barra 或 Brinson。

## 主要验证

```bash
npm run build
PYTHONPATH=backend python3 -m py_compile backend/main.py backend/services/performance_attribution_service.py
curl http://127.0.0.1:8005/api/health
```

产品范围见 [CONTEXT.md](./CONTEXT.md)、[ADR-0002](./docs/adr/0002-simple-fund-selection-product-scope.md) 和 [ADR-0003](./docs/adr/0003-independent-product-and-desk-adapter.md)。
