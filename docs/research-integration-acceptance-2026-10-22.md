# Research 的 Desk 集成候选（2026-10-22）

## 固定范围

- Desk 基线：`109bbbe1b543f321d338696fe233b765ca211caa`。本候选只组合 Research 业务快照与必需的共享接口，没有带入股票运行时、政策、资金、全球、Agent Gateway 或 Shell 的其他未提交改动。
- 原生主源：`/Volumes/PSSD/Projects/newma-desk-projects/vibe-research`，固定 `8e81b428f510cc6bfff66a4112aaea55ea29ee10`。包含 `cbebdcb` 的全部业务修复；新增一处测试隔离修复，避免 Research 与 Desk 同名 `tests` 包冲突，不改变业务输出。原生该项21测试通过。
- 业务同步预览 `files: []`，本机同步基线已推进；未提交包含其他14工程状态的整份本机版本锁。
- 干净集成副本：`/tmp/desk-research-integration-20261022-PoT2yP/project`。由上述 Desk 基线克隆，逐项加入已固定的 Research 前后端、测试、三份 Suite、数据能力声明及下述接缝，不复制开发目录的依赖、数据库或凭据。

## 必须一起交付的接缝

1. 私有文件：`ResearchApiAdapter` 校验签名会话、实例、当前发布修订及 `investment.files`；仅 research-library / earnings-workbench 可用。用户和工作区来自签名，不信任自报身份头；服务端原生凭据不下发到页面。旧独立文件不自动归属 Desk 账户。兼容旧双 `/api` 路径，但不保留匿名读取。
2. 档案与输入：研究档案、估值的财报输入改用已授权会话；不可读的来源显式列出，不冒充空档案。关系原文与图谱片段按相同用户/工作区读取，版本不符拒绝替换为最新图。
3. 图谱预览：增加不落库的 `/api/artifacts/preview`，不把浏览示例当发布。预览 HTML 禁止外部连接，并保留 iframe sandbox；原文读取限制公开目标、重定向、大小与 PDF 工作进程耗时。
4. 数据入口：Research 独立基址为 `/api`，Desk 为 `/api/research`；能力路径不再重复拼 `/api`。加入健康、财报与原文核对能力，保留日线截止日语义；财务取数具有服务端预算，上游失败返回固定安全错误，不回传凭据/地址或自动重发。
5. 依赖：API 直接依赖 lxml / pypdf 并更新锁；避免 BeautifulSoup 在加入业务虚拟环境前初始化而缺失 lxml。日频来源仅按显式 `VR_CN_SCAN_SOURCE` 选择，默认仍是 eastmoney。

未纳入共享层的股票会话转发、其他项目运行时适配及 Agent 扩展；它们不因本次通过而获得验收结论。

## 实际验证

- 根目录与 Research 前端分别 `npm ci --ignore-scripts --no-audit --no-fund` 成功。根锁未被更新；前端使用本候选共享包，不借开发 node_modules。
- Research 前端239项通过；Contracts 103项通过及类型检查通过；33项官方数据能力检查通过。
- Research 集成构建与 Shell 构建通过。前者明确设置 `VITE_BASE_PATH=/mod-runtime/research/`、`VITE_API_BASE=/api/research`、`VITE_NEWMA_DESK_INTEGRATED=1`。
- API 在新 Python 3.12 环境用 `uv sync --project services/api --frozen --extra test --python 3.12` 安装46包；随后按现有生产约束安装 akshare/requests/pandas/tushare，最终71包兼容检查通过。核心依赖冻结安装，数据源的传递依赖由安装器解析，不能称完整71包均冻结。
- API/档案/公开原文/图谱输入/数据网关/配置169项通过。其中新测试用真实 Mod 编译器、真实发布声明和真实 Desk 挂载，在临时数据库完成：资料上传、财报共享读取、估值文件拒绝、跨工作区404、匿名401、旧路径兼容、财报底稿保存和估值投影回读。
- Research 集成后端最终387项通过，11项live未选、2个既有弃用警告。首次执行因跨测试包导入失败1项，修复后无业务失败；公开财报样本缺失时4项跳过，随后放入原生仓已带的茅台2024年报重新执行，最终无跳过，不把缺样本的运行算原文验收。
- 所有写入仅临时测试资料/数据库；没有操作用户持仓或原有研报。未调用真实模型。

复现入口：

```sh
uv sync --project services/api --frozen --extra test --python 3.12
uv pip install --python services/api/.venv/bin/python -c deploy/server/constraints-domain-runtime.txt akshare requests pandas tushare
npm ci --ignore-scripts --no-audit --no-fund
npm ci --prefix bundled-runtimes/vibe-research/frontend --ignore-scripts --no-audit --no-fund
npx vitest run --config vitest.research.config.ts
VITE_BASE_PATH=/mod-runtime/research/ VITE_API_BASE=/api/research VITE_NEWMA_DESK_INTEGRATED=1 npm run build --prefix bundled-runtimes/vibe-research/frontend
npm run build -w @newma-desk/desk
services/api/.venv/bin/python -m pytest services/api/tests/research_archive services/api/tests/test_domain_suites.py services/api/tests/test_research_sources.py services/api/tests/mod_storage/test_industry_map_inputs.py services/api/tests/mod_storage/test_industry_maps.py services/api/tests/artifacts services/api/tests/data_services services/api/tests/test_config.py -q
```

## 发布与尚未验证

本候选须配套部署 API、Research 编译产物、三份 Research Suite 与数据服务声明；只替换前端会导致权限/接口不匹配。生产不能采用本机 `.venv` 或 `node_modules`。共享 API 与域数据依赖保持生产约束；无需安装与统一 httpx 不兼容的 mootdx。

本轮没有切换本地5888/8911服务、更新正式注册库或远端部署，也未执行完整Docker镜像构建。真实外部 newma/Hermes、当前候选的嵌入点击与模型回答仍未验收。普通 Chrome 探针由用户确认正常，自动化 iframe 操作问题不再当业务缺陷反复排查。原生宏观/行情真实网络结果见 `research-fixed-candidate-2026-10-22.md`，本次不把离线测试冒充新一次上游稳定性验收。

c10375 远端仍由 Newma 主发布会话部署；这不是五组30页全部完成的声明。

主发布会话补充：云端行业109bbbe1隔离候选已通过，不需重复取数；生产API仍同进程挂载Research/Trading。上述71包只是本次Research集成测试环境，不能拿它直接替换完整生产环境。正式切换须保留现有Trading依赖与定制配置，按完整domain-runtime要求重建并单列兼容预检；现有资源代理仍须补行业精确路由。
