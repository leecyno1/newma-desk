# Provider 路由

只使用官方模型入口，不接第三方聚合服务。

| 顺序 | Provider | 使用条件 | 失败后的动作 |
|---|---|---|---|
| 0 | `remotion_local_motion` | 已绑定 Shotcraft，或镜头承载真实网页、精确图表和程序化动效 | 退回镜头实现，不得静默改为生成式证据 |
| 1 | `gemini_api_omni` | `GEMINI_API_KEY`/`GOOGLE_API_KEY` 可用，且当前 SDK 支持 Omni 视频模型 | 记录错误，转 Veo API |
| 2 | `gemini_api_veo` | 官方 Google Gen AI SDK 可用 | 同镜改走浏览器 Omni |
| 3 | `gemini_browser_omni` | Chrome 已登录 Gemini | 同镜切 `motion_mode: in_place` 重试一次 |
| 4 | `remotion_local_motion` | 生成式镜头连续失败，但仍可用本地局部动效表达 | 标记 `fallback_ready` |

`minimax_mmx` 与 `seedance` 只在用户明确允许时加入单镜 `provider_order`，不得静默替换整片。

## 路由规则

1. 先判断生产路线。带 `motion.shotcraft_card` 的镜头先运行 `shotcraft_adapter.py bind`，Manifest 会将其锁定为 `ready_for_remotion`。
2. 再运行 `scripts/vox_manifest.py build`，生成式和程序化镜头共用同一个 Manifest。
3. `ready_for_remotion` 镜头跳过参考图和 Gemini；已是 `approved` 或 `fallback_ready` 的镜头不得重做。
4. 每次生成模型调用前写入 `started` 尝试；成功、失败或人工拒绝后写回结果。
5. API 生成使用 `scripts/gemini_video_api.py`：模型名包含 `omni` 时走官方 Interactions API；其余 Google 视频模型走 `models.generate_videos`。同时提供首尾帧时，Omni 按图片顺序引用，Veo 使用 `last_frame`。模型 ID 可配置，不在 Skill 内假定未公开模型一定可用。官方 Veo 单次原生时长按接口允许值（当前 4–8 秒）提交；需要约 10 秒镜头时，在 Remotion 中对齐旁白，必要时延长稳定尾帧。
6. 浏览器生成调用 `dasheng-video-omni-browser`，只使用已有登录态，不读取 Cookie、密码或本地存储。
7. Gemini 镜头默认 `assemble`；若物件拆解、漂移、变形或卡死，改为 `in_place`，保持参考图全部物件从首帧存在，只做局部动作。

## Manifest 操作

```bash
python scripts/vox_manifest.py build --shots director/scene_plan.production.json --output-dir vox_run
python scripts/vox_manifest.py record-attempt --manifest vox_run/vox_manifest.json --shot shot-01 --provider gemini_api_veo --status started
python scripts/vox_manifest.py record-attempt --manifest vox_run/vox_manifest.json --shot shot-01 --provider gemini_api_veo --status succeeded --output vox_run/clips/shot-01.mp4
python scripts/vox_manifest.py set-status --manifest vox_run/vox_manifest.json --shot shot-01 --status approved
```
