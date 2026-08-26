#!/usr/bin/env python3
"""
美元指数近20年的6维度周期分析
使用系统的周期滤波器进行分析并输出相应的周期划分图
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import akshare as ak
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

# 导入周期分析模块
from cycle_analysis.cycle_filter import CycleFilter
from cycle_analysis.cycle_detector import CycleDetector
from config.cycle_config import CycleConfig

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class DollarIndexCycleAnalysis:
    """美元指数周期分析类"""
    
    def __init__(self):
        """初始化分析器"""
        self.cycle_config = CycleConfig()
        self.cycle_filter = CycleFilter()
        self.cycle_detector = CycleDetector()
        self.data = None
        self.cycles_data = {}
        
    def fetch_dollar_index_data(self, years=20):
        """获取美元指数数据"""
        print(f"🔄 正在获取美元指数近{years}年的数据...")
        
        try:
            # 获取美元指数历史数据
            dxy_data = ak.index_global_hist_em(symbol="美元指数")
            
            # 数据预处理
            dxy_data['日期'] = pd.to_datetime(dxy_data['日期'])
            dxy_data = dxy_data.sort_values('日期')
            dxy_data = dxy_data.set_index('日期')
            
            # 筛选近20年数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=years * 365)
            
            # 过滤数据
            mask = dxy_data.index >= start_date
            self.data = dxy_data[mask].copy()
            
            # 使用收盘价作为分析目标
            self.data['价格'] = self.data['收盘']
            
            print(f"✅ 成功获取数据，数据范围：{self.data.index[0].strftime('%Y-%m-%d')} 到 {self.data.index[-1].strftime('%Y-%m-%d')}")
            print(f"📊 数据点数量：{len(self.data)}")
            
            return True
            
        except Exception as e:
            print(f"❌ 获取美元指数数据失败：{e}")
            return False
    
    def perform_cycle_decomposition(self):
        """进行6个维度的周期分解"""
        if self.data is None or self.data.empty:
            print("❌ 无可用数据进行周期分析")
            return False
            
        print("\n🔄 开始进行6个维度的周期分解...")
        
        # 获取价格序列
        price_series = self.data['价格'].values
        dates = self.data.index
        
        # 获取所有周期配置
        cycle_types = self.cycle_config.get_all_cycle_types()
        
        print(f"📊 将进行 {len(cycle_types)} 个周期维度的分析：")
        for cycle_type in cycle_types:
            print(f"   - {cycle_type.name}: {cycle_type.period_months}个月周期 (权重: {cycle_type.weight})")
        
        # 对每个周期类型进行滤波分析
        for cycle_type in cycle_types:
            try:
                print(f"\n🔧 分析 {cycle_type.name} ({cycle_type.period_months}个月周期)...")
                
                # 计算周期对应的天数（近似）
                period_days = cycle_type.period_months * 30
                
                # 使用带通滤波器提取特定周期
                filtered_data = self.cycle_filter.apply_bandpass_filter(
                    data=price_series,
                    period_range=(period_days * 0.7, period_days * 1.3),  # 允许30%的范围波动
                    sample_rate=1.0  # 日频数据
                )
                
                # 检测周期特征
                cycle_info = self.cycle_detector.detect_cycles(filtered_data)
                
                # 存储结果
                self.cycles_data[cycle_type.name] = {
                    'original_data': price_series,
                    'filtered_data': filtered_data,
                    'dates': dates,
                    'cycle_info': cycle_info,
                    'period_months': cycle_type.period_months,
                    'weight': cycle_type.weight
                }
                
                print(f"✅ {cycle_type.name} 周期分析完成")
                if cycle_info:
                    print(f"   检测到 {len(cycle_info.get('peaks', []))} 个峰值，{len(cycle_info.get('troughs', []))} 个谷值")
                
            except Exception as e:
                print(f"❌ {cycle_type.name} 周期分析失败：{e}")
                continue
        
        print(f"\n✅ 周期分解完成，成功分析了 {len(self.cycles_data)} 个周期维度")
        return len(self.cycles_data) > 0
    
    def plot_cycle_analysis(self, save_dir="cycle_charts"):
        """绘制周期分析图表"""
        if not self.cycles_data:
            print("❌ 无周期分析数据可绘制")
            return False
        
        # 创建保存目录
        save_path = Path(save_dir)
        save_path.mkdir(exist_ok=True)
        
        print(f"\n📊 开始绘制周期分析图表，保存至：{save_path.absolute()}")
        
        # 1. 绘制综合对比图
        self._plot_comprehensive_comparison(save_path)
        
        # 2. 为每个周期维度绘制独立图表
        for cycle_name, cycle_data in self.cycles_data.items():
            self._plot_individual_cycle(cycle_name, cycle_data, save_path)
        
        # 3. 绘制周期权重贡献图
        self._plot_cycle_weights(save_path)
        
        print(f"✅ 所有图表已保存至：{save_path.absolute()}")
        return True
    
    def _plot_comprehensive_comparison(self, save_path):
        """绘制综合对比图"""
        fig, axes = plt.subplots(len(self.cycles_data) + 1, 1, figsize=(15, 3 * (len(self.cycles_data) + 1)))
        fig.suptitle('美元指数近20年 - 6维度周期分解分析', fontsize=16, fontweight='bold')
        
        # 获取第一个数据作为参考
        first_cycle = list(self.cycles_data.values())[0]
        dates = first_cycle['dates']
        original_data = first_cycle['original_data']
        
        # 第一个子图：原始数据
        axes[0].plot(dates, original_data, 'k-', linewidth=1.5, label='美元指数原始数据')
        axes[0].set_title('原始美元指数数据', fontweight='bold')
        axes[0].set_ylabel('价格')
        axes[0].grid(True, alpha=0.3)
        axes[0].legend()
        
        # 为每个周期绘制滤波后的数据
        for i, (cycle_name, cycle_data) in enumerate(self.cycles_data.items(), 1):
            ax = axes[i]
            
            # 绘制滤波后的数据
            ax.plot(cycle_data['dates'], cycle_data['filtered_data'], 
                   linewidth=2, label=f'{cycle_name}周期分量')
            
            # 标记峰值和谷值
            if cycle_data['cycle_info']:
                peaks = cycle_data['cycle_info'].get('peaks', [])
                troughs = cycle_data['cycle_info'].get('troughs', [])
                
                if peaks:
                    peak_dates = [cycle_data['dates'][p] for p in peaks if p < len(cycle_data['dates'])]
                    peak_values = [cycle_data['filtered_data'][p] for p in peaks if p < len(cycle_data['filtered_data'])]
                    ax.scatter(peak_dates, peak_values, color='red', s=50, marker='^', 
                             label=f'峰值 ({len(peaks)}个)', zorder=5)
                
                if troughs:
                    trough_dates = [cycle_data['dates'][t] for t in troughs if t < len(cycle_data['dates'])]
                    trough_values = [cycle_data['filtered_data'][t] for t in troughs if t < len(cycle_data['filtered_data'])]
                    ax.scatter(trough_dates, trough_values, color='blue', s=50, marker='v', 
                             label=f'谷值 ({len(troughs)}个)', zorder=5)
            
            ax.set_title(f'{cycle_name} ({cycle_data["period_months"]}个月周期, 权重: {cycle_data["weight"]:.1%})', 
                        fontweight='bold')
            ax.set_ylabel('滤波值')
            ax.grid(True, alpha=0.3)
            ax.legend()
        
        # 格式化x轴
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.YearLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig(save_path / '美元指数_综合周期分析.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("✅ 综合对比图已保存")
    
    def _plot_individual_cycle(self, cycle_name, cycle_data, save_path):
        """为单个周期绘制详细图表"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        fig.suptitle(f'美元指数 - {cycle_name}详细分析', fontsize=14, fontweight='bold')
        
        dates = cycle_data['dates']
        original_data = cycle_data['original_data']
        filtered_data = cycle_data['filtered_data']
        
        # 子图1：原始数据 vs 滤波数据
        ax1.plot(dates, original_data, 'k-', alpha=0.7, linewidth=1, label='原始美元指数')
        ax1.plot(dates, filtered_data, 'r-', linewidth=2, label=f'{cycle_name}周期分量')
        
        # 标记峰值和谷值
        if cycle_data['cycle_info']:
            peaks = cycle_data['cycle_info'].get('peaks', [])
            troughs = cycle_data['cycle_info'].get('troughs', [])
            
            if peaks:
                peak_dates = [dates[p] for p in peaks if p < len(dates)]
                peak_values = [filtered_data[p] for p in peaks if p < len(filtered_data)]
                ax1.scatter(peak_dates, peak_values, color='red', s=100, marker='^', 
                           label=f'周期峰值 ({len(peaks)}个)', zorder=5)
            
            if troughs:
                trough_dates = [dates[t] for t in troughs if t < len(dates)]
                trough_values = [filtered_data[t] for t in troughs if t < len(filtered_data)]
                ax1.scatter(trough_dates, trough_values, color='blue', s=100, marker='v', 
                           label=f'周期谷值 ({len(troughs)}个)', zorder=5)
        
        ax1.set_title(f'{cycle_name} - 原始数据与周期分量对比')
        ax1.set_ylabel('价格 / 滤波值')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 子图2：仅滤波数据，突出周期特征
        ax2.plot(dates, filtered_data, 'b-', linewidth=2, label=f'{cycle_name}周期分量')
        ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
        
        # 填充正负区域
        ax2.fill_between(dates, filtered_data, 0, where=(np.array(filtered_data) > 0), 
                        color='green', alpha=0.3, label='上升周期')
        ax2.fill_between(dates, filtered_data, 0, where=(np.array(filtered_data) <= 0), 
                        color='red', alpha=0.3, label='下降周期')
        
        ax2.set_title(f'{cycle_name} - 周期波动特征 ({cycle_data["period_months"]}个月周期)')
        ax2.set_ylabel('标准化滤波值')
        ax2.set_xlabel('时间')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 格式化x轴
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.YearLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        plt.savefig(save_path / f'美元指数_{cycle_name}_详细分析.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✅ {cycle_name}详细分析图已保存")
    
    def _plot_cycle_weights(self, save_path):
        """绘制周期权重贡献图"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        fig.suptitle('美元指数周期分析 - 权重配置与周期特征', fontsize=14, fontweight='bold')
        
        # 提取数据
        cycle_names = []
        weights = []
        periods = []
        
        for cycle_name, cycle_data in self.cycles_data.items():
            cycle_names.append(cycle_name)
            weights.append(cycle_data['weight'])
            periods.append(cycle_data['period_months'])
        
        # 子图1：权重饼图
        colors = plt.cm.Set3(np.linspace(0, 1, len(cycle_names)))
        wedges, texts, autotexts = ax1.pie(weights, labels=cycle_names, autopct='%1.1f%%', 
                                         colors=colors, startangle=90)
        ax1.set_title('各周期权重分布')
        
        # 子图2：周期长度条形图
        bars = ax2.bar(range(len(cycle_names)), periods, color=colors)
        ax2.set_xlabel('周期类型')
        ax2.set_ylabel('周期长度 (月)')
        ax2.set_title('各周期长度对比')
        ax2.set_xticks(range(len(cycle_names)))
        ax2.set_xticklabels(cycle_names, rotation=45)
        
        # 在条形图上添加数值标签
        for i, (bar, period) in enumerate(zip(bars, periods)):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                    f'{period}个月', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(save_path / '美元指数_周期权重配置.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("✅ 周期权重配置图已保存")
    
    def generate_analysis_report(self):
        """生成分析报告"""
        if not self.cycles_data:
            print("❌ 无周期分析数据可生成报告")
            return
        
        print("\n📋 生成周期分析报告...")
        
        report = []
        report.append("="*60)
        report.append("美元指数近20年 - 6维度周期分析报告")
        report.append("="*60)
        report.append(f"分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"数据范围：{self.data.index[0].strftime('%Y-%m-%d')} 至 {self.data.index[-1].strftime('%Y-%m-%d')}")
        report.append(f"数据点数量：{len(self.data)}")
        report.append("")
        
        # 各周期详细信息
        report.append("📊 各周期维度分析结果：")
        report.append("-" * 40)
        
        total_weight = 0
        for cycle_name, cycle_data in self.cycles_data.items():
            report.append(f"\n🔹 {cycle_name}")
            report.append(f"   周期长度：{cycle_data['period_months']}个月")
            report.append(f"   权重配置：{cycle_data['weight']:.1%}")
            total_weight += cycle_data['weight']
            
            if cycle_data['cycle_info']:
                peaks = cycle_data['cycle_info'].get('peaks', [])
                troughs = cycle_data['cycle_info'].get('troughs', [])
                report.append(f"   检测峰值：{len(peaks)}个")
                report.append(f"   检测谷值：{len(troughs)}个")
                
                # 计算周期统计
                if len(peaks) > 1:
                    peak_intervals = np.diff(peaks)
                    avg_peak_interval = np.mean(peak_intervals)
                    report.append(f"   平均峰值间隔：{avg_peak_interval:.1f}天 ({avg_peak_interval/30:.1f}个月)")
                
                if len(troughs) > 1:
                    trough_intervals = np.diff(troughs)
                    avg_trough_interval = np.mean(trough_intervals)
                    report.append(f"   平均谷值间隔：{avg_trough_interval:.1f}天 ({avg_trough_interval/30:.1f}个月)")
        
        report.append(f"\n📈 总权重检查：{total_weight:.1%}")
        
        # 保存报告
        report_text = "\n".join(report)
        with open("cycle_charts/美元指数_周期分析报告.txt", "w", encoding="utf-8") as f:
            f.write(report_text)
        
        print(report_text)
        print(f"\n✅ 分析报告已保存至：cycle_charts/美元指数_周期分析报告.txt")

def main():
    """主函数"""
    print("🚀 启动美元指数6维度周期分析系统")
    print("="*50)
    
    # 创建分析器
    analyzer = DollarIndexCycleAnalysis()
    
    # 1. 获取数据
    if not analyzer.fetch_dollar_index_data(years=20):
        print("❌ 数据获取失败，程序退出")
        return
    
    # 2. 进行周期分解
    if not analyzer.perform_cycle_decomposition():
        print("❌ 周期分解失败，程序退出")
        return
    
    # 3. 绘制图表
    if not analyzer.plot_cycle_analysis():
        print("❌ 图表绘制失败")
        return
    
    # 4. 生成报告
    analyzer.generate_analysis_report()
    
    print("\n🎉 美元指数6维度周期分析完成！")
    print("📁 所有结果已保存至 cycle_charts/ 目录")

if __name__ == "__main__":
    main() 