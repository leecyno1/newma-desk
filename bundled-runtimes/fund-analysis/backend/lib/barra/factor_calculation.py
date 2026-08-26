"""Barra 风格因子定义。

本项目未接入正式因子协方差矩阵和特异风险数据，因此这里只保留可核验的
因子名称，不提供经验风险贡献、特异风险或 R² 计算。
"""

BARRA_FACTORS = {
    "SIZE": {"name": "规模因子", "description": "大盘/小盘暴露"},
    "SIZENL": {"name": "非线性规模", "description": "非线性规模效应"},
    "BETA": {"name": "Beta因子", "description": "市场系统性风险"},
    "MOMENTUM": {"name": "动量因子", "description": "历史收益动量"},
    "RESVOL": {"name": "残余波动率", "description": "特异性波动率"},
    "SRSIZE": {"name": "短期规模", "description": "短期规模效应"},
    "LIQUIDITY": {"name": "流动性因子", "description": "交易流动性"},
    "BHADGE": {"name": "价值因子", "description": "账面市值比"},
    "LEVERAGE": {"name": "杠杆因子", "description": "财务杠杆"},
    "STORIE": {"name": "成长因子", "description": "营收/利润增速"},
    "BTOP": {"name": "价值因子", "description": "账面市值比"},
    "GROWTH": {"name": "成长因子", "description": "收入与利润增长"},
}
