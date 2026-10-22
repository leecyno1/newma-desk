# 独立市场扫描数据源

`GET /api/market-terminal/scan` 是独立 HTTP 数据接口，不导入 Desk 私有源码。股票项目只配置该服务的 Base URL / 服务凭据，不需要获取 Tushare 凭据。

## 选择数据源

- 默认 `VR_CN_SCAN_SOURCE=eastmoney`，维持原东财两入口；无数据源响应返回 502，不将失败缓存为空池。
- 显式设置 `VR_CN_SCAN_SOURCE=tushare-daily` 并配置服务端 `TUSHARE_TOKEN`，A 股改用日频截面。缺少配置或权限直接报错，不静默回退东财或实时个股报价。
- 此设置仅影响 CN；HK/US 保留原数据源。不得把 CN 成功等同港美股可用。
- `VR_API_KEY` 仍控制此 Research 服务的客户端鉴权，与 Tushare token 是不同凭据。公网部署必须配置访问控制。

示例（先由本机秘密管理配置 token，不将它写入代码、URL 或日志）：

```sh
VR_CN_SCAN_SOURCE=tushare-daily .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900
```

## 数据含义

1. 用 `trade_cal` 选择北京时间昨日及以前的最近交易日，不使用当日尚可能更新中的收盘截面。
2. `stock_basic` 当前上市 A 股目录、`daily` 日线、`daily_basic` 每日指标均先分页获取，再按证券、同一交易日匹配和排序。排除 B 股及基准日之后上市的证券；当前目录不是历史点时证券库。
3. 成交额从千元换为元，市值从万元换为元；CN 成交量保持手，与既有扫描接口一致。PE 使用 `daily_basic.pe`（静态），不是 `pe_ttm`。比例字段为百分数。
4. 缺失指标为 `null`，真实 0 保留。排序只包含该字段有效的证券；不得把缺失 PE 当 0 排在低估值榜前。
5. `asOf` 是该交易日收盘时间；`receivedAt` 是本次取数时间。`source=tushare-daily`，`coverage.frequency=daily`、`realtime=false`。
6. `listedCount/quoteCount/missingQuoteCount/basicCount` 表达当前目录与日频输入匹配情况；`rankableCount/missingSortCount` 随排序字段变化。未返回日线的原因没有核验，不推断为停牌或无风险。
7. 所有排序共享 300 秒内的同一内存截面，避免 11 个排序轴反复取完整市场数据；失败不缓存为成功。股票端日频扫描不再混入实时补价。
8. 申万归属来自 `index_member_all(is_new=Y)` 的分页证券成员表（官方接口需2000积分），不把 `stock_basic.industry` 当申万分类。保留原 `industry`，新增 `industryL1/industryL2/industryClassification`，包含目录代码、纳入日、获取时间及非点时说明。成员查询失败仍返回有效报价，归属留空，coverage明确 unavailable 和缺失数；不靠名称补齐。排除未来纳入、已剔除及非最新成员；当前最新成员表仍不能用于历史点时回测。

最多返回前 200 条；11 轴合并仍是候选并集，不是全部上市证券。不能将样本筛空解释为全市场无候选。默认配置不变；源切换需同时加载已保留来源元数据的股票消费者。

## 复权日线备用

显式选择 `tushare-daily` 后，CN 股票日线在腾讯/东财无有效复权序列时，使用同证券、同交易日 `daily` 与 `adj_factor`：qfq 为价格×当日因子÷最后价格日因子，hfq 为价格×当日因子。缺因子不补 1、不前填，失败仍走既有未复权备用并标 `none`。基金/ETF/指数和周/月/分钟不套股票因子；默认 eastmoney 配置不启用此路径。

成交量保持手、不复权；成交额千元换为元；真实零保留。两请求各 4 秒、无重试，非全部来源总时限。返回实际 source/adjust、qfq adjustmentAnchor、adjustmentMethod 和单位。截止不晚于北京时间昨日，asOf 模式为 bounded-daily-window；腾讯等仍是 latest-window-filter，不保证来源间复权锚点一致。不是完整历史证券池/财务点时回测。

## 扫描验收记录

2026-10-20 隔离服务与股票安装包实际 HTTP 验证：10-19 截面当前目录 5575、日线 5564、未覆盖 11；11 轴共 1565 个唯一候选，失败 0。PE 可排序 4111、缺失 1453；量比缺失 4、PB 缺失 52。不是完整行情审计，也不是港美股、浏览器双模式或外部 newma 验收。正式运行配置未切换。
