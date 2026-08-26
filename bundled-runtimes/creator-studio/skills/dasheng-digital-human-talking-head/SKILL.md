---
name: dasheng-digital-human-talking-head
description: Create governed single-presenter or dual-interview digital-human video from authorized portraits and speaker audio, using image generation plus audio-driven lip, eye and subtle body motion, then compositing independent presenter sources in Remotion. Use for 数字人、类真人、AI 访谈、照片说话、动物头像口播 or Luma lip-sync presenter videos.
---

# Newma AI 数字人口播与访谈

主路线：

`授权肖像 → Codex imagegen 角色参考图 → omni（Gemini 图生视频）中文口型/眼部微动作 → 独立无声人物源 → 数字人导演分镜 → Remotion 合成`

不再使用 Inochi2D 贴图换头作为正式路线。它和 JoyVASA 只保留为历史实验/离线备用。

**Luma 路线已废弃（2026-08-22 用户裁决）**：上一版已停用，禁止再用 luma_dream_machine；数字人人物源一律走 omni-video-bridge。

## 路由

- `human_video`：已有真人口播视频，直接走 `dasheng-video-roughcut`。
- `luma_animal_presenter`：当前默认。保留真人身材、服装、姿势和手部，用 imagegen 将头部重绘为写实 3D 动物头或头套，再让 Luma 按 MiniMax 音频生成口型与自然微动作。
- `single_presenter`：一张授权肖像对应一条 MiniMax 主音频，先生成短样，再按字幕停顿拆段。
- `dual_interview`：两张授权肖像和两条说话人音轨分别生成。禁止让一次图生视频同时控制两个人物的精确口型；最终使用双人全景、交替近景或分屏合成。
- `joyvasa_liveportrait`：Luma 不可用且用户明确要求完全本地时才使用；必须先过 6–10 秒短样。
- `inochi2d_openseeface`：仅用于技术研究，不得作为正式交付。

## 标准流程

1. **确认授权**：只处理本人、已授权人物或虚构角色。未确认肖像和声音权利时停止。
2. **锁定音频**：使用审核后的 MiniMax 中文音频。它是全片唯一主音频。
3. **检查原图**：优先单人正面、头肩或半身、手部完整、背景干净的 768–1536px 照片。
4. **用 imagegen 换头**：先查看原图，再调用内置 imagegen 编辑。只替换头部，保留身体、服装、姿势、手、背景、镜头和光线。
5. **默认造型**：大猩猩优先，其次牛、马、戴头套悍匪。生成一版后先由用户确认，再进入视频生成。
6. **建立任务包**：

```bash
python3 scripts/build_digital_human_job.py \
  --image <animal_head_portrait.png> \
  --audio <minimax.wav> \
  --output-dir <project>/digital_human_source \
  --consent confirmed \
  --engine luma_dream_machine \
  --profile animal_presenter
```

7. **进入 omni**：使用 dasheng-omni-video-bridge（Gemini 图生视频）。上传换头图和 MiniMax 音频，选择支持音频驱动/口型同步的工作流。账号、付费、额度和 CAPTCHA 由用户确认。
8. **生成短样**：先做 6–10 秒。要求镜头锁定、人物正面、身体和手势只做自然小动作、口型按中文音频、动物身份不漂移。
9. **审核短样**：重点检查口型延迟、嘴部畸变、牙齿闪烁、眼神、动物头尺寸、头颈接缝、手部和身体漂移。
10. **生成正文段落**：按字幕停顿拆成短段，失败只重做对应段。最终以 MiniMax 主音频重新对齐，不依赖 Luma 输出音频作为母带。
11. **转入导演链**：写入独立 `digital_human_video` Lane，再执行分镜、证据、B-roll、字幕、花字、Remotion 和 QC。
12. **披露**：发布时明确标注“AI 生成角色/AI 生成画面”。

## 双人访谈规则

1. 每位人物有独立 `speaker_id`、肖像、声音、生成任务、短样和 QC。
2. 编剧稿必须拆成明确 turn；每个 turn 只有一位 `active_speaker`。
3. 对话时间轴优先使用分轨音频或说话人时间戳；WhisperX diarization 只作备用。
4. 非发言者只能保持自然待机、轻微眨眼和呼吸，不做同步口型。
5. 构图在双人全景、发言者近景、反应镜头和分屏之间切换；人物姓名标签和字幕颜色保持固定。
6. 两个人物源均静音，最终按 turn 在 Remotion 根时间轴挂载各自 MiniMax 音轨一次。

## imagegen 换头约束

提示词必须明确：

- `Replace only the human head`；
- 原图是编辑目标，不是风格参考；
- 完整保留身材、服装、姿势、双手、手表、座椅、背景、构图和光线；
- 动物头为原创、可爱但写实的电影级 3D/VFX 造型；
- 头部尺寸接近原真人头，脖子自然进入衣领；
- 正视镜头，嘴唇/口腔结构清晰，便于后续中文口型；
- 禁止新增动物身体、改变手部、放大头部、加文字或水印。

大猩猩可参考高质量智慧猿类电影质感，但不得复制具体版权角色。

## Luma 提示词基线

```text
Locked camera, front-facing seated presenter. Preserve the exact character, body,
suit, hands, chair, background and framing from the input image. The realistic 3D
animal character speaks the supplied Chinese audio with accurate, restrained lip
sync and natural jaw motion. Add subtle blinking, breathing, tiny head motion and
small natural hand/body movement only. No identity drift, no head-size change, no
camera move, no scene cut, no new objects, no warped hands, no subtitles or text.
```

## 与导演系统的约定

- `lane`：`digital_human_video`。
- `presenter_source.kind`：`digital_human`。
- `presenter_source.mode`：`single_presenter` 或 `dual_interview`。
- `presenter_source.engine`：默认 `omni`。
- `voice.provider`：`minimax`；主音频只挂载一次。
- omni 输出若带音频，进入 Remotion 前先静音，只保留视觉层。
- 数字人不是事实证据；所有数据和判断仍绑定真实图表、新闻或文件。
- 每 8–20 秒切换证据、图表、B-roll 或人物构图，避免长时间盯着合成角色。

## 硬门禁

- 无肖像授权、声音授权或人物身份不明：停止。
- 用公众人物照片替其发言：停止。
- 未经用户确认换头图：不得消耗 Luma 额度。
- 账号选择、首次授权、付费、购买额度、CAPTCHA：交给用户。
- 短样出现身份漂移、严重嘴部畸变或手部变形：不得生成长片。

## 输出

- `animal_head_portrait.png`
- `digital_human_job.json`
- `presenter_source_manifest.json`
- `luma_segments/*.mp4`
- `digital_human_source.mp4`
- `digital_human_qc.json`

需要了解旧本地方案和回退边界时，读取 [references/model-selection.md](references/model-selection.md)。
