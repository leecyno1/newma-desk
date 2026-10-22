# 市场比较口径修复验收

原生固定版本：`852f3f2ebdb9eb0dd179dd2c3a69a4e876fda1ad`，目录 `/Volumes/PSSD/Projects/newma-desk-projects/market-daily`，工作树干净。

## 修改范围

- 多周期：日线复权与分钟不复权分别披露；每图提供实际来源、复权、条数、状态及时间。Context与页面一致。
- 强弱比较：按当地交易日交集统一起止点；周度从共同日线采样；空值、失效源、复权降级不当作零收益；单标的失败不阻塞其他有效标的。排名为本币价格收益，非总回报、非汇率或风险调整收益。
- 共享图表：按时间戳定位而非点序号；StrictMode重新创建图表时重设证券/周期，忽略已销毁图表的异步回调，修复有数据但只有空坐标轴。
- 配套说明行布局与定向业务测试。未更改权限、Gateway或数据库。

## 配对同步

依赖和接入声明变更触发自动同步保护，未删除/绕过该保护。已逐项人工审阅：原生仅切换ChartKit固定包及其锁文件；Desk使用同一共享源码；两侧多周期描述一致，没有权限变化。业务目标逐文件与共同基线`981669c`比对无分叉后，以补丁合入。版本清单更新后，同步预览应无业务差异。

最终原生固定包为 `vendor/newma-desk-chart-kit-0.1.0-market-20261022.tgz`；旧包保留但不再引用。Desk构建使用`packages/chart-kit`，不用拷贝原生node_modules。

## 已执行

- 原生市场53项测试、类型检查、独立/Desk路径构建通过。
- Desk配对市场53项测试、类型检查、构建通过；共享ChartKit5项测试及类型检查通过。
- 15项目/117 Mod归属检查通过。
- 隔离Desk真实行情：日线后复权、3分钟图不复权，各420条，`ready/acknowledged/received`；Context在隔离库回读一致。
- 相对强弱日线共同区间2025-01-23至2026-10-22、420点；独立页面切周度2025-01-24至2026-10-22、91点。中芯国际返回`sina-unadjusted`，如实排除；其余4只正常排名。
- 最终新ChartKit独立实机四图K线/成交量均可见。早期空轴截图不是通过证据，最终截图是`market-candles-verified-20261022.png`。

隔离状态：`runtime/project-acceptance/market-daily-8slv5_my`。原生最终产物：`/tmp/market-chart-kit-20261022-jN1hVy/verified-desk-dist`及`verified-standalone-dist`。截图目录：`/Users/lichengyin/.codex/visualizations/2026/10/19/01a15412-3a37-7863-ba8c-b0286f247ca0`。

## 边界

临时5901/5902/18940已停止，测试标签已关闭；正式服务未重启、未远端部署。这里仅市场候选通过，不代表前五组整体已发布。跨域内嵌周线按钮自动化点击未成功，独立周线点击与真实结果已验；不把自动化连接问题判作业务失败。真实newma宿主及Linux发布由主发布会话负责。
