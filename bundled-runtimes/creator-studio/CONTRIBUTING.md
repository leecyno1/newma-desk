# 贡献指南

欢迎通过 Issue、文档、测试、Skill、适配器和工作流改进参与项目。

## 开发流程

```bash
git clone https://github.com/YOUR_NAME/newma-media-studio.git
cd newma-media-studio
git switch -c feat/short-description
./scripts/install.sh
source .venv/bin/activate
```

修改后至少运行：

```bash
python -m pytest tests -q
python scripts/verify_installation.py
python scripts/build_project_catalog.py --check
git diff --check
```

## 变更原则

- 保持六阶段主链和 Manifest/Gate 契约。
- 新 Skill 需要 `SKILL.md`、注册表登记、清晰输入输出和测试。
- 新外部项目先进入 `configs/external/reserved_projects.json`，不要把第三方源码提交到主仓库。
- 外部项目的本地兼容修改应导出到 `patches/upstreams/` 并登记。
- 新路径必须使用环境变量或仓库相对路径，不得写个人绝对路径。
- 不得提交密钥、Cookie、OTP、账号 Profile、抓取数据、成品媒体或运行产物。
- 生成型文档应由脚本维护，并提供陈旧检查。

## 提交

采用 Conventional Commits，例如：

```text
feat(video): add director scene quality gate
fix(publish): verify platform receipt before success
docs: refresh reserve project catalog
```

Pull Request 请说明变更目的、影响的阶段、验证命令和必要的回滚方式。更完整的历史说明见 `docs/CONTRIBUTING.md`。
