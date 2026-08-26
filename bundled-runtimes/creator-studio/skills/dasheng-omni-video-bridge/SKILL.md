---
name: dasheng-omni-video-bridge
description: Use when Newma video production needs image-to-video synthesis via the omni engine (Gemini image-to-video), in parallel with html-anything / remotion / html-video engines. omni converts storyboard image sequences + segment prompts into 10s-capped video segments that directors call as source elements; this bridge packages the full driver (prompt adapter + batch executor + download/concat) as a plugin — storyboard-to-prompt conversion lives INSIDE this package (adapter is omni-specific), never hardcodes duration/shot-count (template/content decides).
---

# Newma Omni Video Bridge

## Role

`omni`（Gemini 图生视频引擎）与 html-anything / remotion / html-video **平行**，是 Newma 视频生产的素材生成引擎之一：输入分镜图序列 + 分段提示词 → 输出 10 秒上限的视频段，供导演（director）在时间线上调用。

**关键定位**：
- **生成素材/元素**，不做最终剪辑——剪辑/拼接在 manual_edit / render_qc 节点完成
- **提示词组转换器内置本包**（`build_omni_prompts.py`）：分镜意图 → omni 组提示词——适配 omni 的引擎特性，是 omni 的一部分，不是独立通用脚本
- **不硬编码时长/分镜数**：段划分默认规则 `ceil(total_seconds / 10)` 仅是建议；实际段数/时长由剧本与模板决定（参数化输入）

## Package Layout

```
skills/dasheng-omni-video-bridge/
├── SKILL.md                  # 本文件
├── config.json               # 引擎配置（会话 URL/账号/下载目录/默认参数）
├── build_omni_prompts.py     # P0-4 转换器：分镜意图 → omni 提示词组（omni 适配层）
└── run_omni_batch.py         # 批处理驱动器：目录+提示词 → 浏览器执行 → 下载 → 可选拼接
```

## Config

`config.json` 字段：

```yaml
engine: omni
provider: gemini_web           # Gemini 图生视频（浏览器会话）
session_url: https://gemini.google.com/u/1/app   # 新会话入口（干净会话避免「视频」模式干扰）
max_segment_seconds: 10        # omni 单次上限（硬约束）
download_dir: ~/Downloads      # Gemini 下载落点
default_aspect: "9:16"         # 缺省竖屏（模板可覆盖——引擎不限定画幅）
state_cleanup: new_session_each_run   # 每次新开干净会话
```

## Batch Input Contract（run_omni_batch.py 输入）

```json
{
  "schema_version": "newma.omni.batch.v1",
  "run_id": "...",
  "segments": [
    {
      "segment_id": "seg-1",
      "seconds": 10,
      "prompt": "Create one 10-second ... (English group prompt)",
      "keyframes": ["sb1.png", "sb2.png", "sb3.png"]
    }
  ],
  "concat": true,
  "output": "final.mp4"
}
```

段数/每段秒数/每段分镜数全部来自输入（剧本/模板决定），引擎只执行。

## Usage

```bash
# 1) 剧本/分镜 → omni 提示词组（P0-4 适配层）
python skills/dasheng-omni-video-bridge/build_omni_prompts.py \
  --storyboard-dir <分镜目录> --script <剧本.json> --out <batch.json>

# 2) 批量执行（浏览器驱动）
python skills/dasheng-omni-video-bridge/run_omni_batch.py \
  --batch <batch.json> --download-dir ~/Downloads [--concat]
```

## Hard Rules

- 每次执行新开干净会话（Gemini「视频」按钮选中态会拦截粘贴——务必 new_session）
- 图片走剪贴板粘贴（AppKit 写剪贴板 + Cmd+V），不走 + 号菜单
- 下载依赖浏览器侧人工或轮询监听 download_dir 新文件
- 引擎不关心内容语义——时长/风格/分镜数由导演与模板决定
