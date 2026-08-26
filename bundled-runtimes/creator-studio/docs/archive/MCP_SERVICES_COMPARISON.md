# MCP Services Comparison Report

## Executive Summary

Based on research, **neither Postiz nor Aidelly currently support Chinese social media platforms** (WeChat, Weibo, Xiaohongshu, Douyin). Both services focus exclusively on Western platforms.

**Critical Finding**: MCP migration is **NOT viable** for the Dasheng workflow due to lack of Chinese platform support.

---

## Detailed Comparison

### Postiz

**Pricing**: [Postiz Pricing](https://www.socialrails.com/blog/postiz-pricing)
- Standard: $23/month (5 channels)
- Team: $49/month (15 channels)
- Agency: $79/month (50 channels)
- Open-source self-hosting available (free)

**Platform Coverage**: [Postiz Agent](https://postiz.com/agent)
- **Total**: 30+ platforms
- **Supported**: X/Twitter, LinkedIn, Reddit, Instagram, Facebook, Threads, YouTube, TikTok, Pinterest, Dribbble, Discord, Slack, Mastodon, Bluesky
- **NOT Supported**: WeChat, Weibo, Xiaohongshu, Douyin

**MCP Integration**: [Social Media MCP](https://postiz.com/blog/social-media-mcp)
- Native MCP support for Claude, Cursor, OpenClaw
- REST API available
- n8n, Make.com, Zapier integrations

**Strengths**:
- Most comprehensive Western platform coverage (30+)
- Open-source option available
- Affordable pricing ($23-$79/month)
- Strong MCP maturity

**Weaknesses**:
- ❌ **Zero Chinese platform support**
- Focused exclusively on Western markets

---

### Aidelly

**Pricing**: [Aidelly Pricing](https://www.aidelly.ai/pricing)
- Pricing not publicly disclosed (requires contact)
- Free trial available
- API access requires paid subscription

**Platform Coverage**: [Aidelly Agents](https://www.aidelly.ai/agents)
- **Total**: 6 platforms
- **Supported**: Instagram, TikTok, YouTube, X/Twitter, LinkedIn, Facebook
- **NOT Supported**: WeChat, Weibo, Xiaohongshu, Douyin

**MCP Integration**: [Best Social Media MCP Servers in 2026](https://www.aidelly.ai/guides/best-social-media-mcp-servers-2026)
- Deepest agentic MCP integration
- Content creation, scheduling, analytics, inbox management
- Unified inbox across all 6 platforms

**Strengths**:
- Deepest integration depth (analytics + inbox management)
- Strong AI-native features
- Unified inbox for engagement tracking

**Weaknesses**:
- ❌ **Zero Chinese platform support**
- Limited platform count (6 vs Postiz's 30+)
- Pricing not transparent
- Requires paid subscription for API access

---

## Chinese Platform Support Research

**Finding**: No major MCP service supports Chinese platforms as of 2026.

**Reason**: Chinese social media platforms have:
1. Closed APIs with strict access controls
2. Government regulations requiring local business registration
3. Different authentication systems (WeChat requires Chinese phone number)
4. Platform-specific browser automation requirements

**Alternative Solutions**:
- [KAWO](https://www.quora.com/Which-social-media-management-tool-works-for-Chinese-sites) - Specialized tool for WeChat, Weibo, Douyin (not MCP-based)
- Local OpenClaw skills (current approach) - Browser automation-based

---

## Decision Matrix

| Criteria | Postiz | Aidelly | Local Skills (Current) | Winner |
|----------|--------|---------|----------------------|--------|
| Chinese platforms (WeChat, Weibo, XHS, Douyin) | ❌ None | ❌ None | ✅ All 5 | **Local Skills** |
| Western platforms | ✅ 30+ | ✅ 6 | ❌ Only X | Postiz |
| MCP integration | ✅ Native | ✅ Native | ❌ None | Tie |
| Cost | $23-79/mo | Unknown | Free | **Local Skills** |
| Analytics | Basic | ✅ Deep | ❌ None | Aidelly |
| Maintenance | Low | Low | High | MCP |
| Control | Medium | Medium | ✅ Full | **Local Skills** |
| **Total Score** | 3/7 | 2/7 | **5/7** | **Local Skills** |

---

## Revised Recommendation

### ❌ Do NOT Migrate to MCP

**Reason**: Neither Postiz nor Aidelly support the 5 core Chinese platforms required by Dasheng workflow:
- WeChat Official Account
- WeChat Channels (video)
- Weibo
- Xiaohongshu
- Douyin

**Impact**: MCP migration would require maintaining **two separate systems**:
1. MCP service for Western platforms (if needed in future)
2. Local skills for all Chinese platforms (current requirement)

This defeats the purpose of unified architecture.

---

## Alternative Strategy: Hybrid Approach

### Phase 1: Enhance Local Skills (Immediate)
✅ Install `social-copy-generator` for content adaptation
✅ Install `wechat-video-publish` for WeChat Channels
✅ Install `auto-publisher` for multi-platform video orchestration
✅ Keep existing 5 local platform skills

### Phase 2: Add Western Platforms (Optional, Future)
If international expansion needed:
- Add Postiz MCP for Western platforms only
- Keep local skills for Chinese platforms
- Use `social-copy-generator` as bridge between both systems

### Phase 3: Monitor Chinese Platform API Development
- Watch for official API releases from WeChat, Weibo, XHS, Douyin
- Evaluate future MCP services that add Chinese platform support
- Migrate only when native API support becomes available

---

## Updated Implementation Plan

### Immediate Actions (Week 1)
1. ✅ Install 3 ClawHub skills (social-copy-generator, wechat-video-publish, auto-publisher)
2. ❌ ~~Sign up for Postiz trial~~ - Not needed (no Chinese platform support)
3. ❌ ~~Sign up for Aidelly trial~~ - Not needed (no Chinese platform support)
4. ✅ Update distribute stage to integrate new skills
5. ✅ Test enhanced workflow with current run_id

### Future Considerations
- Monitor KAWO for potential API/MCP integration
- Watch for Chinese platform official API announcements
- Evaluate Postiz/Aidelly only if Western platform expansion needed

---

## Sources

- [Postiz Pricing](https://www.socialrails.com/blog/postiz-pricing)
- [Postiz Agent - 30+ Platforms](https://postiz.com/agent)
- [Postiz Social Media MCP](https://postiz.com/blog/social-media-mcp)
- [Aidelly Pricing](https://www.aidelly.ai/pricing)
- [Aidelly Agents](https://www.aidelly.ai/agents)
- [Best Social Media MCP Servers in 2026](https://www.aidelly.ai/guides/best-social-media-mcp-servers-2026)
- [Which social media management tool works for Chinese sites?](https://www.quora.com/Which-social-media-management-tool-works-for-Chinese-sites)
- [2026 China Social Media Algorithm Guide](https://www.dchbi.com/post/douyin-vs-xiaohongshu-vs-wechat-channels-decoding-the-2026-algorithms-for-cross-border-growth)
