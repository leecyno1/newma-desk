import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

from cycle_analysis_system.utils.data_loader import load_indicator_data, calculate_mom
from cycle_analysis_system.analysis.deep_cycle_decomposition import CycleDecomposer

def analyze_indicator(name, series, decomposer):
    """
    分析单个指标并返回报告字符串
    """
    if series.dropna().empty:
        return f"### {name}\n\n数据为空，无法分析。\n"
    
    # 分解
    df_decomp = decomposer.decompose(series)
    
    # 获取最近的数据点
    last_date = df_decomp.index[-1]
    last_row = df_decomp.iloc[-1]
    
    report = f"### {name}\n\n"
    report += f"**分析日期**: {last_date.strftime('%Y-%m-%d')}\n\n"
    report += f"**当前值**: {last_row['Original']:.4f}\n\n"
    
    # 校验闭合性
    reconstructed = last_row['Reconstructed']
    diff = last_row['Original'] - reconstructed
    if abs(diff) > 1e-4:
        report += f"⚠️ **闭合性警告**: 重构值 {reconstructed:.4f} 与 原始值差异 {diff:.4f}\n\n"
    
    report += "**周期分解 (解耦分析)**:\n\n"
    report += "| 成分 | 贡献值 | 说明 |\n"
    report += "|---|---|---|\n"
    report += f"| **趋势项 (HP)** | {last_row['Trend']:.4f} | 长期增长/衰退趋势 |\n"
    
    periods = [200, 100, 42, 21, 12]
    for p in periods:
        col = f'Cycle_{p}m'
        val = last_row[col]
        direction = "↑" if val > 0 else "↓"
        desc = f"约{p}个月周期 ({p/12:.1f}年)"
        
        # 获取相位信息
        phase_col = f'Phase_{p}m'
        phase_val = last_row[phase_col]
        phase_deg = np.degrees(phase_val)
        
        report += f"| {col} | {val:.4f} {direction} | {desc} (相位: {phase_deg:.1f}°) |\n"
        
    report += f"| **残差/噪音** | {last_row['Residual']:.4f} | 短期随机波动 |\n"
    report += "\n"
    
    # 简单的相位判断
    report += "**当前周期相位判断**:\n"
    for p in periods:
        col = f'Cycle_{p}m'
        # 取最近3个月判断方向
        recent = df_decomp[col].iloc[-3:]
        if len(recent) >= 2:
            diff = recent.iloc[-1] - recent.iloc[-2]
            val = recent.iloc[-1]
            
            phase = ""
            if val > 0 and diff > 0: phase = "扩张期 (上升)"
            elif val > 0 and diff < 0: phase = "衰退前期 (高位回落)"
            elif val < 0 and diff < 0: phase = "萧条期 (下降)"
            elif val < 0 and diff > 0: phase = "复苏期 (低位回升)"
            
            report += f"- **{p}个月周期**: {phase}\n"
            
    report += "\n---\n"
    return report

def main():
    # 1. 设置路径
    excel_path = os.environ.get("SEVEN_CYCLE_REFERENCE_XLSX", "")
    output_file = project_root / "output" / "cycle_research_report.md"
    
    # 确保输出目录存在
    os.makedirs(output_file.parent, exist_ok=True)
    
    print(f"正在加载数据: {excel_path} ...")
    df = load_indicator_data(excel_path)
    
    if df.empty:
        print("数据加载失败。")
        return

    print(f"加载成功，共 {len(df)} 行数据，{len(df.columns)} 个指标。")
    print(f"时间范围: {df.index[0]} 到 {df.index[-1]}")
    
    # 2. 初始化分解器
    decomposer = CycleDecomposer(periods=[200, 100, 42, 21, 12])
    
    # 3. 选择关键指标进行分析
    # 根据Excel列名选择一些代表性指标
    # 注意：列名可能包含空格或特殊字符，需模糊匹配
    target_indicators = [
        "中国:制造业PMI",
        "中国:工业增加值:当月同比",
        "中国:CPI:当月同比",
        "中国:M1:同比",
        "中国:中债国债到期收益率:10年:月:平均值",
        "美元指数:月:最后一条"
    ]
    
    full_report = "# 宏观经济周期解耦分析报告\n\n"
    full_report += f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    full_report += "## 1. 分析框架\n"
    full_report += "- **基准周期**: 200个月(地产/建筑), 100个月(设备投资), 42个月(库存), 21个月(短期), 12个月(季节).\n"
    full_report += "- **方法**: Butterworth带通滤波 + HP滤波趋势分解.\n"
    full_report += "- **数据源**: 参考Excel指标库 (未来将迁移至统一Parquet数据库).\n\n"
    full_report += "## 2. 核心指标分析\n\n"
    
    for target in target_indicators:
        # 查找匹配的列
        matched_col = None
        for col in df.columns:
            if target in col:
                matched_col = col
                break
        
        if matched_col:
            print(f"正在分析: {matched_col} ...")
            series = df[matched_col]
            
            # 数据预处理优化
            if "PMI" in matched_col:
                # PMI是扩散指数，50为荣枯线，减去50使其中心化
                series = series - 50.0
            elif "美元指数" in matched_col or "收盘价" in matched_col:
                 # 价格指数取对数
                 series = np.log(series)
            # 对于同比数据(YoY)，通常已经是平稳序列，可以直接分析，或者做HP滤波提取趋势
            
            report_segment = analyze_indicator(matched_col, series, decomposer)
            full_report += report_segment
        else:
            print(f"未找到指标: {target}")
            full_report += f"### {target}\n\n未在数据文件中找到该指标。\n\n---\n"

    # 4. 保存报告
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_report)
        
    print(f"\n分析完成！报告已保存至: {output_file}")

if __name__ == "__main__":
    main()
