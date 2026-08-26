#!/usr/bin/env python3
"""
启动经济周期分析仪表板

运行Streamlit应用程序，提供交互式的可视化界面。
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    """主函数"""
    # 确保在正确的目录中
    current_dir = Path(__file__).parent
    os.chdir(current_dir)
    
    # 检查streamlit是否安装
    try:
        import streamlit
        print("✓ Streamlit已安装")
    except ImportError:
        print("❌ Streamlit未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
        print("✓ Streamlit安装完成")
    
    # 检查plotly是否安装
    try:
        import plotly
        print("✓ Plotly已安装")
    except ImportError:
        print("❌ Plotly未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "plotly"])
        print("✓ Plotly安装完成")
    
    # 启动仪表板
    dashboard_path = current_dir / "visualization" / "dashboard.py"
    
    print(f"\n🚀 启动经济周期分析仪表板...")
    print(f"📁 仪表板路径: {dashboard_path}")
    print(f"🌐 访问地址: http://localhost:8501")
    print(f"⏹️  停止服务: Ctrl+C\n")
    
    try:
        # 运行streamlit应用
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(dashboard_path),
            "--server.port", "8501",
            "--server.address", "localhost",
            "--browser.gatherUsageStats", "false"
        ])
    except KeyboardInterrupt:
        print("\n👋 仪表板已停止")
    except Exception as e:
        print(f"❌ 启动仪表板时发生错误: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 