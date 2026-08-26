# 基金经理评价分析系统 - 部署文档

## 📋 目录

1. [系统要求](#系统要求)
2. [环境准备](#环境准备)
3. [数据库配置](#数据库配置)
4. [应用部署](#应用部署)
5. [Wind 服务部署](#wind-服务部署)
6. [环境变量配置](#环境变量配置)
7. [生产环境优化](#生产环境优化)
8. [故障排查](#故障排查)
9. [备份和恢复](#备份和恢复)

---

## 系统要求

### 硬件要求
- **CPU**: 2核心以上
- **内存**: 4GB 以上（推荐 8GB）
- **磁盘**: 20GB 以上可用空间
- **网络**: 稳定的互联网连接

### 软件要求
- **操作系统**: Linux (Ubuntu 20.04+), macOS, Windows 10+
- **Node.js**: 18.x 或更高版本
- **PostgreSQL**: 15.x 或更高版本（需支持 pgvector 扩展）
- **Python**: 3.8 或更高版本
- **Git**: 2.x 或更高版本

---

## 环境准备

### 1. 安装 Node.js

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# macOS (使用 Homebrew)
brew install node@18

# 验证安装
node --version
npm --version
```

### 2. 安装 PostgreSQL

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

# macOS (使用 Homebrew)
brew install postgresql@15

# 启动 PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql@15  # macOS

# 验证安装
psql --version
```

### 3. 安装 Python

```bash
# Ubuntu/Debian
sudo apt-get install -y python3 python3-pip python3-venv

# macOS (通常已预装)
brew install python@3.11

# 验证安装
python3 --version
pip3 --version
```

---

## 数据库配置

### 1. 创建数据库用户

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 psql 中执行
CREATE USER fundanalysis WITH PASSWORD 'your_secure_password';
CREATE DATABASE fund_analysis OWNER fundanalysis;
GRANT ALL PRIVILEGES ON DATABASE fund_analysis TO fundanalysis;

# 退出 psql
\q
```

### 2. 启用 pgvector 扩展

```bash
# 连接到数据库
psql -U fundanalysis -d fund_analysis

# 启用扩展
CREATE EXTENSION IF NOT EXISTS vector;

# 验证
\dx

# 退出
\q
```

### 3. 配置 PostgreSQL 远程访问（可选）

编辑 `/etc/postgresql/15/main/postgresql.conf`:
```conf
listen_addresses = '*'
```

编辑 `/etc/postgresql/15/main/pg_hba.conf`:
```conf
host    all             all             0.0.0.0/0               md5
```

重启 PostgreSQL:
```bash
sudo systemctl restart postgresql
```

---

## 应用部署

### 1. 克隆代码

```bash
cd /opt
git clone <your-repo-url> fund-analysis
cd fund-analysis
```

### 2. 安装依赖

```bash
npm install
```

### 3. 配置环境变量

创建 `.env.local` 文件:
```bash
cp .env.example .env.local
```

编辑 `.env.local`:
```env
# 数据库连接
DATABASE_URL="postgresql://fundanalysis:your_secure_password@localhost:5432/fund_analysis"

# Claude API
ANTHROPIC_API_KEY="sk-ant-xxx"

# OpenAI API (用于语义搜索)
OPENAI_API_KEY="sk-xxx"

# Wind 服务地址
WIND_SERVICE_URL="http://localhost:8000"

# 应用配置
NODE_ENV="production"
NEXT_PUBLIC_APP_URL="https://your-domain.com"
```

### 4. 运行数据库迁移

```bash
npx prisma migrate deploy
npx prisma generate
```

### 5. 构建应用

```bash
npm run build
```

### 6. 启动应用

#### 开发模式
```bash
npm run dev
```

#### 生产模式
```bash
npm start
```

#### 使用 PM2（推荐）
```bash
# 安装 PM2
npm install -g pm2

# 启动应用
pm2 start npm --name "fund-analysis" -- start

# 设置开机自启
pm2 startup
pm2 save

# 查看日志
pm2 logs fund-analysis

# 重启应用
pm2 restart fund-analysis
```

---

## Wind 服务部署

### 1. 创建 Python 虚拟环境

```bash
cd backend/wind_service
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 Wind 终端

确保 Wind 终端已安装并正确配置。

### 4. 启动服务

#### 开发模式
```bash
uvicorn main:app --reload --port 8000
```

#### 生产模式（使用 Gunicorn）
```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

#### 使用 Systemd（推荐）

创建 `/etc/systemd/system/wind-service.service`:
```ini
[Unit]
Description=Wind Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/fund-analysis/backend/wind_service
Environment="PATH=/opt/fund-analysis/backend/wind_service/venv/bin"
ExecStart=/opt/fund-analysis/backend/wind_service/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务:
```bash
sudo systemctl daemon-reload
sudo systemctl start wind-service
sudo systemctl enable wind-service
sudo systemctl status wind-service
```

---

## 环境变量配置

### 必需的环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://user:pass@localhost:5432/db` |
| `ANTHROPIC_API_KEY` | Claude API Key | `sk-ant-xxx` |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxx` |
| `WIND_SERVICE_URL` | Wind 服务地址 | `http://localhost:8000` |

### 可选的环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `NODE_ENV` | 运行环境 | `development` |
| `PORT` | 应用端口 | `3000` |
| `NEXT_PUBLIC_APP_URL` | 应用 URL | `http://localhost:3000` |

---

## 生产环境优化

### 1. 使用 Nginx 反向代理

安装 Nginx:
```bash
sudo apt-get install nginx
```

配置 `/etc/nginx/sites-available/fund-analysis`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/wind/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

启用配置:
```bash
sudo ln -s /etc/nginx/sites-available/fund-analysis /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 2. 配置 SSL (Let's Encrypt)

```bash
# 安装 Certbot
sudo apt-get install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

### 3. 数据库连接池

在 `prisma/schema.prisma` 中配置:
```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
  
  // 连接池配置
  connection_limit = 10
  pool_timeout = 20
}
```

### 4. 启用缓存

安装 Redis:
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

---

## 故障排查

### 1. 数据库连接失败

**症状**: `Error: Can't reach database server`

**解决方案**:
```bash
# 检查 PostgreSQL 是否运行
sudo systemctl status postgresql

# 检查连接字符串
echo $DATABASE_URL

# 测试连接
psql $DATABASE_URL
```

### 2. Prisma 迁移失败

**症状**: `Migration failed`

**解决方案**:
```bash
# 重置数据库（警告：会删除所有数据）
npx prisma migrate reset

# 或手动修复
npx prisma migrate resolve --applied <migration-name>
```

### 3. Wind 服务无法连接

**症状**: `Wind 服务连接失败`

**解决方案**:
```bash
# 检查服务状态
sudo systemctl status wind-service

# 查看日志
sudo journalctl -u wind-service -f

# 测试连接
curl http://localhost:8000/health
```

### 4. 内存不足

**症状**: 应用崩溃或响应缓慢

**解决方案**:
```bash
# 增加 Node.js 内存限制
NODE_OPTIONS="--max-old-space-size=4096" npm start

# 或在 PM2 中配置
pm2 start npm --name "fund-analysis" --node-args="--max-old-space-size=4096" -- start
```

### 5. 端口被占用

**症状**: `Error: listen EADDRINUSE: address already in use`

**解决方案**:
```bash
# 查找占用端口的进程
lsof -i :3000

# 杀死进程
kill -9 <PID>
```

---

## 备份和恢复

### 1. 数据库备份

```bash
# 创建备份
pg_dump -U fundanalysis fund_analysis > backup_$(date +%Y%m%d_%H%M%S).sql

# 自动备份脚本
cat > /opt/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups"
mkdir -p $BACKUP_DIR
pg_dump -U fundanalysis fund_analysis | gzip > $BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz
# 保留最近 7 天的备份
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
EOF

chmod +x /opt/backup-db.sh

# 添加到 crontab（每天凌晨 2 点备份）
crontab -e
# 添加: 0 2 * * * /opt/backup-db.sh
```

### 2. 数据库恢复

```bash
# 从备份恢复
psql -U fundanalysis fund_analysis < backup_20240418_020000.sql

# 或从压缩备份恢复
gunzip -c backup_20240418_020000.sql.gz | psql -U fundanalysis fund_analysis
```

### 3. 应用文件备份

```bash
# 备份上传的文件和配置
tar -czf app_backup_$(date +%Y%m%d).tar.gz \
  .env.local \
  uploads/ \
  logs/
```

---

## 监控和日志

### 1. 应用日志

```bash
# PM2 日志
pm2 logs fund-analysis

# Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Wind 服务日志
sudo journalctl -u wind-service -f
```

### 2. 性能监控

```bash
# 使用 PM2 监控
pm2 monit

# 查看资源使用
pm2 status
```

---

## 安全建议

1. **定期更新依赖**
```bash
npm audit
npm audit fix
```

2. **使用强密码**
- 数据库密码至少 16 位
- API Key 妥善保管

3. **配置防火墙**
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

4. **限制数据库访问**
- 仅允许本地连接
- 使用 SSL 连接

5. **定期备份**
- 每天自动备份数据库
- 异地存储备份文件

---

## 联系支持

如遇到问题，请查看:
- [GitHub Issues](https://github.com/your-repo/issues)
- [文档](./README.md)
- [常见问题](./FAQ.md)

---

**最后更新**: 2024-04-18  
**版本**: 1.0.0
