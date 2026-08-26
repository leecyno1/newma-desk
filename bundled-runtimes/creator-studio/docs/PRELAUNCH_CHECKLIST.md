# 上线前检查清单

## 仓库

- [ ] `README.md` 与当前目录结构一致
- [ ] `docs/INSTALLATION.md` 不引用不存在路径
- [ ] `docs/STAGE_INTERFACES.md` 与当前主链一致
- [ ] `.gitignore` 已屏蔽运行时污染目录

## 主链

- [ ] 唯一正式入口为 `dasheng-media-sop`
- [ ] 旧入口仅做重定向
- [ ] `run_mainline_stage.py` 不再猜最新目录
- [ ] `workflow_doctor.py` 可在无 `CLAUDE.md` 时定位仓库

## 导出包

- [ ] `scripts/export_skill_suite.py` 可导出正式包
- [ ] 导出结果不含 `.git`
- [ ] 导出结果不含 `__pycache__`
- [ ] 导出结果包含安装脚本与环境模板

## 安装

- [ ] `install_to_openclaw.sh` 可安装到自定义目录
- [ ] `install_to_hermes.sh` 可安装到自定义目录
- [ ] 安装后能定位 `OPENCLAW_WORKSPACE` / `HERMES_WORKSPACE`

## 验证

- [ ] `pytest` 通过主链硬化测试
- [ ] `pytest` 通过导出测试
- [ ] `scripts/export_skill_suite.py` 可成功运行
