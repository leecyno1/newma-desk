# 经济周期分析系统

一个基于多维度指标的智能经济周期判断和分析系统，支持六种主要经济周期类型的实时分析和可视化展示。

## 🎯 项目特色

- **多周期分析**: 支持康波、地产、资本、基钦、信用、年度六种周期类型
- **五维度指标体系**: 海外面、资金面、基本面、政策面、情绪面全方位分析
- **实时数据采集**: 基于AKShare的24个核心经济指标实时获取
- **智能周期判断**: 机器学习算法自动识别当前经济周期阶段
- **交互式可视化**: Streamlit仪表板提供丰富的图表和分析界面
- **风险评估**: 综合风险水平评估和投资建议

## 📊 系统架构

```
cycle_analysis_system/
├── analysis/                 # 周期分析核心模块
│   ├── __init__.py
│   └── cycle_analyzer.py     # 周期分析器
├── config/                   # 配置管理
│   ├── __init__.py
│   ├── settings.py          # 系统设置
│   ├── indicators_config.py # 指标配置
│   └── cycles_config.py     # 周期配置
├── data_collection/          # 数据采集模块
│   ├── __init__.py
│   └── akshare_collector.py # AKShare数据采集器
├── visualization/            # 可视化模块
│   ├── __init__.py
│   └── dashboard.py         # Streamlit仪表板
├── tests/                   # 测试模块
├── main.py                  # 主程序入口
├── run_dashboard.py         # 仪表板启动脚本
├── requirements.txt         # 依赖包列表
└── README.md               # 项目文档
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd cycle_analysis_system

# 创建虚拟环境（推荐）
conda create -n cycle_analysis python=3.9
conda activate cycle_analysis

# 安装依赖
pip install -r requirements.txt
```

### 2. 基础测试

```bash
# 测试系统配置
python main.py --mode test

# 测试数据采集
python test_updated_collection.py

# 测试周期分析
python test_cycle_analysis.py
```

### 3. 启动可视化仪表板

```bash
# 方式1：使用启动脚本（推荐）
python run_dashboard.py

# 方式2：直接运行streamlit
streamlit run visualization/dashboard.py
```

访问 http://localhost:8501 查看仪表板

## 📈 功能模块

### 数据采集模块

- **支持指标**: 24个核心经济指标
- **数据源**: AKShare金融数据接口
- **更新频率**: 实时获取最新数据
- **容错机制**: 智能重试和错误处理

### 周期分析模块

- **分析算法**: 基于机器学习的周期识别
- **周期类型**: 
  - 康波周期 (50-60年)
  - 地产周期 (18-20年)
  - 资本开支周期 (9-10年)
  - 基钦周期 (3-4年)
  - 信用周期 (1.5-2年)
  - 年度周期 (1年)

- **分析维度**:
  - 海外面: 美国经济指标
  - 资金面: 货币政策和流动性
  - 基本面: 实体经济指标
  - 政策面: 政府政策和利率
  - 情绪面: 市场情绪和预期

### 可视化模块

- **综合分析**: 所有周期类型概览
- **单一周期分析**: 深度分析特定周期
- **指标趋势分析**: 关键指标走势图
- **风险评估**: 综合风险水平评估

## 🔧 配置说明

### 指标配置 (indicators_config.py)

```python
# 示例：添加新指标
new_indicator = IndicatorConfig(
    name="新指标名称",
    akshare_function="ak.function_name",
    dimension=IndicatorDimension.FUNDAMENTAL,
    indicator_type=IndicatorType.LEADING,
    weight=0.1,
    frequency="monthly",
    lag_months=1,
    data_source="AKShare",
    description="指标描述"
)
```

### 系统设置 (settings.py)

```python
# 主要配置项
DATA_COLLECTION_TIMEOUT = 30      # 数据采集超时时间
MAX_CONCURRENT_REQUESTS = 5       # 最大并发请求数
CACHE_EXPIRY_HOURS = 24           # 缓存过期时间
LOG_LEVEL = "INFO"                # 日志级别
```

## 📊 使用示例

### 命令行分析

```python
from analysis.cycle_analyzer import CycleAnalyzer, CycleType

# 创建分析器
analyzer = CycleAnalyzer()

# 分析基钦周期
result = analyzer.analyze_cycle(CycleType.KITCHIN)
print(f"当前阶段: {result.current_phase.value}")
print(f"置信度: {result.phase_confidence:.2%}")
print(f"风险水平: {result.risk_level}")

# 获取所有周期摘要
summary = analyzer.get_cycle_summary()
for cycle_type, info in summary.items():
    print(f"{cycle_type}: {info['current_phase']} (置信度: {info['confidence']:.2%})")
```

### 数据采集

```python
from data_collection.akshare_collector import AKShareCollector

# 创建采集器
collector = AKShareCollector()

# 获取单个指标
data = collector.fetch_indicator("中国制造业PMI")

# 获取所有指标
all_data = collector.fetch_all_indicators()
```

## 🎨 仪表板功能

### 1. 综合分析页面
- 周期阶段分布饼图
- 置信度水平柱状图
- 风险评估可视化
- 历史位置散点图

### 2. 单一周期分析页面
- 基本信息指标卡
- 五维度雷达图
- 阶段转换概率图
- 关键指标列表

### 3. 指标趋势分析页面
- 分维度趋势图表
- 数据可用性统计
- 实时数据更新

### 4. 风险评估页面
- 综合风险气泡图
- 风险分布统计
- 投资建议

## 🔍 技术栈

- **后端**: Python 3.9+
- **数据处理**: Pandas, NumPy, SciPy
- **机器学习**: Scikit-learn
- **数据源**: AKShare
- **可视化**: Streamlit, Plotly
- **异步处理**: asyncio, aiohttp
- **日志**: Loguru
- **配置管理**: Pydantic

## 📝 开发指南

### 添加新指标

1. 在 `indicators_config.py` 中添加指标配置
2. 确保AKShare函数名正确
3. 设置合适的权重和维度
4. 测试数据获取功能

### 添加新周期类型

1. 在 `cycles_config.py` 中定义新周期
2. 更新 `CycleType` 枚举
3. 在分析器中添加相应逻辑
4. 更新可视化界面

### 自定义分析算法

1. 继承 `CycleAnalyzer` 类
2. 重写 `_calculate_cycle_phase` 方法
3. 实现自定义的周期判断逻辑
4. 添加相应的测试用例

## 🧪 测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python test_cycle_analysis.py
python test_updated_collection.py

# 性能测试
python main.py --mode benchmark
```

## 📈 性能优化

- **数据缓存**: 使用内存和磁盘缓存减少API调用
- **异步处理**: 并发获取多个指标数据
- **智能重试**: 网络错误自动重试机制
- **增量更新**: 只获取新增数据

## 🚨 注意事项

1. **API限制**: AKShare有访问频率限制，请合理使用
2. **数据质量**: 部分指标可能存在缺失或延迟
3. **网络依赖**: 需要稳定的网络连接获取数据
4. **计算资源**: 大量数据处理需要足够的内存

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📞 联系方式

- 项目维护者: [您的姓名]
- 邮箱: [您的邮箱]
- 项目链接: [项目地址]

## 🙏 致谢

- [AKShare](https://github.com/akfamily/akshare) - 提供优秀的金融数据接口
- [Streamlit](https://streamlit.io/) - 强大的数据应用框架
- [Plotly](https://plotly.com/) - 交互式可视化库

---

**免责声明**: 本系统仅供学习和研究使用，不构成投资建议。投资有风险，决策需谨慎。 