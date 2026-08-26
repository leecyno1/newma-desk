# 指标体系设计（≥100 个指标，按类别划分，数据源：Tushare Pro + OpenBB + AkShare 等）

> 说明：本文件是“指标字典”，用于指导后续的统一数据拉取与加工。  
> 数值数据统一通过代码从 Tushare Pro、OpenBB、本地/海外公开数据源获取，不直接使用 Excel / PDF 中的原始数值。

## 1. 宏观增长类（Macro Growth）

代表指标（约 20 个）：

1. CN_GDP_NOMINAL           – 中国名义 GDP（年频，Tushare/官方）
2. CN_GDP_REAL              – 中国实际 GDP（年频，Tushare/官方）
3. CN_IP_YOY                – 规模以上工业增加值同比（月/年，AkShare/Tushare）
4. CN_RETAIL_TOTAL_YOY      – 社会消费品零售总额同比（月/年）
5. CN_FIX_INV_TOTAL_YOY     – 固定资产投资完成额同比（月/年）
6. CN_FIX_INV_INFRA_YOY     – 基建投资同比
7. CN_FIX_INV_MANU_YOY      – 制造业投资同比
8. CN_FIX_INV_RE_YOY        – 房地产开发投资同比
9. CN_EXPORT_YOY            – 出口金额同比
10. CN_IMPORT_YOY           – 进口金额同比
11. CN_NET_EXPORT_YOY       – 贸易顺差同比
12. CN_PMFG_INDEX           – 制造业 PMI 指数（月度）
13. CN_PMFG_NEW_ORDER       – PMI 新订单分项
14. CN_PMFG_NEW_EXPORT      – PMI 新出口订单
15. CN_PMFG_INV             – PMI 原材料库存
16. CN_PMI_NONMFG           – 非制造业 PMI
17. CN_POWER_GEN_YOY        – 全社会发电量同比
18. CN_FREIGHT_VOL_YOY      – 货运量同比
19. CN_AUTO_SALES_YOY       – 汽车销量同比
20. CN_REAL_ESTATE_SALES_YOY – 商品房销售面积/金额同比

## 2. 通胀与价格类（Inflation & Prices）

代表指标（约 15 个）：

21. CN_CPI_HEADLINE_YOY     – CPI 总指数同比（Tushare cn_cpi）
22. CN_CPI_CORE_YOY         – 核心 CPI 同比（若有）
23. CN_CPI_FOOD_YOY         – 食品 CPI 同比
24. CN_CPI_NONFOOD_YOY      – 非食品 CPI 同比
25. CN_PPI_HEADLINE_YOY     – PPI 总指数同比（Tushare cn_ppi.ppi_yoy）
26. CN_PPI_MP_YOY           – PPI 生产资料同比
27. CN_PPI_CG_YOY           – PPI 生活资料同比
28. CN_PPI_RAWMAT_YOY       – PPI 原材料同比
29. CN_PPI_INTER_YOY        – PPI 中间品同比
30. CN_PPI_CONS_YOY         – PPI 终端消费品同比
31. CRB_INDEX               – CRB 大宗商品价格指数（月/日，OpenBB/海外）
32. OIL_WTI_SPOT            – WTI 原油现货价格
33. OIL_BRENT_SPOT          – Brent 原油现货价格
34. CN_STEEL_PRICE_IDX      – 中国钢价综合指数
35. CN_COAL_PRICE_IDX       – 中国动力煤价格指数

## 3. 货币与信用类（Money & Credit）

代表指标（约 15 个）：

36. CN_M0_YOY               – M0 同比
37. CN_M1_YOY               – M1 同比
38. CN_M2_YOY               – M2 同比
39. CN_SOCIAL_FIN_FLOW      – 社会融资规模单月新增（绝对额）
40. CN_SOCIAL_FIN_STOCK_YOY – 社融存量同比
41. CN_NEW_RMB_LOANS        – 金融机构人民币贷款新增额
42. CN_TOTAL_LOANS_STOCK_YOY – 贷款余额同比
43. CN_HOUSEHOLD_LOANS_YOY  – 居民贷款余额同比
44. CN_CORP_LOANS_YOY       – 非金融企业贷款余额同比
45. CN_REAL_ESTATE_LOANS_YOY – 房地产贷款余额同比
46. CN_TRUST_LOANS_YOY      – 信托贷款余额同比
47. CN_WEALTH_MGMT_YOY      – 理财产品余额同比（如可得）
48. CN_CREDIT_IMPULSE       – 信用脉冲（社融/GDP 环比或同比变化构造）
49. CN_SHADOW_BANKING_IDX   – 影子银行规模指数（如可构造）
50. CN_FISCAL_DEFICIT_GDP   – 财政赤字占 GDP 比重

## 4. 利率与债券类（Rates & Bonds）

代表指标（约 15 个）：

51. CN_POLICY_RATE_1Y       – 1 年期贷款基础利率 LPR / 基准利率
52. CN_POLICY_RATE_5Y       – 5 年期 LPR
53. CN_SHIBOR_O/N           – 银行间隔夜拆借利率
54. CN_SHIBOR_3M            – 3 个月 Shibor
55. CN_GOV_BOND_1Y          – 1 年期国债收益率
56. CN_GOV_BOND_3Y          – 3 年期国债收益率
57. CN_GOV_BOND_5Y          – 5 年期国债收益率
58. CN_GOV_BOND_10Y         – 10 年期国债收益率
59. CN_GOV_BOND_TERM_SPREAD – 10Y-1Y 利差
60. CN_CREDIT_AAA_3Y        – AAA 企业债 3 年期收益率
61. CN_CREDIT_AA_3Y         – AA 企业债 3 年期收益率
62. CN_CREDIT_SPREAD_AAA_3Y – 3 年期 AAA 信用利差（AAA-国债）
63. CN_CREDIT_SPREAD_AA_3Y  – 3 年期 AA 信用利差
64. CN_CB_INDEX             – 可转债综合指数收益率
65. CN_BOND_TERM_PREMIUM    – 期限利差风险溢价 proxy

## 5. 汇率与外部部门（FX & External）

代表指标（约 10 个）：

66. USD_CNY_SPOT            – 即期美元兑人民币汇率
67. USD_CNY_CFETS           – CFETS 人民币指数
68. DXY_INDEX               – 美元指数 DXY（OpenBB/yfinance）
69. CN_FOREX_RESERVES       – 中国外汇储备规模
70. CN_CURRENT_ACC_GDP      – 经常账户余额占 GDP 比重
71. CN_CAPITAL_ACC_GDP      – 资本项目占 GDP 比重
72. CN_FDI_NET              – 外商直接投资净额
73. CN_PORTFOLIO_FLOW       – 证券投资流入/流出（如可得）
74. NORTHBOUND_NET_FLOW     – 陆股通资金净流入（日/月）
75. SOUTHBOUND_NET_FLOW     – 港股通资金净流入

## 6. 股票市场与估值（Equity Market & Valuation）

代表指标（约 15 个）：

76. IDX_SH_COMP_TR          – 上证综指总回报指数（月度，TR 近似）
77. IDX_SZ_COMP_TR          – 深证成指总回报指数
78. IDX_HS300_TR            – 沪深 300 总回报指数
79. IDX_CSI500_TR           – 中证 500 总回报指数
80. IDX_CSI1000_TR          – 中证 1000 总回报指数
81. IDX_GEM_TR              – 创业板指数总回报
82. IDX_STAR50_TR           – 科创 50 指数总回报
83. IDX_CITIC_L1_xx_TR      – 中信一级行业各指数总回报（若可得）
84. HS300_PE_TTM            – 沪深 300 市盈率 TTM
85. HS300_PB                – 沪深 300 市净率
86. HS300_ROE_TTM           – 沪深 300 ROE（TTM）
87. A_SHARE_ERP             – A 股权益风险溢价（ERP 表中的构造）
88. CN_MARGIN_FIN_BAL       – 融资余额
89. CN_MARGIN_FIN_YOY       – 融资余额同比
90. CN_TURNOVER_A_SHARE     – A 股总成交额/换手率

## 7. 情绪与风险偏好（Sentiment & Risk Appetite）

代表指标（约 15 个）：

91. CN_INVESTOR_SENTIMENT_IDX – 投资者情绪综合指数（由情绪表构造）
92. IPO_COUNT_A_SHARE        – A 股 IPO 数量
93. IPO_PROCEEDS_A_SHARE     – A 股 IPO 融资额
94. CN_VOL_INDEX             – A 股波动率指数（如有）
95. CN_PUT_CALL_RATIO        – 权证/期权认沽认购比（如可得）
96. CN_STOCK_INDEX_FUT_POS   – 股指期货净多/净空持仓
97. CN_MARGIN_TRADING_RATIO  – 融资融券余额/总市值
98. CN_HY_SPREAD_PROXY       – 高收益信用利差 proxy
99. CN_FEAR_GREED_PROXY      – 恐慌与贪婪组合指标
100. MEDIA_SENTIMENT_CN      – 媒体情绪指数（如 NLP 处理后）

## 8. 全球资产与对照指标（Global Assets & Benchmarks）

代表指标（≥ 10 个）：

101. US_SPX_TR               – 标普 500 总回报指数（OpenBB/yfinance，含分红）
102. US_NDX_TR               – 纳斯达克 100 总回报指数
103. EU_STOXX50_TR           – 欧洲 STOXX50 总回报指数
104. JP_NIKKEI225_TR         – 日经 225 总回报指数
105. EM_MSCI_EM_TR           – MSCI 新兴市场总回报指数
106. US_10Y_YIELD            – 美国 10 年期国债收益率
107. US_TREASURY_TERM_SPREAD – 美国 10Y–2Y 利差
108. GOLD_LBMA_TR            – 伦敦金总回报指数（含持有成本，可近似）
109. GSCI_COMMODITY_TR       – 标普 GSCI 大宗商品总回报
110. VIX_INDEX               – 美股恐慌指数 VIX

---

后续实现中，每个指标会在 `indicator_registry.py` 中赋予：

- `id`：程序内部使用的唯一标识（如 `CN_CPI_HEADLINE_YOY`）
- `name`：中文描述
- `category`：上述类别之一
- `source`：优先数据源（Tushare / AkShare / OpenBB / FRED / FF 等）
- `backend_params`：数据接口所需的代码/表名
- `base_freq`：原始频率（年 / 季 / 月 / 日）
- `value_type`：原始值类型（绝对量 / 指数 / 比率 / 已经是同比等）

统一拉取后，将按照：

- 2000 年之前：以年频为主（取年末或全年均值），构造 YoY；
- 2000 年之后：以月频为主，同时汇总到年频；
- 对价格/指数类：使用复权价或总回报（OpenBB 调整价 / 分红信息）计算月度总回报；
- 对宏观量：统一构造环比（MoM）和同比（YoY）两个版本，供周期分析使用。
