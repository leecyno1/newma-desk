# 长历史（1800/1900–2024）全球数据库：扩展方案与口径

目标：把“周期研究”可用的长历史宏观/金融指标从当前以 UK 为主的面板扩展到多国家，并尽可能延伸到 2024。

## 1) 当前已落盘的数据面板

- 年频长历史（year-index）：`data/indicator_panel_annual_long_history_year.parquet`
  - 主体：BoE Millennium（UK，1800–2016）+ OECD（UK/EA，1960+，扩展到 2024）+ Shiller（US，1871–2023）
  - 说明：BoE 很多序列在 2016 截断，因此对部分关键序列做了 `*_EXT_OECD`（利率/失业为加性拼接；指数类为增长率拼接）与 `*_EXT_WB`（World Bank 增长率拼接）。

- 月频长历史（month-end）：`data/indicator_panel_monthly_long_history.parquet`
  - 主体：Shiller（US，1900–2023）+ OECD（UK/EA，1960+，至 2024）

## 2) 本轮新增：Maddison Project Database（MPD 2020）

新增用途：补齐“1800/1900 起”的多国家**真实经济**核心序列（人口、GDP per capita，并派生 GDP）。

- 数据源：MPD 2020（公开数据）
  - `gdppc`：2011 international-$（PPP）口径的 GDP per capita
  - `pop`：人口（单位：千人）
  - `gdp`（派生）：`gdppc * pop` → GDP（单位：百万 2011 international-$）

落盘列名约定（年频）：
- `MPD_{CC}_GDPPC_2011_INTL`
- `MPD_{CC}_POP_THOUSANDS`
- `MPD_{CC}_GDP_MN_2011_INTL`

其中 `{CC}` 为国家三字码（如 `USA/GBR/DEU/FRA/JPN/CHN/IND/...`）。

## 3) 延伸到 2024：用 World Bank 做“增长率拼接”

MPD 截止到 2018；为了满足“到 2024”，对 MPD 的 2019–2024 使用 World Bank 的增长率做**无量纲拼接**（不做跨口径换算，只借用增长率）：

- GDP per capita 扩展：用 World Bank GDPpc（level）计算增长率并拼接到 `MPD_*_GDPPC_2011_INTL`
- 人口扩展：用 World Bank `SP.POP.TOTL` 的增长率拼接到 `MPD_*_POP_THOUSANDS`
- 派生 GDP 扩展：`GDPPC_EXT * POP_EXT`

落盘列名：
- `MPD_{CC}_GDPPC_2011_INTL_EXT_WB_GROWTH`
- `MPD_{CC}_POP_THOUSANDS_EXT_WB_GROWTH`
- `MPD_{CC}_GDP_MN_2011_INTL_EXT_WB_GROWTH`

重要声明：
- 这是“增长率拼接”，不是严格的口径统一；适合做周期/频谱/相位研究，不适合做跨口径绝对水平比较。

## 4) 现阶段覆盖的资产/金融类（长历史）

- 利率：UK（BoE/OECD）、EA（OECD）、US（Shiller 10Y）
- 股市：UK（BoE/OECD 股价指数）、US（Shiller S&P）
- 汇率：UK 的 `USD/GBP` 与“实际汇率”（BoE）；多国家 FX 尚未系统补齐

## 5) 下一步（可选增强）

- 多国家利率/通胀/信用：优先补齐 1870+ 的公开宏观金融数据库（若可稳定抓取）并统一落盘口径
- 多国家 FX / 大宗 / 股指：用 OpenBB/yfinance 或替代公开源补齐（并明确可用起点年）

