# ClawHub Skills Installation Research Report

## Installation Method (2026)

Based on research, OpenClaw v2026.3.24+ provides native ClawHub integration. The standard installation command is:

```bash
openclaw skills install <skill-name>
```

**Security Note**: After the ClawHavoc incident (Feb 2026), 13.4% of ClawHub skills were flagged for critical security issues. Always verify skills before installation.

---

## Target Skills Research

### 1. social-copy-generator

**Source**: [playbooks.com/skills/openclaw/skills/social-copy-generator](https://playbooks.com/skills/openclaw/skills/social-copy-generator)

**Description**: Generates platform-optimized social media copy for 14 platforms from single input (Twitter/X, LinkedIn, Hacker News, Reddit, Xiaohongshu, Jike, WeChat Moments, Weibo, Zhihu, Bilibili, etc.)

**Installation**:
```bash
openclaw skills install social-copy-generator
```

**Authentication**: None required (content generation only)

**Usage Pattern**: 
- Input: Single product/content description
- Output: Editable HTML page with platform-specific copy and copy buttons
- Platforms: 14+ including all major Chinese and Western social networks

**Integration Point**: Pre-processing step in distribute stage before platform-specific publishing

---

### 2. wechat-video-publish

**Source**: [playbooks.com/skills/openclaw/skills/wechat-video-publish](https://playbooks.com/skills/openclaw/skills/wechat-video-publish)

**Description**: Automates publishing videos to WeChat Channels via browser automation, handling login, upload, metadata, and publication

**Installation**:
```bash
openclaw skills install wechat-video-publish
```

**Authentication**: Browser automation (manual login required first time, session persisted)

**Features**:
- Video upload to WeChat Channels
- Title, description, tags metadata
- Location and originality settings
- Browser CDP-based automation

**Integration Point**: New platform option in distribute stage for WeChat video content

---

### 3. auto-publisher

**Source**: [playbooks.com/skills/openclaw/skills/auto-publisher](https://playbooks.com/skills/openclaw/skills/auto-publisher)

**Description**: Multi-platform video auto-publisher supporting Douyin, WeChat Channels, Xiaohongshu, Bilibili, YouTube

**Installation**:
```bash
openclaw skills install auto-publisher
```

**Authentication**: Platform-specific (varies by target platform)

**Features**:
- Batch publishing across multiple platforms
- Scheduled posting
- Auto-caption generation
- Hashtag optimization
- Supports: Douyin, WeChat Channels, Xiaohongshu, Bilibili, YouTube

**Integration Point**: Could replace or complement existing platform-specific video skills (douyin-upload-skill, xiaohongshu-auto)

---

## Installation Commands Summary

```bash
# Install all three skills
openclaw skills install social-copy-generator
openclaw skills install wechat-video-publish
openclaw skills install auto-publisher

# Verify installations
openclaw skills list

# Optional: Install with restricted permissions
openclaw skills install social-copy-generator --allow-tools=read,write
openclaw skills install wechat-video-publish --allow-tools=browser,network
openclaw skills install auto-publisher --allow-tools=browser,network,filesystem
```

---

## Security Verification Steps

Before using any installed skill:

1. **Run SkillCheck** (if available):
```bash
skillcheck verify social-copy-generator
skillcheck verify wechat-video-publish
skillcheck verify auto-publisher
```

2. **Manual Code Review**:
```bash
# Check skill source code
cat ~/.openclaw/skills/social-copy-generator/SKILL.md
cat ~/.openclaw/skills/wechat-video-publish/SKILL.md
cat ~/.openclaw/skills/auto-publisher/SKILL.md
```

3. **Test in Sandbox**:
```bash
openclaw run --sandbox "test social-copy-generator with sample content"
```

---

## Alternative Installation Methods

If `openclaw skills install` is not available:

### Method 1: Direct GitHub Clone
```bash
cd ~/.openclaw/skills
git clone https://github.com/openclaw/skills/social-copy-generator
git clone https://github.com/openclaw/skills/wechat-video-publish
git clone https://github.com/openclaw/skills/auto-publisher
```

### Method 2: NPM-based ClawHub CLI
```bash
# Install ClawHub CLI
npm install -g clawhub-cli

# Login to ClawHub
clawhub login

# Install skills
clawhub install social-copy-generator
clawhub install wechat-video-publish
clawhub install auto-publisher
```

---

## Next Steps

1. ✅ Installation commands identified
2. ⏳ Execute installations
3. ⏳ Test each skill independently
4. ⏳ Document authentication requirements
5. ⏳ Integrate into distribute stage

---

## Sources

- [Best ClawHub Skills: A Complete Guide](https://www.datacamp.com/blog/best-clawhub-skills)
- [OpenClaw Skills: How to Install from ClawHub Safely in 2026](https://blink.new/blog/openclaw-clawhub-skills-safe-install-guide-2026)
- [How to Install OpenClaw Skills the Right Way in Five Steps](https://www.roborhythms.com/openclaw-how-to-install-skills/)
- [social-copy-generator skill](https://playbooks.com/skills/openclaw/skills/social-copy-generator)
- [wechat-video-publish skill](https://playbooks.com/skills/openclaw/skills/wechat-video-publish)
- [auto-publisher skill](https://playbooks.com/skills/openclaw/skills/auto-publisher)
- [OpenClaw v2026.3.24 Skill Install Guide](https://www.elegantsoftwaresolutions.com/blog/openclaw-v2026-3-24-skill-install-guide)
