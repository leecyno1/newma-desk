# 候选测试指标库（~60 年月频，供周期/频谱分析使用）

> 目的：列出尽可能覆盖 1965–2024 的经济与市场指标，用于后续通用周期/频谱分析和机器学习研究。  
> 数据源以 FRED、Stooq 等公共来源为主，便于在代码中自动获取和更新。  
> 注意：本表为“指标清单”，不是直接照抄本地 Excel 的数据。

---

## 1. 宏观经济指标（FRED）

### 1.1 通胀与物价

- CPI：`CPIAUCSL`
  - Consumer Price Index for All Urban Consumers: All Items (SA)
  - 频率：月度，自 1947 年起（可覆盖 1965–）。
  - 用法：取环比 `%ΔCPI` 或同比 `%ΔYoY`，做周期分析和通胀波动研究。

- PCE 物价指数：`PCEPI`
  - Personal Consumption Expenditures: Chain-type Price Index
  - 频率：月度，自 1959 年起。
  - 用法：作为 CPI 的补充，更贴近居民消费结构。

- 生产者物价指数：`PPIACO`
  - Producer Price Index by Commodity: All Commodities
  - 频率：月度，自 1913 年起。
  - 用法：中游/上游价格周期、成本推进型通胀研究。

### 1.2 产出与经济活动

- 工业生产指数：`INDPRO`
  - Industrial Production Index
  - 频率：月度，自 1919 年起。
  - 用法：衡量工业景气，可用于识别 3–10 年左右的商业周期。

- 非农就业人数：`PAYEMS`
  - All Employees: Total Nonfarm Payrolls
  - 频率：月度，自 1939 年起。
  - 用法：劳动力市场景气、就业周期。

- 失业率：`UNRATE`
  - Unemployment Rate
  - 频率：月度，自 1948 年起。
  - 用法：与产出缺口/商业周期相对应的“滞后”或同步指标。

- 零售销售：`RSAFS` 或 `RRSFS`
  - Retail Sales（或 Real Retail and Food Services Sales）
  - 频率：月度，自 1950s–1960s 起（具体起始视系列而定）。
  - 用法：消费周期、需求侧波动。

### 1.3 货币与信贷

- M2 货币供应量：`M2SL`
  - M2 Money Stock
  - 频率：月度，自 1959 年起。
  - 用法：宽货币环境、流动性周期。

- 联邦基金利率：`FEDFUNDS`
  - Effective Federal Funds Rate
  - 频率：月度（由日频/周频聚合），自 1954 年起。
  - 用法：货币政策立场、利率周期。

- 美国 10 年期国债收益率：`DGS10`
  - 10-Year Treasury Constant Maturity Rate
  - 频率：日度，自 1962 年起，可聚合为月度。
  - 用法：长期利率周期、通胀预期与风险溢价。

- 美国 2 年期国债收益率：`DGS2`
  - 2-Year Treasury Constant Maturity Rate
  - 频率：日度，自 1976 年起。
  - 用法：短端利率、期限结构分析。

- 期限利差：`T10Y3M`
  - 10-Year Treasury minus 3-Month Treasury Bill
  - 频率：日度，可转月度。
  - 用法：经典衰退预测指标，与中周期/长周期关系密切。

- 信用利差：`BAA10Y`
  - Moody's Seasoned Baa Corporate Bond Yield Relative to Yield on 10-Year Treasury Constant Maturity
  - 频率：月度，自 1950s 起。
  - 用法：信用风险偏好、金融周期。

---

## 2. 金融市场指数（Stooq / FRED / ETF）

### 2.1 美国股指

- 标普 500 指数（价指数）：
  - Stooq：`^SPX`（或 `spx` 系列），日度数据可追溯数十年，可聚合成月度。
  - FRED：`SP500`（日度），同样可聚合为月度。
  - 用法：作为全球股票风险溢价的重要代表，检测长/中周期与股市的关系。

- 道琼斯工业平均：`^DJI`（Stooq）
  - 日度，自 19xx 起，月度聚合。
  - 用法：更偏传统工业权重的美国股市指标。

- 纳斯达克 100：`^NDX` 或 ETF QQQ（`qqq.us`）
  - 作为科技成长代表，历史稍短，但足够覆盖 20–30 年周期分析。

### 2.2 海外主要股指

- 英国富时 100：`^UKX`（Stooq）
- 法国 CAC40：`^CAC`（Stooq）
- 德国 DAX：`^DAX`（Stooq）
- 日本 Nikkei 225：`^NKX`（Stooq）
  - 上述指数多有 1960s–1980s 起的历史，可用于全球同步/错位周期研究。

### 2.3 行业与风格（美股为主）

- 美股行业 ETF（SPDR Sector ETFs）：
  - 可选消费：`XLY`
  - 必选消费：`XLP`
  - 能源：`XLE`
  - 金融：`XLF`
  - 工业：`XLI`
  - 信息科技：`XLK`
  - 公用事业：`XLU`
  - 医疗保健：`XLV`
  - 原材料：`XLB`
  - 历史：多数从 1998–2000 年左右开始，适合做近 25 年的行业周期分析（不满 60 年，但行业信息丰富）。

- Fama-French 行业组合（US）：
  - 数据集：`17_Industry_Portfolios`（via pandas_datareader / famafrench）
  - 提供 17 个行业的月度收益率（%），历史可追溯至 1960s 甚至更早。
  - 用法：学术口径的美国行业指数，可用于验证周期性结构和跨资产因子。

---

## 3. 大宗商品与汇率

- WTI 原油价格：`DCOILWTICO`（FRED）
  - 日度，自 1986 年起，聚合为月度。
  - 虽不足完整 60 年，但足够覆盖若干库存/能源价格周期。

- 黄金价格（London Fix / LBMA）：`GOLDAMGBD228NLBM`（FRED）
  - 日度，自 1968 年起，可聚合为月度。
  - 用法：货币/风险偏好长期周期的对照资产。

- 美元指数：`DTWEXBGS`（FRED）
  - Trade Weighted U.S. Dollar Index: Broad, Goods
  - 频率：月度，自 1973 年起。
  - 用法：全球流动性、美元周期。

---

## 4. 中国相关（作为局部参考）

> 中国完整高质量宏观月频数据普遍开始于 1990s–2000s，因此很难覆盖完整 60 年。  
> 这里列出的主要用于 20–30 年窗口，但可以与上述长历史指标配合使用。

- 中国 PMI：官方制造业 PMI（2005 年起）
- 中国工业增加值：国家统计局数据（大致 1990s 以后）
- 中国 CPI / PPI：1990s 起
- 主要股指：沪深300、中证500、中证1000（2000s 以后）
- 行业指数：中信一级行业指数（Tushare 约 2010 年起，可用于行业轮动验证）

这些指标可以纳入研究体系，但在“60 年周期”分析中更多用于 **后 20–30 年的局部验证**。

---

## 5. 小结：后续频谱分析的推荐指标集

为了进行“先不预设 5 个周期，基于数据找出显著周期”的频谱分析，建议首选以下指标（基本都可覆盖 1965–2024）：

1. 宏观：
   - CPI：`CPIAUCSL`
   - PPI：`PPIACO`
   - 工业生产：`INDPRO`
   - 非农就业：`PAYEMS`
   - 失业率：`UNRATE`
   - M2：`M2SL`
   - Fed Funds：`FEDFUNDS`
   - 10Y/2Y 利率：`DGS10`, `DGS2`
   - 期限利差：`T10Y3M`
   - 信用利差：`BAA10Y`

2. 市场：
   - 美股：`^SPX`, `^DJI`, `^NDX`
   - 欧洲/日本：`^UKX`, `^CAC`, `^DAX`, `^NKX`
   - 大宗：`DCOILWTICO`, `GOLDAMGBD228NLBM`
   - 美元指数：`DTWEXBGS`
   - 美股行业 ETF：XLY, XLP, XLE, XLF, XLI, XLK, XLU, XLV, XLB（约 25 年历史）
   - FF 17 行业组合（US）：`17_Industry_Portfolios`

后续脚本可以基于上述列表自动抓取数据、统一为月度环比/收益，并对每个指标进行频谱分析，寻找数据驱动的显著周期结构。 
