# Configuration Templates

This directory contains template files for external configuration. Copy and customize these templates for your environment.

## Quick Start

```bash
# 1. Feishu API Configuration
mkdir -p ~/clawd/configs
cp configs/feishu/feishu_api.conf.template ~/clawd/configs/feishu_api.conf
chmod 600 ~/clawd/configs/feishu_api.conf
# Edit and fill in your credentials

# 2. Image Generation Providers
cp configs/image_generation/providers.local.env.template configs/image_generation/providers.local.env
# Edit and fill in your API keys

# 3. Tushare Token (for financial data)
cp .tushare_token.template .tushare_token
# Edit and fill in your token

# 4. Environment Variables (optional)
# Copy relevant sections from .env.template to your ~/.zshrc or ~/.bashrc
```

## Template Files

### 1. Feishu API Configuration
**Template**: `configs/feishu/feishu_api.conf.template`  
**Target**: `~/clawd/configs/feishu_api.conf`  
**Purpose**: Feishu (Lark) API credentials for collaboration sync

Required fields:
- `APP_ID` - Feishu app ID
- `APP_SECRET` - Feishu app secret
- `TENANT_KEY` - Feishu tenant key
- `CHAT_ID` - Target chat/group ID

### 2. Image Generation Providers
**Template**: `configs/image_generation/providers.local.env.template`  
**Target**: `configs/image_generation/providers.local.env`  
**Purpose**: API keys for AI image generation services

Supported providers (at least one required):
- `VIVIAI_IMAGE_API_KEY`
- `VECTORENGINE_API_KEY`
- `QHAIGC_API_KEY`
- `GITEE_AI_API_KEY`

### 3. Tushare Token
**Template**: `.tushare_token.template`  
**Target**: `.tushare_token`  
**Purpose**: Financial data API token for Material stage

Get your token from: https://tushare.pro/register

### 4. Environment Variables
**Template**: `.env.template`  
**Target**: Your shell profile (`~/.zshrc` or `~/.bashrc`)  
**Purpose**: System-wide configuration overrides

Key variables:
- `DASHENG_PROJECT_ROOT` - Project root directory
- `DASHENG_DESKTOP_ROOT` - Desktop delivery directory
- `DASHENG_FEISHU_CONFIG` - Feishu config file path
- `DASHENG_INTAKE_*` - Data source URLs
- `DASHENG_WECHAT_*` - WeChat fetch configuration
- `MATERIAL_*` - Material stage control flags
- `TUSHARE_TOKEN` - Tushare API token

## Path Configuration

The system uses `scripts/path_config.py` to manage all hardcoded paths. All paths can be overridden via environment variables.

Test your configuration:
```bash
python3 scripts/path_config.py
```

## Security Notes

1. **Never commit actual credentials** - All `.template` files are safe to commit, but actual config files should be in `.gitignore`
2. **File permissions** - Set restrictive permissions on credential files:
   ```bash
   chmod 600 ~/clawd/configs/feishu_api.conf
   chmod 600 configs/image_generation/providers.local.env
   chmod 600 .tushare_token
   ```
3. **Environment variables** - Prefer file-based configuration over environment variables for sensitive data

## Verification

After configuration, run diagnostics:
```bash
python3 scripts/workflow_doctor.py --latest
```

This will check:
- All configuration files exist
- API credentials are present (masked in output)
- Stage contracts are valid
- Provider connections work

## Troubleshooting

**Problem**: `FileNotFoundError` for config files  
**Solution**: Ensure you've copied templates to target locations and filled in credentials

**Problem**: Image generation fails  
**Solution**: Check `providers.local.env` has at least one valid API key

**Problem**: Feishu sync fails  
**Solution**: Verify `feishu_api.conf` credentials and chat ID are correct

**Problem**: Material stage can't fetch financial data  
**Solution**: Ensure `.tushare_token` exists and contains valid token
