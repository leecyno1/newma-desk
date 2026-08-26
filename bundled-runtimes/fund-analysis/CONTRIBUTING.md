# 贡献指南

感谢你对基金经理评价分析系统的关注！我们欢迎所有形式的贡献。

## 如何贡献

### 报告 Bug

如果你发现了 Bug，请在 GitHub Issues 中提交，包含：

- **清晰的标题**：简要描述问题
- **详细描述**：问题的具体表现
- **复现步骤**：如何重现这个问题
- **期望行为**：你期望的正确行为
- **实际行为**：实际发生的情况
- **环境信息**：
  - 操作系统
  - Node.js 版本
  - 浏览器版本
  - 其他相关信息
- **截图或日志**：如果有的话

### 提出新功能

如果你有新功能的想法：

1. 先在 Issues 中搜索，确保没有重复
2. 创建新的 Issue，标记为 `enhancement`
3. 详细描述功能需求和使用场景
4. 等待社区讨论和反馈

### 提交代码

#### 1. Fork 项目

点击 GitHub 页面右上角的 "Fork" 按钮。

#### 2. 克隆到本地

```bash
git clone https://github.com/your-username/fund-analysis.git
cd fund-analysis
```

#### 3. 创建分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

分支命名规范：
- `feature/` - 新功能
- `fix/` - Bug 修复
- `docs/` - 文档更新
- `refactor/` - 代码重构
- `test/` - 测试相关

#### 4. 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 运行测试
npm test
```

#### 5. 提交代码

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```bash
git add .
git commit -m "feat: 添加基金对比功能"
# 或
git commit -m "fix: 修复净值图表显示错误"
```

提交信息格式：
- `feat:` - 新功能
- `fix:` - Bug 修复
- `docs:` - 文档更新
- `style:` - 代码格式（不影响功能）
- `refactor:` - 重构
- `test:` - 测试
- `chore:` - 构建/工具相关

#### 6. 推送到 GitHub

```bash
git push origin feature/your-feature-name
```

#### 7. 创建 Pull Request

1. 访问你的 Fork 页面
2. 点击 "New Pull Request"
3. 填写 PR 描述：
   - 改动内容
   - 相关 Issue
   - 测试情况
   - 截图（如果有）

## 代码规范

### TypeScript/JavaScript

- 使用 TypeScript
- 遵循 ESLint 规则
- 使用有意义的变量名
- 添加必要的注释
- 保持函数简洁（< 50 行）

```typescript
// ✅ 好的示例
async function fetchFundData(fundId: string): Promise<Fund> {
  const fund = await prisma.fund.findUnique({
    where: { id: fundId }
  })
  
  if (!fund) {
    throw new NotFoundError('基金')
  }
  
  return fund
}

// ❌ 不好的示例
async function f(id: string) {
  return await prisma.fund.findUnique({ where: { id } })
}
```

### React 组件

- 使用函数组件和 Hooks
- 组件名使用 PascalCase
- Props 使用 TypeScript 接口
- 提取可复用逻辑到自定义 Hooks

```typescript
// ✅ 好的示例
interface FundCardProps {
  fund: Fund
  onSelect?: (fund: Fund) => void
}

export function FundCard({ fund, onSelect }: FundCardProps) {
  return (
    <div onClick={() => onSelect?.(fund)}>
      <h3>{fund.name}</h3>
      <p>{fund.windCode}</p>
    </div>
  )
}
```

### API 路由

- 使用 RESTful 设计
- 统一错误处理
- 添加输入验证
- 返回标准格式

```typescript
// ✅ 好的示例
export async function GET(request: Request) {
  try {
    const funds = await prisma.fund.findMany()
    return NextResponse.json({ data: funds })
  } catch (error) {
    return NextResponse.json(
      { error: '获取基金列表失败' },
      { status: 500 }
    )
  }
}
```

### 数据库

- 使用 Prisma 模型
- 添加适当的索引
- 使用事务处理复杂操作
- 避免 N+1 查询

## 测试

### 运行测试

```bash
# 运行所有测试
npm test

# 运行特定测试
npm test -- funds

# 查看覆盖率
npm test -- --coverage
```

### 编写测试

```typescript
describe('FundCard', () => {
  it('should render fund information', () => {
    const fund = { id: '1', name: '测试基金', windCode: '000001' }
    render(<FundCard fund={fund} />)
    
    expect(screen.getByText('测试基金')).toBeInTheDocument()
    expect(screen.getByText('000001')).toBeInTheDocument()
  })
})
```

## 文档

### 更新文档

如果你的改动影响了用户使用：

- 更新 README.md
- 更新相关文档
- 添加代码注释
- 更新 API 文档

### 文档风格

- 使用清晰的标题
- 提供代码示例
- 添加截图（如果有帮助）
- 保持简洁明了

## Pull Request 检查清单

提交 PR 前，请确保：

- [ ] 代码遵循项目规范
- [ ] 添加了必要的测试
- [ ] 所有测试通过
- [ ] 更新了相关文档
- [ ] 提交信息清晰明确
- [ ] 没有不必要的文件改动
- [ ] 解决了所有冲突

## 代码审查

### 审查流程

1. 自动检查（CI/CD）
2. 代码审查（Maintainers）
3. 讨论和修改
4. 合并到主分支

### 审查标准

- 代码质量
- 功能完整性
- 测试覆盖
- 文档完善
- 性能影响

## 社区准则

### 行为规范

- 尊重他人
- 保持友善
- 接受建设性批评
- 关注项目目标

### 沟通方式

- GitHub Issues - Bug 报告和功能请求
- Pull Requests - 代码贡献
- Discussions - 一般讨论

## 开发环境

### 推荐工具

- **编辑器**: VS Code
- **插件**:
  - ESLint
  - Prettier
  - Prisma
  - TypeScript
- **浏览器**: Chrome DevTools

### 环境配置

```bash
# 安装依赖
npm install

# 配置环境变量
cp .env.example .env.local

# 启动数据库
./scripts/start-db.sh

# 运行迁移
npx prisma migrate dev

# 启动开发服务器
npm run dev
```

## 发布流程

### 版本号

遵循 [Semantic Versioning](https://semver.org/)：

- `MAJOR.MINOR.PATCH`
- `1.0.0` - 主版本（不兼容的改动）
- `1.1.0` - 次版本（新功能）
- `1.1.1` - 补丁版本（Bug 修复）

### 发布步骤

1. 更新版本号
2. 更新 CHANGELOG
3. 创建 Git Tag
4. 发布到 npm（如果适用）
5. 创建 GitHub Release

## 获取帮助

如果你在贡献过程中遇到问题：

1. 查看文档
2. 搜索 Issues
3. 在 Discussions 提问
4. 联系 Maintainers

## 致谢

感谢所有贡献者！你们的贡献让这个项目变得更好。

---

**Happy Coding!** 🎉
