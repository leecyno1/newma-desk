# OpenClaw / Hermes 冒烟测试

## 1. 导出

```bash
python3 scripts/export_skill_suite.py --target-dir /tmp/dasheng-smoke-export
```

检查：

- `/tmp/dasheng-smoke-export/skills/dasheng-media-sop/SKILL.md`
- `/tmp/dasheng-smoke-export/scripts/run_mainline_stage.py`
- `/tmp/dasheng-smoke-export/install_to_openclaw.sh`

## 2. OpenClaw 安装

```bash
bash /tmp/dasheng-smoke-export/install_to_openclaw.sh \
  /tmp/openclaw-skills \
  /tmp/openclaw-workspace
```

检查：

- `/tmp/openclaw-skills/dasheng-media-sop`
- `/tmp/openclaw-workspace/scripts/run_mainline_stage.py`
- `OPENCLAW_WORKSPACE=/tmp/openclaw-workspace`

## 3. Hermes 安装

```bash
bash /tmp/dasheng-smoke-export/install_to_hermes.sh \
  /tmp/hermes-skills \
  /tmp/hermes-workspace
```

检查：

- `/tmp/hermes-skills/dasheng-media-sop`
- `/tmp/hermes-workspace/scripts/run_mainline_stage.py`
- `HERMES_WORKSPACE=/tmp/hermes-workspace`

## 4. 主链脚本

```bash
python3 /tmp/openclaw-workspace/scripts/run_mainline_stage.py --help
python3 /tmp/openclaw-workspace/scripts/workflow_doctor.py --run-id smoke
```

## 5. 旧入口重定向

```bash
node /tmp/openclaw-workspace/skills/dasheng-daily-draft/index.js
```

期望：

- 非零退出
- 输出中包含 `dasheng-media-sop`
