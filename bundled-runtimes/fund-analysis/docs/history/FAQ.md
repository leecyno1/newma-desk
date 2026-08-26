# 常见问题 (FAQ)

## 安装和配置

### Q: 如何获取 Claude API Key？
A: 访问 [Anthropic Console](https://console.anthropic.com/) 注册账号并创建 API Key。

### Q: 如何获取 OpenAI API Key？
A: 访问 [OpenAI Platform](https://platform.openai.com/) 注册账号并创建 API Key。

### Q: 必须要有 Wind 终端吗？
A: 不是必须的。Wind 服务仅用于数据同步功能。如果没有 Wind 终端，可以手动导入数据或使用其他数据源。

### Q: 如何启用 pgvector 扩展？
A: 连接到 PostgreSQL 数据库后执行：
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Q: 数据库迁移失败怎么办？
A: 尝试以下步骤：
```bash
# 1. 重置数据库
npx prisma migrate reset

# 2. 重新运行迁移
npx prisma migrate dev

# 3. 生成客户端
npx prisma generate
```

## 功能使用

### Q: 如何上传调研报告？
A: 
1. 访问 `/reports/upload` 页面
2. 拖拽或选择文件（支持 PDF、Word、TXT、Markdown）
3. AI 会自动提取元数据
4. 点击保存

### Q: 语义搜索如何工作？
A: 
- 上传报告时，系统会使用 OpenAI Embeddings 生成向量
- 搜索时，查询文本也会转换为向量
- 使用 pgvector 进行相似度匹配
- 返回最相关的报告

### Q: AI 分析报告需要多长时间？
A: 通常 30-60 秒，取决于：
- 分析类型（基金/经理/对比）
- 是否包含调研报告
- Claude API 响应速度

### Q: 如何保存筛选条件？
A: 
1. 在筛选器页面设置条件
2. 点击"保存模板"按钮
3. 输入模板名称
4. 下次可以直接加载模板

## 性能优化

### Q: 如何提高应用性能？
A: 
1. 启用 Redis 缓存
2. 优化数据库查询（添加索引）
3. 使用 CDN 加速静态资源
4. 增加服务器资源

### Q: 数据库查询很慢怎么办？
A: 
1. 检查是否有大量数据
2. 为常用查询字段添加索引
3. 使用 `EXPLAIN ANALYZE` 分析查询
4. 考虑分页加载

### Q: 如何减少 API 调用成本？
A: 
1. 缓存 AI 分析结果
2. 批量处理报告上传
3. 使用更小的模型（如 Claude Haiku）
4. 限制分析频率

## 部署相关

### Q: 如何部署到生产环境？
A: 参考 [部署文档](./DEPLOYMENT.md)，推荐使用：
- Vercel（Next.js 应用）
- Railway/Render（数据库）
- Docker（完整部署）

### Q: Docker 部署失败怎么办？
A: 
1. 检查 Docker 版本（需要 20.10+）
2. 确保端口未被占用
3. 查看日志：`docker-compose logs`
4. 重新构建：`docker-compose up -d --build`

### Q: 如何配置 HTTPS？
A: 
1. 使用 Nginx 反向代理
2. 配置 Let's Encrypt SSL 证书
3. 参考 [部署文档](./DEPLOYMENT.md#配置-ssl)

### Q: 如何备份数据？
A: 
```bash
# 备份数据库
pg_dump -U postgres fund_analysis > backup.sql

# 备份上传的文件
tar -czf uploads_backup.tar.gz uploads/
```

## 错误排查

### Q: 端口 3000 被占用
A: 
```bash
# 查找占用进程
lsof -i :3000

# 杀死进程
kill -9 <PID>

# 或使用其他端口
PORT=3001 npm run dev
```

### Q: Prisma 客户端未生成
A: 
```bash
npx prisma generate
```

### Q: API 请求失败
A: 
1. 检查 API Key 是否正确
2. 查看浏览器控制台错误
3. 检查网络连接
4. 查看服务器日志

### Q: 页面显示 404
A: 
1. 确保应用正在运行
2. 检查路由配置
3. 清除浏览器缓存
4. 重启开发服务器

## 数据管理

### Q: 如何导入现有数据？
A: 
1. 准备 CSV 或 JSON 格式数据
2. 使用 Prisma Studio 导入
3. 或编写导入脚本

### Q: 如何清空数据库？
A: 
```bash
npx prisma migrate reset
```
⚠️ 警告：这会删除所有数据

### Q: 如何导出数据？
A: 
```bash
# 导出为 SQL
pg_dump -U postgres fund_analysis > export.sql

# 或使用 Prisma Studio 导出
npx prisma studio
```

## 开发相关

### Q: 如何添加新功能？
A: 
1. 阅读代码结构文档
2. 创建新的 API 路由
3. 添加前端页面
4. 更新数据库模型（如需要）
5. 编写测试

### Q: 如何调试？
A: 
1. 使用浏览器开发者工具
2. 查看 Next.js 日志
3. 使用 `console.log` 或断点
4. 检查网络请求

### Q: 如何贡献代码？
A: 
1. Fork 项目
2. 创建功能分支
3. 提交 Pull Request
4. 等待代码审查

## 其他问题

### Q: 支持哪些浏览器？
A: 
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Q: 是否支持移动端？
A: 目前主要针对桌面端优化，移动端体验可能不佳。计划在未来版本中改进。

### Q: 如何获取技术支持？
A: 
1. 查看文档
2. 搜索 GitHub Issues
3. 提交新的 Issue
4. 联系开发团队

### Q: 项目开源吗？
A: 是的，项目采用 MIT 许可证。

### Q: 如何报告 Bug？
A: 在 GitHub Issues 中提交，包含：
- 问题描述
- 复现步骤
- 错误信息
- 环境信息

---

**找不到答案？** 请在 [GitHub Issues](https://github.com/your-repo/issues) 提问。
