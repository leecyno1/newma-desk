# Installation Guide - OpenClaw/Hermes Deployment

This guide covers installing the Newma Media Studio into OpenClaw or Hermes agent frameworks.

## System Requirements

### Software Dependencies
- **Python**: 3.13+ (required for f-string syntax)
- **Node.js**: 25.8.1+ (for skill wrappers)
- **Git**: For repository cloning
- **Operating System**: macOS, Linux, or Windows with WSL2

### Python Packages
```bash
pip install anthropic requests pytest matplotlib pandas tushare akshare
```

### Node.js Packages
```bash
npm install -g @anthropic-ai/sdk
```

### External Services (Optional)
- **Feishu/Lark API**: For collaboration sync
- **Tushare**: For financial data (Material stage)
- **Image Generation APIs**: VivAI, VectorEngine, QhAIGC, or Gitee AI

## Installation Steps

### 1. Clone Repository

```bash
# Clone to your preferred location
git clone <repository-url> /path/to/dasheng-media-workflow
cd /path/to/dasheng-media-workflow
```

### 2. Set Environment Variables

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
# Core paths
export DASHENG_PROJECT_ROOT="/path/to/dasheng-media-workflow"
export DASHENG_DESKTOP_ROOT="$HOME/Desktop/自媒体创作"

# Feishu configuration
export DASHENG_FEISHU_CONFIG="$HOME/clawd/configs/feishu_api.conf"

# Data sources (adjust to your environment)
export DASHENG_INTAKE_5173_BASE="http://127.0.0.1:18000"
export DASHENG_INTAKE_REPORTS_BASE="http://45.197.148.64:8080"
export DASHENG_INTAKE_8000_BASE="http://45.197.148.64:8000"

# WeChat fetch configuration
export DASHENG_WECHAT_FETCH_ROUNDS=3
export DASHENG_WECHAT_WAIT_SECONDS=8
export DASHENG_WECHAT_MIN_VALID_ITEMS=8

# Material stage flags
export MATERIAL_ENABLE_NEWS_SCREENSHOT=1
export MATERIAL_SKIP_VIDEO_PROBE=1
export MATERIAL_AI_STOP_AFTER_FIRST_SUCCESS=1

# Matplotlib (for headless servers)
export MPLBACKEND=Agg
```

Reload your shell:
```bash
source ~/.zshrc  # or source ~/.bashrc
```

### 3. Configure External Services

#### Feishu API (Optional)
```bash
mkdir -p ~/clawd/configs
cp configs/feishu/feishu_api.conf.template ~/clawd/configs/feishu_api.conf
chmod 600 ~/clawd/configs/feishu_api.conf
# Edit and fill in your credentials
```

#### Image Generation Providers (Required for Material stage)
```bash
cp configs/image_generation/providers.local.env.template \
   configs/image_generation/providers.local.env
chmod 600 configs/image_generation/providers.local.env
# Edit and add at least one API key
```

#### Tushare Token (Optional, for financial data)
```bash
cp .tushare_token.template .tushare_token
chmod 600 .tushare_token
# Edit and add your token from https://tushare.pro/register
```

### 4. Verify Configuration

```bash
# Test path configuration
python3 scripts/path_config.py

# Run diagnostics
python3 scripts/workflow_doctor.py --latest

# Run test suite
python3 -m pytest tests/ -v
```

Expected output:
- Path configuration shows correct paths
- Workflow doctor reports no ERROR-level issues
- Tests: 87 passed, 2 skipped

## OpenClaw Integration

### Install as OpenClaw Skill Package

```bash
# Copy skills to OpenClaw workspace
cp -r skills/* $OPENCLAW_WORKSPACE/skills/

# Copy shared runtime data
cp -r skills/dasheng-daily-shared $OPENCLAW_WORKSPACE/skills/

# Register skills
openclaw skill register dasheng-daily-intake
openclaw skill register dasheng-daily-brief
openclaw skill register dasheng-stage-draft
openclaw skill register dasheng-daily-material
openclaw skill register dasheng-media-sop
openclaw skill register dasheng-stage-publish-video
openclaw skill register dasheng-daily-postmortem
```

### Verify Installation

```bash
# List installed skills
openclaw skill list | grep dasheng

# Test a skill
openclaw skill run dasheng-daily-intake --test
```

## Hermes Integration

### Install as Hermes Agent Module

```bash
# Copy to Hermes modules directory
cp -r . $HERMES_MODULES/dasheng-media-workflow

# Register module
hermes module register dasheng-media-workflow

# Configure module
hermes module config dasheng-media-workflow \
  --project-root $DASHENG_PROJECT_ROOT \
  --desktop-root $DASHENG_DESKTOP_ROOT
```

### Verify Installation

```bash
# Check module status
hermes module status dasheng-media-workflow

# Run health check
hermes module health-check dasheng-media-workflow
```

## Usage

### Running Individual Stages

```bash
# Stage 1: Intake
python3 scripts/run_stage1_intake.py

# Stage 2: Brief (AI-assisted)
# Use dasheng-stage-brief-ai skill or manual editing

# Stage 3: Draft (iterative with editor)
python3 scripts/build_stage3_draft.py \
  --selected-topics /path/to/selected_topics.json \
  --run-id $(date +%Y-%m-%d_%H%M%S)

# Stage 4: Transwrite
python3 scripts/build_stage4_transwrite.py \
  --draft-manifest /path/to/draft_manifest.json \
  --transwrite-decision /path/to/transwrite_decision.json

# Stage 5: Publish
python3 scripts/build_stage5_publish.py \
  --transwrite-manifest /path/to/transwrite_manifest.json \
  --publish-decision /path/to/publish_decision.json

# Stage 6: Postmortem
# Use dasheng-daily-postmortem skill
```

### Running Full Workflow

```bash
# Using OpenClaw
openclaw workflow run dasheng-media-daily

# Using Hermes
hermes agent run dasheng-media-workflow --mode daily
```

### Feishu Collaboration Sync

```bash
# Sync latest run to Feishu
python3 scripts/feishu_stage_sync.py --latest

# Resume interrupted sync
python3 scripts/feishu_stage_sync.py --resume-only <run_id>

# Force fresh sync (use with caution)
python3 scripts/feishu_stage_sync.py --fresh <run_id>
```

## Troubleshooting

### Common Issues

#### 1. Import Errors
**Problem**: `ModuleNotFoundError: No module named 'path_config'`

**Solution**:
```bash
# Ensure scripts directory is in Python path
export PYTHONPATH="$DASHENG_PROJECT_ROOT/scripts:$PYTHONPATH"
```

#### 2. Path Not Found Errors
**Problem**: `FileNotFoundError: ${DASHENG_PROJECT_ROOT}/...`

**Solution**:
```bash
# Set correct project root
export DASHENG_PROJECT_ROOT="/your/actual/path"
python3 scripts/path_config.py  # Verify
```

#### 3. Feishu Sync Fails
**Problem**: `401 Unauthorized` or `403 Forbidden`

**Solution**:
```bash
# Check credentials
cat ~/clawd/configs/feishu_api.conf
# Verify APP_ID, APP_SECRET, TENANT_KEY are correct
```

#### 4. Image Generation Fails
**Problem**: `No valid image provider found`

**Solution**:
```bash
# Check provider configuration
cat configs/image_generation/providers.local.env
# Ensure at least one API key is valid
```

#### 5. Tests Fail
**Problem**: `test_workflow_doctor.py` fails with path errors

**Solution**:
```bash
# Run from project root
cd $DASHENG_PROJECT_ROOT
python3 -m pytest tests/test_workflow_doctor.py -v
```

### Getting Help

1. **Check diagnostics**:
   ```bash
   python3 scripts/workflow_doctor.py --latest
   ```

2. **Review logs**:
   ```bash
   # Stage outputs are in 产物/<stage>/<run_id>/
   ls -la 产物/
   ```

3. **Run tests**:
   ```bash
   python3 -m pytest tests/ -v --tb=short
   ```

4. **Report issues**:
   - GitHub: https://github.com/anthropics/claude-code/issues
   - Include: error message, environment info, steps to reproduce

## Uninstallation

### OpenClaw

```bash
# Unregister skills
openclaw skill unregister dasheng-daily-intake
openclaw skill unregister dasheng-daily-brief
# ... (repeat for all skills)

# Remove files
rm -rf $OPENCLAW_WORKSPACE/skills/dasheng-*
```

### Hermes

```bash
# Unregister module
hermes module unregister dasheng-media-workflow

# Remove files
rm -rf $HERMES_MODULES/dasheng-media-workflow
```

### Clean Environment Variables

Remove the `DASHENG_*` exports from your `~/.zshrc` or `~/.bashrc`.

## Next Steps

- Read [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options
- Read [API_REFERENCE.md](API_REFERENCE.md) for API documentation
- Review [CLAUDE.md](../CLAUDE.md) for development guidelines
- Read [STAGE_INTERFACES.md](docs/STAGE_INTERFACES.md) for stage input/output specifications
- Check [PRODUCTION_READINESS_STATUS.md](PRODUCTION_READINESS_STATUS.md) for system status

## Support

For questions or issues:
- Documentation: See `docs/` directory
- Configuration help: `docs/CONFIGURATION.md`
- API reference: `docs/API_REFERENCE.md`
- GitHub Issues: Report bugs and feature requests
