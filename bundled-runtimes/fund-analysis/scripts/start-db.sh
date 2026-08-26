#!/bin/bash

# 基金分析系统 - 数据库启动脚本

echo "正在启动 PostgreSQL 数据库..."

docker run -d \
  --name fund-db \
  -e POSTGRES_PASSWORD=fundanalysis2024 \
  -e POSTGRES_DB=fund_analysis \
  -p 5432:5432 \
  pgvector/pgvector:pg15

echo "数据库容器已启动"
echo "连接信息："
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: fund_analysis"
echo "  Username: postgres"
echo "  Password: fundanalysis2024"
echo ""
echo "请更新 .env.local 中的 DATABASE_URL："
echo 'DATABASE_URL="postgresql://postgres:fundanalysis2024@localhost:5432/fund_analysis"'
