"""
经济周期分析仪表板

提供交互式的可视化界面，展示周期分析结果。
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any
import warnings
warnings.filterwarnings('ignore')

try:
    from ..analysis.cycle_analyzer import CycleAnalyzer, CycleType, CyclePhase
    from ..data_collection.akshare_collector import AKShareCollector
    from ..config.indicators_config import indicators_config, IndicatorDimension
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from analysis.cycle_analyzer import CycleAnalyzer, CycleType, CyclePhase
    from data_collection.akshare_collector import AKShareCollector
    from config.indicators_config import indicators_config, IndicatorDimension


class CycleDashboard:
    """经济周期分析仪表板"""
    
    def __init__(self):
        self.analyzer = CycleAnalyzer()
        self.collector = AKShareCollector()
        
        # 颜色配置
        self.colors = {
            CyclePhase.TROUGH: '#FF6B6B',      # 红色 - 萧条期
            CyclePhase.RECOVERY: '#4ECDC4',    # 青色 - 复苏期
            CyclePhase.EXPANSION: '#45B7D1',   # 蓝色 - 扩张期
            CyclePhase.PEAK: '#96CEB4',        # 绿色 - 繁荣期
            CyclePhase.CONTRACTION: '#FFEAA7'  # 黄色 - 收缩期
        }
        
        # 风险颜色
        self.risk_colors = {
            '低': '#2ECC71',    # 绿色
            '中': '#F39C12',    # 橙色
            '高': '#E74C3C'     # 红色
        }
    
    def create_cycle_overview_chart(self, summary: Dict[str, Any]) -> go.Figure:
        """
        创建周期概览图表
        
        Args:
            summary: 周期分析摘要
            
        Returns:
            go.Figure: 概览图表
        """
        # 准备数据
        cycle_names = list(summary.keys())
        phases = [info['current_phase'] for info in summary.values()]
        confidences = [info['confidence'] for info in summary.values()]
        risk_levels = [info['risk_level'] for info in summary.values()]
        historical_positions = [info['historical_position'] for info in summary.values()]
        
        # 创建子图
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('周期阶段分布', '置信度水平', '风险评估', '历史位置'),
            specs=[[{"type": "pie"}, {"type": "bar"}],
                   [{"type": "bar"}, {"type": "scatter"}]]
        )
        
        # 1. 周期阶段分布饼图
        phase_counts = pd.Series(phases).value_counts()
        fig.add_trace(
            go.Pie(
                labels=phase_counts.index,
                values=phase_counts.values,
                name="阶段分布",
                marker_colors=[self.colors.get(CyclePhase(phase), '#95A5A6') 
                             for phase in phase_counts.index]
            ),
            row=1, col=1
        )
        
        # 2. 置信度水平柱状图
        fig.add_trace(
            go.Bar(
                x=cycle_names,
                y=confidences,
                name="置信度",
                marker_color='#3498DB',
                text=[f'{c:.1%}' for c in confidences],
                textposition='auto'
            ),
            row=1, col=2
        )
        
        # 3. 风险评估柱状图
        risk_colors_list = [self.risk_colors.get(risk, '#95A5A6') for risk in risk_levels]
        fig.add_trace(
            go.Bar(
                x=cycle_names,
                y=[1 if risk == '低' else 2 if risk == '中' else 3 for risk in risk_levels],
                name="风险水平",
                marker_color=risk_colors_list,
                text=risk_levels,
                textposition='auto'
            ),
            row=2, col=1
        )
        
        # 4. 历史位置散点图
        fig.add_trace(
            go.Scatter(
                x=cycle_names,
                y=historical_positions,
                mode='markers+text',
                name="历史位置",
                marker=dict(
                    size=15,
                    color=historical_positions,
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(title="位置", x=1.02)
                ),
                text=[f'{pos:.1%}' for pos in historical_positions],
                textposition='top center'
            ),
            row=2, col=2
        )
        
        # 更新布局
        fig.update_layout(
            title_text="经济周期分析概览",
            title_x=0.5,
            height=800,
            showlegend=False
        )
        
        # 更新子图标题
        fig.update_xaxes(title_text="周期类型", row=1, col=2)
        fig.update_xaxes(title_text="周期类型", row=2, col=1)
        fig.update_xaxes(title_text="周期类型", row=2, col=2)
        
        fig.update_yaxes(title_text="置信度", row=1, col=2)
        fig.update_yaxes(title_text="风险等级", row=2, col=1)
        fig.update_yaxes(title_text="历史位置", row=2, col=2)
        
        return fig
    
    def create_dimension_radar_chart(self, detailed_scores: Dict[str, float]) -> go.Figure:
        """
        创建维度雷达图
        
        Args:
            detailed_scores: 各维度详细得分
            
        Returns:
            go.Figure: 雷达图
        """
        dimensions = list(detailed_scores.keys())
        scores = list(detailed_scores.values())
        
        # 标准化得分到0-100范围
        normalized_scores = [(score + 2) * 25 for score in scores]  # 假设得分范围是-2到2
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatterpolar(
            r=normalized_scores,
            theta=dimensions,
            fill='toself',
            name='当前得分',
            line_color='#3498DB',
            fillcolor='rgba(52, 152, 219, 0.3)'
        ))
        
        # 添加基准线（中性水平）
        baseline_scores = [50] * len(dimensions)  # 中性水平
        fig.add_trace(go.Scatterpolar(
            r=baseline_scores,
            theta=dimensions,
            fill='toself',
            name='中性水平',
            line_color='#95A5A6',
            fillcolor='rgba(149, 165, 166, 0.1)',
            line_dash='dash'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    tickvals=[0, 25, 50, 75, 100],
                    ticktext=['极弱', '弱', '中性', '强', '极强']
                )
            ),
            title="五维度指标雷达图",
            title_x=0.5,
            showlegend=True
        )
        
        return fig
    
    def create_trend_analysis_chart(self, data: Dict[str, pd.DataFrame]) -> go.Figure:
        """
        创建趋势分析图表
        
        Args:
            data: 指标数据
            
        Returns:
            go.Figure: 趋势图表
        """
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('海外面指标', '资金面指标', '基本面指标', '政策面指标'),
            vertical_spacing=0.1
        )
        
        # 按维度分组显示关键指标
        dimension_indicators = {
            '海外面': ['美国失业率', '波罗的海干散货指数', '美国CPI月率'],
            '资金面': ['美联储利率决议', '欧央行利率决议', '中国M2货币供应量'],
            '基本面': ['中国制造业PMI', '中国GDP年率', '中国CPI月率'],
            '政策面': ['央行利率决议', '中国新增信贷', '新增人民币贷款']
        }
        
        positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12']
        
        for i, (dimension, indicators) in enumerate(dimension_indicators.items()):
            row, col = positions[i]
            color = colors[i]
            
            for j, indicator in enumerate(indicators):
                if indicator in data and not data[indicator].empty:
                    df = data[indicator]
                    
                    # 寻找时间和数值列
                    time_col = None
                    value_col = None
                    
                    for col_name in df.columns:
                        if any(keyword in col_name.lower() for keyword in ['日期', 'date', '时间', 'time']):
                            time_col = col_name
                        elif df[col_name].dtype in ['float64', 'int64']:
                            value_col = col_name
                    
                    if time_col and value_col:
                        # 取最近一年的数据
                        df_recent = df.tail(12)
                        
                        fig.add_trace(
                            go.Scatter(
                                x=df_recent[time_col],
                                y=df_recent[value_col],
                                mode='lines+markers',
                                name=indicator,
                                line=dict(color=color, width=2),
                                opacity=0.7 + j * 0.1,
                                showlegend=(i == 0 and j < 2)  # 只在第一个子图显示部分图例
                            ),
                            row=row, col=col
                        )
        
        fig.update_layout(
            title_text="关键指标趋势分析",
            title_x=0.5,
            height=600,
            showlegend=True
        )
        
        return fig
    
    def create_phase_transition_chart(self, next_phase_prob: Dict[CyclePhase, float]) -> go.Figure:
        """
        创建阶段转换概率图表
        
        Args:
            next_phase_prob: 下一阶段概率
            
        Returns:
            go.Figure: 转换概率图表
        """
        phases = list(next_phase_prob.keys())
        probabilities = list(next_phase_prob.values())
        
        # 创建桑基图显示转换概率
        fig = go.Figure(go.Bar(
            x=[phase.value for phase in phases],
            y=probabilities,
            marker_color=[self.colors.get(phase, '#95A5A6') for phase in phases],
            text=[f'{prob:.1%}' for prob in probabilities],
            textposition='auto'
        ))
        
        fig.update_layout(
            title="下一阶段转换概率",
            title_x=0.5,
            xaxis_title="经济周期阶段",
            yaxis_title="转换概率",
            yaxis=dict(tickformat='.0%')
        )
        
        return fig
    
    def create_risk_assessment_chart(self, summary: Dict[str, Any]) -> go.Figure:
        """
        创建风险评估图表
        
        Args:
            summary: 周期分析摘要
            
        Returns:
            go.Figure: 风险评估图表
        """
        cycle_names = list(summary.keys())
        risk_levels = [info['risk_level'] for info in summary.values()]
        confidences = [info['confidence'] for info in summary.values()]
        
        # 将风险等级转换为数值
        risk_values = [1 if risk == '低' else 2 if risk == '中' else 3 for risk in risk_levels]
        
        fig = go.Figure()
        
        # 添加气泡图
        fig.add_trace(go.Scatter(
            x=cycle_names,
            y=risk_values,
            mode='markers+text',
            marker=dict(
                size=[conf * 100 for conf in confidences],  # 气泡大小表示置信度
                color=[self.risk_colors.get(risk, '#95A5A6') for risk in risk_levels],
                opacity=0.7,
                line=dict(width=2, color='white')
            ),
            text=[f'{risk}<br>置信度: {conf:.1%}' for risk, conf in zip(risk_levels, confidences)],
            textposition='middle center',
            name='风险评估'
        ))
        
        fig.update_layout(
            title="综合风险评估",
            title_x=0.5,
            xaxis_title="周期类型",
            yaxis_title="风险等级",
            yaxis=dict(
                tickvals=[1, 2, 3],
                ticktext=['低风险', '中风险', '高风险']
            ),
            height=400
        )
        
        return fig
    
    def run_dashboard(self):
        """运行仪表板"""
        st.set_page_config(
            page_title="经济周期分析系统",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        st.title("🔄 经济周期分析系统")
        st.markdown("---")
        
        # 侧边栏控制
        st.sidebar.header("分析控制")
        
        # 选择分析类型
        analysis_type = st.sidebar.selectbox(
            "选择分析类型",
            ["综合分析", "单一周期分析", "指标趋势分析", "风险评估"]
        )
        
        # 刷新数据按钮
        if st.sidebar.button("🔄 刷新数据"):
            st.cache_data.clear()
            st.rerun()
        
        try:
            if analysis_type == "综合分析":
                self._show_comprehensive_analysis()
            elif analysis_type == "单一周期分析":
                self._show_single_cycle_analysis()
            elif analysis_type == "指标趋势分析":
                self._show_trend_analysis()
            elif analysis_type == "风险评估":
                self._show_risk_assessment()
                
        except Exception as e:
            st.error(f"分析过程中发生错误: {str(e)}")
            st.info("请检查数据连接或稍后重试")
    
    @st.cache_data(ttl=3600)  # 缓存1小时
    def _get_cycle_summary(self):
        """获取周期分析摘要（带缓存）"""
        return self.analyzer.get_cycle_summary()
    
    @st.cache_data(ttl=3600)
    def _get_indicator_data(self):
        """获取指标数据（带缓存）"""
        return self.collector.fetch_all_indicators()
    
    def _show_comprehensive_analysis(self):
        """显示综合分析"""
        st.header("📈 综合周期分析")
        
        with st.spinner("正在分析所有周期类型..."):
            summary = self._get_cycle_summary()
        
        # 显示概览图表
        overview_fig = self.create_cycle_overview_chart(summary)
        st.plotly_chart(overview_fig, use_container_width=True)
        
        # 显示详细信息表格
        st.subheader("📋 详细分析结果")
        
        summary_df = pd.DataFrame(summary).T
        summary_df.index.name = "周期类型"
        
        # 格式化数据
        summary_df['置信度'] = summary_df['confidence'].apply(lambda x: f"{x:.1%}")
        summary_df['历史位置'] = summary_df['historical_position'].apply(lambda x: f"{x:.1%}")
        
        display_df = summary_df[['current_phase', '置信度', 'risk_level', 'trend_direction', '历史位置']]
        display_df.columns = ['当前阶段', '置信度', '风险水平', '趋势方向', '历史位置']
        
        st.dataframe(display_df, use_container_width=True)
    
    def _show_single_cycle_analysis(self):
        """显示单一周期分析"""
        st.header("🎯 单一周期深度分析")
        
        # 选择周期类型
        cycle_type = st.selectbox(
            "选择要分析的周期类型",
            [cycle.value for cycle in CycleType]
        )
        
        selected_cycle = next(cycle for cycle in CycleType if cycle.value == cycle_type)
        
        with st.spinner(f"正在分析{cycle_type}..."):
            result = self.analyzer.analyze_cycle(selected_cycle)
        
        # 显示基本信息
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("当前阶段", result.current_phase.value)
        
        with col2:
            st.metric("置信度", f"{result.phase_confidence:.1%}")
        
        with col3:
            st.metric("风险水平", result.risk_level)
        
        with col4:
            st.metric("趋势方向", result.trend_direction)
        
        # 显示维度雷达图
        radar_fig = self.create_dimension_radar_chart(result.detailed_scores)
        st.plotly_chart(radar_fig, use_container_width=True)
        
        # 显示转换概率
        transition_fig = self.create_phase_transition_chart(result.next_phase_probability)
        st.plotly_chart(transition_fig, use_container_width=True)
        
        # 显示关键指标
        st.subheader("🔑 关键指标")
        for i, indicator in enumerate(result.key_indicators, 1):
            st.write(f"{i}. {indicator}")
    
    def _show_trend_analysis(self):
        """显示趋势分析"""
        st.header("📊 指标趋势分析")
        
        with st.spinner("正在获取指标数据..."):
            data = self._get_indicator_data()
        
        # 显示趋势图表
        trend_fig = self.create_trend_analysis_chart(data)
        st.plotly_chart(trend_fig, use_container_width=True)
        
        # 显示数据可用性统计
        st.subheader("📋 数据可用性统计")
        
        available_count = sum(1 for df in data.values() if not df.empty)
        total_count = len(data)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("总指标数", total_count)
        
        with col2:
            st.metric("可用指标数", available_count)
        
        with col3:
            st.metric("可用率", f"{available_count/total_count:.1%}")
    
    def _show_risk_assessment(self):
        """显示风险评估"""
        st.header("⚠️ 风险评估分析")
        
        with st.spinner("正在进行风险评估..."):
            summary = self._get_cycle_summary()
        
        # 显示风险评估图表
        risk_fig = self.create_risk_assessment_chart(summary)
        st.plotly_chart(risk_fig, use_container_width=True)
        
        # 风险等级统计
        risk_levels = [info['risk_level'] for info in summary.values()]
        risk_counts = pd.Series(risk_levels).value_counts()
        
        st.subheader("📊 风险分布统计")
        
        for risk_level, count in risk_counts.items():
            percentage = count / len(risk_levels)
            st.write(f"**{risk_level}风险**: {count} 个周期 ({percentage:.1%})")
        
        # 风险建议
        st.subheader("💡 风险管理建议")
        
        high_risk_cycles = [name for name, info in summary.items() if info['risk_level'] == '高']
        
        if high_risk_cycles:
            st.warning(f"⚠️ 高风险周期: {', '.join(high_risk_cycles)}")
            st.write("建议采取谨慎的投资策略，密切关注相关指标变化。")
        else:
            st.success("✅ 当前整体风险水平可控")
            st.write("可以考虑适度的投资机会，但仍需保持警惕。")


def main():
    """主函数"""
    dashboard = CycleDashboard()
    dashboard.run_dashboard()


if __name__ == "__main__":
    main() 