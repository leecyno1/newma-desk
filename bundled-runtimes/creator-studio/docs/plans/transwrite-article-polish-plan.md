# 转写环节文章打磨计划（article_build v2）

日期：2026-08-21 | Run：creator-ffcdfbbb1615（T01/T06/T09 三篇）

## 用户标准（转写环节写作规范）

1. **DNA 档案先行**：转写前拉取 DNA 档案（风格/结构选型记录），按档案转写
2. **网图素材**：转写时从网上搜索图片素材（标注来源）
3. **数据补全**：数据表 + 数据图（Tushare 实测）
4. **AI 说明图**：手绘/漫画/柳叶刀/小黑（lemon 柠檬人）风格，与内容高度匹配
5. **字数 ≥5000**
6. **结构完整**：名言引用、前言、引言、各章节
7. **媒体水印 + 话题标注**（文末）
8. **边界澄清**：transwrite 只做内容生产；上传草稿/发布 = publish 环节（registry + 前端描述体现）

## 技术储备（已核）

- DNA：core/dna_engine.py + dna/dna_config.yaml（选型+质量阈值 rewrite≥8.0）
- 小黑：skills/dasheng-lemon-illustrations（柠檬人系统，改编自 helloianneo/ian-xiaohei-illustrations，prompt 模板齐备）
- 改写引擎：skills/dasheng-media-rewrite-v2（EnhancedPromptBuilder/QualityScorer/AnchorMapper）
- 数据：Tushare（.tushare_token）+ matplotlib
- 生图：ImageGen + configs/image_generation/cover_presets_imagegen.yaml（封面 11 风格先例）

## 执行项

### P1 编码
- [x] P1.1 说明图风格库 configs/image_generation/explain_illustration_styles.yaml（lemon/手绘白描/漫画分格/柳叶刀）
- [x] P1.2 生产器 scripts/build_transwrite_articles.py（DNA→重写→数据→图→HTML 流水线，可复跑）
- [x] P1.3 registry：article_build 描述升级 + transwrite/publish 边界描述 + publish 节点描述（上传/发布职责）

### P2 前端显示
- [x] P2.1 环节/节点描述在 creator-studio UI 生效验证（节点级 description 已在 snapshot 生效，stage 名称更新为「转写生产/多平台发布」）

### P3 生产（3 篇）
- [x] P3.1 T06 美债 40 万亿 → 默丘利Lab（投资市场组）
- [x] P3.2 T01 中美 AI 生态 → Newma牛马进化论（AI 科技组）
- [x] P3.3 T09 芯片军备赛 → 墨丘利实验室（财经商业组）
- 每篇：DNA 档案 → ≥5000 字重写 → 数据表/图 → 说明图×2 → 网图×1 → HTML v2（水印+话题）→ register

### P4 反馈
- [x] P4.1 全量交付汇报（可点击链接）

## 完成记录（2026-08-21）

- T06 5036 字 / T01 5436 字 / T09 5013 字，三篇全部 ≥5000
- 说明图风格库 4 风格落地（小黑柠檬人/手绘白描/漫画分格/柳叶刀），首用 6 张
- 官方数据核验：美债 $39,986,657,878,071.92（Debt to the Penny 8-17）；8-20 收盘闭环：黄金 ETF +2.90% / 中概互联 +1.53%
- 产物已 register 至 article_build 节点
