# AI 升级快速参考

## 核心改进（一句话）

**从硬编码规则系统转向 AI 驱动创作流程，选题范围扩大 2-3 倍，标题质量显著提升，框架和策略从文档到实际执行。**

---

## 主要变化

### Brief 环节 ⭐ 新系统

**旧系统**：
- 7 个固定模板
- 字符串拼接标题
- 5 个候选选题

**新系统**：
- AI 理解事件因果
- 自然语言标题
- 10-15 个候选选题
- 推荐框架和策略

**使用方式**：
```
通过 Claude Code 调用：dasheng-stage-brief-ai
输入：产物/01_内容采集/{run_id}/
输出：产物/02_Brief/{run_id}/selected_topics.json
```

---

### Rewrite 环节 ⭐ 增强

**新增功能**：
- ✅ 完整应用 7 种写作框架
- ✅ 完整应用 4 种内容增强策略
- ✅ 智能字数补充（不再是硬编码财经块）
- ✅ 从 brief 继承框架和策略推荐

**新增模块**：
- `scripts/framework_strategy_loader.py` - 框架和策略加载器
- `scripts/ai_content_expander.py` - AI 智能字数补充

---

## 7 种写作框架

1. **痛点型** - 解决问题、提供方案
2. **故事型** - 人物、事件、趋势
3. **清单型** - 盘点、推荐、方法论
4. **对比型** - A vs B 分析
5. **热点解读型** - 时事评论、趋势分析
6. **纯观点型** - 立场鲜明的评论
7. **复盘型** - 事后分析、经验总结

---

## 4 种内容增强策略

1. **角度发现** - 找独特切入点（适合热点解读型/纯观点型）
2. **密度强化** - 增加可操作干货（适合痛点型/清单型）
3. **细节锚定** - 用真实细节增强代入感（适合故事型/复盘型）
4. **真实体感** - 用真实用户声音（适合对比型）

---

## 工作流程

```
Intake (采集)
    ↓
Brief (AI 生成 10-15 个候选)
    ↓ 推荐框架和策略
Brief Gate (编辑选择 3-5 个)
    ↓
Draft (根据框架生成)
    ↓
Material (素材补充)
    ↓
Rewrite (应用框架+策略+DNA)
    ↓ 智能字数补充
Rewrite Gate (编辑选择最佳版本)
    ↓
Publish
```

---

## 质量对比

### 选题标题对比

**旧系统** ❌：
```
外交部、伊朗：事件升级之外，长期秩序成本在怎样上升
美联储、中东这条线，市场是否低估了再通胀与利率预期回摆
```

**新系统** ✅：
```
中东冲突如何重塑全球能源供应链
中东冲突推高油价，美联储降息预期为何一再落空
```

### 字数补充对比

**旧系统** ❌：
```python
# 硬编码的财经内容块
"补充说明：判断是否进入'结构性改善'，必须同时满足三项条件..."
```

**新系统** ✅：
```python
# 根据框架类型智能生成
痛点型 → "3个常见错误做法 + 工具对比表 + 完整操作流程"
故事型 → "关键对话 + 转折点细节 + 人物心理活动"
清单型 → "隐藏推荐 + 避坑指南 + 使用场景对比"
```

---

## 预期效果

| 指标 | 升级前 | 升级后 | 提升 |
|------|--------|--------|------|
| 选题数量 | 5 个 | 10-15 个 | +100-200% |
| 选题采用率 | 60% | 80% | +33% |
| 编辑修改量 | 100% | 50% | -50% |
| 标题质量 | 6/10 | 8/10 | +33% |

---

## 关键文件

### 新创建的文件
- `skills/dasheng-stage-brief-ai/` - AI 驱动的 Brief 系统
- `scripts/framework_strategy_loader.py` - 框架和策略加载器
- `scripts/ai_content_expander.py` - AI 智能字数补充
- `AI_UPGRADE_PHASE1_SUMMARY.md` - 完整升级总结

### 更新的文件
- `skills/dasheng-sop-orchestrator/SKILL.md` - 集成 Brief AI
- `CLAUDE.md` - 更新架构说明

### 参考文档
- `skills/dasheng-stage-brief-ai/references/frameworks.md` - 7 种框架定义
- `skills/dasheng-stage-brief-ai/references/content-enhance.md` - 4 种策略定义
- `skills/dasheng-stage-brief-ai/references/ai-generation-guide.md` - AI 生成指南
- `skills/dasheng-stage-brief-ai/references/topic-evaluation.md` - 5 维评估框架

---

## 下一步

### 立即行动
1. 测试新的 Brief AI 系统
2. 收集编辑反馈
3. 对比新旧系统效果

### 后续阶段
- **第二阶段（2-4周）**：Draft 框架生成 + Material 优化
- **第三阶段（4-8周）**：Intake 分类 + 事实核查
- **第四阶段（8+周）**：学习飞轮 + 持续优化

---

## 风险控制

✅ **保留人工审核**：3 个 Gate（Brief/Draft/Rewrite）
✅ **回退机制**：AI 失败时使用旧系统
✅ **兼容性**：不破坏现有流程
✅ **质量验证**：自动检查 + 人工审核

---

## 联系方式

- 完整规划：`${HOME}/.claude/plans/gleaming-rolling-petal.md`
- 详细总结：`AI_UPGRADE_PHASE1_SUMMARY.md`
- 问题分析：`BRIEF_PROBLEM_ANALYSIS.md`
- 测试报告：`BRIEF_AI_TEST_REPORT.md`
