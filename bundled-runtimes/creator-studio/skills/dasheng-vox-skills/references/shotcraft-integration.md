# Shotcraft 接入规则

只在重写口播和审核分镜获批后使用 Shotcraft。它负责镜头运动语法，不参与改写论点、证据或结论。

## 适用镜头

| 内容 | 优先类别 |
|---|---|
| 新闻网页、官网通知、研报、文档 | `camera`、`ui-entrance`、`interaction` |
| 数据、增长、对比和时间演变 | `data` |
| 钩子、重点花字、章节呼吸位 | `typography`、`effects` |
| 留存打断、并列信息、段落转场 | `rhythm`、`transition` |
| 品牌开场和收尾 | `opening`、`outro` |

生成式隐喻镜头继续走 Gemini。真实新闻、人物发言、历史影像和精确证据继续使用真实素材；Shotcraft 只能负责运镜和动效，不能把示意画面伪装成证据。

## 固定步骤

1. 从 `gallery/api/library.json` 检索候选卡。
2. 选定卡名和 `style_key` 后，完整阅读卡片文档和对应 demo TSX。
3. 把绑定写入已批准的 `scene_plan`，不改口播、结论和证据关系。
4. 对真实页面采集 2× 全页图、元素切片和 `layout.json`。优先复用 Shotcraft 的 `assets/scripts/capture-template.mjs`。
5. 真实页面运镜优先复用 `assets/lib/PageCam.tsx`；精确文字、数字、图表和来源仍由 Remotion 覆盖。
6. 将选中的 demo 和必要依赖复制进当前成片工程，按视觉圣经替换字体、色板、材质和间距。
7. 每镜至少渲染 `qa_frames` 中的两个静帧；成片终检时对照镜头卡动作语法和已知坑。

## 命令

检索镜头卡：

```bash
python skills/dasheng-vox-skills/scripts/shotcraft_adapter.py search \
  --query "增长 图表" \
  --category data
```

给已批准的场景绑定并校验卡片：

```bash
python skills/dasheng-vox-skills/scripts/shotcraft_adapter.py bind \
  --input <project>/director/scene_plan.json \
  --output <project>/director/scene_plan.production.json

python scripts/video_scene_plan_quality_gate.py \
  <project>/director/scene_plan.production.json \
  --output <project>/director/scene_plan.production.quality_gate.json
```

每个待绑定场景先写：

```json
{
  "motion": {
    "shotcraft_card": "chart-live-moves",
    "style_key": "axis-rescale-shock"
  }
}
```

适配器会补齐：

- `production_route: shotcraft_remotion`
- `provider_order: [remotion_local_motion]`
- `motion.card_source`
- `motion.demo_source`
- `motion.duration_frames`
- `motion.qa_frames`
- `motion.brand_tokens`（当 `visual_bible` 已包含可用 tokens 时）

这类镜头不生成 Codex 参考图，也不调用 Gemini 视频模型。

## 硬规则

- 实际网页不得用 AI 伪造；先截真实页面，再做 PageCam 运镜。
- 一定读取准确 demo 源码，禁止只看卡名后重新凭感觉实现。
- 同一种高辨识度手法默认一支片只做一次主角。
- 禁止 `Math.random()`、`Date.now()` 和无参 `new Date()`；随机效果使用固定种子。
- SFX 使用 `SHOTS.<id>.from + offset` 或 `beatF(n)` 相对钉帧，不写裸绝对帧号。
- 画面时间线锁定后再铺 SFX；镜头时长变化后必须重验音画同步。
- 不依赖尚未合并的 ClipCard 和剪映导出 PR；需要时单独评审后再升级。
