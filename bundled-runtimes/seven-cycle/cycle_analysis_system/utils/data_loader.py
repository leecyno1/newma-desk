import pandas as pd
import numpy as np
from pathlib import Path

def load_indicator_data(file_path: str) -> pd.DataFrame:
    """
    加载宏观指标数据
    
    Args:
        file_path: Excel文件路径
        
    Returns:
        pd.DataFrame: 清洗后的数据，索引为日期
    """
    try:
        # 读取Excel，header=2表示第三行是列名
        df = pd.read_excel(file_path, header=2)
        
        # 重命名第一列为Date
        df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
        
        # 转换日期列
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # 删除日期为空的行
        df = df.dropna(subset=['Date'])
        
        # 设置日期为索引
        df.set_index('Date', inplace=True)
        
        # 确保所有列都是数值型
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # 按时间排序
        df.sort_index(inplace=True)
        
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame()

def calculate_mom(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算环比 (Month-over-Month)
    如果数据已经是百分比（如CPI同比），则可能需要先还原或直接使用差分。
    这里根据用户要求：'尽可能标准化为环比'。
    
    对于已经是同比(YoY)的数据，直接转环比比较困难，除非有指数/绝对值。
    如果列名包含 '同比'，我们假设它是增长率。
    如果列名包含 '指数' 或 '收盘价'，我们计算 pct_change(1)。
    """
    df_mom = pd.DataFrame(index=df.index)
    
    for col in df.columns:
        # 简单的启发式规则
        if '同比' in col or '收益率' in col or '%' in col:
            # 已经是比率数据，可能不需要再做环比，或者取差分
            # 用户说 "标准化为环比"，对于同比数据，通常意味着我们要看它的边际变化
            # 或者用户希望统一量纲。
            # 这里我们采取：如果是比率，保持不变（或者取一阶差分表示动量）；如果是绝对值，取环比。
            # 但为了统一，我们先保留原始值，在分析时处理。
            # 实际上，混合了同比和绝对值的数据很难直接统一为环比。
            # 假设用户希望看到的是“增长动能”。
            df_mom[col] = df[col] # 暂时保留，后续处理
        else:
            # 绝对值数据，计算环比
            df_mom[col] = df[col].pct_change()
            
    return df_mom
