# 周期判断系统项目结构

## 项目概述
基于多周期理论的量化投资决策支持系统，通过全球经济指标的周期分析，为资产配置提供数据驱动的投资建议。

## 核心模块架构

```
cycle_analysis_system/
├── config/                     # 配置文件
│   ├── __init__.py
│   ├── settings.py            # 全局配置
│   ├── indicators_config.py   # 指标配置
│   └── cycles_config.py       # 周期配置
├── data_collection/           # 数据采集模块
│   ├── __init__.py
│   ├── akshare_collector.py   # AKShare数据采集
│   ├── global_indicators.py   # 全球指标采集
│   └── data_validator.py      # 数据验证
├── cycle_analysis/            # 周期分析模块
│   ├── __init__.py
│   ├── cycle_detector.py      # 周期识别
│   ├── cycle_filter.py        # 周期滤波
│   └── cycle_classifier.py    # 周期分类
├── indicators/                # 指标体系模块
│   ├── __init__.py
│   ├── leading_indicators.py  # 先行指标
│   ├── sync_indicators.py     # 同步指标
│   └── lagging_indicators.py  # 滞后指标
├── asset_analysis/            # 资产分析模块
│   ├── __init__.py
│   ├── performance_analyzer.py # 收益分析
│   ├── risk_analyzer.py       # 风险分析
│   └── correlation_analyzer.py # 相关性分析
├── prediction/                # 预测模块
│   ├── __init__.py
│   ├── single_indicator_predictor.py # 单指标预测
│   ├── multi_cycle_predictor.py      # 多周期预测
│   └── ensemble_predictor.py         # 集成预测
├── visualization/             # 可视化模块
│   ├── __init__.py
│   ├── cycle_charts.py        # 周期图表
│   ├── performance_charts.py  # 表现图表
│   └── dashboard.py           # 仪表板
├── database/                  # 数据库模块
│   ├── __init__.py
│   ├── models.py              # 数据模型
│   └── operations.py          # 数据库操作
├── utils/                     # 工具模块
│   ├── __init__.py
│   ├── date_utils.py          # 日期工具
│   ├── math_utils.py          # 数学工具
│   └── file_utils.py          # 文件工具
├── tests/                     # 测试模块
│   ├── __init__.py
│   ├── test_data_collection.py
│   ├── test_cycle_analysis.py
│   └── test_prediction.py
├── main.py                    # 主程序入口
├── requirements.txt           # 依赖包
├── README.md                  # 项目说明
└── .cursor-rules             # Cursor开发规则
```

## 六大周期体系
1. **康波周期 (600个月)**: 技术革命驱动的长期周期
2. **地产周期 (200个月)**: 房地产投资周期
3. **资本周期 (100个月)**: 设备投资周期（朱格拉周期）
4. **基钦周期 (42个月)**: 库存周期
5. **信用周期 (20个月)**: 货币信贷周期
6. **年度周期 (12个月)**: 季节性周期

## 五大指标维度
1. **海外面**: 全球经济、贸易、汇率指标
2. **资金面**: 流动性、利率、货币政策指标
3. **基本面**: GDP、通胀、就业等宏观指标
4. **政策面**: 财政、货币政策变化指标
5. **情绪面**: 市场情绪、波动率指标

## 开发阶段规划
### 第一阶段：基础架构
- 项目结构搭建
- 配置系统建立
- 数据采集框架

### 第二阶段：数据采集
- AKShare接口集成
- 全球指标体系构建
- 数据清洗和验证

### 第三阶段：周期分析
- 周期识别算法
- 多周期滤波
- 周期位置判断

### 第四阶段：资产分析
- 收益表现分析
- 风险指标计算
- 相关性分析

### 第五阶段：预测系统
- 单指标预测模型
- 多周期集成预测
- 概率预测框架

### 第六阶段：可视化界面
- 交互式图表
- 实时仪表板
- 报告生成系统 