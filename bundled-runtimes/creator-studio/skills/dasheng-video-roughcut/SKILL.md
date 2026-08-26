---
name: dasheng-video-roughcut
description: "Use when rough-cutting Chinese talking-head video with the reproducible Agent/FFmpeg path or the existing Jianying production path."
---

# Newma Video Roughcut｜口播视频粗剪

## 定位

这是 Transwrite 的口播视频辅助环节，处理“用户已经有真人口播素材”的场景。

目标是先给出可审核的粗剪版本，不直接替代人工精剪。

它不是独立主阶段，而是 `transwrite -> talking_head_video` 的“初检/粗剪”子环节。后续视频视觉层、HTML 动画、字幕烧录和平台导出继续留在 video lane 内组合。

## 输入

- 真人口播视频：`.mp4` / `.mov`
- 可选热词：股票、平台名、英文公司名、专有名词

## 技术栈

- ASR：FunASR `paraformer-zh + fsmn-vad + ct-punc`
- 渲染：FFmpeg
- 音频增强：FFmpeg 开源滤镜 `afftdn`、`dynaudnorm`、`acompressor`、`loudnorm`、`alimiter`
- 审核：本地 HTML 审核页
- 剪映生产通路：剪映专业版 `智能粗剪`、`智能剪口播`、美颜/滤镜、音频优化、人声美化、导出

## 双路径实验

当前口播粗剪保留两条路径：

- 路径 A：`FunASR -> Agent 字幕/语义整理 -> FFmpeg 精剪 -> HTML 审核页`，作为可复现、可追溯的工程基准链路。
- 路径 B：`剪映专业版 -> 智能粗剪 -> 智能剪口播 -> 导出工作拷贝 -> 重新导入 -> 参数/音频处理 -> 最终导出`，作为真人口播生产高速链路。

外部候选 `auto-editor` 只作为静音、节奏和口播清理算法参考，不是第四条生产路径。只有在独立样本中证明不会吞字、误删数字或破坏中文语义后，才允许通过 `dasheng-video-editing-bridge` 做受控实验；实验输出仍须回到本 Skill 的审核和 QC 门禁。

剪映路径优先依赖剪映自身的粗剪、剪口播和基础美化能力，不叠加 Agent 根据原提纲做二次语义检查。Agent 只负责流程记录、导出核验、门禁判断和必要的专名问题清单。

生产默认使用“剪映 + Record & Replay”，本地 FunASR/FFmpeg 路线作为可复现、可追溯的工程基准。

## 环节拆解

粗剪是真人口播视频的第一道门禁，不是导演剪辑的一部分。它只回答一个问题：这条口播是否已经足够流畅，可以进入包装、分镜、动画和字幕精修。

标准顺序：

1. `source_intake`: 记录原片路径、时长、分辨率、音频状态、是否已有字幕。
2. `asr_or_jianying_analysis`: 走 FunASR/Whisper/FunASR+Agent 或剪映智能剪口播，识别水词、重复、停顿、错话重启。
3. `delete_candidates`: 生成删除候选，必须记录原因：水词、重复、长停顿、错话重说、自我修正、无效开头结尾。
4. `roughcut_review`: 用户或 Agent 审核候选；高风险语义删除不得自动通过。
5. `roughcut_render`: 输出审核后粗剪视频和字幕/转写包。
6. `roughcut_polish`: 仅允许基础画面和声音修整，例如美颜、滤镜、音量、人声增强、降噪；不得进入导演包装、贴纸动效或智能包装。
7. `roughcut_gate`: 判断是否允许进入 `dasheng-video-talking-head`；不过关时只允许生成问题清单和分镜审阅，不允许终片渲染。

## 标准命令

### 初检审核包

```bash
.venv_media/bin/python scripts/video_roughcut_funasr.py \
  --input-video "/path/to/source.mp4" \
  --output-dir "~/Desktop/自媒体创作/<run_id>/04_转写/talking_head_video/roughcut" \
  --mode balanced
```

### Agent 整理稿对齐剪辑

先生成 Agent 整理输入：

```bash
python3 scripts/video_roughcut_agent_align.py \
  --source-video "/path/to/source.mp4" \
  --segments-json "roughcut/work/segments.json" \
  --output-dir "~/Desktop/自媒体创作/<run_id>/04_转写/talking_head_video/roughcut_agent_refine"
```

Agent 输出 `agent_plan.json` 后渲染：

```bash
python3 scripts/video_roughcut_agent_align.py \
  --source-video "/path/to/source.mp4" \
  --segments-json "roughcut/work/segments.json" \
  --agent-plan "roughcut_agent_refine/agent_plan.json" \
  --output-dir "~/Desktop/自媒体创作/<run_id>/04_转写/talking_head_video/roughcut_agent_refine"
```

首次使用媒体环境：

```bash
.venv_media/bin/python -m pip install -r requirements-media.txt
```

## 输出

- `roughcut_manifest.json`
- `work/funasr_raw.json`
- `work/segments.json`
- `work/delete_segments.json`
- `work/keep_segments.json`
- `final/*_roughcut_funasr.mp4`
- `final/*_roughcut_funasr.srt`
- `final/*_roughcut_funasr_softsub.mp4`
- `review/3_review_live.html`
- `review/review_server.js`
- `review/start_review.command`
- `review/2_candidates.json`
- `review/3_delete_segments.json`
- `review/3_delete_segments.reviewed.json`（人工保存后生成）
- `review/reviewed_output_loud.mp4`（保存并重剪后生成）
- `review/reviewed_output_loud.srt`（保存并重剪后生成）
- `review/reviewed_output_loud_softsub.mp4`（保存并重剪后生成）
- `review/proofread_agent_input.md`（保存并重剪后生成）
- 剪映路径必须额外记录：
  - `jianying_first_pass_export`: 智能粗剪/剪口播后的第一版工作拷贝
  - `jianying_final_export`: 重新导入、参数调整后的最终粗剪导出
  - `jianying_operation_log`: 草稿名、时间线名、原片时长、第一版时长、最终版时长、剪口播识别数量、参数调整项

## 审核方式

```bash
cd "<output-dir>/review"
PORT=8899 node review_server.js
```

浏览器打开 `http://localhost:8899/`。

- 勾选候选片段只影响实时预览，不会自动保存。
- 点击“保存审核”写入 `3_delete_segments.reviewed.json`。
- 点击“保存并重剪”生成审核后视频、SRT、软字幕视频和 Agent 字幕校对输入包。
- 字幕显示默认小字号，可关闭或调整。

## 剪映生产粗剪通路

适用条件：

- 用户本机已安装剪映专业版。
- 用户允许用剪映草稿作为交付物或由助理继续云端接力。
- 当前目标是快速得到“可继续导演剪辑”的真人口播粗剪素材，而不是追求完全可复现的开源流水线。

操作顺序：

1. 新建干净剪映草稿。
2. 导入口播原片。
3. 把素材放入时间线；必须在时间线片段上操作，不从素材库直接触发口播 AI。
4. 先运行 `智能粗剪`。如果出现提示词窗口，输入清晰中文要求：删除口误、重说、重复口头禅和无效停顿；保留数据、公司名、关键判断和完整逻辑链路；不要误删关键观点。
5. 等待粗剪/片段分割完成，抽查开头、中段、结尾是否仍有大段废话、错话和重说。
6. 再运行 `智能剪口播`，观察并记录剪映识别出的类别、数量和阈值，例如语气词、重复、停顿、静音阈值。
7. 应用剪口播删除结果后，导出第一版工作拷贝到桌面或 `~/Desktop/自媒体创作/<run_id>/roughcut/`。这一步的目的不是终稿，而是把复杂时间线压成轻量素材，让剪映后续参数调整和最终导出更快。
8. 重新导入第一版工作拷贝，建立第二阶段时间线。
9. 调整视频参数：美颜、美体或轻度滤镜只做基础形象修整，避免脸部失真、字幕漂移、过度磨皮和强塑料感。
10. 调整音频参数：放大音量、优化音频、人声增强/美化和必要降噪；确认没有爆音、金属音和明显抽吸感。
11. 导出最终粗剪视频，记录最终路径、时长、分辨率和音频状态。
12. 生成或填写 `roughcut_gate_report.json`；只有门禁通过，才能进入真人导演剪辑。

默认剪映提示词：

```text
删除口误、重说、重复口头禅、无效停顿和无意义铺垫；保留完整逻辑链路、关键判断、公司名、股票名、年份、数字和数据结论；剪辑节奏要流畅，不要吞字，不要把一句完整判断剪断。
```

注意：

- 不要从素材库直接右键触发“智能剪口播”；那会进入“选择文本插入时间线”模式，不是自动去水词路径。
- 不要使用录屏里的拼音输入作为自动化动作；所有提示词都用明确中文。
- “导出后再次导入上一版 MP4”是剪映生产通路的标准必选步骤，记录为 `roughcut_working_copy` / `jianying_first_pass_export`；必须同时记录第一版导出和最终导出，不能混淆两个版本。
- `智能包装` 不纳入标准粗剪流程。当前测试效果不稳定，容易引入无关包装、模板化素材和不可控改动；需要导演包装时交给 `dasheng-video-talking-head` 单独处理。
- 剪映草稿主时间线文件在新版剪映中可能被封装或加密，不能假设可用普通 JSON 解析。
- 剪映路径的最低交付是最终粗剪 MP4 加操作记录；如果用户或助理要继续接力，可同步保留本地草稿或上传云草稿。

## Record & Replay 维护

当剪映 UI 路径变化、粗剪质量异常、或用户要求重新录屏时：

- 先开启 Record & Replay，再执行剪映操作。
- 录制内容必须覆盖完整主路径：导入 -> 入时间线 -> 智能粗剪 -> 智能剪口播 -> 检查删除结果 -> 导出工作拷贝 -> 重新导入 -> 视频/音频参数调整 -> 最终导出或保存草稿。
- 录制结束后，把稳定结论写入全局 `video-rough-cut` skill 的 `references/recorded-workflow-summary.md`。
- 本 skill 只保留抽象规则和门禁；具体按钮、控件名、弹窗行为写到录制参考里。
- 如果录屏中出现会员、登录、云处理、权限、崩溃或 UI 路径不一致，记录为 caveat，不要写成稳定步骤。
- 如果误点 `智能包装` 或其他效果实验，必须在记录中标记为 `discarded_experiment`，不得写入标准粗剪链路。

## 剪辑策略

- 默认只做句段级删除，避免字词级硬切导致口播断裂。
- 删除长静音时保留少量呼吸间隔。
- 删除纯口水句，如单独的“嗯、呃、这个、那个”。
- 删除相邻重复句，保留更完整的一句；高风险语义候选必须让用户审核确认。
- 删除明显错话、重说、半句话重启、口播自我修正时，必须保留后一版更完整表达，并在审核页标注“错话/重说/自我修正”原因。
- 粗剪输出必须先过审核门禁，才能进入真人导演剪辑；如果还有大量“这个、那个、嗯、其实、就是、然后”、明显重复句或专名识别错误，不得直接进入终片渲染。
- 语义删改必须进入 `delete_segments.json`，供审核页追溯。
- 更精细的口水词、口吃、重复表达，优先走 Agent 整理稿对齐剪辑：Agent 按原口播顺序整理文字，脚本用差异对齐反推删除区间。
- Agent 整理稿不得重构文章，只能在原始口播顺序上做轻量删改、断句和专名修正；否则无法稳定映射回视频时间轴。

## 粗剪门禁

进入导演剪辑前必须生成并通过 `roughcut_gate_report.json`：

- `asr_quality`: 专名、股票/公司名、数字和年份不能大面积错误；低质量 ASR 只能生成候选，不允许终渲染。
- `filler_density`: 无效口头词密度过高时必须继续剪口播。
- `repeat_density`: 相邻重复、重说、错话重启必须进入删除候选。
- `continuity`: 剪后语音不能出现吞字、突兀跳切、逻辑断裂或明显音量断层。
- `jianying_audit`: 如果使用剪映路径，必须记录识别数量、分类、阈值、原片时长、第一版工作拷贝时长、最终导出时长和抽查结果。
- `jianying_polish`: 如果使用剪映路径，必须记录视频参数调整和音频参数调整；不得包含 `智能包装`。
- `review_status`: 用户或 Agent 审核明确通过后，才允许后续 `dasheng-video-talking-head` 读取该视频。
- `render_allowed`: 只有上述条件满足时才为 `true`；否则只能输出分镜审阅页和待处理清单。
- `opening_review`: 发布版前 30 秒必须逐句人工复听；不得以“呃/嗯/大家好”起手，不得保留重复字、半句重启和明显口误。
- `hook_deadline`: 核心判断默认必须在前 5 秒出现。若内容需要铺垫，最长不得超过 8 秒，并必须先给冲突或结果。
- `jianying_reimport_listen`: 剪映第一版导出并重新导入后，必须从头到尾复听一次。智能剪口播通过不等于人工粗剪通过。
- `repetition_scan`: ASR 出现相邻重复字、连续“嗯/呃”、同一句重复时，必须生成复听时间点；不得直接进入导演包装。

## 音频策略

- 默认对输出视频应用降噪、动态音量平衡、压缩、响度提升和限幅。
- 当前内置滤镜：`highpass -> lowpass -> afftdn -> dynaudnorm -> acompressor -> loudnorm(I=-14) -> alimiter`。
- 剪映路径可使用剪映内置音量放大、人声增强/美化和降噪；必须抽听确认没有爆音、金属音、抽吸声或音画不同步。
- 如果录音底噪很重，可后续升级接入 RNNoise / DeepFilterNet，但默认先用 FFmpeg 内置开源滤镜，减少部署复杂度。

## 视觉参数后处理

- 剪映路径可在重新导入第一版工作拷贝后做基础美颜、滤镜和画面参数调整；默认只做低风险增强，不做强瘦身、不做夸张滤镜。
- 原视频已经烧录大字幕时，滤镜环节默认不再封装 softsub，避免出现两套字幕。
- 远景侧脸素材不默认做局部 FaceMesh 拉瘦，优先用轻微整体横向瘦身，避免人物和字幕漂移。

## 字幕时间轴

- SRT 输出必须强制单调递增，避免字幕重叠。
- 删除区间映射后，字幕 cue 默认只做时间重映射，不整体平移。
- Agent 校对默认只改文字，不重算时间轴；拆分/合并 cue 必须显式记录。

## 字幕校对

- Agent 字幕校对发生在人工审核和重剪之后。
- 校对输入是 `review/proofread_agent_input.md` / `review/proofread_agent_input.json`。
- 默认只改字幕文字，不整体平移时间轴，避免“字幕滞后”。
- 不再用 Python 写死专名替换词表；专名、同音词、断句和口水词由主 Agent 根据上下文校正。

## 约束

1. 不在这里改正文事实。
2. 不把粗剪当终剪；必须让用户审核。
3. 专名修正交给 Agent 校对字幕，不用硬编码词表替换。
4. 如果 FunASR 缺失，先安装 `requirements-media.txt`，不要静默退回低质量转写。
