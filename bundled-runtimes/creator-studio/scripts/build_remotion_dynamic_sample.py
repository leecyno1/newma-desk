#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML_VIDEO_ROOT = Path(
    os.environ.get("HTML_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-video"))
).expanduser()


CHAT_SCRIPTS = [
    "我先说结论，楼市真不是只看政策。政策能开闸，但水从哪来？水其实在居民的钱包里。过去二十年，A股几次大牛之后，楼市基本都会晚半拍跟上。",
    "你看这张表就很直观。2005、2008、2014、2019，股市先涨，楼市后动。不是每天同步，但财富效应会慢慢传过去。",
    "为什么我一直盯着百分之五十？因为资产跌三成以后，要涨回五成，人才会觉得自己终于没那么亏了。这不是玄学，是心理账户。",
    "现在最大的问题是，居民资产负债表这个坑太深。房产从高点下来以后，账面资产缩水，大家第一反应不是买房，而是先保命、先还债。",
    "工资能不能把这个坑填回来？太慢了。原文估算，光靠工资和储蓄要十多年。所以只靠降息和放开限购，力度是不够的。",
    "那什么东西填坑最快？股市。权益资产如果涨一轮，居民会突然觉得，诶，我手里又有余粮了。看房的人变多，往往就是这么来的。",
    "所以我看楼市，只看三个按钮：信贷、财富、政策。信贷决定你有没有能力买，财富决定你想不想买，政策决定让不让你买。",
    "一句话，财富是种子，信贷是放大器，政策是闸门。闸门可以打开，但如果水库没水，开再大也没用。",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def number_value(text: str, fallback: float) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return fallback
    try:
        value = float(match.group(0))
    except ValueError:
        value = fallback
    if "-" in str(text):
        return -abs(value)
    return value


def asset_lookup(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(asset.get("id")): asset for asset in inventory.get("assets", []) if asset.get("id")}


def metrics_from_table(table: list[list[str]], limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(table[1 : limit + 1], 1):
        if not row:
            continue
        display = ""
        for cell in row[1:]:
            if re.search(r"\d|%|万|亿", str(cell)):
                display = str(cell)
                break
        if not display and len(row) > 1:
            display = str(row[1])
        out.append(
            {
                "label": str(row[0])[:12],
                "display": display[:18],
                "value": number_value(display, idx * 10.0),
            }
        )
    return out


def build_sample_data(storyboard: dict[str, Any], inventory: dict[str, Any], *, scene_count: int, fps: int) -> dict[str, Any]:
    assets = asset_lookup(inventory)
    scenes = []
    for idx, scene in enumerate(storyboard.get("scenes", [])[:scene_count], 0):
        refs = [ref for ref in scene.get("evidence_refs", []) if ref in assets]
        table_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "table"]
        image_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "image"]
        table = table_assets[0].get("rows") if table_assets else []
        scenes.append(
            {
                "id": scene.get("scene_id") or f"scene_{idx + 1:03d}",
                "index": idx + 1,
                "title": scene.get("title"),
                "subtitle": scene.get("core_meaning_lock"),
                "voiceover": CHAT_SCRIPTS[idx] if idx < len(CHAT_SCRIPTS) else scene.get("voiceover_text"),
                "kind": scene_kind(scene.get("content_part"), idx),
                "template": scene.get("template_id"),
                "evidenceRefs": refs,
                "metrics": metrics_from_table(table),
                "table": table[:6] if table else [],
                "image": {
                    "src": image_assets[0].get("local_copy") if image_assets else "",
                    "alt": image_assets[0].get("alt") if image_assets else "",
                },
                "durationSec": 8.0,
            }
        )
    return {
        "schemaVersion": "dasheng.remotion.dynamic_sample.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "地产周期论：先看钱包，再看政策",
        "subtitle": "横版动态样片 · Remotion frame-driven animation",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": sum(float(scene["durationSec"]) for scene in scenes),
        "style": {
            "palette": ["#08111f", "#10243a", "#d6a84f", "#f4efe4", "#a93b2f"],
            "tone": "投资人聊天，少播音腔，多判断和解释",
        },
        "scenes": scenes,
    }


def scene_kind(content_part: str | None, index: int) -> str:
    if index == 0:
        return "hook"
    if content_part in {"financial_chart", "data_table", "data_chart"}:
        return "data"
    if content_part in {"logic_chain", "overall_outline"}:
        return "logic"
    return "data"


def build_package_json() -> str:
    return """{
  "name": "dasheng-remotion-v2-dynamic-sample",
  "private": true,
  "type": "commonjs",
  "scripts": {
    "render": "node render.cjs"
  }
}
"""


def build_index_tsx() -> str:
    return """import {registerRoot} from 'remotion';
import {RemotionRoot} from './Root';

registerRoot(RemotionRoot);
"""


def build_root_tsx() -> str:
    return """import {Composition} from 'remotion';
import {DynamicSample} from './Video';

const data = require('../data/video_data.json');

export const RemotionRoot = () => {
  return (
    <Composition
      id="DynamicSample"
      component={DynamicSample}
      durationInFrames={Math.ceil(data.durationSec * data.fps)}
      fps={data.fps}
      width={data.width}
      height={data.height}
      defaultProps={data}
    />
  );
};
"""


def build_video_tsx() -> str:
    return r"""import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type Metric = {label: string; display: string; value: number};
type Scene = {
  id: string;
  index: number;
  title: string;
  subtitle: string;
  voiceover: string;
  kind: 'hook' | 'data' | 'logic';
  template: string;
  metrics: Metric[];
  table: string[][];
  durationSec: number;
};
type Props = {
  title: string;
  subtitle: string;
  scenes: Scene[];
  fps: number;
};

const C = {
  bg: '#08111f',
  panel: '#10243a',
  gold: '#d6a84f',
  paper: '#f4efe4',
  ink: '#101820',
  red: '#a93b2f',
  mint: '#7bd3a6',
  muted: '#9aa9bb',
};

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);

const clamp = (value: number, input: [number, number], output: [number, number]) =>
  interpolate(value, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: easeOut,
  });

const splitSubtitle = (text: string) => {
  const raw = text.replace(/\s+/g, '');
  const chunks: string[] = [];
  for (let i = 0; i < raw.length; i += 22) {
    chunks.push(raw.slice(i, i + 22));
  }
  return chunks.slice(0, 3);
};

export const DynamicSample: React.FC<Props> = ({scenes, title, subtitle}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{backgroundColor: C.bg, color: C.paper, fontFamily: '"PingFang SC", "Noto Sans SC", sans-serif'}}>
      <Background />
      {scenes.map((scene) => {
        const duration = Math.round(scene.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={scene.id} from={from} durationInFrames={duration} premountFor={fps}>
            <SceneFrame scene={scene} totalTitle={title} totalSubtitle={subtitle} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 70) * 22;
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at ${24 + drift / 8}% 18%, rgba(214,168,79,.18), transparent 26%), radial-gradient(circle at 82% 66%, rgba(52,116,170,.18), transparent 28%), linear-gradient(135deg, #050b14, #08111f 55%, #0e1726)`}} />
      <div style={{position: 'absolute', inset: 0, opacity: 0.12, backgroundImage: 'linear-gradient(rgba(255,255,255,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px)', backgroundSize: '48px 48px', transform: `translate(${drift}px, 0)`}} />
    </AbsoluteFill>
  );
};

const SceneFrame: React.FC<{scene: Scene; totalTitle: string; totalSubtitle: string}> = ({scene, totalTitle, totalSubtitle}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = clamp(frame, [0, fps * 0.8], [0, 1]);
  const exit = clamp(frame, [scene.durationSec * fps - fps * 0.7, scene.durationSec * fps], [0, 1]);
  const y = (1 - enter) * 26 - exit * 18;
  const opacity = enter * (1 - exit * 0.65);
  return (
    <AbsoluteFill style={{padding: 64, opacity, transform: `translateY(${y}px)`}}>
      <TopBar scene={scene} />
      {scene.kind === 'hook' ? <HookScene scene={scene} totalTitle={totalTitle} totalSubtitle={totalSubtitle} /> : null}
      {scene.kind === 'data' ? <DataScene scene={scene} /> : null}
      {scene.kind === 'logic' ? <LogicScene scene={scene} /> : null}
      <Subtitle scene={scene} />
    </AbsoluteFill>
  );
};

const TopBar: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const tickerX = -((frame * 2) % 560);
  return (
    <>
      <div style={{position: 'absolute', top: 34, left: 64, right: 64, height: 1, background: 'linear-gradient(90deg, transparent, rgba(214,168,79,.85), transparent)'}} />
      <div style={{position: 'absolute', top: 44, left: 64, right: 64, display: 'flex', justifyContent: 'space-between', color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 18, letterSpacing: '0.14em'}}>
        <span>DASHENG · DYNAMIC SAMPLE · 16:9</span>
        <span>{String(scene.index).padStart(2, '0')} / 08 · {scene.template}</span>
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 32, overflow: 'hidden', color: 'rgba(244,239,228,.34)', fontFamily: 'Menlo, monospace', fontSize: 15}}>
        <div style={{whiteSpace: 'nowrap', transform: `translateX(${tickerX}px)`}}>
          REAL DATA · WEALTH EFFECT · CREDIT · POLICY · HOUSING CYCLE · REAL DATA · WEALTH EFFECT · CREDIT · POLICY · HOUSING CYCLE ·
        </div>
      </div>
    </>
  );
};

const HookScene: React.FC<{scene: Scene; totalTitle: string; totalSubtitle: string}> = ({scene, totalTitle, totalSubtitle}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const title = clamp(frame, [0, fps * 0.9], [0, 1]);
  const pulse = 1 + Math.sin(frame / 9) * 0.035;
  const threshold = clamp(frame, [fps * 1.4, fps * 3.6], [0, 1]);
  return (
    <>
      <div style={{position: 'absolute', left: 92, top: 170, width: 1020}}>
        <div style={{color: C.gold, fontSize: 26, letterSpacing: '0.18em', marginBottom: 22}}>地产周期论 · 投资人聊天版</div>
        <div style={{fontSize: 88, lineHeight: 1.02, fontWeight: 900, letterSpacing: '-0.055em', transform: `translateX(${(1 - title) * -60}px)`, opacity: title}}>
          {totalTitle}
        </div>
        <div style={{fontSize: 34, color: C.muted, marginTop: 26, opacity: title}}>{totalSubtitle}</div>
      </div>
      <div style={{position: 'absolute', right: 112, top: 205, width: 520, height: 520, borderRadius: 34, background: 'rgba(16,36,58,.82)', border: `1px solid rgba(214,168,79,.35)`, padding: 42, transform: `scale(${pulse})`}}>
        <div style={{fontFamily: 'Menlo, monospace', color: C.gold, fontSize: 20}}>KEY THRESHOLD</div>
        <div style={{fontSize: 142, fontWeight: 900, color: C.paper, marginTop: 60, transform: `scale(${0.85 + threshold * 0.15})`}}>50%</div>
        <div style={{height: 14, background: 'rgba(255,255,255,.12)', borderRadius: 999, overflow: 'hidden', marginTop: 44}}>
          <div style={{height: '100%', width: `${threshold * 100}%`, background: `linear-gradient(90deg, ${C.red}, ${C.gold})`}} />
        </div>
        <div style={{fontSize: 27, color: C.muted, marginTop: 34}}>股市财富效应跨过行为阈值</div>
      </div>
      <VoiceCard text={scene.voiceover} />
    </>
  );
};

const DataScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const titleP = clamp(frame, [0, fps * 0.65], [0, 1]);
  const metrics = scene.metrics.length ? scene.metrics : fallbackMetrics(scene);
  return (
    <>
      <div style={{position: 'absolute', left: 86, top: 128, width: 740}}>
        <div style={{color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 18, letterSpacing: '0.14em'}}>DATA EVIDENCE · ARTICLE TABLE</div>
        <div style={{fontSize: 54, fontWeight: 850, lineHeight: 1.08, marginTop: 18, transform: `translateY(${(1 - titleP) * 22}px)`, opacity: titleP}}>{scene.title}</div>
        <div style={{fontSize: 24, color: C.muted, lineHeight: 1.45, marginTop: 16, maxWidth: 660}}>{scene.subtitle}</div>
      </div>
      <BarChart metrics={metrics} />
      <DataTable rows={scene.table} />
      <VoiceCard text={scene.voiceover} />
    </>
  );
};

const BarChart: React.FC<{metrics: Metric[]}> = ({metrics}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const max = Math.max(...metrics.map((m) => Math.abs(m.value)), 1);
  return (
    <svg style={{position: 'absolute', left: 92, top: 355, width: 980, height: 490}} viewBox="0 0 980 490">
      {[0, 1, 2, 3].map((i) => (
        <line key={i} x1={210 + i * 180} x2={210 + i * 180} y1={24} y2={430} stroke="rgba(244,239,228,.12)" />
      ))}
      {metrics.map((m, i) => {
        const p = spring({frame: frame - i * 8, fps, config: {damping: 180, stiffness: 80}});
        const width = 90 + (Math.abs(m.value) / max) * 620 * p;
        const y = 48 + i * 78;
        const negative = m.value < 0 || String(m.display).includes('-');
        return (
          <g key={`${m.label}-${i}`}>
            <text x={0} y={y + 32} fill={C.paper} fontSize={25} fontFamily="Menlo, monospace">{m.label}</text>
            <rect x={210} y={y} width={width} height={42} rx={8} fill={negative ? C.red : '#2f6f9f'} />
            <text x={230 + width} y={y + 31} fill={C.gold} fontSize={28} fontWeight={800}>{m.display}</text>
          </g>
        );
      })}
    </svg>
  );
};

const DataTable: React.FC<{rows: string[][]}> = ({rows}) => {
  const frame = useCurrentFrame();
  if (!rows || rows.length === 0) return null;
  const visible = rows.slice(0, 5);
  return (
    <div style={{position: 'absolute', right: 76, top: 150, width: 700, borderRadius: 24, overflow: 'hidden', border: '1px solid rgba(214,168,79,.28)', background: 'rgba(244,239,228,.96)', color: C.ink}}>
      {visible.map((row, r) => {
        const p = clamp(frame - r * 7, [20, 44], [0, 1]);
        return (
          <div key={r} style={{display: 'grid', gridTemplateColumns: `repeat(${Math.min(row.length, 4)}, 1fr)`, opacity: p, transform: `translateX(${(1 - p) * 30}px)`, background: r === 0 ? C.panel : r % 2 ? '#fffaf0' : '#ece5d5'}}>
            {row.slice(0, 4).map((cell, c) => (
              <div key={`${r}-${c}`} style={{padding: '16px 14px', fontSize: r === 0 ? 17 : 18, lineHeight: 1.25, color: r === 0 ? C.paper : C.ink, borderBottom: '1px solid rgba(16,24,32,.12)'}}>
                {cell}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

const LogicScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nodes = logicNodes(scene);
  const progress = clamp(frame, [fps * 0.7, fps * 4.2], [0, 1]);
  return (
    <>
      <div style={{position: 'absolute', left: 92, top: 122, width: 820}}>
        <div style={{color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 18, letterSpacing: '0.14em'}}>LOGIC CHAIN · NOT PPT</div>
        <div style={{fontSize: 62, fontWeight: 900, marginTop: 18}}>{scene.title}</div>
        <div style={{fontSize: 27, color: C.muted, lineHeight: 1.45, marginTop: 20}}>{scene.subtitle}</div>
      </div>
      <svg style={{position: 'absolute', inset: 0}} viewBox="0 0 1920 1080">
        <path d="M420 515 C620 380 810 665 1010 520 S1320 410 1510 595" fill="none" stroke={C.gold} strokeWidth={6} strokeLinecap="round" strokeDasharray="1100" strokeDashoffset={(1 - progress) * 1100} />
      </svg>
      {nodes.map((node, i) => <LogicNode key={node} text={node} index={i} />)}
      <VoiceCard text={scene.voiceover} />
    </>
  );
};

const LogicNode: React.FC<{text: string; index: number}> = ({text, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pos = [
    [270, 430],
    [710, 585],
    [1110, 420],
    [1430, 585],
  ][index] || [270 + index * 310, 520];
  const p = spring({frame: frame - fps * 0.55 - index * 12, fps, config: {damping: 160, stiffness: 90}});
  return (
    <div style={{position: 'absolute', left: pos[0], top: pos[1], width: 250, minHeight: 116, padding: 22, borderRadius: 22, background: index % 2 ? 'rgba(123,211,166,.95)' : 'rgba(214,168,79,.95)', color: '#07111f', transform: `scale(${0.82 + p * 0.18})`, opacity: p, boxShadow: '0 18px 60px rgba(0,0,0,.28)'}}>
      <div style={{fontFamily: 'Menlo, monospace', fontSize: 17, opacity: 0.72}}>0{index + 1}</div>
      <div style={{fontSize: 28, fontWeight: 850, lineHeight: 1.14, marginTop: 8}}>{text}</div>
    </div>
  );
};

const VoiceCard: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [fps * 0.35, fps * 1.1], [0, 1]);
  return (
    <div style={{position: 'absolute', left: 92, right: 92, bottom: 58, minHeight: 104, borderRadius: 26, background: 'rgba(4,10,18,.72)', border: '1px solid rgba(214,168,79,.28)', padding: '22px 30px', opacity: p, transform: `translateY(${(1 - p) * 18}px)`, backdropFilter: 'blur(18px)'}}>
      <div style={{color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 15, letterSpacing: '.12em', marginBottom: 8}}>VOICEOVER · 投资人聊天口吻</div>
      <div style={{fontSize: 30, lineHeight: 1.35}}>{splitSubtitle(text).join('  ')}</div>
    </div>
  );
};

const Subtitle: React.FC<{scene: Scene}> = () => null;

const logicNodes = (scene: Scene) => {
  if (scene.title.includes('三因素')) return ['信贷', '财富', '政策', '楼市'];
  if (scene.title.includes('种子')) return ['财富是种子', '信贷放大', '政策开闸', '成交释放'];
  if (scene.title.includes('50')) return ['资产跌坑', '心理账户', '涨回50%', '重新敢买'];
  return ['判断', '证据', '传导', '结论'];
};

const fallbackMetrics = (scene: Scene): Metric[] => {
  if (scene.title.includes('50')) return [{label: '跌30%', display: '70', value: 70}, {label: '涨50%', display: '105', value: 105}];
  return [
    {label: '政策', display: '已放松', value: 42},
    {label: '财富', display: '修复中', value: 28},
    {label: '信贷', display: '偏弱', value: 22},
  ];
};
"""


def build_render_cjs() -> str:
    return """const path = require('path');
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderMedia, renderStill} = require('@remotion/renderer');

const root = __dirname;
const entryPoint = path.join(root, 'src', 'index.tsx');
const data = require(path.join(root, 'data', 'video_data.json'));
const out = path.join(root, 'render', 'remotion_dynamic_sample_silent.mp4');
const poster = path.join(root, 'render', 'poster_frame.jpg');

(async () => {
  const serveUrl = await bundle({entryPoint});
  const composition = await selectComposition({
    serveUrl,
    id: 'DynamicSample',
    inputProps: data,
  });
  await renderStill({
    serveUrl,
    composition,
    inputProps: data,
    output: poster,
    frame: Math.min(90, composition.durationInFrames - 1),
    imageFormat: 'jpeg',
  });
  await renderMedia({
    serveUrl,
    composition,
    inputProps: data,
    codec: 'h264',
    outputLocation: out,
    chromiumOptions: {
      disableWebSecurity: true,
    },
  });
  console.log(JSON.stringify({status: 'ok', output: out, poster, durationInFrames: composition.durationInFrames, fps: composition.fps}, null, 2));
})();
"""


def build_project(output_dir: Path, data: dict[str, Any], html_video_root: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write(output_dir / "package.json", build_package_json())
    write(output_dir / "src" / "index.tsx", build_index_tsx())
    write(output_dir / "src" / "Root.tsx", build_root_tsx())
    write(output_dir / "src" / "Video.tsx", build_video_tsx())
    write(output_dir / "render.cjs", build_render_cjs())
    write_json(output_dir / "data" / "video_data.json", data)
    write(output_dir / "voiceover_chat_script.txt", "\n".join(scene["voiceover"] for scene in data["scenes"]) + "\n")
    node_modules = output_dir / "node_modules"
    target = html_video_root / "node_modules"
    if node_modules.exists() or node_modules.is_symlink():
        if node_modules.is_symlink() and node_modules.resolve() == target.resolve():
            return
        raise RuntimeError(f"Refusing to overwrite existing node_modules: {node_modules}")
    os.symlink(target, node_modules)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a horizontal Remotion dynamic sample from Newma director storyboard.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--html-video-root", default=str(DEFAULT_HTML_VIDEO_ROOT))
    parser.add_argument("--scene-count", type=int, default=8)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    storyboard = load_json(Path(args.storyboard).expanduser().resolve())
    inventory = load_json(Path(args.inventory).expanduser().resolve())
    output_dir = Path(args.output_dir).expanduser().resolve()
    html_video_root = Path(args.html_video_root).expanduser().resolve()
    data = build_sample_data(storyboard, inventory, scene_count=args.scene_count, fps=args.fps)
    build_project(output_dir, data, html_video_root)
    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(output_dir),
                "scene_count": len(data["scenes"]),
                "duration_sec": data["durationSec"],
                "script": str((output_dir / "voiceover_chat_script.txt").resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
