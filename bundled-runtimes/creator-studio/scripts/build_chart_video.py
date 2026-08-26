#!/usr/bin/env python3
"""chart_data.json → matplotlib 动画视频段（不依赖 Chrome，更稳）。

用法：
    python scripts/build_chart_video.py --chart-data <chart_data.json> --chart-id <id> --out <segment.mp4> [--seconds 6] [--fps 12]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def build_bar_video(chart, out, seconds, fps):
    vals = chart["y_axis"]["values"]
    xs = [str(x) for x in chart["x_axis"]["values"]]
    labels = chart.get("data_labels") or [f"{v:g}" for v in vals]
    vmax = max(abs(v) for v in vals) or 1
    has_neg = any(v < 0 for v in vals)
    fig, ax = plt.subplots(figsize=(9, 16), dpi=120)
    fig.patch.set_facecolor("#FFD93B")
    ax.set_facecolor("#FFD93B")
    ax.set_title(chart["title"], fontsize=26, fontweight="bold", color="#1a1a1a", pad=30)
    ax.text(0.5, 1.005, chart.get("subtitle", ""), transform=ax.transAxes, ha="center", fontsize=14, color="#555")
    n = len(vals)
    total_frames = int(seconds * fps)
    hold_frames = int(1.5 * fps)
    grow_frames = total_frames - hold_frames

    def animate(f):
        ax.clear()
        ax.set_facecolor("#FFD93B")
        ax.set_title(chart["title"], fontsize=26, fontweight="bold", color="#1a1a1a", pad=30)
        ax.text(0.5, 1.005, chart.get("subtitle", ""), transform=ax.transAxes, ha="center", fontsize=14, color="#555")
        for s in ["top", "right", "left"]:
            ax.spines[s].set_visible(False)
        ax.set_yticks([])
        ax.set_xticks(range(n))
        ax.set_xticklabels(xs, fontsize=16)
        if has_neg:
            ax.axhline(0, color="#333", lw=1.5)
            ax.set_ylim(-vmax * 1.15, vmax * 1.15)
        else:
            ax.set_ylim(0, vmax * 1.15)
        # 每根柱的进度：grow_frames 内依次完成
        per_bar = grow_frames / n
        for i, (v, lab) in enumerate(zip(vals, labels)):
            prog = min(max((f - i * per_bar) / per_bar, 0), 1)
            cur = v * prog
            color = "#C0392B" if v < 0 else "#1a1a1a"
            ax.bar(i, cur, color=color, width=0.55)
            if prog >= 1:
                offset = 0.04 * vmax if v >= 0 else -0.08 * vmax
                ax.text(i, v + offset, lab, ha="center", fontsize=18, fontweight="bold", color=color)
        # 标注（最后一帧后）
        annos = chart.get("annotations") or []
        if annos and f >= total_frames - hold_frames:
            ax.text(0.5, -0.08 if has_neg else -0.1, annos[-1]["label"], transform=ax.transAxes,
                    ha="center", fontsize=15, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="#C0392B" if annos[-1].get("emphasis") else "#1a1a1a"))
        ax.text(0.5, -0.14 if has_neg else -0.16, f"数据来源：{chart.get('source', '')}", transform=ax.transAxes,
                ha="center", fontsize=11, color="#777")
        return []

    anim = FuncAnimation(fig, animate, frames=total_frames, interval=1000 / fps)
    writer = FFMpegWriter(fps=fps, metadata={"title": chart["title"]}, bitrate=2400)
    anim.save(out, writer=writer)
    plt.close(fig)


def build_line_video(chart, out, seconds, fps):
    vals = chart["y_axis"]["values"]
    xs = [str(x) for x in chart["x_axis"]["values"]]
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1
    fig, ax = plt.subplots(figsize=(9, 16), dpi=120)
    fig.patch.set_facecolor("#FFD93B")
    total_frames = int(seconds * fps)
    hold_frames = int(1.5 * fps)
    draw_frames = total_frames - hold_frames

    def animate(f):
        ax.clear()
        ax.set_facecolor("#FFD93B")
        ax.set_title(chart["title"], fontsize=26, fontweight="bold", color="#1a1a1a", pad=30)
        ax.text(0.5, 1.005, chart.get("subtitle", ""), transform=ax.transAxes, ha="center", fontsize=14, color="#555")
        for s in ["top", "right", "left"]:
            ax.spines[s].set_visible(False)
        ax.set_yticks([])
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(xs, fontsize=15)
        ax.set_ylim(vmin - rng * 0.15, vmax + rng * 0.15)
        prog = min(f / draw_frames, 1)
        k = int(prog * len(vals))
        frac = prog * len(vals) - k
        x_pts = list(range(k))
        y_pts = vals[:k]
        if k < len(vals):
            x_pts.append(k - 1 + frac if k > 0 else 0)
            y_pts.append(vals[k - 1] + (vals[k] - vals[k - 1]) * frac if k > 0 else vals[0])
        ax.plot(x_pts, y_pts, color="#1a1a1a", lw=4, marker="o", ms=9, markerfacecolor="#1a1a1a")
        for i in range(k):
            ax.text(i, vals[i] + rng * 0.06, f"{vals[i]:g}", ha="center", fontsize=15, fontweight="bold",
                    color="#C0392B" if i == len(vals) - 1 else "#1a1a1a")
        annos = chart.get("annotations") or []
        if annos and f >= total_frames - hold_frames:
            ax.text(0.5, -0.12, annos[-1]["label"], transform=ax.transAxes, ha="center", fontsize=14, fontweight="bold",
                    color="white", bbox=dict(boxstyle="round,pad=0.5", facecolor="#C0392B" if annos[-1].get("emphasis") else "#1a1a1a"))
        ax.text(0.5, -0.17, f"数据来源：{chart.get('source', '')}", transform=ax.transAxes, ha="center", fontsize=11, color="#777")
        return []

    anim = FuncAnimation(fig, animate, frames=total_frames, interval=1000 / fps)
    writer = FFMpegWriter(fps=fps, metadata={"title": chart["title"]}, bitrate=2400)
    anim.save(out, writer=writer)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build matplotlib animated chart video from chart_data.json")
    parser.add_argument("--chart-data", required=True)
    parser.add_argument("--chart-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()

    doc = json.loads(Path(args.chart_data).read_text(encoding="utf-8"))
    chart = next((c for c in doc.get("charts", []) if c["chart_id"] == args.chart_id), None)
    if not chart:
        print(f"chart_id {args.chart_id} not found")
        return 1
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if chart.get("chart_type") == "line":
        build_line_video(chart, str(out), args.seconds, args.fps)
    else:
        build_bar_video(chart, str(out), args.seconds, args.fps)
    print(f"视频段 → {out}（{args.seconds}s × {args.fps}fps）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
