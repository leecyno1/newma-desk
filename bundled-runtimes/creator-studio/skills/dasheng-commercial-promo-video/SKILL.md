---
name: dasheng-commercial-promo-video
description: Build brand films, product promos, launch trailers, and performance ads as the commercial_promo_video lane. Use when turning a brand/product brief, official assets, product captures, claims, offer, or CTA into a reviewable commercial script, storyboard, asset route, Remotion/HyperFrames production plan, and QC contract.
---

# Newma 广告宣传片

## 定位

这是广告宣传片的独立生产 Skill，不是无头科普的短版。

标准流程：

`品牌/产品素材接收 -> 广告文案重写 -> 导演分镜 -> 素材生成 -> 剪辑合成 -> 渲染 -> QC/交付`

支持：

- `brand_film`：品牌形象片
- `product_promo`：产品功能宣传片
- `launch_trailer`：新品发布预告
- `performance_ad`：以转化为目标的效果广告

默认时长为 15、30、60 秒；默认 `9:16`，兼容 `16:9`、`1:1`、`4:5`。

## 工作流

### 1. 锁定商业 Brief

先确认：

- 品牌、产品、受众、投放平台和唯一目标
- 用户痛点、产品承诺、核心卖点、证明材料、品牌记忆点和 CTA
- Logo、颜色、字体、产品 UI/实拍、官方图片、价格、优惠、法律说明和授权
- 15/30/60 秒版本、首要比例和交付规格

品牌视觉不完整时，先用 `brandkit` / `brand-guidelines` 建立品牌系统。产品外观、价格、优惠、数据或界面无法核实时，保留阻塞状态，不得用生成画面冒充。

详细合同见 [references/creative-contract.md](references/creative-contract.md)。

### 2. 重写广告脚本

使用一条主线：

`钩子 -> 痛点 -> 产品承诺 -> 卖点/演示 -> 结果或证明 -> 品牌记忆 -> CTA`

要求：

- 每条广告只有一个转化目标。
- 先写口播，再写屏幕短文案；两者不得机械重复。
- 卖点必须翻译为用户收益，不能只列功能名。
- 证明优先使用真实产品录屏、实拍、客户结果、可核验数据或官方页面。
- 价格、优惠、比较、绝对化表述和性能结论必须绑定来源与有效期。
- `performance_ad` 必须明确 offer、CTA 和必要免责声明。

### 3. 生成导演包

先准备商业 Brief JSON，再运行：

```bash
python3 skills/dasheng-commercial-promo-video/scripts/build_commercial_promo_package.py \
  --input <commercial_brief.json> \
  --output-dir ~/Desktop/自媒体创作/<run_id>/commercial_promo_video/director_scene_plan
```

输出：

- `commercial_brief.normalized.json`
- `script.json`
- `scene_plan.json`
- `tool_routing_plan.json`
- `scene_plan_quality_gate.json`
- `storyboard_template_review.html`
- `director_checkpoint.json`

生成后先审核分镜，再进入素材、配音和渲染。

### 4. 素材与动画路由

优先级：

1. 官方 Logo、品牌资产、产品录屏和产品实拍
2. 可核验的客户结果、数据、评价和官方页面
3. 有来源的真实情境 B-roll
4. Codex `imagegen` 生成的概念视觉或参考帧
5. 官方 Gemini/Veo、Seedance、MiniMax 逐镜生成的氛围或转场镜头

动画分工：

- HyperFrames / HTML / GSAP：Hero、产品功能、数字、Logo、CTA、字幕与节拍动画
- Remotion：主时间轴、镜头切换、产品录屏、品牌资产、字幕、BGM、SFX 和多比例适配
- FFmpeg：转码、响度、限幅、探测和最终 QC

生成式镜头不得证明真实产品能力、客户结果、价格或效果。

### 5. 广告 QC

交付前必须确认：

- 前 3 秒能看懂受众、冲突或结果
- 产品在承诺后尽快出现，卖点有演示或证明
- Logo、颜色、字体、产品外观和品牌语气一致
- 屏幕短文案可读，字幕、Logo、价格、优惠和 CTA 不互相遮挡
- 价格、优惠、日期、比较、数据和免责声明准确且仍有效
- 结尾包含品牌记忆点和一个明确 CTA
- 音乐、音效和口播不抢占，响度、峰值、节拍和转场通过 QC
- 最终交付文件与 QC 文件的路径、时长和 SHA-256 完全一致

## 硬门禁

- 未锁定品牌系统、核心承诺和唯一 CTA，不得进入正式素材生成。
- 未经验证的产品能力、客户结果、数字、价格或优惠不得上线。
- 生成式产品界面、虚构评价或虚构使用效果不得包装成真实证明。
- 广告不能只有氛围、Logo 和漂亮转场；必须出现产品、收益与行动指令。
- 广告也不能退化成长篇科普；解释只服务理解产品和完成转化。
- 所有运行产物必须写入 `~/Desktop/自媒体创作/`，不得写入项目或 Skill 目录。
