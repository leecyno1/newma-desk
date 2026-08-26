# circle

七周期研究与资产研究系统。

## 研究目标

- 识别并动态校准 C1–C7 七个周期；
- 展示长历史周期相位、实时单边状态和合格预测虚线；
- 统计 70 多类资产在不同周期相位中的收益与风险；
- 使用样本外验证进行客观资产归因；
- 为所有结论保存数据身份、校准版本和发布门槛。

## 核心原则

- 不使用固定正弦波代替真实周期；
- 不以单一 GDP 指标决定周期；
- 不按行业叙事主观指定资产映射；
- 不生成缺失历史或冒充真实 vintage；
- 不输出组合权重，不运行组合回测；
- 未通过样本外验证的模型不发布预测。

## 当前状态

Phase A 研究基础已经完成并通过全量验证。新版研究前端已在根仓库的 `web/` 中从零搭建，不再使用被废弃的嵌套前端仓库。当前可验证能力包括：

- C1–C7 周期证据复测；
- 104 条市场与经济轨道的 3D/2D 市场曲面，以及通过后段留出验证的轨道级机器学习虚线；
- C1 约 320 年七家族长期结构研究、红噪声检验、滤波稳定性与5/10/20年递归方向验证；资本形成和全球连接已桥接至当前，现代技术扩散因9年重叠相关性过低被拒绝续接，端点动量由改善修正为平稳；
- C2/C3 使用 JST 1870–2020 跨国面板、BIS 与世界银行当前桥接的长历史方向验证；
- C2/C3 的 1–3 年方向概率通过递归样本外和国家留一验证，但固定周期长度、精确幅度与精确拐点仍阻断；
- C2/C3 外部经济结果验证已改为结果通道模型：每类结果分别与只看自身状态惯性的递归样本外基准比较。C3 对未来1年消费增速与失业率改善提供有限增量，C2未形成跨时期稳定增量；两者均不足以解锁广义经济预测；
- C2 已重构为地产—信用双层系统：住房动量与按揭信用定义周期核心，总投资脉冲与融资条件只做确认，房价估值、按揭杠杆和投资水平只描述结构位置，避免与 C3 混叠；
- C2 当前多规格周期范围约 15.5—21 年，所有规格均未触及搜索边界，但周期选择强度弱；当前只能确认“低位”，住房、信用和投资动量存在分歧，因此四相位、精确周期长度与拐点继续阻断；
- C2/C3 保留 137 条长样本资产原始统计，覆盖18国股票/住房/国债/短票及Ken French行业与风格组合；C2 因核心已包含房价动量，16 条跨国住房收益被标记为自解释并排除，可用映射为 121 条；
- C2 当前动量分歧时自动暂停四相位概率和当前资产收益风险情景；历史映射仍可查，但剔除自解释后仅 3 条资产样本外 R² 为正，不能用于当前配置判断；
- C5 已重构为国内政策、信用传导和全球美元流动性三层状态，3至12个月直接期限模型通过递归样本外验证，NFCI仅作独立确认；
- C7 已重构为收益、风格、成交、融资、美元避险、VIX、NFCI与信用利差共同形成的风险偏好状态；修复整体多滞后一个月的问题后，1至5个月未来状态处于风险偏好区间的概率通过递归样本外验证，6个月仍阻断；
- C5/C7 固定周期长度与资产收益映射继续受发布门槛限制；
- C4 历史相位和伪实时状态；
- 104条轨道的周期贡献已分为双边回溯诊断与因果端点确认；端点确认使用三档全局状态空间参数、最多12个滚动截点，并依次评估家族共享权重与长周期→短周期因果正交挑战者。正交模型同时要求60/120期双跨度复核、滚动R²和MAE改善、方向不恶化，并把模型差异计入总不确定性；
- 资产条件预测按期限拆分治理：1个月保留历史截点逐期选模；3个月固定采用历史排名前4模型平均，并要求前3/4/5模型三种规模全部通过；6个月固定使用72期历史先验收缩近邻，取消逐资产选模，并要求同步参照时钟重复通过；
- 所有期限继续保持方向、Brier、MAE、样本外R²、最近48次递归稳定性和3/6个月非重叠路径原门槛。当前1/3/6个月分别有1/2/7条资产通过，6个月新增德国ETF、标普500、美股能源和美股金融，未通过资产继续阻断；
- C4 预测候选模型验证；
- 98 条真实资产的 C4 相位统计与客观关联归因，已补齐黄金、铜、原油、大宗商品综合指数和美元指数；
- 98 条资产在复苏、扩张、放缓、收缩四相位中的收益—风险散点；
- C4 受限预测下的资产风险—收益条件延伸。

前端只保留四个一级研究模块：市场曲面、七周期研究、资产统计、数据与校准。预测虚线、模型验证和资产条件延伸已经并入七周期研究，并同步显示在市场曲面；C2/C3/C5/C7 的阻断状态会直接限制曲线、资产统计和预测输出，不使用占位数据补齐。

## 新版前端

### 一键构建与启动

研究数据刷新完成后，在仓库根目录执行：

`uv run seven-cycle build --as-of 2026-07-21`

该命令会验证注册表、复用或发布已批准的研究基础运行包、生成匹配的 DuckDB 目录、构建网页，并写入统一的 `deployment.json`。正式验收时使用后台守护服务启动网页和只读 API：

`uv run seven-cycle service start`

服务状态、重启和停止命令：

`uv run seven-cycle service status`

`uv run seven-cycle service restart`

`uv run seven-cycle service stop`

守护进程会在服务退出或连续健康检查失败时自动重启。健康检查地址为 `http://127.0.0.1:4174/healthz`，日志位于 `output/services/circle-service.log`。网页、`/data/*` 研究数据和 `/v1/*` API 均由同一服务提供，不再需要分别维护 Vite 与 API 两个进程。前台调试仍可使用 `uv run seven-cycle serve --host 127.0.0.1 --port 4174`。

当项目盘被安全重挂载、文件内容与 inode 均未变化但文件系统 device id
发生漂移时，可显式启用启动前 Catalog 自修复：

`uv run seven-cycle service restart --repair-catalog-on-start`

该选项默认关闭。它会先完整校验 immutable run manifest、全部产品 checksum、
Catalog 审计 checksum、视图定义与产品 inode；只有确认旧 Catalog 除统一的
device id 外完全一致时，才构建候选 Catalog，并将正式 Catalog、
`products/circle/deployment.json` 与 `web/dist/data/deployment.json` 作为带回滚的
同一更新事务提交。缺失、损坏、被替换或产品内容不一致的 Catalog，以及不一致
的部署引用，均会拒绝自动修复；device/inode 防篡改校验不会被绕过。前台
`serve` 命令也支持同名选项。

### 研究数据刷新

C1 全球长期数据首次准备或官方版本更新：

`uv run python scripts/refresh_c1_global_sources.py --refresh`

生成浏览器研究数据：

`uv run python scripts/research_c2_c3_long_panel.py`

`uv run python scripts/research_c2_c3_historical_mapping.py`

`source ~/.codex/finance-env.sh && uv run python scripts/update_c4_realtime_bridge.py --through 2026-06`

`source ~/.codex/finance-env.sh && uv run python scripts/refresh_research_current_panel.py --through 2026-06`

`source ~/.codex/finance-env.sh && uv run python scripts/refresh_asset_returns_current.py --through 2026-06`

仅回填 Ken French 官方 FF17 行业组合完整月频历史时无需 Tushare 凭证：

`uv run python scripts/refresh_asset_returns_current.py --through 2026-06 --ff17-only`

资产条件预测同时比较原始状态近邻、固定72期历史先验的稳健状态近邻、强收缩近邻、资产特征Ridge、类别上下文Ridge与固定规则共识。稳健近邻使用24个局部状态样本，参数不按单项资产调优；6个月直接预注册为固定稳健近邻，避免逐资产冠军切换造成的选择不稳定。

`uv run python scripts/refresh_c4_asset_statistics.py`

`uv run python scripts/research_c4_forecast.py`

`uv run python scripts/research_c5_liquidity_state.py`

`uv run python scripts/research_c7_risk_appetite_state.py --refresh-public`

`uv run python scripts/research_c5_c7_asset_association.py`

`uv run python scripts/research_asset_cycle_state_forecast.py`

`uv run python scripts/build_web_research_data.py --refresh-public --as-of 2026-07-20`

构建器按实际轨道覆盖自动确定市场数据截止月。C4 预测保留独立 vintage，并作为轨道级模型的条件输入；每条虚线同时使用自身滞后、近期斜率和月份季节项，从最后真实点连续起步。3/6/12个月后段留出未同时战胜静态基准的轨道不绘制预测线。

开发模式启动本地界面：

`cd web && npm install && npm run dev`

仅构建前端：

`cd web && npm run build`

默认十条轨道包括美国 PMI（制造商新订单代理）、PPI、CPI、政策利率、美元指数、标普 500、纳斯达克、美债 10 年收益率、COMEX 黄金代理和 WTI。美国制造业 PMI 采用 FRED 制造商新订单作为公开可复核的先行代理，并在逐点详情中展示数据身份和限制。

正式设计规格见：

`docs/superpowers/specs/2026-07-19-seven-cycle-research-system-redesign.md`

## 数据说明

仓库不包含本地原始数据、运行产品、数据库、虚拟环境、密钥和大型演示文档。关键研究摘要和设计验证 JSON 作为可复核样例保留在 `output/`。
