# 贡献指南

感谢您对 Newma Media Studio 项目的关注！我们欢迎各种形式的贡献。

## 贡献方式

### 报告问题

如果您发现bug或有功能建议：

1. 在 [GitHub Issues](https://github.com/leecyno1/newma-media-studio/issues) 搜索是否已有相关issue
2. 如果没有，创建新issue，提供：
   - 清晰的标题和描述
   - 复现步骤（如果是bug）
   - 预期行为和实际行为
   - 环境信息（Python版本、Node.js版本、操作系统）
   - 相关日志或截图

### 提交代码

1. **Fork项目**
   ```bash
   # 在GitHub上fork项目
   git clone https://github.com/YOUR_USERNAME/newma-media-studio.git
   cd newma-media-studio
   ```

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

3. **开发**
   - 遵循代码风格指南
   - 添加测试
   - 更新文档

4. **测试**
   ```bash
   # 运行所有测试
   python3 -m pytest tests/ -v
   
   # 运行代码检查
   flake8 core/ scripts/
   black --check core/ scripts/
   ```

5. **提交**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   # 或
   git commit -m "fix: fix your bug description"
   ```

6. **推送并创建Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```
   
   然后在GitHub上创建Pull Request。

## 代码风格

### Python

- 遵循 [PEP 8](https://pep8.org/)
- 使用 `black` 格式化代码
- 使用 `flake8` 检查代码质量
- 使用类型注解（Python 3.10+）

```python
def process_data(input_file: Path, output_dir: Path) -> dict:
    """处理数据文件
    
    Args:
        input_file: 输入文件路径
        output_dir: 输出目录路径
        
    Returns:
        处理结果字典
    """
    pass
```

### JavaScript/Node.js

- 使用2空格缩进
- 使用 `const` 和 `let`，避免 `var`
- 使用箭头函数
- 添加JSDoc注释

```javascript
/**
 * 执行工作流阶段
 * @param {string} stageName - 阶段名称
 * @param {Object} options - 选项
 * @returns {Promise<Object>} 执行结果
 */
async function runStage(stageName, options) {
  // ...
}
```

## 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type类型

- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式（不影响代码运行）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

### 示例

```
feat(intake): add fallback mechanism for WeChat source

- Add cache layer for WeChat data
- Implement retry logic with exponential backoff
- Add health check for data sources

Closes #123
```

## 测试要求

所有新功能和bug修复都必须包含测试：

### 单元测试

```python
# tests/unit/test_path_resolver.py
def test_resolve_path_with_relative():
    """测试相对路径解析"""
    resolver = PathResolver()
    path = resolver.resolve('work_dirs.materials')
    assert path.is_absolute()
    assert path.name == '素材'
```

### 集成测试

```python
# tests/integration/test_stage_integration.py
def test_intake_to_brief_integration():
    """测试Intake到Brief的数据传递"""
    # 运行Stage 1
    intake_result = run_intake()
    
    # 验证输出
    assert intake_result['success']
    assert Path(intake_result['manifest_file']).exists()
    
    # 运行Stage 2
    brief_result = run_brief(intake_result['manifest_file'])
    assert brief_result['success']
```

## 文档要求

- 所有新功能必须更新相关文档
- 使用清晰的中文或英文
- 包含代码示例
- 更新 CHANGELOG.md

## Pull Request检查清单

提交PR前，请确认：

- [ ] 代码遵循项目风格指南
- [ ] 添加了必要的测试
- [ ] 所有测试通过
- [ ] 更新了相关文档
- [ ] 更新了 CHANGELOG.md
- [ ] 提交信息符合规范
- [ ] PR描述清晰，说明了变更内容和原因

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/leecyno1/newma-media-studio.git
cd newma-media-studio

# 安装依赖
./scripts/install.sh

# 安装开发依赖
pip install -r requirements-dev.txt

# 配置pre-commit hooks（可选）
pre-commit install
```

## 获取帮助

如果您在贡献过程中遇到问题：

- 查看 [文档](docs/)
- 在 [GitHub Discussions](https://github.com/leecyno1/newma-media-studio/discussions) 提问
- 在 [GitHub Issues](https://github.com/leecyno1/newma-media-studio/issues) 报告问题

## 行为准则

请遵守我们的行为准则：

- 尊重所有贡献者
- 接受建设性批评
- 关注对项目最有利的事情
- 对社区成员表现出同理心

## 许可证

通过贡献代码，您同意您的贡献将在 MIT 许可证下发布。

---

再次感谢您的贡献！
