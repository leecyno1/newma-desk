# Tushare Coverage (Draft)

本文件用于记录使用 Tushare 作为统一数据源时，各类核心指标/资产的可用区间和完整度。

## 1. 配置说明

- 当前使用的 Token: 仅在代码中配置（避免明文出现在文档中）
- 访问方式: `tushare.pro_api`，超时默认 30 秒

## 2. 指数类 (index_daily)

待通过 `cycle_analysis_system.huatai.data_loader_ts.get_index_coverage` 自动生成/更新。

计划覆盖的指数包括但不限于：
- 上证综指: `000001.SH`
- 深证成指: `399001.SZ`
- 沪深 300: `000300.SH`
- 中证 500: `000905.SH`
- 中证 1000: `000852.SH`
- 中证全指: `000985.CSI`（如可用）

## 3. 宏观指标 (macro)

目前在 `data_loader_ts.get_macro_monthly` 中预设：
- `cpi_yoy`: 居民消费价格指数同比 (`pro.cn_cpi`)
- `ppi_yoy`: 工业生产者出厂价格指数同比 (`pro.cn_ppi`)

后续将根据《经济周期实证、理论及应用》以及西南金工指标 Excel，逐步补充：
- 工业增加值、社融、M1/M2、房地产投资、固定资产投资等。

## 4. 后续工作

- [ ] 编写小脚本扫描各类 ts_code / 宏观指标的最早/最晚日期，并自动更新本文件
- [ ] 对比 Huatai 报告中使用的样本区间，评估缺失情况
- [ ] 与现有 FRED / Stooq 数据做交叉验证，检查极端值和断档

