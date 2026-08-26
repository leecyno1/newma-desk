#!/usr/bin/env python3
"""omni 提示词组转换器（P0-4：omni 包内的适配层）。

将导演侧的分镜意图/剧本转换为 omni 批量输入（newma.omni.batch.v1）。
适配 omni 引擎特性：
- 分段规则（默认 ceil(total/10s)，但段数与时长由剧本/模板决定——本脚本只把输入规整成 batch，不强加 60s/18 镜）
- 组提示词模板（Vox 英文组提示词：帧序列+每镜运动+转场+风格锁定）
- 角色 DNA 注入（可选 --account：从 dna/account_dna.yaml 拉角色系统到 prompt 风格描述）

用法：
    python skills/dasheng-omni-video-bridge/build_omni_prompts.py \
        --storyboard-dir <分镜目录（含 sb*.png）> \
        --script <剧本.json（shots: [{shot_id, seconds, motion, note}]）> \
        --account slot-1 \
        --out <batch.json>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

STYLE_SYS = {
    "slot-1": "solid black silhouette characters with costume-outline detail, Mercury-myth aesthetic props, warm yellow + black palette",
    "slot-2": "solid black silhouette characters with costume-outline detail, lab-research props, warm yellow + black palette",
    "slot-3": "solid black silhouette characters with costume-outline detail (cow & horse duo), cheap hand-drawn aesthetic, warm yellow + black palette",
}

SEG_TMPL = (
    "Create one {seconds}-second strictly {aspect} mixed-media animation B-roll. "
    "Style: {style}. No text, no captions, no watermarks. "
    "Use the {n} provided storyboard images as sequential keyframes, {per_shot} seconds each, "
    "with quick color-block wipes between shots: {frames} "
    "Even {per_shot}-second beats."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build omni batch prompts from storyboard + script")
    parser.add_argument("--storyboard-dir", required=True)
    parser.add_argument("--script", help="剧本 json（含 shots 列表与总时长；缺省时按目录内分镜平均切分）")
    parser.add_argument("--account", choices=["slot-1", "slot-2", "slot-3"], help="账号 slot（注入角色 DNA 风格）")
    parser.add_argument("--aspect", default="9:16", help="画幅（默认 9:16；模板可覆盖）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    sb_dir = Path(args.storyboard_dir).expanduser().resolve()
    images = sorted(p for p in sb_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if not images:
        print("no storyboard images found")
        return 1

    shots = []
    total_seconds = None
    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        shots = script.get("shots", [])
        total_seconds = script.get("total_seconds")

    # 切分：有剧本按剧本 shots 聚合到 10s 段；无剧本每 5 镜一段（每镜 2s）
    segments = []
    if shots:
        cur, cur_imgs, cur_seconds, cur_shots = None, [], 0.0, []
        for shot in shots:
            sec = float(shot.get("seconds", 2))
            img = shot.get("image") or (images[len(cur_imgs)] if len(cur_imgs) < len(images) else None)
            if cur_seconds + sec > 10.0 and cur_imgs:
                segments.append((cur_imgs, cur_seconds, cur_shots))
                cur_imgs, cur_seconds, cur_shots = [], 0.0, []
            if img:
                cur_imgs.append(str(Path(img)))
            cur_seconds += sec
            cur_shots.append(shot)
        if cur_imgs:
            segments.append((cur_imgs, cur_seconds, cur_shots))
    else:
        per = 5
        for i in range(0, len(images), per):
            chunk = images[i : i + per]
            segments.append(([str(p) for p in chunk], 2.0 * len(chunk), []))

    style = STYLE_SYS.get(args.account, STYLE_SYS["slot-1"])
    batch = {
        "schema_version": "newma.omni.batch.v1",
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "account": args.account,
        "aspect": args.aspect,
        "segments": [],
        "concat": True,
    }
    for idx, (imgs, seconds, shot_list) in enumerate(segments, start=1):
        n = len(imgs)
        per = round(seconds / n, 1) if n else 2.0
        frames = " ".join(
            f"Frame {j + 1} ({j * per:.0f}-{(j + 1) * per:.0f}s): {shot_list[j].get('motion', 'follow the storyboard image motion') if j < len(shot_list) else 'follow the storyboard image motion'}"
            for j in range(n)
        )
        prompt = SEG_TMPL.format(seconds=int(seconds), aspect=args.aspect, style=style, n=n, per_shot=per, frames=frames)
        batch["segments"].append({
            "segment_id": f"seg-{idx}",
            "seconds": int(seconds),
            "prompt": prompt,
            "keyframes": imgs,
        })

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"batch.json → {out}（{len(batch['segments'])} 段，{len(images)} 张分镜）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
