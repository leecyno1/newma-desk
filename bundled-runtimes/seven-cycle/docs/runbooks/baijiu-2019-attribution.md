# 2019 白酒归因报告运行手册

## 用途

`report-baijiu-2019` 用于生成 M3 的正式验收报告。报告同时展示：

- 中证白酒 `399997.SZ` 的低置信度、强收缩结果；
- 中信食品饮料 `CI005019.CI` 的独立代理结果；
- 绝对收益及相对沪深 300 `000300.SH` 的超额收益；
- realtime 与 latest-historical 两套独立运行的归因差异；
- C1–C7、传导渠道、估值、事件、残差、50%/80% 区间和证据等级。

主指数与代理必须同时存在。代理不得替代、拼接或冒充主指数。

## 前置产物

两份已发布运行必须各自包含：

- `asset_attribution.parquet`
- `asset_attribution_conservation.parquet`
- `manifest.json`

每份 manifest 的 `quality_summary.baijiu_2019` 必须记录：

- 当前运行的 `interpretation` 与 `vintage_kind`；
- `realtime`、`latest_historical` 对应的两个 run ID；
- 2019-01-31 至 2019-12-31、12 个月口径；
- 沪深 300 基准；
- 白酒主指数和食品饮料代理的 symbol、proxy 状态、历史与收缩状态；
- 每个不可用归因行的明确原因，键格式为
  `asset_id|return_basis|component_type|component_id`。

报告命令会先校验两份 manifest、文件校验和、Parquet schema、产品契约、
点贡献守恒和主指数/代理完整性。任一门槛失败时不会写出正式报告。

## 运行

```bash
seven-cycle report-baijiu-2019 \
  --run-id <realtime-or-latest-historical-run-id> \
  --product-root products/seven_cycle
```

## 输出

为保持 `runs/<run_id>` 不可变，报告写入派生目录：

```text
products/seven_cycle/reports/<requested-run-id>/baijiu_2019.md
products/seven_cycle/reports/<requested-run-id>/baijiu_2019.json
```

Markdown 与 JSON 会先在同一临时目录完整写入并同步，再通过整目录原子切换
成对发布。相同输入重复执行会复用相同字节；若目标位置已有不同内容，命令会
拒绝覆盖。任何 symlink 路径或非普通文件都会被拒绝。

## 数字来源

报告模板不包含任何白酒收益、超额收益或贡献的固定数值。所有正式数字均来自
两份已验证的 `asset_attribution` 产品或其 manifest provenance；Markdown 中的
百分比只是对 Parquet 小数收益的显示转换。

## 常见失败

- `manifest ... checksums`：运行文件被修改或不完整；重新发布运行，不要手工修补。
- `interpretation_runs is missing`：双 vintage 映射不完整。
- `unavailable reason is missing`：不可用渠道缺少可审计原因。
- `primary ... is missing; proxy ... cannot replace it`：只有代理结果，禁止正式发布。
- `benchmark must be HS300`：manifest 未按正式基准标记沪深 300。
