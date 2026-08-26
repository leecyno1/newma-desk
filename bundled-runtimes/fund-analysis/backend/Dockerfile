# ══════════════════════════════════════════════════════════════
# FastAPI 后端 Dockerfile
# ══════════════════════════════════════════════════════════════
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8005

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
