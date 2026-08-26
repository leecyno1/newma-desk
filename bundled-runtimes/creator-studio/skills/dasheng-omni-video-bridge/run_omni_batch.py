#!/usr/bin/env python3
"""omni 批处理驱动器：batch.json → 浏览器执行 → 下载监听 → 可选 FFmpeg 拼接。

固化已验证的手工流程：
  1. AppleScript 新开干净 Gemini 会话（config.session_url）
  2. 点击输入框 → 循环剪贴板贴分镜图（AppKit 写剪贴板 + Cmd+V）
  3. 贴段提示词 → Enter 发送
  4. 轮询监听 download_dir 新 mp4（或等待手动下载）
  5. concat=true 时 FFmpeg 拼接

用法：
    python skills/dasheng-omni-video-bridge/run_omni_batch.py \
        --batch <batch.json> [--download-dir ~/Downloads] [--concat] [--wait-each 300]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent
CONFIG = json.loads((PKG / "config.json").read_text(encoding="utf-8"))

CLIPBOARD_WRITE = '''import sys
import AppKit
data = AppKit.NSData.dataWithContentsOfFile_(sys.argv[1])
pb = AppKit.NSPasteboard.generalPasteboard()
pb.clearContents()
pb.setData_forType_(data, AppKit.NSPasteboardTypePNG)'''

CLICK_PASTE = '''tell application "System Events"
\ttell process "Google Chrome"
\t\tclick at {%s}
\t\tdelay 0.4
\t\tkeystroke "v" using command down
\tend tell
end tell'''


def run_osascript(script: str) -> None:
    subprocess.run(["osascript", "-e", script], check=True)


SYSTEM_PY = "/opt/homebrew/bin/python3" if Path("/opt/homebrew/bin/python3").exists() else "python3"


def clipboard_image(path: str) -> None:
    """写图片到剪贴板（需系统 Python 的 AppKit，.venv 无 pyobjc）。"""
    subprocess.run([SYSTEM_PY, "-c", CLIPBOARD_WRITE, path], check=True)


def clipboard_text(path: str) -> None:
    with open(path, "rb") as fh:
        subprocess.run(["pbcopy"], stdin=fh, check=True)


def new_session() -> None:
    """新开干净会话（Chrome 无窗口时先建窗口）。"""
    run_osascript(f'''tell application "Google Chrome"
\tactivate
\tif (count of windows) is 0 then make new window
\ttell front window
\t\tmake new tab with properties {{URL:"{CONFIG['session_url']}"}}
\tend tell
end tell''')
    time.sleep(8)


def list_mp4s(directory: Path, since: float) -> list[Path]:
    return sorted(
        (p for p in directory.glob("*.mp4") if p.stat().st_mtime >= since),
        key=lambda p: p.stat().st_mtime,
    )


AUTO_DOWNLOAD = '''
import Quartz
import subprocess
import time
import statistics
from collections import defaultdict
from PIL import Image

# hover 视频区触发按钮
# 动态查 Chrome 主窗口 CGWindowID
win_id = None
wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID)
for win in wins:
    if win.get("kCGWindowOwnerName") == "Google Chrome" and win.get("kCGWindowLayer") == 0 and win.get("kCGWindowBounds", {}).get("Height", 0) > 400:
        win_id = win.get("kCGWindowNumber")
        break
move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (2094, 3400), 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
time.sleep(1.2)
# 全屏截图 + 按 Chrome 窗口 bounds 裁剪（规避遮挡窗口截图失败）
subprocess.run(["screencapture", "-x", "/tmp/omni_full.png"], check=True)
full = Image.open("/tmp/omni_full.png")
if win_id:
    b = None
    for win in wins:
        if win.get("kCGWindowNumber") == win_id:
            b = win.get("kCGWindowBounds", {})
            break
    if b:
        x, y, w_, h_ = int(b.get("X", 0)), int(b.get("Y", 0)), int(b.get("Width", 0)), int(b.get("Height", 0))
        scale = full.size[0] / max(1, full.size[0])
        crop = full.crop((int(x*2), int(y*2), int((x+w_)*2), int((y+h_)*2)))
        crop.save("/tmp/omni_hover.png")
    else:
        full.save("/tmp/omni_hover.png")
else:
    full.save("/tmp/omni_hover.png")
time.sleep(0.3)

# 像素定位三按钮（最左=Download）
img = Image.open("/tmp/omni_hover.png")
w, h = img.size
pixels = defaultdict(list)
for y in range(int(h*0.25), int(h*0.75), 2):
    for x in range(int(w*0.5), int(w*0.95), 2):
        r, g, b = img.getpixel((x, y))[:3]
        if r > 195 and g > 195 and b > 195:
            pixels[x].append(y)
xs = sorted(pixels)
groups, cur = [], []
for x in xs:
    if cur and x - cur[-1] > 25:
        groups.append(cur)
        cur = []
    cur.append(x)
if cur:
    groups.append(cur)
btns = [g for g in groups if len(g) >= 5]
target = None
for g in btns[:5]:
    cx = statistics.mean(g)
    all_ys = [y for x in g for y in pixels.get(x, [])]
    cy = statistics.mean(all_ys) if all_ys else 0
    n = len(all_ys)
    if target is None and 10 < n < 400:
        target = (1230 + cx / 2, 3001 + cy / 2)
if target:
    gx, gy = int(target[0]), int(target[1])
    m = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (gx, gy), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, m)
    time.sleep(0.5)
    c = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (gx, gy), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, c)
    time.sleep(0.08)
    u = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (gx, gy), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, u)
'''


def wait_new_file(directory: Path, before: set[Path], timeout: int) -> Path | None:
    """等待生成完成 → 自动点击下载 → 监听新文件。"""
    # 先等生成（约 150s 后检测 ready）
    time.sleep(150)
    deadline = time.time() + timeout
    downloaded = False
    while time.time() < deadline:
        new = [p for p in directory.glob("*.mp4") if p not in before]
        if new:
            return max(new, key=lambda p: p.stat().st_mtime)
        if not downloaded:
            # 尝试自动下载（hover+像素定位+点击）
            try:
                subprocess.run([SYSTEM_PY, "-c", AUTO_DOWNLOAD], timeout=20)
                downloaded = True
            except Exception:
                pass
        time.sleep(6)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run omni batch generation via browser")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--download-dir", default=CONFIG["download_dir"])
    parser.add_argument("--wait-each", type=int, default=CONFIG["generation_wait_seconds"])
    parser.add_argument("--concat", action="store_true")
    parser.add_argument("--output", help="拼接输出路径（--concat 时必需）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    segments = batch.get("segments", [])
    if not segments:
        print("no segments")
        return 1
    dl = Path(os.path.expanduser(args.download_dir)).resolve()
    dl.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"dry-run：{len(segments)} 段，下载目录 {dl}")
        for s in segments:
            print(f"  [{s['segment_id']}] {s['seconds']}s × {len(s['keyframes'])} 图")
        return 0

    click_xy = "2094, 3780"
    produced: list[Path] = []
    for seg in segments:
        sid = seg["segment_id"]
        print(f"[{sid}] 开始（{seg['seconds']}s × {len(seg['keyframes'])} 图）")
        new_session()
        run_osascript(CLICK_PASTE % click_xy)
        before = set(dl.glob("*.mp4"))
        for img in seg["keyframes"]:
            clipboard_image(img)
            run_osascript('''tell application "System Events"
\ttell process "Google Chrome"
\t\tkeystroke "v" using command down
\tend tell
end tell''')
            time.sleep(CONFIG["paste_interval_seconds"])
        prompt_file = Path(args.batch).parent / f"_prompt_{sid}.txt"
        prompt_file.write_text(seg["prompt"], encoding="utf-8")
        clipboard_text(str(prompt_file))
        run_osascript('''tell application "System Events"
\ttell process "Google Chrome"
\t\tdelay 0.5
\t\tkeystroke "v" using command down
\t\tdelay 1.0
\t\tkey code 36
\tend tell
end tell''')
        print(f"[{sid}] 已发送，等待下载（{args.wait_each}s）")
        got = wait_new_file(dl, before, args.wait_each)
        if got:
            produced.append(got)
            print(f"[{sid}] 下载完成: {got.name}")
        else:
            print(f"[{sid}] 超时未下载（可稍后手动下载，继续下一段）")

    if args.concat and produced:
        output = Path(args.output).expanduser().resolve() if args.output else dl / "omni_batch_final.mp4"
        inputs = []
        for p in produced:
            inputs += ["-i", str(p)]
        subprocess.run(
            ["ffmpeg", "-y", *inputs, "-filter_complex", f"concat=n={len(produced)}:v=1:a=0[v]", "-map", "[v]", "-r", "30", str(output)],
            check=True,
        )
        print(f"拼接完成 → {output}（{len(produced)} 段）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
