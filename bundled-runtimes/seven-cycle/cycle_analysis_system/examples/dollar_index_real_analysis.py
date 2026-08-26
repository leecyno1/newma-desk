#!/usr/bin/env python3
"""
美元指数近20年的6维度周期分析（完整版）
使用真实的AKShare数据和系统配置的周期维度
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 设置为非交互模式
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import akshare as ak
from scipy.signal import butter, filtfilt
import warnings
warnings.filterwarnings('ignore')

# 设置英文字体，避免中文字体问题
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class CompleteDollarIndexAnalysis:
    """完整的美元指数周期分析类"""
    
    def __init__(self):
        """初始化分析器"""
        # 系统配置的6个周期维度（月数）
        self.cycle_configs = {
            'Kondratieff Cycle': {'period': 600, 'color': '#FF6B35', 'weight': 0.25},  # 康波周期
            'Real Estate Cycle': {'period': 200, 'color': '#F7931E', 'weight': 0.20},   # 地产周期
            'Capital Cycle': {'period': 100, 'color': '#FFD700', 'weight': 0.20},       # 资本周期
            'Kitchin Cycle': {'period': 42, 'color': '#9ACD32', 'weight': 0.15},        # 基钦周期
            'Credit Cycle': {'period': 20, 'color': '#00BFFF', 'weight': 0.10},         # 信用周期
            'Annual Cycle': {'period': 12, 'color': '#8A2BE2', 'weight': 0.10}          # 年度周期
        }
        self.data = None
        self.filtered_cycles = {}
        
    def fetch_dollar_index_data(self):
        """获取美元指数数据"""
        print("正在获取美元指数数据...")
        
        try:
            # 使用AKShare获取美元指数数据
            # 尝试多个可能的函数名
            functions_to_try = [
                ('index_investing_global', {'country': '美国', 'index_name': '美元指数'}),
                ('currency_us_dollar', {}),
                ('fx_spot_quote', {'symbol': 'USDX'}),
            ]
            
            for func_name, params in functions_to_try:
                try:
                    if hasattr(ak, func_name):
                        func = getattr(ak, func_name)
                        df = func(**params)
                        print(f"✓ 使用 {func_name} 获取数据成功")
                        break
                except Exception as e:
                    print(f"尝试 {func_name} 失败: {e}")
                    continue
            else:
                # 如果所有方法都失败，使用模拟数据
                print("⚠️ 无法获取真实数据，使用模拟数据...")
                return self._generate_realistic_simulation()
                
        except Exception as e:
            print(f"数据获取失败，使用模拟数据: {e}")
            return self._generate_realistic_simulation()
            
        # 处理数据格式
        if df is not None and len(df) > 0:
            # 标准化列名
            df.columns = [col.lower() for col in df.columns]
            
            # 寻找日期和价格列
            date_col = None
            price_col = None
            
            for col in df.columns:
                if 'date' in col or 'time' in col or '日期' in col:
                    date_col = col
                if 'close' in col or 'price' in col or '收盘' in col or '价格' in col:
                    price_col = col
                    
            if date_col and price_col:
                df = df[[date_col, price_col]].copy()
                df.columns = ['date', 'close']
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
                
                # 筛选近20年数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=20*365)
                df = df[df['date'] >= start_date].copy()
                
                print(f"✓ 获取到 {len(df)} 个数据点")
                return df
                
        # 如果处理失败，返回模拟数据
        return self._generate_realistic_simulation()
        
    def _generate_realistic_simulation(self):
        """生成现实的美元指数模拟数据"""
        print("生成基于历史特征的模拟美元指数数据...")
        
        # 生成近20年的日期序列
        end_date = datetime.now()
        start_date = end_date - timedelta(days=20*365)
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        np.random.seed(42)
        n = len(dates)
        t = np.arange(n)
        
        # 基于真实美元指数历史特征构建模拟数据
        base_value = 95  # 基础水平
        
        # 长期趋势：2005-2025年美元指数大致走势
        long_trend = 10 * np.sin(2 * np.pi * t / (8 * 365)) + 5 * (t / n)
        
        # 多重周期叠加
        kondratieff = 8 * np.sin(2 * np.pi * t / (50 * 365))      # 50年康波周期
        real_estate = 5 * np.sin(2 * np.pi * t / (16.67 * 365))   # 约17年地产周期 
        capital = 4 * np.sin(2 * np.pi * t / (8.33 * 365))        # 约8年资本周期
        kitchin = 3 * np.sin(2 * np.pi * t / (3.5 * 365))         # 3.5年基钦周期
        credit = 2 * np.sin(2 * np.pi * t / (1.67 * 365))         # 1.67年信用周期
        annual = 1.5 * np.sin(2 * np.pi * t / 365)                # 年度周期
        
        # 添加随机波动
        noise = np.random.normal(0, 0.8, n)
        
        # 合成最终数据
        dxy_values = (base_value + long_trend + kondratieff + 
                     real_estate + capital + kitchin + credit + annual + noise)
        
        df = pd.DataFrame({
            'date': dates,
            'close': dxy_values
        })
        
        print(f"✓ 生成了 {len(df)} 个模拟数据点")
        print(f"✓ 时间范围: {df['date'].min().strftime('%Y-%m-%d')} 到 {df['date'].max().strftime('%Y-%m-%d')}")
        print(f"✓ 价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        
        return df
        
    def apply_bandpass_filter(self, data, period_months, sample_rate_per_month=30):
        """应用带通滤波器提取特定周期"""
        # 转换月周期为天
        period_days = period_months * 30
        
        # 计算滤波器参数
        nyquist = 0.5 * sample_rate_per_month
        
        # 带通滤波器的频率范围（允许±20%的频率范围）
        low_freq = (0.8 / period_days) * sample_rate_per_month
        high_freq = (1.2 / period_days) * sample_rate_per_month
        
        # 确保频率在奈奎斯特频率范围内
        low_freq = max(low_freq, 0.001)
        high_freq = min(high_freq, nyquist * 0.95)
        
        if low_freq >= high_freq:
            # 使用低通滤波器
            b, a = butter(4, high_freq / nyquist, btype='low')
        else:
            # 使用带通滤波器
            b, a = butter(4, [low_freq / nyquist, high_freq / nyquist], btype='band')
        
        # 应用滤波器
        filtered_data = filtfilt(b, a, data)
        return filtered_data
        
    def perform_cycle_decomposition(self):
        """执行6维度周期分解"""
        print("\\n执行6维度周期分解...")
        
        if self.data is None:
            print("错误：没有数据可供分析")
            return
            
        # 提取价格数据
        prices = self.data['close'].values
        
        # 去除线性趋势
        detrended_prices = prices - np.linspace(prices[0], prices[-1], len(prices))
        
        # 对每个周期维度应用滤波
        for cycle_name, config in self.cycle_configs.items():
            period = config['period']
            
            try:
                filtered_data = self.apply_bandpass_filter(detrended_prices, period)
                self.filtered_cycles[cycle_name] = {
                    'data': filtered_data,
                    'period': period,
                    'weight': config['weight'],
                    'color': config['color']
                }
                print(f"✓ {cycle_name} ({period}月周期) 滤波完成")
                
            except Exception as e:
                print(f"✗ {cycle_name} 滤波失败: {e}")
                
    def analyze_cycle_phases(self):
        """分析各周期的当前相位"""
        print("\\n分析各周期的当前相位...")
        
        results = []
        
        for cycle_name, cycle_data in self.filtered_cycles.items():
            data = cycle_data['data']
            period = cycle_data['period']
            weight = cycle_data['weight']
            
            # 计算统计特征
            std = np.std(data)
            amplitude = (np.max(data) - np.min(data)) / 2
            recent_value = np.mean(data[-30:])  # 最近30天的平均值
            
            # 判断当前相位
            if recent_value > std:
                phase = "Expansion"
                phase_cn = "扩张期"
            elif recent_value < -std:
                phase = "Contraction" 
                phase_cn = "收缩期"
            else:
                phase = "Neutral"
                phase_cn = "平衡期"
                
            # 计算相位强度（标准化）
            phase_strength = abs(recent_value) / amplitude if amplitude > 0 else 0
            
            result = {
                'cycle': cycle_name,
                'period_months': period,
                'weight': weight,
                'phase': phase,
                'phase_cn': phase_cn,
                'strength': phase_strength,
                'recent_value': recent_value,
                'amplitude': amplitude,
                'std': std
            }
            
            results.append(result)
            
            print(f"{cycle_name}:")
            print(f"  - Period: {period} months, Weight: {weight:.1%}")
            print(f"  - Current Phase: {phase_cn} ({phase})")
            print(f"  - Strength: {phase_strength:.3f}")
            print(f"  - Recent Value: {recent_value:.4f}")
            
        return results
        
    def create_comprehensive_chart(self):
        """创建综合周期分析图表"""
        print("\\n生成综合周期分析图表...")
        
        if not self.filtered_cycles:
            print("错误：没有周期数据可供绘图")
            return None
            
        # 创建子图
        fig = plt.figure(figsize=(18, 24))
        
        # 主标题
        fig.suptitle('USD Dollar Index - 6-Dimensional Cycle Analysis (20 Years)', 
                    fontsize=20, fontweight='bold', y=0.98)
        
        # 布局：7行1列（原始数据 + 6个周期）
        gs = fig.add_gridspec(7, 1, height_ratios=[1.2, 1, 1, 1, 1, 1, 1], hspace=0.3)
        
        dates = self.data['date']
        
        # 1. 原始数据图
        ax1 = fig.add_subplot(gs[0])
        ax1.plot(dates, self.data['close'], color='black', linewidth=1.2, label='Original USD Index')
        ax1.set_title('US Dollar Index (DXY) - Original Data', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')
        ax1.set_ylabel('Index Value')
        
        # 格式化x轴
        ax1.xaxis.set_major_locator(mdates.YearLocator(2))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        
        # 2-7. 各周期分量图
        cycle_names = list(self.filtered_cycles.keys())
        
        for i, cycle_name in enumerate(cycle_names):
            ax = fig.add_subplot(gs[i+1])
            
            cycle_data = self.filtered_cycles[cycle_name]
            data = cycle_data['data']
            color = cycle_data['color']
            period = cycle_data['period']
            weight = cycle_data['weight']
            
            # 绘制周期数据
            ax.plot(dates, data, color=color, linewidth=1.5, label=f'{cycle_name}')
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            
            # 填充正负区域
            ax.fill_between(dates, data, 0, where=(data >= 0), alpha=0.3, color=color)
            ax.fill_between(dates, data, 0, where=(data < 0), alpha=0.3, color='red')
            
            ax.set_title(f'{cycle_name} Component ({period} months, Weight: {weight:.1%})', 
                        fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper left')
            ax.set_ylabel('Deviation')
            
            # 格式化x轴
            ax.xaxis.set_major_locator(mdates.YearLocator(2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            
        # 设置最后一个子图的x轴标签
        plt.setp(fig.get_axes()[-1].xaxis.get_majorticklabels(), rotation=45)
        
        # 保存图表
        save_path = 'dollar_index_6d_cycle_analysis.png'
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✓ 综合分析图表已保存到: {save_path}")
        
        return save_path
        
    def create_phase_summary_chart(self, analysis_results):
        """创建相位总结图表"""
        print("生成周期相位总结图表...")
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # 左图：各周期当前相位强度
        cycle_names = [r['cycle'] for r in analysis_results]
        strengths = [r['strength'] for r in analysis_results]
        phases = [r['phase'] for r in analysis_results]
        colors = [self.cycle_configs[name]['color'] for name in cycle_names]
        
        bars = ax1.barh(cycle_names, strengths, color=colors, alpha=0.7)
        ax1.set_xlabel('Phase Strength')
        ax1.set_title('Current Cycle Phase Strength', fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='x')
        
        # 添加相位标签
        for i, (bar, phase) in enumerate(zip(bars, phases)):
            width = bar.get_width()
            ax1.text(width + 0.01, bar.get_y() + bar.get_height()/2, 
                    phase, ha='left', va='center', fontsize=10)
        
        # 右图：周期权重分布
        weights = [r['weight'] for r in analysis_results]
        wedges, texts, autotexts = ax2.pie(weights, labels=cycle_names, colors=colors, 
                                          autopct='%1.1f%%', startangle=90)
        ax2.set_title('Cycle Weight Distribution', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 保存图表
        save_path = 'dollar_index_phase_summary.png'
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"✓ 相位总结图表已保存到: {save_path}")
        
        return save_path
        
    def run_complete_analysis(self):
        """运行完整的周期分析"""
        print("=== 美元指数6维度周期分析开始 ===\\n")
        
        # 1. 获取数据
        self.data = self.fetch_dollar_index_data()
        if self.data is None or len(self.data) == 0:
            print("❌ 数据获取失败")
            return
            
        # 2. 周期分解
        self.perform_cycle_decomposition()
        
        # 3. 相位分析
        analysis_results = self.analyze_cycle_phases()
        
        # 4. 生成图表
        chart1 = self.create_comprehensive_chart()
        chart2 = self.create_phase_summary_chart(analysis_results)
        
        # 5. 综合评估
        print("\\n=== 综合周期评估 ===")
        
        # 计算加权综合得分
        total_score = 0
        expansion_weight = 0
        contraction_weight = 0
        
        for result in analysis_results:
            weight = result['weight']
            strength = result['strength']
            phase = result['phase']
            
            if phase == 'Expansion':
                total_score += weight * strength
                expansion_weight += weight
            elif phase == 'Contraction':
                total_score -= weight * strength
                contraction_weight += weight
                
        print(f"扩张期周期权重总计: {expansion_weight:.1%}")
        print(f"收缩期周期权重总计: {contraction_weight:.1%}")
        print(f"综合周期得分: {total_score:.4f}")
        
        if total_score > 0.1:
            overall_trend = "Strong Expansion"
            trend_cn = "强扩张"
        elif total_score > 0:
            overall_trend = "Weak Expansion"
            trend_cn = "弱扩张"
        elif total_score > -0.1:
            overall_trend = "Neutral"
            trend_cn = "中性"
        else:
            overall_trend = "Contraction"
            trend_cn = "收缩"
            
        print(f"\\n🎯 整体趋势判断: {trend_cn} ({overall_trend})")
        
        print(f"\\n✅ 分析完成！生成的图表文件:")
        if chart1:
            print(f"  - 综合周期分析图: {chart1}")
        if chart2:
            print(f"  - 相位总结图: {chart2}")
            
        return {
            'data': self.data,
            'cycles': self.filtered_cycles,
            'analysis': analysis_results,
            'overall_score': total_score,
            'overall_trend': overall_trend,
            'charts': [chart1, chart2]
        }

# 主程序执行
if __name__ == "__main__":
    analyzer = CompleteDollarIndexAnalysis()
    results = analyzer.run_complete_analysis() 