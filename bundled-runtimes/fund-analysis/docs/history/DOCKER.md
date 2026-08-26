# Docker 部署指南

## 快速开始

### 1. 使用 Docker Compose（推荐）

```bash
# 1. 配置环境变量
cp .env.example .env.local
# 编辑 .env.local 填入 API Keys

# 2. 启动所有服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 访问应用
# http://localhost:3000
```

### 2. 停止服务

```bash
docker-compose down
```

### 3. 重新构建

```bash
docker-compose up -d --build
```

## 服务说明

### 包含的服务

1. **postgres** - PostgreSQL 15 + pgvector
   - 端口: 5432
   - 数据持久化: postgres_data volume

2. **app** - Next.js 应用
   - 端口: 3000
   - 依赖: postgres

3. **wind-service** - Wind API 服务（可选）
   - 端口: 8000

## 数据库迁移

首次启动后需要运行数据库迁移：

```bash
# 进入应用容器
docker-compose exec app sh

# 运行迁移
npx prisma migrate deploy
npx prisma generate

# 退出容器
exit
```

## 环境变量

在 `.env.local` 中配置：

```env
ANTHROPIC_API_KEY=sk-ant-your-key
OPENAI_API_KEY=sk-your-key
```

## 仅启动数据库

如果只需要数据库服务：

```bash
docker-compose up -d postgres
```

## 故障排查

### 数据库连接失败

```bash
# 检查数据库状态
docker-compose ps postgres

# 查看数据库日志
docker-compose logs postgres

# 重启数据库
docker-compose restart postgres
```

### 应用启动失败

```bash
# 查看应用日志
docker-compose logs app

# 重新构建
docker-compose up -d --build app
```

### 清理所有数据

```bash
# 停止并删除所有容器和数据卷
docker-compose down -v
```

## 生产部署

### 使用环境变量文件

```bash
# 创建生产环境变量
cp .env.example .env.production

# 使用生产配置启动
docker-compose --env-file .env.production up -d
```

### 使用外部数据库

修改 `docker-compose.yml`，移除 postgres 服务，并更新 DATABASE_URL：

```yaml
services:
  app:
    environment:
      DATABASE_URL: postgresql://user:pass@external-db:5432/fund_analysis
```

## 性能优化

### 限制资源使用

在 `docker-compose.yml` 中添加：

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 使用 Redis 缓存

添加 Redis 服务：

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

## 备份和恢复

### 备份数据库

```bash
docker-compose exec postgres pg_dump -U postgres fund_analysis > backup.sql
```

### 恢复数据库

```bash
docker-compose exec -T postgres psql -U postgres fund_analysis < backup.sql
```

## 监控

### 查看资源使用

```bash
docker stats
```

### 查看容器状态

```bash
docker-compose ps
```

---

**提示**: 首次启动可能需要几分钟来下载镜像和构建应用。
