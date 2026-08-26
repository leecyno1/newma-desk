#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


WIDTH = 1080
HEIGHT = 1920
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML_VIDEO_ROOT = Path(
    os.environ.get("HTML_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-video"))
).expanduser()
MOTION_RUNTIME_MODE = "auto"
MOTION_LIB_CACHE: dict[str, str | None] = {}


def clean_text(text: Any) -> str:
    value = html.unescape(str(text or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def html_video_root() -> Path:
    return Path(os.environ.get("HTML_VIDEO_ROOT", str(DEFAULT_HTML_VIDEO_ROOT))).expanduser().resolve()


def find_first(root: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0]
    return None


def read_motion_lib(name: str) -> str | None:
    if name in MOTION_LIB_CACHE:
        return MOTION_LIB_CACHE[name]
    root = html_video_root()
    if name == "gsap":
        path = find_first(root, ["node_modules/**/gsap/dist/gsap.min.js"])
    elif name == "lottie":
        path = find_first(root, ["node_modules/**/lottie-web/build/player/lottie_light.min.js", "node_modules/**/lottie-web/build/player/lottie.min.js"])
    else:
        path = None
    if path and path.exists():
        MOTION_LIB_CACHE[name] = path.read_text(encoding="utf-8", errors="ignore")
    else:
        MOTION_LIB_CACHE[name] = None
    return MOTION_LIB_CACHE[name]


def esc(text: Any) -> str:
    return html.escape(clean_text(text), quote=True)


def short(text: Any, limit: int) -> str:
    value = clean_text(text)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def split_units(text: str, limit: int = 6) -> list[str]:
    parts = [item.strip() for item in re.split(r"[。；;，,、\n]+", clean_text(text)) if item.strip()]
    if not parts:
        parts = [clean_text(text)]
    return [short(item, 28) for item in parts[:limit]]


def table_from_variables(scene: dict[str, Any]) -> list[list[str]]:
    variables = scene.get("variables") or {}
    table = variables.get("table") or variables.get("rows") or []
    if not isinstance(table, list):
        return []
    out: list[list[str]] = []
    for row in table[:8]:
        if isinstance(row, list):
            out.append([clean_text(cell) for cell in row[:4]])
    return out


def numbers_from_scene(scene: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    text = clean_text(scene.get("narration"))
    rows = []
    metric_patterns = [
        (r"(?:年营收|营收)[^，。；]{0,10}?([-+]?\d+(?:\.\d+)?\s*亿元)", "未来年营收"),
        (r"(?:净利率)[^，。；]{0,8}?([-+]?\d+(?:\.\d+)?%)", "净利率"),
        (r"(?:净利润|利润)[^，。；]{0,8}?([-+]?\d+(?:\.\d+)?\s*亿元)", "净利润"),
        (r"(?:给予|对应|乘以)[^，。；]{0,8}?([-+]?\d+(?:\.\d+)?\s*倍)(?:市盈率|PE)?", "估值倍数"),
        (r"(?:市值|对应市值)[^，。；]{0,8}?([-+]?\d+(?:\.\d+)?\s*亿元)", "对应市值"),
    ]
    seen: set[tuple[str, str]] = set()
    for pattern, label in metric_patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        display = clean_text(match.group(1)).replace(" ", "")
        key = (label, display)
        if key in seen:
            continue
        seen.add(key)
        found = NUMBER_RE.search(display)
        if not found:
            continue
        raw = found.group(0).replace("%", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        rows.append({"label": label, "display": display, "value": value})
        if len(rows) >= limit:
            break
    return rows


def chart_rows(scene: dict[str, Any]) -> list[dict[str, Any]]:
    variables = scene.get("variables") or {}
    metrics = variables.get("metrics") or []
    if isinstance(metrics, list):
        rows = []
        for idx, item in enumerate(metrics[:6], 1):
            if not isinstance(item, dict):
                continue
            label = item.get("label") or f"指标 {idx}"
            display = item.get("display") or item.get("value") or ""
            found = NUMBER_RE.search(str(display).replace(",", ""))
            if found:
                try:
                    value = float(found.group(0).replace("%", ""))
                except ValueError:
                    value = float(idx * 10)
            else:
                value = float(idx * 8)
            rows.append({"label": short(label, 9), "display": short(display, 12), "value": value})
        if rows:
            return rows
    table = table_from_variables(scene)
    rows = []
    for idx, row in enumerate(table[1:7] if len(table) > 1 else table[:6], 1):
        label = row[0] if row else f"指标 {idx}"
        value_text = row[1] if len(row) > 1 else ""
        found = NUMBER_RE.search(value_text.replace(",", ""))
        if found:
            try:
                value = float(found.group(0).replace("%", ""))
            except ValueError:
                value = float(idx * 10)
        else:
            value = float(idx * 8)
        rows.append({"label": short(label, 9), "display": short(value_text or str(value), 12), "value": value})
    return rows or numbers_from_scene(scene)


def motion_policy(scene: dict[str, Any]) -> dict[str, Any]:
    policy = scene.get("motion_policy") or {}
    if not isinstance(policy, dict):
        policy = {}
    return {
        "framework": policy.get("framework", "hyperframes"),
        "animation": policy.get("animation", "gsap_fade_rise"),
        "lottie_allowed": bool(policy.get("lottie_allowed", True)),
        "lottie_required": bool(policy.get("lottie_required", False)),
        "lottie_role": policy.get("lottie_role", "optional_ambient"),
        "lottie_keywords": policy.get("lottie_keywords", ["abstract", "motion graphics"]),
        "fact_rule": policy.get("fact_rule", "Lottie is decorative only; facts come from article variables."),
    }


def motion_meta(scene: dict[str, Any]) -> str:
    return html.escape(json.dumps(motion_policy(scene), ensure_ascii=False), quote=True)


def director_meta(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "beat_class": scene.get("beat_class") or "claim",
        "director_state": scene.get("director_state") or "question_setup",
        "transition_to_next": scene.get("transition_to_next") or "hard_cut",
        "driver_score": scene.get("driver_score"),
        "audio": scene.get("audio") or {},
    }


def director_meta_attr(scene: dict[str, Any]) -> str:
    return html.escape(json.dumps(director_meta(scene), ensure_ascii=False), quote=True)


def director_body_class(scene: dict[str, Any]) -> str:
    state = re.sub(r"[^0-9A-Za-z_-]+", "-", str(scene.get("director_state") or "question_setup"))
    transition = re.sub(r"[^0-9A-Za-z_-]+", "-", str(scene.get("transition_to_next") or "hard_cut"))
    beat = re.sub(r"[^0-9A-Za-z_-]+", "-", str(scene.get("beat_class") or "claim"))
    return f"state-{state} transition-{transition} beat-{beat}"


def motion_layer(scene: dict[str, Any]) -> str:
    policy = motion_policy(scene)
    return f"""
<div id="lottie-accent" class="motion-accent" data-lottie-role="{esc(policy['lottie_role'])}" aria-hidden="true">
</div>
"""


def lottie_color_for_scene(scene: dict[str, Any]) -> list[float]:
    part = str(scene.get("content_part") or "")
    if part in {"warning_or_risk", "opening_hook"}:
        return [0.92, 0.18, 0.12, 1]
    if part in {"data_chart", "financial_chart", "data_table", "kpi_card"}:
        return [0.1, 0.37, 0.55, 1]
    if part in {"article_title", "chapter_divider", "closing_outro", "brand_mark"}:
        return [0.85, 0.67, 0.33, 1]
    return [0.38, 0.68, 0.56, 1]


def lottie_data_for_scene(scene: dict[str, Any]) -> dict[str, Any]:
    color = lottie_color_for_scene(scene)
    part = str(scene.get("content_part") or "")
    role = motion_policy(scene)["lottie_role"]
    # Minimal valid Lottie shape animation generated from the scene role. This
    # gives lottie-web a real asset now; later an asset search step can replace it.
    if part in {"data_chart", "financial_chart", "data_table"}:
        shapes = [
            {
                "ty": "rc",
                "s": {"a": 0, "k": [18 + i * 8, 70 + i * 18]},
                "p": {"a": 0, "k": [-64 + i * 44, 0]},
                "r": {"a": 0, "k": 6},
            }
            for i in range(4)
        ]
    else:
        shapes = [
            {
                "ty": "el",
                "s": {"a": 1, "k": [{"t": 0, "s": [80, 80]}, {"t": 45, "s": [124, 124]}, {"t": 90, "s": [80, 80]}]},
                "p": {"a": 0, "k": [0, 0]},
            }
        ]
    return {
        "v": "5.13.0",
        "fr": 30,
        "ip": 0,
        "op": 90,
        "w": 240,
        "h": 240,
        "nm": role,
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": role,
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 72},
                    "r": {"a": 1, "k": [{"t": 0, "s": [0]}, {"t": 90, "s": [360]}]},
                    "p": {"a": 0, "k": [120, 120, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "ao": 0,
                "shapes": [
                    {"ty": "gr", "it": shapes + [{"ty": "fl", "c": {"a": 0, "k": color}, "o": {"a": 0, "k": 100}}, {"ty": "tr", "p": {"a": 0, "k": [0, 0]}, "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0}, "o": {"a": 0, "k": 100}}]},
                ],
                "ip": 0,
                "op": 90,
                "st": 0,
                "bm": 0,
            }
        ],
    }


def inline_real_motion_libs() -> str:
    if MOTION_RUNTIME_MODE == "lite":
        return ""
    chunks = []
    gsap_code = read_motion_lib("gsap")
    lottie_code = read_motion_lib("lottie")
    if gsap_code:
        chunks.append(f"<script data-motion-lib=\"gsap\">{gsap_code}</script>")
    if lottie_code:
        chunks.append(f"<script data-motion-lib=\"lottie-web\">{lottie_code}</script>")
    return "\n".join(chunks)


def motion_runtime() -> str:
    # Tiny GSAP-compatible facade for offline previews. Production can swap this
    # with real GSAP and lottie-web when assets are installed.
    return """
<script data-motion-runtime="dasheng">
(function(){
  var q=function(sel){return Array.prototype.slice.call(document.querySelectorAll(sel));};
  window.gsap=window.gsap||{
    to:function(sel,vars){q(sel).forEach(function(el){Object.keys(vars||{}).forEach(function(k){if(k!=='duration'&&k!=='delay'&&k!=='stagger'&&k!=='ease'){el.style[k]=vars[k];}});});},
    from:function(sel,vars){q(sel).forEach(function(el,i){el.style.opacity='0';el.style.transform='translateY(26px)';setTimeout(function(){el.style.transition='opacity .7s ease, transform .7s ease';el.style.opacity='1';el.style.transform='none';},((vars&&vars.delay)||0)*1000+i*((vars&&vars.stagger)||.08)*1000);});},
    timeline:function(){return {from:function(sel,vars){window.gsap.from(sel,vars);return this;},to:function(sel,vars){window.gsap.to(sel,vars);return this;}};}
  };
  window.initScene=function(){
    var root=document.querySelector('[data-motion-policy]');
    var policy={};
    try{policy=JSON.parse(root.getAttribute('data-motion-policy')||'{}');}catch(e){}
    document.documentElement.setAttribute('data-animation',policy.animation||'gsap_fade_rise');
    window.gsap.from('.kicker,.title,h1,.subtitle,.lead,.card,.paper,.logo',{stagger:.08,delay:.06});
    window.gsap.from('.note,.bar,li,tr,.motion-accent',{stagger:.06,delay:.16});
    if(window.lottie){
      var holder=document.getElementById('lottie-accent');
      var dataNode=document.getElementById('lottie-data');
      if(holder&&dataNode){
        try{
          var data=JSON.parse(dataNode.textContent||'{}');
          holder.innerHTML='';
          window.lottie.loadAnimation({container:holder,renderer:'svg',loop:true,autoplay:true,animationData:data});
        }catch(e){}
      }
    }
  };
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',window.initScene);}else{window.initScene();}
})();
</script>
"""


def base_css() -> str:
    return f"""
*{{box-sizing:border-box}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;margin:0;overflow:hidden;background:#07090d;color:#f5f2e9}}
body{{font-family:"PingFang SC","Noto Sans SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}}
.frame{{position:relative;width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;padding:72px}}
.mono{{font-family:"SFMono-Regular","Menlo","Consolas",monospace}}
.serif{{font-family:"Songti SC","Noto Serif SC","Iowan Old Style",serif}}
.kicker{{font-size:22px;letter-spacing:.16em;text-transform:uppercase;color:#d8aa55}}
.title{{font-size:86px;line-height:1.04;font-weight:900;letter-spacing:-.04em}}
.subtitle{{font-size:34px;line-height:1.55;color:#d3d7df}}
.caption{{display:none!important}}
.hairline{{height:1px;background:linear-gradient(90deg,transparent,#d8aa55,transparent)}}
.safe-bottom{{position:absolute;left:72px;right:72px;bottom:74px}}
.motion-accent{{position:absolute;right:54px;top:180px;width:180px;height:180px;border:1px solid rgba(216,170,85,.28);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:#d8aa55;background:radial-gradient(circle,rgba(216,170,85,.12),rgba(216,170,85,.02) 58%,transparent);opacity:.58;animation:pulse 5s ease-in-out infinite;pointer-events:none;text-align:center}}
body.state-evidence_scene .motion-accent{{top:126px;right:44px;opacity:.38}}
body.state-chapter_card .motion-accent{{top:230px;right:72px;transform:scale(1.25)}}
body.state-logic_animation .motion-accent{{border-radius:24px;opacity:.42}}
body.transition-impact_cut .frame:after{{content:"";position:absolute;inset:0;border:8px solid rgba(216,170,85,.34);animation:impactFlash .42s ease both;pointer-events:none}}
body.transition-chapter_hit .frame:after{{content:"";position:absolute;left:0;right:0;top:0;height:9px;background:#d8aa55;animation:slideIn .7s ease both}}
body.transition-data_reveal .bar rect{{transform-origin:left center;animation:barGrow .8s cubic-bezier(.2,.8,.2,1) both}}
body.transition-path_highlight .lines path{{stroke-dasharray:16 9;stroke:#b8862f}}
.fade-in{{animation:fadeIn .8s ease both}}
.rise{{animation:rise .9s cubic-bezier(.2,.8,.2,1) both}}
.delay1{{animation-delay:.18s}}.delay2{{animation-delay:.34s}}.delay3{{animation-delay:.5s}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(34px)}}to{{opacity:1;transform:none}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.035)}}}}
@keyframes slideIn{{from{{opacity:0;transform:translateX(60px)}}to{{opacity:1;transform:none}}}}
@keyframes impactFlash{{0%{{opacity:0;transform:scale(.98)}}20%{{opacity:1;transform:scale(1)}}100%{{opacity:0;transform:scale(1.03)}}}}
@keyframes barGrow{{from{{transform:scaleX(.08)}}to{{transform:scaleX(1)}}}}
@media (prefers-reduced-motion: reduce){{*{{animation:none!important;transition:none!important}}}}
"""


def landscape_overrides() -> str:
    if WIDTH <= HEIGHT:
        return ""
    return """
.frame{padding:58px 72px}
.safe-bottom{left:72px;right:72px;bottom:42px}
.motion-accent{right:44px;top:72px;width:132px;height:132px}
.liquid .title{margin:190px 0 28px!important;font-size:92px!important;max-width:1450px}
.liquid .subtitle{max-width:1320px!important;font-size:30px}
.glitch-title{top:320px!important;right:230px!important}
.glitch h1{font-size:82px!important;max-width:1500px}
.cinema .kicker{margin-top:220px!important}
.cinema h1{font-size:76px!important;max-width:1450px}
.cinema .subtitle{max-width:1200px!important;font-size:30px}
.letterbox{height:110px!important}
.dash h1,.rollup h1{font-size:54px!important;max-width:1500px!important;margin-bottom:24px!important}
.dash section,.rollup section{grid-template-columns:repeat(3,1fr)!important;gap:18px!important;margin-top:26px!important}
.dash-card,.metric{min-height:154px!important;padding:22px!important}
.dash-card b,.metric b{font-size:38px!important;margin:12px 0!important}
.data h1,.nyt h1{font-size:54px!important;max-width:1500px!important;margin:18px 0 12px!important}
.data .lead,.nyt .lead{font-size:25px!important;max-width:1450px!important}
.doc .paper{left:70px!important;right:70px!important;top:54px!important;bottom:54px!important;padding:38px 54px!important}
.doc .paper h1{font-size:44px!important;margin:16px 0 18px!important}
.doc img,.doc .evidence-note{height:590px!important;margin:14px 0!important}
.doc .paper>p:last-child{font-size:22px!important;margin:8px 0 0!important}
.outro .logo{width:170px!important;height:170px!important;margin:170px auto 32px!important;font-size:96px!important}
.outro h1{font-size:62px!important;margin-bottom:18px!important}
.outro p{font-size:28px!important;max-width:1050px!important}
.outro .safe-bottom{bottom:28px!important}
.note,.judgement-card,.dash-card,.metric,.pressure-row,.evidence-level,.chain-bridge article,.stream,.signal-gate,.proof-ladder article,.gap-bar,.thesis-balance article,.tree-label,.route-card{position:relative}
.note:after,.judgement-card:after,.dash-card:after,.metric:after,.pressure-row:after,.evidence-level:after,.chain-bridge article:after,.stream:after,.signal-gate:after,.proof-ladder article:after,.gap-bar:after,.thesis-balance article:after,.tree-label:after,.route-card:after{content:"";position:absolute;inset:-6px;border:3px solid rgba(214,168,78,.78);background:rgba(214,168,78,.12);box-shadow:0 0 44px rgba(214,168,78,.2);opacity:0;pointer-events:none;z-index:8;animation:semanticHalo 2.4s ease var(--focus-delay,3s) 1 both}
.note.n0,.judgement-card:nth-child(1),.dash-card:nth-child(1),.metric:nth-child(1),.pressure-row:nth-child(1),.evidence-level:nth-child(1),.chain-bridge article:nth-child(1),.stream-0,.signal-gate:nth-child(1),.proof-ladder article:nth-child(1),.gap-bar:nth-child(1),.route-card:nth-child(1){--focus-delay:2.4s}
.note.n1,.judgement-card:nth-child(2),.dash-card:nth-child(2),.metric:nth-child(2),.pressure-row:nth-child(2),.evidence-level:nth-child(2),.chain-bridge article:nth-child(2),.stream-1,.signal-gate:nth-child(2),.proof-ladder article:nth-child(2),.gap-bar:nth-child(2),.route-card:nth-child(2),.thesis-balance .optimistic{--focus-delay:5.8s}
.note.n2,.judgement-card:nth-child(3),.dash-card:nth-child(3),.metric:nth-child(3),.pressure-row:nth-child(3),.evidence-level:nth-child(3),.chain-bridge article:nth-child(3),.stream-2,.signal-gate:nth-child(3),.proof-ladder article:nth-child(3),.route-card:nth-child(3),.thesis-balance .restrained{--focus-delay:9.2s}
.note.n3,.judgement-card:nth-child(4),.dash-card:nth-child(4),.metric:nth-child(4),.stream-3,.proof-ladder article:nth-child(4),.route-card:nth-child(4){--focus-delay:12.6s}
.note.n4,.dash-card:nth-child(5),.metric:nth-child(5),.route-card:nth-child(5){--focus-delay:15.6s}
.data tbody tr{animation:rowFocus 2.5s ease-in-out var(--row-delay,2.4s) 1 both}.data tbody tr:nth-child(2){--row-delay:3s}.data tbody tr:nth-child(3){--row-delay:6s}.data tbody tr:nth-child(4){--row-delay:9s}.data tbody tr:nth-child(5){--row-delay:12s}.data tbody tr:nth-child(6){--row-delay:15s}
.verified-chart .chart-shell:before{content:"";position:absolute;z-index:2;inset:54px 26px 35px;background:radial-gradient(circle at 12% 50%,rgba(78,163,216,.23),transparent 18%),radial-gradient(circle at 50% 50%,rgba(214,168,78,.18),transparent 18%),radial-gradient(circle at 88% 50%,rgba(224,95,95,.2),transparent 18%);opacity:0;pointer-events:none;animation:chartSemanticFocus 16s ease 1 both}
.doc .paper{overflow:hidden}
.doc .paper:after{content:"";position:absolute;inset:-35%;pointer-events:none;background:radial-gradient(circle at 20% 50%,rgba(31,95,139,.16),transparent 24%);animation:evidenceSpotlight 14s ease-in-out 1 both}
.doc .document-stage img{height:100%!important;margin:0!important;animation:evidenceClarity 12s ease-in-out 1 both}
.doc-overlay.overlay-0{animation-delay:2s!important}.doc-overlay.overlay-1{animation-delay:5s!important}.doc-overlay.overlay-2{animation-delay:8s!important}.doc-overlay.overlay-3{animation-delay:11s!important}
.tree-label.root{--focus-delay:4s}.tree-label.crown{--focus-delay:8s}.tree-label.water-label{--focus-delay:12s}
.outro .logo{animation:logoBreath 4.6s ease-in-out 1 both!important}
.semantic-focus-stage{position:fixed;inset:0;z-index:90;pointer-events:none}.semantic-focus{position:absolute;inset:0;padding:120px 150px;display:flex;flex-direction:column;justify-content:center;opacity:0}.semantic-focus small{font:800 22px Menlo,monospace;letter-spacing:.16em;margin-bottom:30px}.semantic-focus b{font-size:86px;line-height:1.05;max-width:1500px}.semantic-focus span{font-size:31px;line-height:1.45;max-width:1250px;margin-top:32px}.semantic-focus.focus-a{background:linear-gradient(135deg,rgba(6,14,22,.985),rgba(16,48,66,.985));color:#f4f1e8;align-items:flex-start;animation:semanticCutA 3.4s cubic-bezier(.2,.8,.2,1) var(--focus-a-delay) 1 both}.semantic-focus.focus-a small{color:#d6a84e}.semantic-focus.focus-b{background:linear-gradient(135deg,rgba(241,237,228,.99),rgba(218,229,232,.99));color:#151b20;align-items:flex-end;text-align:right;animation:semanticCutB 3.4s cubic-bezier(.2,.8,.2,1) var(--focus-b-delay) 1 both}.semantic-focus.focus-b small{color:#1f6c8c}.semantic-focus.focus-b b,.semantic-focus.focus-b span{max-width:1380px}
body.beat-evidence_data .semantic-focus.focus-a{background:linear-gradient(135deg,rgba(5,16,25,.99),rgba(13,53,72,.99))}body.beat-evidence_data .semantic-focus b{font-family:Menlo,"PingFang SC",sans-serif;color:#f0cf82}body.beat-logic_chain .semantic-focus.focus-b{background:linear-gradient(135deg,#f4ede1,#dcebe7)}body.beat-cinematic_bridge .semantic-focus.focus-a{background:linear-gradient(135deg,rgba(12,18,23,.99),rgba(45,38,27,.99))}
@keyframes semanticHalo{0%,100%{opacity:0;transform:scale(.99)}25%,68%{opacity:1;transform:scale(1.015)}}
@keyframes rowFocus{0%,100%{background:transparent;transform:none}22%,68%{background:rgba(31,95,139,.2);transform:translateX(12px)}}
@keyframes chartSemanticFocus{0%,12%,100%{opacity:0;transform:none}18%,28%{opacity:1;transform:translateX(-18%)}38%,48%{opacity:1;transform:none}60%,74%{opacity:1;transform:translateX(18%)}82%{opacity:0;transform:translateX(18%)}}
@keyframes evidenceSpotlight{0%,100%{transform:translateX(-18%);opacity:.35}32%{transform:translateX(8%);opacity:.9}66%{transform:translateX(38%);opacity:1}}
@keyframes evidenceClarity{0%,100%{filter:saturate(.9) contrast(.98);opacity:.92}38%{filter:saturate(1.12) contrast(1.06);opacity:1}72%{filter:saturate(.98) contrast(1.02);opacity:.96}}
@keyframes logoBreath{0%,100%{transform:scale(1);box-shadow:0 0 48px rgba(216,170,85,.18)}50%{transform:scale(1.055);box-shadow:0 0 86px rgba(216,170,85,.38)}}
@keyframes semanticCutA{0%,100%{opacity:0;transform:translateX(-8%)}14%,78%{opacity:1;transform:none}}
@keyframes semanticCutB{0%,100%{opacity:0;transform:translateX(8%)}14%,78%{opacity:1;transform:none}}
"""


def semantic_focus_layer(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    if not variables.get("allow_fullscreen_focus"):
        return ""
    cards = variables.get("focus_cards") if isinstance(variables.get("focus_cards"), list) else []
    cards = [card for card in cards[:2] if isinstance(card, dict) and clean_text(card.get("title"))]
    if not cards:
        return ""
    duration = max(float(scene.get("duration_sec") or 12.0), 8.0)
    first_delay = max(3.0, duration * 0.28)
    second_delay = max(first_delay + 4.0, duration * 0.65)
    beat = clean_text(scene.get("beat_class"))
    part = clean_text(scene.get("content_part"))
    if beat == "evidence_data" or part in {"data_table", "financial_chart", "article_dynamic_chart"}:
        default_eyebrow = "关键数据"
    elif beat == "cinematic_bridge":
        default_eyebrow = "场景隐喻"
    elif beat == "logic_chain":
        default_eyebrow = "机制拆解"
    elif beat == "recap":
        default_eyebrow = "执行重点"
    else:
        default_eyebrow = "关键判断"
    rendered = []
    for index, card in enumerate(cards):
        class_name = "focus-a" if index == 0 else "focus-b"
        eyebrow = clean_text(card.get("eyebrow"))
        if not eyebrow or eyebrow.upper().startswith("FOCUS"):
            eyebrow = default_eyebrow if index == 0 else "进一步看"
        rendered.append(
            f'<article class="semantic-focus {class_name}"><small>{esc(eyebrow)}</small>'
            f'<b>{esc(card.get("title"))}</b><span>{esc(card.get("detail") or "")}</span></article>'
        )
    return (
        f'<div class="semantic-focus-stage" style="--focus-a-delay:{first_delay:.2f}s;--focus-b-delay:{second_delay:.2f}s">'
        + "".join(rendered)
        + "</div>"
    )


def scene_shell(scene: dict[str, Any], body: str, extra_css: str = "") -> str:
    title = esc(scene.get("title"))
    duration = scene.get("duration_sec", "")
    template_id = esc(scene.get("template_id"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={WIDTH}, initial-scale=1">
<title>{title}</title>
<style>{base_css()}{extra_css}{landscape_overrides()}</style>
</head>
<body class="{director_body_class(scene)}" data-motion-policy="{motion_meta(scene)}" data-director-policy="{director_meta_attr(scene)}">
<!-- template: {template_id}; duration: {duration}s -->
{body}
{semantic_focus_layer(scene)}
<script id="lottie-data" type="application/json">{html.escape(json.dumps(lottie_data_for_scene(scene), ensure_ascii=False), quote=False)}</script>
{inline_real_motion_libs()}
{motion_runtime()}
</body>
</html>
"""


def render_liquid_hero(scene: dict[str, Any]) -> str:
    return scene_shell(
        scene,
        f"""
<main class="frame liquid">
  <div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
  {motion_layer(scene)}
  <div class="kicker fade-in">DASHENG · MARKET BRIEF</div>
  <h1 class="title serif rise">{esc(scene.get('title'))}</h1>
  <p class="subtitle rise delay1">{esc(short(scene.get('narration'), 90))}</p>
  <div class="safe-bottom">
    <div class="hairline"></div>
    <p class="caption mono">MARKET BRIEF · SIGNAL BEFORE PRICE</p>
  </div>
</main>
""",
        """
.liquid{background:#090b12}
.blob{position:absolute;border-radius:999px;filter:blur(58px);opacity:.72;mix-blend-mode:screen;animation:pulse 7s ease-in-out infinite}
.b1{width:760px;height:760px;left:-210px;top:120px;background:#173b7a}
.b2{width:680px;height:680px;right:-240px;top:360px;background:#a4512d;animation-delay:-2s}
.b3{width:620px;height:620px;left:120px;bottom:-160px;background:#184b3d;animation-delay:-4s}
.liquid .title{position:relative;margin:290px 0 34px;font-size:98px;text-shadow:0 14px 60px rgba(0,0,0,.42)}
.liquid .subtitle{position:relative;max-width:850px}
""",
    )


def render_glitch(scene: dict[str, Any]) -> str:
    title = esc(scene.get("title"))
    return scene_shell(
        scene,
        f"""
<main class="frame glitch">
  <div class="scan"></div>
  {motion_layer(scene)}
  <div class="top mono">&gt;&gt; SIGNAL · MARKET · WATCH</div>
  <section class="glitch-title">
    <h1 data-text="{title}">{title}</h1>
    <p class="mono">{esc(short(scene.get('narration'), 96))}</p>
  </section>
  <div class="safe-bottom mono">NOISE ≠ SIGNAL · FOLLOW THE MONEY</div>
</main>
""",
        """
.glitch{background:#08090d;background-image:linear-gradient(rgba(0,255,220,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,220,.045) 1px,transparent 1px);background-size:54px 54px}
.scan{position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.035),rgba(255,255,255,.035) 1px,transparent 1px,transparent 4px)}
.top{position:absolute;top:62px;left:72px;right:72px;color:#80fff0;font-size:20px;letter-spacing:.14em}
.glitch-title{position:absolute;left:72px;right:72px;top:520px}
.glitch h1{position:relative;margin:0;font-size:96px;line-height:1.05;font-weight:950;letter-spacing:-.05em;animation:glitch 3.8s infinite}
.glitch h1:before,.glitch h1:after{content:attr(data-text);position:absolute;inset:0;pointer-events:none}
.glitch h1:before{color:#00f0ff;transform:translate(-4px,2px);mix-blend-mode:screen}
.glitch h1:after{color:#ff2bd6;transform:translate(4px,-2px);mix-blend-mode:screen}
.glitch p{margin-top:34px;color:#c7cbd6;font-size:28px;line-height:1.55}
@keyframes glitch{0%,92%,100%{transform:none}94%{transform:translateX(-10px)}95%{transform:translateX(8px)}96%{transform:translateX(-3px)}}
""",
    )


def render_cinema(scene: dict[str, Any]) -> str:
    return scene_shell(
        scene,
        f"""
<main class="frame cinema">
  <div class="leak"></div>
  <div class="letterbox top"></div><div class="letterbox bottom"></div>
  {motion_layer(scene)}
  <div class="kicker rise">CHAPTER</div>
  <h1 class="serif rise delay1">{esc(scene.get('title'))}</h1>
  <p class="subtitle rise delay2">{esc(short(scene.get('narration'), 80))}</p>
</main>
""",
        """
.cinema{background:#17110d}
.cinema:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 15% 20%,rgba(255,177,89,.35),transparent 28%),radial-gradient(circle at 85% 45%,rgba(141,38,20,.32),transparent 35%),linear-gradient(180deg,#17110d,#090806)}
.leak{position:absolute;inset:-20%;background:linear-gradient(115deg,transparent 35%,rgba(255,205,120,.36),transparent 58%);animation:slideIn 1.6s ease both}
.letterbox{position:absolute;left:0;right:0;height:180px;background:#030303;z-index:3}.letterbox.top{top:0}.letterbox.bottom{bottom:0}
.cinema .kicker{position:relative;z-index:4;margin-top:380px}
.cinema h1{position:relative;z-index:4;margin:28px 0 22px;font-size:92px;line-height:1.05}
.cinema .subtitle{position:relative;z-index:4;max-width:790px}
""",
    )


def render_flowchart(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    nodes = variables.get("headings") if isinstance(variables.get("headings"), list) else split_units(scene.get("narration", ""), 5)
    nodes = [short(item, 18) for item in nodes[:5] if clean_text(item)] or split_units(scene.get("title", ""), 5)
    if WIDTH > HEIGHT:
        card_width = 310
        positions = [(70 + idx * 365, 440) for idx in range(5)]
    else:
        card_width = 330
        positions = [(84, 445), (558, 410), (178, 760), (620, 828), (320, 1135)]
    cards = []
    path_parts = []
    for idx, node in enumerate(nodes):
        x, y = positions[idx % len(positions)]
        cards.append(
            f'<div class="note n{idx}" style="left:{x}px;top:{y}px;--node-delay:{idx * 0.32:.2f}s">'
            f'<b>{idx+1:02d}</b><span>{esc(node)}</span></div>'
        )
        if idx < len(nodes) - 1:
            x2, y2 = positions[(idx + 1) % len(positions)]
            path_parts.append(f'M{x+card_width},{y+85} C{x+card_width+45},{y+35} {x2-45},{y2+135} {x2},{y2+85}')
    paths = "".join(f'<path d="{d}" />' for d in path_parts)
    return scene_shell(
        scene,
        f"""
<main class="frame flow">
  {motion_layer(scene)}
  <div class="kicker">LOGIC MAP</div>
  <h1>{esc(scene.get('title'))}</h1>
  <svg class="lines" viewBox="0 0 {WIDTH} {HEIGHT}">{paths}</svg>
  {''.join(cards)}
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.flow{background:#f4ede1;color:#1f1d18;background-image:linear-gradient(rgba(0,0,0,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(0,0,0,.035) 1px,transparent 1px);background-size:42px 42px}
.flow h1{font-size:54px;line-height:1.16;margin:22px 0 0;max-width:860px}
.lines{position:absolute;inset:0}.lines path{fill:none;stroke:#1f1d18;stroke-width:4;stroke-dasharray:10 9;stroke-linecap:round;opacity:.55;animation:draw 1.1s ease both}
.note{position:absolute;width:330px;min-height:190px;background:#fcd34d;color:#1b1b18;box-shadow:0 18px 38px rgba(0,0,0,.16);padding:24px;transform:rotate(-2deg);animation:nodeReveal .72s ease var(--node-delay) both}
.note:nth-of-type(odd){background:#a7f3d0;transform:rotate(1.6deg)}.note b{display:block;font-size:22px;margin-bottom:18px}.note span{font-size:31px;line-height:1.22;font-weight:800}
@keyframes draw{from{stroke-dashoffset:500;opacity:0}to{stroke-dashoffset:0;opacity:.55}}
.flow .safe-bottom{color:#5f584d}
@media (min-aspect-ratio: 4/3){
  .flow h1{font-size:48px;max-width:1500px;margin-top:14px}
  .note{width:310px;min-height:170px;padding:22px}
  .note span{font-size:25px;line-height:1.2}
  .flow .safe-bottom{font-size:21px;line-height:1.4;bottom:42px}
}
@keyframes nodeReveal{from{opacity:0;translate:0 24px;scale:.96}to{opacity:1;translate:0 0;scale:1}}
""",
    )


def render_data(scene: dict[str, Any], table_mode: bool = False) -> str:
    rows = chart_rows(scene)
    values = [abs(float(row["value"])) for row in rows]
    max_value = max(values) if values else 1
    bars = []
    for idx, row in enumerate(rows[:6]):
        w = 120 + int((abs(float(row["value"])) / max_value) * 600)
        y = (440 + idx * 82) if WIDTH > HEIGHT else (700 + idx * 118)
        color = "#b91c1c" if float(row["value"]) < 0 or "-" in str(row["display"]) else "#1f5f8b"
        bars.append(
            f'<g class="bar" style="animation-delay:{idx*.12}s"><text x="80" y="{y+38}">{esc(row["label"])}</text><rect x="250" y="{y}" width="{w}" height="54" rx="8" fill="{color}"/><text x="{270+w}" y="{y+38}" class="value">{esc(row["display"])}</text></g>'
        )
    table = table_from_variables(scene)
    table_html = ""
    if table_mode and table:
        trs = []
        for ridx, row in enumerate(table[:7]):
            tag = "th" if ridx == 0 else "td"
            trs.append("<tr>" + "".join(f"<{tag}>{esc(cell)}</{tag}>" for cell in row[:4]) + "</tr>")
        table_html = f"<table>{''.join(trs)}</table>"
    chart_html = "" if table_mode else f"""
  <svg class="chart" viewBox="0 0 {WIDTH} {HEIGHT}">
    <line x1="250" y1="{390 if WIDTH > HEIGHT else 650}" x2="250" y2="{940 if WIDTH > HEIGHT else 1420}" />
    {''.join(bars)}
  </svg>
"""
    return scene_shell(
        scene,
        f"""
<main class="frame data">
  {motion_layer(scene)}
  <div class="kicker mono">DATA · FROM ARTICLE</div>
  <h1 class="serif">{esc(scene.get('title'))}</h1>
  <p class="lead">{esc(short(scene.get('narration'), 92))}</p>
  {chart_html}
  {table_html}
  <footer class="mono">Source: 原文资料 · 情景数字不构成预测</footer>
</main>
""",
        """
.data{background:#f7f5ee;color:#161616}
.data h1{font-size:66px;line-height:1.1;margin:24px 0 18px;max-width:900px}.lead{font-size:30px;line-height:1.45;max-width:880px;color:#4a463d}
.chart{position:absolute;left:0;top:0}.chart line{stroke:#1a1a1a;stroke-width:2;opacity:.25}.bar{opacity:0;animation:slideIn .65s ease both}.bar text{font:26px Menlo,monospace;fill:#333}.bar .value{font-weight:800;fill:#111}
table{position:absolute;left:72px;right:72px;bottom:145px;width:936px;border-collapse:collapse;background:#fffaf0;border:1px solid #d7d0bf;font-size:22px}
th,td{padding:16px 14px;border-bottom:1px solid #ded6c8;text-align:left}th{background:#1b365d;color:#fff}td{color:#1f1d18}
footer{position:absolute;left:72px;bottom:78px;color:#777;font-size:18px}
@media (min-aspect-ratio: 4/3){
  .data .chart{top:0}
  .data table{left:72px;right:72px;top:330px;bottom:auto;width:calc(100% - 144px);font-size:20px}
  .data th,.data td{padding:13px 16px}
  .data footer{bottom:34px}
}
""",
    )


def render_verified_multi_line(scene: dict[str, Any], *, margin_mode: bool = False) -> str:
    variables = scene.get("variables") or {}
    series = variables.get("series") if isinstance(variables.get("series"), list) else []
    valid_series = []
    for index, item in enumerate(series[:6]):
        if not isinstance(item, dict):
            continue
        values = item.get("values") if isinstance(item.get("values"), list) else []
        points = []
        for value in values:
            if not isinstance(value, dict):
                continue
            try:
                points.append({"label": clean_text(value.get("label")), "value": float(value.get("value"))})
            except (TypeError, ValueError):
                continue
        if points:
            valid_series.append(
                {
                    "name": clean_text(item.get("name") or f"序列 {index + 1}"),
                    "color": clean_text(item.get("color") or ["#d6a84e", "#4ea3d8", "#e05f5f", "#62b88a", "#b487d6", "#f19b56"][index]),
                    "values": points,
                }
            )
    if not valid_series:
        return render_data(scene)

    all_values = [point["value"] for item in valid_series for point in item["values"]]
    min_value = min(all_values)
    max_value = max(all_values)
    padding = max((max_value - min_value) * 0.12, 0.35 if margin_mode else 1.0)
    chart_min = min_value - padding
    chart_max = max_value + padding
    chart_span = max(chart_max - chart_min, 1.0)
    x0, y0, chart_w, chart_h = 135.0, 85.0, 1180.0, 430.0
    max_points = max(len(item["values"]) for item in valid_series)

    grid = []
    for tick in range(5):
        ratio = tick / 4
        y = y0 + chart_h * ratio
        value = chart_max - chart_span * ratio
        label = f"{value:.2f}" if margin_mode else f"{value:.1f}"
        grid.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + chart_w}" y2="{y:.1f}"/><text x="{x0 - 20}" y="{y + 7:.1f}">{esc(label)}</text>')

    paths = []
    legends = []
    endpoint_labels = []
    date_labels = []
    reference_labels = valid_series[0]["values"]
    tick_indices = sorted(set([0, max(0, len(reference_labels) // 3), max(0, len(reference_labels) * 2 // 3), len(reference_labels) - 1]))
    for tick_index in tick_indices:
        point = reference_labels[tick_index]
        x = x0 + chart_w * tick_index / max(1, len(reference_labels) - 1)
        label = point["label"]
        if len(label) == 8 and label.isdigit():
            label = f"{int(label[4:6])}/{int(label[6:8])}"
        date_labels.append(f'<text class="date-label" x="{x:.1f}" y="575">{esc(label)}</text>')

    for index, item in enumerate(valid_series):
        coords = []
        for point_index, point in enumerate(item["values"]):
            x = x0 + chart_w * point_index / max(1, len(item["values"]) - 1)
            y = y0 + (chart_max - point["value"]) / chart_span * chart_h
            coords.append((x, y))
        d = " ".join(("M" if idx == 0 else "L") + f" {x:.1f} {y:.1f}" for idx, (x, y) in enumerate(coords))
        last_x, last_y = coords[-1]
        paths.append(
            f'<path class="verified-line line-{index}" d="{d}" style="--line-color:{esc(item["color"])};--line-delay:{index * .34:.2f}s"/>'
            f'<circle class="end-dot dot-{index}" cx="{last_x:.1f}" cy="{last_y:.1f}" r="7" fill="{esc(item["color"])}" style="--line-delay:{1.1 + index * .34:.2f}s"/>'
        )
        display = f'{item["values"][-1]["value"]:.4f}' if margin_mode else f'{item["values"][-1]["value"]:.2f}'
        endpoint_labels.append(
            f'<text class="endpoint endpoint-{index}" x="{last_x - 8:.1f}" y="{last_y - 15:.1f}" fill="{esc(item["color"])}" style="--line-delay:{1.3 + index * .34:.2f}s">{esc(display)}</text>'
        )
        legends.append(f'<span><i style="background:{esc(item["color"])}"></i>{esc(item["name"])}</span>')

    source_note = variables.get("source_note") or "来源：Tushare Pro · 抓取日期见证据清单"
    unit = variables.get("unit") or ("万亿元" if margin_mode else "2026-06-23 = 100")
    emphasis = variables.get("emphasis") or ""
    return scene_shell(
        scene,
        f"""
<main class="frame verified-chart">
  <div class="kicker mono">VERIFIED MARKET DATA</div>
  <header><h1>{esc(scene.get('title'))}</h1><p>{esc(short(scene.get('narration'), 115))}</p></header>
  <section class="chart-shell">
    <div class="chart-legend">{''.join(legends)}<b>{esc(unit)}</b></div>
    <svg viewBox="0 0 1500 650"><g class="chart-grid">{''.join(grid)}</g>{''.join(paths)}{''.join(endpoint_labels)}<g>{''.join(date_labels)}</g></svg>
    <div class="chart-emphasis">{esc(emphasis)}</div>
  </section>
  <footer>{esc(source_note)}</footer>
</main>
""",
        """
.verified-chart{background:#081018;color:#eef4f7;padding:38px 64px}.verified-chart header{display:grid;grid-template-columns:1.1fr .9fr;gap:50px;align-items:end}.verified-chart h1{font-size:54px;line-height:1.1;margin:14px 0 0}.verified-chart header p{font-size:24px;line-height:1.45;color:#b9c5cc;margin:0}
.chart-shell{position:absolute;left:64px;right:64px;top:205px;bottom:64px;background:linear-gradient(180deg,#0d1c28,#09141d);border:1px solid #345064;overflow:hidden}.chart-shell svg{width:100%;height:100%}.chart-grid line{stroke:#446072;stroke-width:1;opacity:.42}.chart-grid text,.date-label{fill:#8da0ac;font:17px Menlo,monospace;text-anchor:end}.date-label{text-anchor:middle}.verified-line{fill:none;stroke:var(--line-color);stroke-width:5;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:2600;stroke-dashoffset:2600;animation:verifiedLineDraw 2.35s cubic-bezier(.2,.8,.2,1) var(--line-delay) both}.end-dot,.endpoint{opacity:0;animation:verifiedPointReveal .45s ease var(--line-delay) both}.endpoint{font:800 18px Menlo,monospace;text-anchor:end}.chart-legend{position:absolute;left:76px;right:70px;top:26px;display:flex;align-items:center;gap:24px;z-index:3;font-size:19px;color:#c4cdd3}.chart-legend span{display:flex;align-items:center;gap:8px}.chart-legend i{width:24px;height:5px;display:inline-block}.chart-legend b{margin-left:auto;color:#d6a84e;font:700 17px Menlo,monospace}.chart-emphasis{position:absolute;right:54px;bottom:44px;max-width:520px;padding:15px 20px;background:rgba(214,168,78,.12);border-left:5px solid #d6a84e;color:#f1d899;font-size:23px;font-weight:800;opacity:0;animation:verifiedPointReveal .55s ease 3s both}.verified-chart footer{position:absolute;left:64px;bottom:30px;font:16px Menlo,monospace;color:#7f909b}
@keyframes verifiedLineDraw{to{stroke-dashoffset:0}}@keyframes verifiedPointReveal{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
""",
    )


def render_liquidation_stack(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else []
    colors = ["#d6a84e", "#4f9fbd", "#d25c5c", "#6db58b"]
    max_value = max([float(item.get("high") or item.get("value") or 0) for item in items if isinstance(item, dict)] + [1])
    rows = []
    for index, item in enumerate(items[:4]):
        if not isinstance(item, dict):
            continue
        low = float(item.get("low") or item.get("value") or 0)
        high = float(item.get("high") or item.get("value") or low)
        width = 240 + 920 * high / max_value
        display = item.get("display") or (f"{low:.0f}-{high:.0f} 亿元" if low != high else f"约 {high:.0f} 亿元")
        rows.append(
            f'<article class="pressure-row" style="--delay:{index * .45:.2f}s"><span>{esc(item.get("label"))}</span><div><i style="width:{width:.0f}px;background:{colors[index % len(colors)]}"></i><b>{esc(display)}</b></div><small>{esc(item.get("note"))}</small></article>'
        )
    return scene_shell(
        scene,
        f"""
<main class="frame liquidation-stack"><div class="kicker mono">SCENARIO STRESS TEST</div><h1>{esc(scene.get('title'))}</h1><p class="deck">{esc(short(scene.get('narration'), 105))}</p><section>{''.join(rows)}</section><footer><b>{esc(variables.get('total') or '合计潜在出清 9000-10000 亿元')}</b><span>作者情景测算，不是官方预测</span></footer></main>
""",
        """
.liquidation-stack{background:#f1ede4;color:#171b1f}.liquidation-stack h1{font-size:56px;margin:16px 0 10px}.liquidation-stack .deck{font-size:23px;line-height:1.45;color:#5a6065;max-width:1500px}.liquidation-stack section{margin-top:34px;display:grid;gap:18px}.pressure-row{display:grid;grid-template-columns:260px 1fr 330px;gap:25px;align-items:center;opacity:0;animation:pressureReveal .65s ease var(--delay) both}.pressure-row>span{font-size:29px;font-weight:850}.pressure-row div{height:68px;position:relative;background:#dcd7cd;overflow:hidden}.pressure-row i{display:block;height:100%;transform-origin:left;animation:pressureGrow 1.25s cubic-bezier(.2,.8,.2,1) var(--delay) both}.pressure-row b{position:absolute;inset:0;display:flex;align-items:center;padding-left:24px;color:#101418;font:850 25px Menlo,monospace}.pressure-row small{font-size:20px;line-height:1.35;color:#5a6065}.liquidation-stack footer{margin-top:28px;padding:22px 28px;background:#172f42;color:#fff;display:flex;justify-content:space-between;align-items:center}.liquidation-stack footer b{font-size:33px;color:#f0cf82}.liquidation-stack footer span{font-size:21px;color:#bdc9d0}
@keyframes pressureGrow{from{transform:scaleX(.02)}}@keyframes pressureReveal{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
""",
    )


def render_support_gap(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else []
    cards = []
    max_value = max([float(item.get("high") or 0) for item in items if isinstance(item, dict)] + [1])
    for index, item in enumerate(items[:3]):
        high = float(item.get("high") or 0)
        height = 120 + 390 * high / max_value
        tone = "need" if index else "current"
        cards.append(
            f'<article class="gap-bar {tone}"><div style="height:{height:.0f}px"><b>{esc(item.get("display"))}</b></div><span>{esc(item.get("label"))}</span><small>{esc(item.get("note"))}</small></article>'
        )
    return scene_shell(
        scene,
        f"""
<main class="frame support-gap"><div class="kicker mono">SUPPORT CAPACITY GAP</div><h1>{esc(scene.get('title'))}</h1><section>{''.join(cards)}<div class="gap-arrow"><b>缺口</b><span>{esc(variables.get('gap') or '约 700-1500 亿元/日')}</span></div></section><p class="safe-bottom caption">{esc(short(scene.get('narration'), 125))}</p></main>
""",
        """
.support-gap{background:#081018}.support-gap h1{font-size:58px;margin:18px 0}.support-gap section{position:absolute;left:260px;right:260px;top:210px;bottom:135px;display:flex;align-items:flex-end;justify-content:center;gap:160px;border-bottom:3px solid #718694}.gap-bar{width:360px;text-align:center}.gap-bar div{display:flex;align-items:flex-start;justify-content:center;padding-top:28px;background:linear-gradient(180deg,#5889a5,#29485d);transform-origin:bottom;animation:gapRise 1.2s cubic-bezier(.2,.8,.2,1) both}.gap-bar.need div{background:linear-gradient(180deg,#d6a84e,#8c6425);animation-delay:.45s}.gap-bar b{font:850 38px Menlo,monospace;color:#fff}.gap-bar>span{display:block;font-size:29px;font-weight:850;margin-top:18px}.gap-bar small{font-size:19px;color:#9eacb5}.gap-arrow{position:absolute;left:50%;top:165px;transform:translateX(-50%);display:grid;text-align:center;color:#e6c272}.gap-arrow:before{content:"";width:210px;height:6px;background:#d6a84e;margin:auto}.gap-arrow b{font-size:22px;margin-top:12px}.gap-arrow span{font:800 24px Menlo,monospace}
@keyframes gapRise{from{transform:scaleY(.02);opacity:.2}to{transform:scaleY(1);opacity:1}}
""",
    )


def render_tree_rescue(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    return scene_shell(
        scene,
        f"""
<main class="frame tree-rescue"><div class="kicker mono">CAPITAL MARKET · HARD TECH</div><h1>{esc(scene.get('title'))}</h1><section><svg viewBox="0 0 1100 650"><path class="ground" d="M80 550 C300 500 800 600 1020 530"/><path class="trunk" d="M540 540 C520 420 555 330 540 185"/><path class="branch b1" d="M545 360 C435 300 350 260 275 190"/><path class="branch b2" d="M548 320 C660 280 760 230 830 155"/><path class="branch b3" d="M535 430 C430 400 350 390 245 330"/><path class="branch b4" d="M548 420 C675 390 780 395 900 330"/><g class="leaves"><circle cx="260" cy="185" r="95"/><circle cx="845" cy="155" r="100"/><circle cx="225" cy="330" r="85"/><circle cx="915" cy="330" r="90"/><circle cx="540" cy="160" r="115"/></g><path class="water" d="M110 160 C210 220 300 305 430 485"/><circle class="drop" cx="110" cy="160" r="20"/></svg><div class="tree-label root">{esc(variables.get('root') or '股权融资')}</div><div class="tree-label crown">{esc(variables.get('crown') or '硬科技产业化')}</div><div class="tree-label water-label">{esc(variables.get('water') or '稳定预期与流动性')}</div></section><p class="safe-bottom caption">{esc(short(scene.get('narration'), 130))}</p></main>
""",
        """
.tree-rescue{background:linear-gradient(180deg,#07131c,#102331 70%,#172819)}.tree-rescue h1{font-size:62px;margin:18px 0}.tree-rescue section{position:absolute;left:360px;right:360px;top:170px;bottom:105px}.tree-rescue svg{width:100%;height:100%}.ground{fill:none;stroke:#627d54;stroke-width:12}.trunk,.branch{fill:none;stroke:#bc8c4d;stroke-width:28;stroke-linecap:round;stroke-dasharray:1200;stroke-dashoffset:1200;animation:treeGrow 2s ease .3s both}.branch{stroke-width:17}.b1{animation-delay:1.2s}.b2{animation-delay:1.4s}.b3{animation-delay:1.6s}.b4{animation-delay:1.8s}.leaves circle{fill:#3a825d;opacity:0;transform-box:fill-box;transform-origin:center;animation:leafPop .65s ease 2.15s both}.leaves circle:nth-child(2){animation-delay:2.3s}.leaves circle:nth-child(3){animation-delay:2.45s}.leaves circle:nth-child(4){animation-delay:2.6s}.leaves circle:nth-child(5){animation-delay:2.75s}.water{fill:none;stroke:#4ba9d6;stroke-width:12;stroke-dasharray:18 14;animation:waterFlow 1.8s linear infinite}.drop{fill:#80d4f0;animation:dropPulse 1s ease-in-out infinite}.tree-label{position:absolute;padding:13px 20px;background:rgba(7,16,24,.88);border:1px solid #587187;font-size:25px;font-weight:850}.root{left:44%;bottom:15px}.crown{left:42%;top:5px;color:#d7e9da}.water-label{left:-120px;top:130px;color:#9ddcf1}
@keyframes treeGrow{to{stroke-dashoffset:0}}@keyframes leafPop{from{opacity:0;transform:scale(.2)}to{opacity:.92;transform:scale(1)}}@keyframes waterFlow{to{stroke-dashoffset:-64}}@keyframes dropPulse{50%{r:28;opacity:.7}}
""",
    )


def render_article_chart(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    kind = str(variables.get("chart_kind") or "")
    if kind == "market_multi_line":
        return render_verified_multi_line(scene)
    if kind == "margin_balance":
        return render_verified_multi_line(scene, margin_mode=True)
    if kind == "liquidation_stack":
        return render_liquidation_stack(scene)
    if kind == "support_gap":
        return render_support_gap(scene)
    source_image = esc(variables.get("source_image") or "")
    source_note = esc(variables.get("source_note") or "原文图表重绘，数据口径沿用原文")

    if kind == "valuation_compare":
        chart = """
<svg class="article-chart-svg" viewBox="0 0 1500 650">
  <g class="axis"><line x1="150" y1="540" x2="1370" y2="540"/><line x1="150" y1="90" x2="150" y2="540"/></g>
  <g class="chart-bar bar-a"><rect x="310" y="130" width="330" height="410" rx="12"/><text x="475" y="105">1.28 万亿元</text><text x="475" y="590">SpaceX 估值</text></g>
  <g class="chart-bar bar-b"><rect x="900" y="490" width="330" height="50" rx="12"/><text x="1065" y="465">855 亿元</text><text x="1065" y="590">中国商业航天 Top5</text></g>
  <g class="annotation"><path d="M 1050 430 C 1140 350, 1210 300, 1290 245"/><text x="1120" y="230">约 15 倍差距</text></g>
</svg>
"""
    elif kind == "core_metrics":
        metrics = [
            ("发射成本", "$2,700/kg", "$7,500/kg", 36, 100),
            ("2025 营收", "186.7 亿元", "0.7 亿元", 100, 5),
            ("年发射次数", "165 次", "50 次", 100, 30),
            ("累计亏损", "49 亿美元", "67 亿美元", 73, 100),
            ("估值/营收", "100×", "1,400×", 7, 100),
        ]
        panels = []
        for idx, (label, left_text, right_text, left_h, right_h) in enumerate(metrics):
            x = 42 + idx * 292
            panels.append(
                f'<g class="metric-panel metric-{idx}"><text class="metric-title" x="{x+120}" y="90">{esc(label)}</text>'
                f'<rect class="spacex" x="{x+35}" y="{500-left_h*3.2:.1f}" width="82" height="{left_h*3.2:.1f}" rx="8"/>'
                f'<rect class="china" x="{x+145}" y="{500-right_h*3.2:.1f}" width="82" height="{right_h*3.2:.1f}" rx="8"/>'
                f'<text x="{x+76}" y="540">SpaceX</text><text x="{x+186}" y="540">中国</text>'
                f'<text class="value-label" x="{x+76}" y="{470-left_h*3.2:.1f}">{esc(left_text)}</text>'
                f'<text class="value-label" x="{x+186}" y="{470-right_h*3.2:.1f}">{esc(right_text)}</text></g>'
            )
        chart = f'<svg class="article-chart-svg core-metrics" viewBox="0 0 1500 650">{"".join(panels)}</svg>'
    elif kind == "supply_chain":
        rows = [
            ("卫星载荷平台", 60, 40),
            ("发射场/回收设施", 75, 25),
            ("地面测控网络", 80, 20),
            ("制导/导航系统", 90, 10),
            ("箭体结构材料", 70, 30),
            ("发动机核心部件", 85, 15),
        ]
        bars = []
        for idx, (label, state, private) in enumerate(rows):
            y = 95 + idx * 82
            bars.append(
                f'<g class="stack-row row-{idx}"><text x="30" y="{y+31}">{esc(label)}</text>'
                f'<rect class="state" x="310" y="{y}" width="{state*10.2}" height="44" rx="8"/>'
                f'<rect class="private" x="{310+state*10.2}" y="{y}" width="{private*10.2}" height="44" rx="8"/>'
                f'<text class="inside" x="{310+state*5.1}" y="{y+30}">{state}%</text>'
                f'<text class="inside light" x="{310+state*10.2+private*5.1}" y="{y+30}">{private}%</text></g>'
            )
        chart = f'<svg class="article-chart-svg supply" viewBox="0 0 1500 650">{"".join(bars)}<g class="legend"><rect x="1040" y="610" width="22" height="22"/><text x="1070" y="628">军工/国有体系供给</text><rect class="private" x="1260" y="610" width="22" height="22"/><text x="1290" y="628">纯民营供给</text></g></svg>'
    elif kind == "margin_compare":
        values = [("SpaceX\n星链业务", 45, "#278f43"), ("SpaceX\n整体", -14, "#8e8e92"), ("A股军工\n行业均值", 22, "#cda827"), ("中国商业\n航天公司", -50, "#df001b")]
        bars = []
        for idx, (label, value, color) in enumerate(values):
            x = 230 + idx * 310
            y = 315 - max(value, 0) * 5
            height = abs(value) * 5
            if value < 0:
                y = 315
            lines = label.split("\n")
            value_y = y - 18 if value >= 0 else y + height - 22
            value_class = "profit-value" if value >= 0 else "profit-value negative"
            bars.append(
                f'<g class="profit-bar profit-{idx}"><rect x="{x}" y="{y}" width="170" height="{height}" rx="9" fill="{color}"/>'
                f'<text class="{value_class}" x="{x+85}" y="{value_y}">{value}%</text>'
                f'<text x="{x+85}" y="{590}">{esc(lines[0])}</text><text x="{x+85}" y="{620}">{esc(lines[1])}</text></g>'
            )
        chart = f'<svg class="article-chart-svg profit" viewBox="0 0 1500 650"><line class="zero" x1="120" y1="315" x2="1420" y2="315"/>{"".join(bars)}</svg>'
    else:
        return render_data(scene)

    return scene_shell(
        scene,
        f"""
<main class="frame article-chart">
  <header><p class="kicker mono">ARTICLE DATA · DYNAMIC REDRAW</p><h1>{esc(scene.get('title'))}</h1></header>
  <section class="source-chart"><div><span>原文图表</span><img src="{source_image}" alt="原文图表"></div></section>
  <section class="dynamic-chart">{chart}</section>
  <footer><span>{source_note}</span><b>原文数据口径 · 仅作分析情景，不构成预测</b></footer>
</main>
""",
        """
.article-chart{background:#f5f2ea;color:#17191d;padding:44px 64px}
.article-chart header{position:relative;z-index:5}.article-chart h1{font-size:54px;line-height:1.12;margin:12px 0 0;max-width:1450px}.article-chart .kicker{margin:0}
.source-chart,.dynamic-chart{position:absolute;left:64px;right:64px;top:160px;bottom:92px}
.source-chart{z-index:3;display:flex;align-items:center;justify-content:center;background:#ede9df;animation:sourceChartExit 2.8s cubic-bezier(.7,0,.3,1) 1 both}
.source-chart div{width:86%;height:82%;padding:22px;background:#fff;border:1px solid #d7d1c4;box-shadow:0 22px 70px rgba(30,33,38,.16)}
.source-chart span{display:block;font:700 18px Menlo,monospace;color:#9a6b24;margin-bottom:12px}.source-chart img{width:100%;height:calc(100% - 34px);object-fit:contain}
.dynamic-chart{z-index:2;background:#fbfaf6;border:1px solid #d7d1c4;opacity:0;animation:dynamicChartEnter .9s ease 2.1s 1 both;overflow:hidden}
.article-chart-svg{width:100%;height:100%}.article-chart-svg text{font-family:"PingFang SC","Noto Sans SC",sans-serif;fill:#3f4248;font-size:24px;text-anchor:middle}.article-chart-svg .axis line,.profit .zero{stroke:#aeb2b8;stroke-width:2}
.chart-bar rect{transform-box:fill-box;transform-origin:center bottom;animation:articleBarGrow 1.2s cubic-bezier(.2,.8,.2,1) 2.8s 1 both}.chart-bar text{font-size:28px;font-weight:750}.bar-a rect{fill:#0b74de}.bar-b rect{fill:#df001b;animation-delay:3.25s}.annotation{opacity:0;animation:annotationEnter .7s ease 4.5s 1 both}.annotation path{fill:none;stroke:#df001b;stroke-width:5}.annotation text{fill:#df001b;font-size:30px;font-weight:800}
.metric-panel rect{transform-box:fill-box;transform-origin:center bottom;animation:articleBarGrow .95s cubic-bezier(.2,.8,.2,1) 1 both}.metric-panel .spacex{fill:#0b74de}.metric-panel .china{fill:#df001b}.metric-0 rect{animation-delay:2.7s}.metric-1 rect{animation-delay:3.2s}.metric-2 rect{animation-delay:3.7s}.metric-3 rect{animation-delay:4.2s}.metric-4 rect{animation-delay:4.7s}.metric-title{font-size:23px!important;font-weight:800}.value-label{font-size:18px!important;font-weight:750}
.stack-row rect{transform-box:fill-box;transform-origin:left center;animation:stackGrow 1s cubic-bezier(.2,.8,.2,1) 1 both}.stack-row .state,.legend rect{fill:#c6c7cc}.stack-row .private,.legend .private{fill:#0b74de}.stack-row text{font-size:22px;text-anchor:start}.stack-row .inside{text-anchor:middle;font-weight:750}.stack-row .light{fill:#fff}.row-0 rect{animation-delay:2.6s}.row-1 rect{animation-delay:3s}.row-2 rect{animation-delay:3.4s}.row-3 rect{animation-delay:3.8s}.row-4 rect{animation-delay:4.2s}.row-5 rect{animation-delay:4.6s}.legend text{font-size:17px;text-anchor:start}
.profit-bar rect{transform-box:fill-box;transform-origin:center top;animation:profitGrow 1.05s cubic-bezier(.2,.8,.2,1) 1 both}.profit-0 rect{transform-origin:center bottom;animation-name:articleBarGrow;animation-delay:2.7s}.profit-1 rect{animation-delay:3.2s}.profit-2 rect{transform-origin:center bottom;animation-name:articleBarGrow;animation-delay:3.7s}.profit-3 rect{animation-delay:4.2s}.profit-value{font-size:30px!important;font-weight:850}.profit-value.negative{fill:#fff!important}.profit text{font-size:22px}
.article-chart footer{position:absolute;left:64px;right:64px;bottom:28px;display:flex;justify-content:space-between;color:#686a70;font-size:17px}.article-chart footer b{color:#9a6b24}
@keyframes sourceChartExit{0%,52%{opacity:1;transform:none}72%,100%{opacity:0;transform:translateX(-80px) scale(.96)}}
@keyframes dynamicChartEnter{from{opacity:0;transform:translateX(70px)}to{opacity:1;transform:none}}
@keyframes articleBarGrow{from{transform:scaleY(.02);opacity:.25}to{transform:scaleY(1);opacity:1}}
@keyframes stackGrow{from{transform:scaleX(.02);opacity:.25}to{transform:scaleX(1);opacity:1}}
@keyframes profitGrow{from{transform:scaleY(.02);opacity:.25}to{transform:scaleY(1);opacity:1}}
@keyframes annotationEnter{from{opacity:0;transform:translate(-18px,18px)}to{opacity:1;transform:none}}
""",
    )


def render_rollup(scene: dict[str, Any]) -> str:
    rows = chart_rows(scene)[:6]
    cards = []
    for idx, row in enumerate(rows):
        cards.append(
            f"""
<div class="metric rise" style="animation-delay:{idx * .1:.2f}s">
  <span>{esc(row["label"])}</span>
  <b>{esc(row["display"])}</b>
</div>
"""
        )
    return scene_shell(
        scene,
        f"""
<main class="frame rollup">
  {motion_layer(scene)}
  <p class="kicker mono">DATA ROLLUP</p>
  <h1>{esc(scene.get('title'))}</h1>
  <section>{''.join(cards)}</section>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.rollup{background:#07111f;color:#eef6ff;background-image:radial-gradient(circle at 82% 18%,rgba(32,98,160,.35),transparent 32%)}
.rollup h1{font-size:64px;line-height:1.12;margin:26px 0 44px;max-width:840px}
.rollup section{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:70px}
.metric{min-height:205px;padding:28px;border:1px solid rgba(216,170,85,.34);border-radius:28px;background:linear-gradient(145deg,rgba(255,255,255,.08),rgba(255,255,255,.02));box-shadow:0 20px 60px rgba(0,0,0,.24)}
.metric span{display:block;color:#93a8c2;font-size:23px;line-height:1.35}.metric b{display:block;margin-top:24px;color:#f0c766;font-size:58px;line-height:1;font-family:Menlo,monospace}
""",
    )


def render_stat(scene: dict[str, Any]) -> str:
    rows = chart_rows(scene)
    primary = rows[0] if rows else {"label": "关键数字", "display": short(scene.get("title"), 10)}
    secondary = rows[1:4]
    chips = "".join(f"<li><b>{esc(row['display'])}</b><span>{esc(row['label'])}</span></li>" for row in secondary)
    return scene_shell(
        scene,
        f"""
<main class="frame stat">
  {motion_layer(scene)}
  <div class="orb"></div>
  <p class="kicker mono">KEY NUMBER</p>
  <h1>{esc(primary['display'])}</h1>
  <h2>{esc(primary['label'])}</h2>
  <p>{esc(short(scene.get('narration'), 118))}</p>
  <ul>{chips}</ul>
</main>
""",
        """
.stat{background:#0b0c10;color:#fff}.orb{position:absolute;right:-180px;top:230px;width:680px;height:680px;border-radius:50%;background:radial-gradient(circle,#d8aa55,rgba(216,170,85,.18) 42%,transparent 70%);filter:blur(10px);opacity:.45}
.stat .kicker{margin-top:310px}.stat h1{position:relative;margin:24px 0 8px;font-size:142px;line-height:.92;color:#f2c86b;letter-spacing:-.08em}.stat h2{position:relative;margin:0 0 36px;font-size:46px;color:#e8edf7}
.stat p{position:relative;max-width:780px;font-size:32px;line-height:1.5;color:#c8ced8}.stat ul{position:absolute;left:72px;right:72px;bottom:120px;display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:0;margin:0}
.stat li{list-style:none;padding:18px;border:1px solid rgba(255,255,255,.14);border-radius:20px;background:rgba(255,255,255,.06)}.stat li b{display:block;color:#f2c86b;font-size:28px}.stat li span{font-size:20px;color:#aeb8c8}
""",
    )


def render_line_graph(scene: dict[str, Any]) -> str:
    rows = chart_rows(scene)[:7]
    values = [float(row["value"]) for row in rows] or [0.0]
    max_v = max(values)
    min_v = min(values)
    span = max(max_v - min_v, 1.0)
    points = []
    labels = []
    for idx, row in enumerate(rows):
        x = 120 + idx * (820 / max(1, len(rows) - 1))
        y = 1110 - ((float(row["value"]) - min_v) / span) * 420
        points.append(f"{x:.1f},{y:.1f}")
        labels.append(f'<text x="{x:.1f}" y="1188">{esc(row["label"])}</text>')
    point_tags = "".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="9" />' for p in points)
    return scene_shell(
        scene,
        f"""
<main class="frame nyt">
  {motion_layer(scene)}
  <p class="kicker mono">REAL DATA LINE</p>
  <h1 class="serif">{esc(scene.get('title'))}</h1>
  <p class="lead">{esc(short(scene.get('narration'), 100))}</p>
  <svg viewBox="0 0 {WIDTH} {HEIGHT}">
    <g class="grid"><line x1="100" y1="690" x2="1000" y2="690"/><line x1="100" y1="900" x2="1000" y2="900"/><line x1="100" y1="1110" x2="1000" y2="1110"/></g>
    <polyline points="{' '.join(points)}" />
    {point_tags}
    <g class="labels">{''.join(labels)}</g>
  </svg>
  <footer class="mono">Source: 原文数据 / 图表变量</footer>
</main>
""",
        """
.nyt{background:#fbf7ef;color:#151515}.nyt h1{font-size:64px;line-height:1.12;margin:24px 0 18px;max-width:880px}.lead{font-size:28px;line-height:1.45;color:#524d45;max-width:880px}
.nyt svg{position:absolute;left:0;top:0}.grid line{stroke:#d7d0c2;stroke-width:2}.nyt polyline{fill:none;stroke:#1c5d89;stroke-width:8;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1800;animation:drawline 1.2s ease both}.nyt circle{fill:#d8aa55;stroke:#111;stroke-width:3}.labels text{font:20px Menlo,monospace;fill:#5b564d;text-anchor:middle}
.nyt footer{position:absolute;left:72px;bottom:78px;color:#777;font-size:18px}@keyframes drawline{from{stroke-dashoffset:1800}to{stroke-dashoffset:0}}
""",
    )


def render_dashboard(scene: dict[str, Any]) -> str:
    rows = chart_rows(scene)[:6]
    if not rows:
        units = split_units(scene.get("narration", ""), 4)
        cards = "".join(
            f"<div class=\"judgement-card\"><b>{idx:02d}</b><span>{esc(unit)}</span></div>"
            for idx, unit in enumerate(units, 1)
        )
        focus_items = "".join(
            f'<article class="report-focus focus-{idx-1}"><b>{idx:02d}</b><span>{esc(unit)}</span></article>'
            for idx, unit in enumerate(units[:4], 1)
        )
        return scene_shell(
            scene,
            f"""
<main class="frame report">
  {motion_layer(scene)}
  <p class="kicker mono">INVESTMENT JUDGEMENT</p>
  <h1>{esc(scene.get('title'))}</h1>
  <section>{cards}</section>
  <div class="report-focus-stage">{focus_items}</div>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
            """
.report{background:#081018;color:#eaf2f8;background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:48px 48px}
.report h1{font-size:56px;line-height:1.12;margin:18px 0 30px;max-width:1500px}
.report section{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;max-width:1500px}
.judgement-card{min-height:190px;padding:24px 28px;border:1px solid rgba(95,170,215,.28);border-radius:24px;background:linear-gradient(145deg,rgba(12,45,67,.94),rgba(8,27,42,.9));display:flex;gap:20px;align-items:flex-start}
.judgement-card b{color:#f2c86b;font:700 28px Menlo,monospace}
.judgement-card span{font-size:29px;line-height:1.42;color:#eef4f8;font-weight:650}
.report .safe-bottom{font-size:20px;color:#9fb0be}
.report-focus-stage{position:absolute;inset:0;pointer-events:none}
.report-focus{position:absolute;inset:0;padding:250px 190px 170px;background:rgba(8,16,24,.99);display:flex;align-items:center;gap:55px;opacity:0;animation:reportFocusSequence 12s linear 1 both}
.report-focus b{font:800 72px Menlo,monospace;color:#f2c86b}
.report-focus span{font-size:62px;line-height:1.22;font-weight:850;max-width:1320px;color:#f4f8fb}
.report-focus.focus-1{animation-delay:3s}.report-focus.focus-2{animation-delay:6s}.report-focus.focus-3{animation-delay:9s}
@keyframes reportFocusSequence{0%,4%{opacity:0;transform:translateX(32px)}7%,20%{opacity:1;transform:none}24%,100%{opacity:0;transform:translateX(-24px)}}
""",
        )
    cards = []
    for idx, row in enumerate(rows):
        pct = min(100, max(8, abs(float(row["value"]))))
        cards.append(
            f"""
<div class="dash-card">
  <span>{esc(row['label'])}</span>
  <b>{esc(row['display'])}</b>
  <i><em style="width:{pct}%"></em></i>
</div>
"""
        )
    return scene_shell(
        scene,
        f"""
<main class="frame dash">
  {motion_layer(scene)}
  <p class="kicker mono">LIVE DASHBOARD</p>
  <h1>{esc(scene.get('title'))}</h1>
  <section>{''.join(cards)}</section>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.dash{background:#081018;color:#eaf2f8;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:46px 46px}
.dash h1{font-size:60px;line-height:1.12;margin:22px 0 42px;max-width:880px}.dash section{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:62px}
.dash-card{padding:24px;border:1px solid rgba(95,170,215,.28);border-radius:24px;background:rgba(8,32,50,.82);box-shadow:inset 0 0 0 1px rgba(255,255,255,.04)}
.dash-card span{display:block;color:#8fb4d0;font-size:22px}.dash-card b{display:block;margin:16px 0;color:#f2c86b;font-size:44px;font-family:Menlo,monospace}.dash-card i{display:block;height:8px;background:#172838;border-radius:999px;overflow:hidden}.dash-card em{display:block;height:100%;background:linear-gradient(90deg,#1f77a8,#d8aa55);animation:barGrow .9s ease both}
""",
    )


def render_social(scene: dict[str, Any]) -> str:
    return scene_shell(
        scene,
        f"""
<main class="frame social">
  {motion_layer(scene)}
  <article>
    <header><b>Market Desk</b><span>@dasheng · now</span></header>
    <h1>{esc(scene.get('title'))}</h1>
    <p>{esc(short(scene.get('narration'), 170))}</p>
    <footer>转发 1.8万 · 评论 6,420 · 收藏 3.1万</footer>
  </article>
</main>
""",
        """
.social{background:linear-gradient(135deg,#eef4ff,#f8efe1);color:#111827}.social article{position:absolute;left:90px;right:90px;top:420px;padding:42px;border-radius:34px;background:#fff;box-shadow:0 30px 90px rgba(15,23,42,.18)}
.social header{display:flex;gap:18px;align-items:baseline;font-size:26px}.social header span{color:#697386;font-size:20px}.social h1{font-size:54px;line-height:1.15;margin:34px 0 26px}.social p{font-size:31px;line-height:1.55;color:#253043}.social footer{margin-top:32px;color:#667085;font-size:22px;border-top:1px solid #e5e7eb;padding-top:20px}
""",
    )


def render_swiss_grid(scene: dict[str, Any]) -> str:
    units = split_units(scene.get("narration", ""), 6)
    cells = "".join(f"<li><b>{idx+1:02d}</b><span>{esc(unit)}</span></li>" for idx, unit in enumerate(units))
    return scene_shell(
        scene,
        f"""
<main class="frame swiss">
  {motion_layer(scene)}
  <p class="kicker mono">SWISS GRID</p>
  <h1>{esc(scene.get('title'))}</h1>
  <ul>{cells}</ul>
</main>
""",
        """
.swiss{background:#f5f1e8;color:#111}.swiss:before{content:"";position:absolute;inset:72px;border:3px solid #111}.swiss h1{font-size:64px;line-height:1.08;margin:64px 0 60px;max-width:860px;text-transform:uppercase}.swiss ul{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0;padding:0;border-top:2px solid #111;border-left:2px solid #111}
.swiss li{list-style:none;min-height:190px;padding:24px;border-right:2px solid #111;border-bottom:2px solid #111}.swiss li b{display:block;color:#b8862f;font-size:28px;margin-bottom:18px}.swiss li span{font-size:29px;line-height:1.28;font-weight:800}
""",
    )


def render_takram(scene: dict[str, Any]) -> str:
    nodes = split_units(scene.get("narration", ""), 6)
    positions = [(180, 610), (620, 540), (420, 840), (220, 1120), (690, 1120), (480, 1360)]
    html_nodes = []
    lines = []
    for idx, node in enumerate(nodes):
        x, y = positions[idx % len(positions)]
        html_nodes.append(f'<div class="bubble" style="left:{x}px;top:{y}px">{esc(node)}</div>')
        if idx:
            px, py = positions[idx - 1]
            lines.append(f'<line x1="{px+110}" y1="{py+70}" x2="{x+110}" y2="{y+70}" />')
    return scene_shell(
        scene,
        f"""
<main class="frame organic">
  {motion_layer(scene)}
  <p class="kicker mono">SYSTEM MAP</p>
  <h1>{esc(scene.get('title'))}</h1>
  <svg viewBox="0 0 {WIDTH} {HEIGHT}">{''.join(lines)}</svg>
  {''.join(html_nodes)}
</main>
""",
        """
.organic{background:#f0eee7;color:#172017}.organic h1{font-size:60px;line-height:1.12;margin:24px 0 0;max-width:860px}.organic svg{position:absolute;inset:0}.organic line{stroke:#6a7d56;stroke-width:5;stroke-linecap:round;opacity:.45;stroke-dasharray:18 10}
.bubble{position:absolute;width:245px;min-height:145px;padding:26px;border-radius:44% 56% 52% 48%;background:#d7e7c6;color:#172017;font-size:28px;line-height:1.22;font-weight:800;display:flex;align-items:center;box-shadow:0 18px 44px rgba(43,61,38,.18);animation:rise .8s ease both}.bubble:nth-of-type(odd){background:#c8dde8}
""",
    )


def render_alert(scene: dict[str, Any]) -> str:
    bullets = split_units(scene.get("narration", ""), 4)
    lis = "".join(f"<li>{esc(item)}</li>" for item in bullets)
    return scene_shell(
        scene,
        f"""
<main class="frame alert">
  <div class="stripe"></div>
  {motion_layer(scene)}
  <p class="mono kicker">RISK ALERT</p>
  <h1>{esc(scene.get('title'))}</h1>
  <ul>{lis}</ul>
  <div class="safe-bottom mono">WATCH: POLICY · LIQUIDITY · POSITIONING</div>
</main>
""",
        """
.alert{background:#130807;color:#fff4ea}.stripe{position:absolute;left:-80px;right:-80px;top:0;height:190px;background:repeating-linear-gradient(135deg,#2b0505 0 34px,#c2410c 34px 68px)}
.alert .kicker{margin-top:260px;color:#ffbd6b}.alert h1{font-size:74px;line-height:1.08;margin:30px 0 60px;max-width:870px;text-decoration:line-through;text-decoration-color:#ff6b47}
.alert li{list-style:none;margin:0 0 28px;padding:24px 28px;border-left:8px solid #ff6b47;background:#26100e;font-size:34px;line-height:1.35;animation:rise .7s ease both}
""",
    )


def render_quote(scene: dict[str, Any]) -> str:
    quote = (scene.get("variables") or {}).get("quote") or scene.get("narration") or scene.get("title")
    return scene_shell(
        scene,
        f"""
<main class="frame quote">
  {motion_layer(scene)}
  <div class="card rise">
    <p class="mark">“</p>
    <h1 class="serif">{esc(quote)}</h1>
    <p class="mono">— 关键判断 · FROM ARTICLE</p>
  </div>
</main>
""",
        """
.quote{background:#111827;background-image:radial-gradient(circle at 18% 20%,rgba(216,170,85,.2),transparent 32%),radial-gradient(circle at 78% 70%,rgba(31,95,139,.25),transparent 30%)}
.card{position:absolute;left:72px;right:72px;top:420px;padding:68px;background:#f7f2e7;color:#14120f;border-radius:42px;box-shadow:0 30px 90px rgba(0,0,0,.38)}
.mark{font-size:120px;margin:0;color:#b67b2f}.quote h1{font-size:62px;line-height:1.2;margin:-30px 0 42px}.quote .mono{font-size:22px;color:#686055}
""",
    )


def render_document(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    image_src = esc(variables.get("src") or "")
    display_title = variables.get("alt") if str(scene.get("title") or "").startswith("资料画面") else scene.get("title")
    image_block = (
        f'<img src="{image_src}" alt="{esc(variables.get("alt"))}">'
        if image_src
        else f'<div class="evidence-note"><b>{esc(scene.get("title"))}</b><span>{esc(short(scene.get("narration"), 120))}</span></div>'
    )
    overlay_labels = variables.get("overlay_labels") if isinstance(variables.get("overlay_labels"), list) else []
    overlays = "".join(
        f'<span class="doc-overlay overlay-{index}">{esc(label)}</span>'
        for index, label in enumerate(overlay_labels[:4])
    )
    return scene_shell(
        scene,
        f"""
<main class="frame doc">
  {motion_layer(scene)}
  <section class="paper">
    <p class="mono">DOCUMENT EVIDENCE</p>
    <h1 class="serif">{esc(display_title)}</h1>
    <div class="document-stage">{image_block}{overlays}</div>
  </section>
</main>
""",
        """
.doc{background:#0b1118;color:#f1eee7}.paper{position:absolute;left:64px;right:64px;top:52px;bottom:52px;background:#111b25;border:1px solid #334759;padding:38px 44px;overflow:hidden}
.paper .mono{color:#d6a84e;letter-spacing:.14em}.paper h1{font-size:52px;line-height:1.12;margin:14px 0 20px;max-width:1500px}
.document-stage{position:relative;height:650px;background:#081018;border:1px solid #40566a;overflow:hidden}
.document-stage img,.document-stage .evidence-note{display:block;width:100%;height:100%;object-fit:cover;background:#0a1219;margin:0;border:0;filter:saturate(.82) contrast(1.04)}
.document-stage:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(4,8,12,.62),transparent 42%,rgba(4,8,12,.18));pointer-events:none}
.evidence-note{padding:58px;display:flex!important;flex-direction:column;justify-content:center;border-left:10px solid #d6a84e!important}.evidence-note b{font-size:54px;line-height:1.15;margin-bottom:34px}.evidence-note span{font-size:32px;line-height:1.5;color:#cbd3d9}
.doc-overlay{position:absolute;z-index:4;left:70px;padding:14px 20px;background:rgba(8,16,24,.9);border-left:6px solid #d6a84e;color:#fff;font-size:29px;font-weight:850;opacity:0;animation:docLabelReveal .7s ease both}.overlay-0{top:95px;animation-delay:.45s}.overlay-1{top:190px;animation-delay:1.35s}.overlay-2{top:285px;animation-delay:2.25s}.overlay-3{top:380px;animation-delay:3.15s}
@keyframes docLabelReveal{from{opacity:0;transform:translateX(-45px)}to{opacity:1;transform:none}}
""",
    )


def render_route_map(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    headings = variables.get("headings") if isinstance(variables.get("headings"), list) else []
    headings = [short(item, 22) for item in headings[:8] if clean_text(item)]
    cards = "".join(
        f'<article class="route-card" style="--delay:{index * .16:.2f}s"><b>{index + 1:02d}</b><span>{esc(item)}</span></article>'
        for index, item in enumerate(headings)
    )
    return scene_shell(
        scene,
        f"""
<main class="frame route-map">
  <div class="kicker mono">DIRECTOR ROUTE · 7 QUESTIONS</div>
  <h1>{esc(scene.get('title'))}</h1>
  <section class="route-grid">{cards}</section>
  <div class="route-progress"><i></i></div>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.route-map{background:#f2eee5;color:#181a1f;background-image:radial-gradient(circle at 92% 8%,rgba(18,77,112,.13),transparent 30%)}
.route-map h1{font-size:62px;margin:20px 0 34px}.route-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;position:relative;z-index:2}
.route-card{min-height:178px;padding:25px;border:1px solid #c9c4b7;background:rgba(255,255,255,.74);box-shadow:0 16px 35px rgba(24,26,31,.08);animation:routeReveal .62s ease var(--delay) both}
.route-card:nth-child(4n+2),.route-card:nth-child(4n+4){background:#17344a;color:#f7f3e9;border-color:#17344a}.route-card b{display:block;color:#c89232;font:800 22px Menlo,monospace;margin-bottom:20px}.route-card span{font-size:26px;line-height:1.25;font-weight:800}
.route-progress{height:5px;background:#d9d4c9;margin-top:28px;overflow:hidden}.route-progress i{display:block;height:100%;background:#c89232;animation:routeLine 1.7s ease .2s both}
@keyframes routeReveal{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}@keyframes routeLine{from{width:0}to{width:100%}}
""",
    )


def render_source_web_evidence(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    sources = variables.get("sources") if isinstance(variables.get("sources"), list) else []
    cards = []
    for index, source in enumerate(sources[:2]):
        if not isinstance(source, dict):
            continue
        cards.append(
            f"""
<article class="web-source" style="--delay:{index * .38:.2f}s">
  <div class="browser-bar"><i></i><i></i><i></i><span>{esc(source.get('url'))}</span></div>
  <img src="{esc(source.get('src'))}" alt="{esc(source.get('label'))}">
  <footer><b>{esc(source.get('label'))}</b><span>{esc(source.get('claim'))}</span></footer>
</article>
"""
        )
    return scene_shell(
        scene,
        f"""
<main class="frame web-evidence">
  <div class="kicker mono">SOURCE EVIDENCE · OFFICIAL WEBSITE</div>
  <h1>{esc(scene.get('title'))}</h1>
  <section class="web-grid">{''.join(cards)}</section>
  <p class="safe-bottom source-line">{esc(variables.get('source_note') or '来源：机构官方网站，截图时间见证据清单')}</p>
</main>
""",
        """
.web-evidence{background:#0b1118}.web-evidence h1{font-size:54px;margin:18px 0 24px}.web-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.web-source{background:#f7f5ef;color:#12171d;border:1px solid #34485a;box-shadow:0 28px 70px rgba(0,0,0,.34);overflow:hidden;animation:webReveal .82s ease var(--delay) both}.browser-bar{height:42px;background:#e9e6dd;display:flex;align-items:center;gap:7px;padding:0 14px}.browser-bar i{width:10px;height:10px;border-radius:50%;background:#c89232}.browser-bar i:nth-child(2){background:#7890a4}.browser-bar i:nth-child(3){background:#496a80}.browser-bar span{font:15px Menlo,monospace;color:#65717b;margin-left:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.web-source img{width:100%;height:480px;object-fit:cover;display:block}.web-source footer{padding:18px 22px 22px;display:grid;gap:8px}.web-source footer b{font-size:25px}.web-source footer span{font-size:19px;line-height:1.4;color:#56616b}.source-line{font:18px Menlo,monospace;color:#8694a1}
@keyframes webReveal{from{opacity:0;transform:translateY(32px) scale(.985)}to{opacity:1;transform:none}}
""",
    )


def render_business_flywheel(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else ["低成本发射", "部署星链", "终端订阅", "现金反哺运力"]
    items = [short(item, 18) for item in items[:4]]
    nodes = "".join(
        f'<article class="wheel-node wheel-{index}"><b>{index + 1:02d}</b><span>{esc(item)}</span></article>'
        for index, item in enumerate(items)
    )
    return scene_shell(
        scene,
        f"""
<main class="frame flywheel">
  <div class="kicker mono">BUSINESS FLYWHEEL</div><h1>{esc(scene.get('title'))}</h1>
  <section class="wheel-stage"><svg viewBox="0 0 900 620"><ellipse cx="450" cy="310" rx="330" ry="220"/><path d="M450 68 l28 18 -28 18"/><path d="M782 310 l-18 28 -18-28"/></svg>{nodes}<div class="wheel-core">闭环利润<br><strong>留在公司</strong></div></section>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.flywheel{background:radial-gradient(circle at 50% 52%,#173750,#081018 52%,#05080c);color:#f7f2e8}.flywheel h1{font-size:58px;margin:18px 0 0}.wheel-stage{position:absolute;left:260px;right:260px;top:190px;bottom:120px}.wheel-stage svg{position:absolute;inset:0;width:100%;height:100%}.wheel-stage ellipse,.wheel-stage path{fill:none;stroke:#d5a548;stroke-width:6;stroke-dasharray:14 10;animation:wheelDraw 1.8s ease both}.wheel-stage path{fill:#d5a548;stroke:none}.wheel-node{position:absolute;width:240px;min-height:120px;border:1px solid #57728a;background:rgba(10,25,38,.94);padding:18px 20px;box-shadow:0 20px 46px rgba(0,0,0,.3);animation:wheelNode .65s ease both}.wheel-node b{display:block;color:#d5a548;font:800 18px Menlo,monospace;margin-bottom:10px}.wheel-node span{font-size:25px;line-height:1.2;font-weight:800}.wheel-0{left:330px;top:10px}.wheel-1{right:0;top:245px;animation-delay:.35s}.wheel-2{left:330px;bottom:0;animation-delay:.7s}.wheel-3{left:0;top:245px;animation-delay:1.05s}.wheel-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:250px;height:250px;border-radius:50%;border:1px solid #d5a548;background:#f0e7d5;color:#14212b;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;font-size:28px;line-height:1.3;box-shadow:0 0 65px rgba(213,165,72,.18)}.wheel-core strong{font-size:34px}
@keyframes wheelDraw{from{stroke-dashoffset:900;opacity:0}to{stroke-dashoffset:0;opacity:1}}@keyframes wheelNode{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:scale(1)}}
""",
    )


def render_customer_funnel(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    suppliers = variables.get("suppliers") if isinstance(variables.get("suppliers"), list) else ["蓝箭", "天兵", "中科宇航", "其他供给"]
    buyers = variables.get("buyers") if isinstance(variables.get("buyers"), list) else ["星网", "国家级项目"]
    supplier_html = "".join(f'<span style="--delay:{index * .14:.2f}s">{esc(item)}</span>' for index, item in enumerate(suppliers[:5]))
    buyer_html = "".join(f'<b>{esc(item)}</b>' for item in buyers[:3])
    return scene_shell(
        scene,
        f"""
<main class="frame funnel-scene"><div class="kicker mono">CUSTOMER CONCENTRATION</div><h1>{esc(scene.get('title'))}</h1>
  <section class="funnel-layout"><div class="suppliers"><em>供给端：多家竞争</em>{supplier_html}</div><div class="funnel-shape"><i></i></div><div class="buyers"><em>需求端：集中采购</em>{buyer_html}</div></section>
  <div class="pricing-arrow"><span>订单量可能上升</span><strong>议价权未必同步上升</strong></div>
  <p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p>
</main>
""",
        """
.funnel-scene{background:#f0eee7;color:#171a1e}.funnel-scene h1{font-size:58px;margin:18px 0 35px}.funnel-layout{display:grid;grid-template-columns:1fr 330px 1fr;gap:32px;align-items:center}.suppliers,.buyers{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}.suppliers em,.buyers em{grid-column:1/-1;font-style:normal;color:#64717c;font-size:21px;margin-bottom:5px}.suppliers span,.buyers b{min-height:92px;padding:24px;background:#fff;border:1px solid #c9c4b7;font-size:25px;font-weight:800;display:flex;align-items:center;justify-content:center;animation:funnelCard .6s ease var(--delay) both}.buyers b{grid-column:1/-1;background:#17344a;color:#fff;border-color:#17344a}.funnel-shape{height:360px;clip-path:polygon(0 0,100% 0,66% 100%,34% 100%);background:linear-gradient(#cf9d3f,#17344a);position:relative;animation:funnelDrop 1s ease .3s both}.funnel-shape i{position:absolute;left:50%;top:18%;width:12px;height:62%;background:rgba(255,255,255,.76);transform:translateX(-50%)}.pricing-arrow{margin:34px auto 0;max-width:1080px;display:flex;align-items:center;justify-content:space-between;border-top:4px solid #c89232;padding-top:16px;font-size:26px}.pricing-arrow strong{color:#a92f2f}
@keyframes funnelCard{from{opacity:0;transform:translateX(-25px)}to{opacity:1;transform:none}}@keyframes funnelDrop{from{opacity:0;transform:scaleY(.3);transform-origin:top}to{opacity:1;transform:scaleY(1)}}
""",
    )


def render_valuation_waterfall(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    steps = variables.get("steps") if isinstance(variables.get("steps"), list) else [
        {"label": "年营收", "value": "30亿元"}, {"label": "净利率", "value": "10%"}, {"label": "净利润", "value": "3亿元"}, {"label": "市盈率", "value": "40倍"}, {"label": "对应市值", "value": "120亿元"}
    ]
    step_html = "".join(
        f'<article class="valuation-step" style="--delay:{index * .24:.2f}s"><small>{esc(item.get("label"))}</small><b>{esc(item.get("value"))}</b><i>{"×" if index in {1, 3} else "→"}</i></article>'
        for index, item in enumerate(steps[:5]) if isinstance(item, dict)
    )
    return scene_shell(
        scene,
        f"""
<main class="frame valuation"><div class="kicker mono">VALUATION WATERFALL</div><h1>{esc(scene.get('title'))}</h1><section class="valuation-chain">{step_html}</section><div class="valuation-rule">估值不是从故事直接跳到市值，而是逐级穿过收入、利润率和现金流。</div><p class="safe-bottom caption">{esc(short(scene.get('narration'), 120))}</p></main>
""",
        """
.valuation{background:#0a1017}.valuation h1{font-size:58px;margin:18px 0 70px}.valuation-chain{display:flex;align-items:flex-end;justify-content:center;gap:14px}.valuation-step{position:relative;width:270px;min-height:170px;padding:28px 24px;background:#132639;border:1px solid #36526a;display:flex;flex-direction:column;justify-content:center;animation:valueStep .65s ease var(--delay) both}.valuation-step:nth-child(2),.valuation-step:nth-child(4){min-height:230px;background:#eee7d7;color:#17212a;border-color:#d6c59e}.valuation-step:last-child{min-height:285px;background:#b98a31;border-color:#d7b567;color:#fff}.valuation-step small{font-size:21px;color:#9bacb9}.valuation-step:nth-child(2) small,.valuation-step:nth-child(4) small{color:#68727a}.valuation-step b{font-size:46px;margin-top:14px}.valuation-step i{position:absolute;right:-24px;top:50%;font-size:32px;color:#d6a84e;font-style:normal;z-index:3}.valuation-step:last-child i{display:none}.valuation-rule{max-width:1180px;margin:48px auto 0;border-left:7px solid #d6a84e;padding:18px 28px;font-size:27px;line-height:1.45;background:rgba(255,255,255,.05)}
@keyframes valueStep{from{opacity:0;transform:translateY(45px)}to{opacity:1;transform:none}}
""",
    )


def render_proof_ladder(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else ["火箭能飞", "订单持续", "成本转利润", "客户更市场化"]
    steps = "".join(f'<article style="--delay:{index * .25:.2f}s"><b>{index + 1:02d}</b><span>{esc(item)}</span></article>' for index, item in enumerate(items[:5]))
    return scene_shell(scene, f"""
<main class="frame proof-ladder"><div class="kicker mono">COMMERCIAL PROOF LADDER</div><h1>{esc(scene.get('title'))}</h1><section>{steps}</section><div class="ladder-cap">高估值只有在每一级证据都成立时才站得住</div><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.proof-ladder{background:linear-gradient(135deg,#efe9dc,#f7f5ef);color:#15191d}.proof-ladder h1{font-size:58px;margin:18px 0 45px}.proof-ladder section{display:flex;align-items:flex-end;gap:16px}.proof-ladder article{flex:1;min-height:130px;padding:25px;background:#fff;border:1px solid #cac3b4;animation:ladderRise .7s ease var(--delay) both}.proof-ladder article:nth-child(2){min-height:205px}.proof-ladder article:nth-child(3){min-height:280px}.proof-ladder article:nth-child(4){min-height:355px;background:#17344a;color:#fff}.proof-ladder b{display:block;color:#c89232;font:800 22px Menlo,monospace;margin-bottom:18px}.proof-ladder span{font-size:29px;line-height:1.25;font-weight:850}.ladder-cap{margin-top:30px;padding:20px 26px;border-top:5px solid #c89232;font-size:27px;font-weight:800}
@keyframes ladderRise{from{opacity:0;transform:scaleY(.15);transform-origin:bottom}to{opacity:1;transform:scaleY(1)}}
""")


def render_value_chain(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    lanes = variables.get("lanes") if isinstance(variables.get("lanes"), list) else [
        {"name": "上游稀缺", "items": "特种材料 · 芯片 · 核心部件", "power": "较强"},
        {"name": "火箭总装", "items": "发射服务 · 系统集成", "power": "受约束"},
        {"name": "下游应用", "items": "通信 · 遥感 · 导航服务", "power": "看付费"},
    ]
    lane_html = "".join(
        f'<article class="chain-lane" style="--delay:{index * .28:.2f}s"><small>{esc(item.get("name"))}</small><b>{esc(item.get("items"))}</b><span>定价权：{esc(item.get("power"))}</span></article>'
        for index, item in enumerate(lanes[:4]) if isinstance(item, dict)
    )
    return scene_shell(scene, f"""
<main class="frame value-chain"><div class="kicker mono">VALUE CHAIN · PROFIT POSITION</div><h1>{esc(scene.get('title'))}</h1><section>{lane_html}</section><div class="chain-axis"><span>体系约束更强</span><i></i><span>市场化收入更强</span></div><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.value-chain{background:#0a1016}.value-chain h1{font-size:58px;margin:18px 0 48px}.value-chain section{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}.chain-lane{min-height:350px;padding:34px;background:linear-gradient(180deg,#17344a,#0e1b26);border:1px solid #3d5a70;animation:chainReveal .7s ease var(--delay) both}.chain-lane:nth-child(1){border-top:8px solid #d6a84e}.chain-lane:nth-child(2){border-top:8px solid #8795a1}.chain-lane:nth-child(3){border-top:8px solid #4aa585}.chain-lane small{font:800 21px Menlo,monospace;color:#d6a84e}.chain-lane b{display:block;font-size:33px;line-height:1.35;margin:52px 0 70px}.chain-lane span{font-size:25px;border:1px solid #6a8294;padding:13px 18px;display:inline-block}.chain-axis{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center;margin-top:38px;font-size:22px;color:#aeb9c2}.chain-axis i{height:4px;background:linear-gradient(90deg,#8795a1,#d6a84e,#4aa585)}
@keyframes chainReveal{from{opacity:0;transform:translateY(35px)}to{opacity:1;transform:none}}
""")


def render_signal_gate(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else ["订单持续兑现", "利润率与客户改善", "估值回到现金流"]
    gates = "".join(f'<article class="signal-gate gate-{index}"><i></i><b>{index + 1:02d}</b><span>{esc(item)}</span></article>' for index, item in enumerate(items[:3]))
    return scene_shell(scene, f"""
<main class="frame gates"><div class="kicker mono">INVESTMENT GATES</div><h1>{esc(scene.get('title'))}</h1><section>{gates}</section><div class="gate-result">三道门全部打开，才从“产业梦想”进入“可投资区间”</div><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.gates{background:#eee9de;color:#15191d}.gates h1{font-size:58px;margin:18px 0 55px}.gates section{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}.signal-gate{position:relative;min-height:360px;background:#fff;border:1px solid #c8c2b5;padding:34px;overflow:hidden;animation:gateOpen .8s cubic-bezier(.2,.8,.2,1) both}.gate-1{animation-delay:.35s}.gate-2{animation-delay:.7s}.signal-gate i{position:absolute;left:0;right:0;top:0;height:18px;background:#17344a}.signal-gate b{display:block;font:900 54px Menlo,monospace;color:#c89232;margin:45px 0 65px}.signal-gate span{font-size:35px;line-height:1.25;font-weight:900}.gate-result{margin:38px auto 0;max-width:1120px;background:#17344a;color:#fff;padding:22px 30px;text-align:center;font-size:27px;font-weight:800}
@keyframes gateOpen{from{opacity:0;transform:perspective(700px) rotateY(-70deg);transform-origin:left}to{opacity:1;transform:none}}
""")


def render_thesis_balance(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    left = variables.get("left") if isinstance(variables.get("left"), dict) else {
        "kicker": "产业方向",
        "title": "可以乐观",
        "detail": "技术突破 · 订单增长 · 长期空间",
    }
    right = variables.get("right") if isinstance(variables.get("right"), dict) else {
        "kicker": "投资价格",
        "title": "必须克制",
        "detail": "利润率 · 客户结构 · 现金流",
    }
    return scene_shell(scene, f"""
<main class="frame thesis-balance"><div class="kicker mono">{esc(variables.get('kicker') or 'DIRECTION ≠ PRICE')}</div><h1>{esc(scene.get('title'))}</h1><section><article class="optimistic"><small>{esc(left.get('kicker'))}</small><b>{esc(left.get('title'))}</b><span>{esc(left.get('detail'))}</span></article><div class="balance-beam"><i></i><em></em></div><article class="restrained"><small>{esc(right.get('kicker'))}</small><b>{esc(right.get('title'))}</b><span>{esc(right.get('detail'))}</span></article></section><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.thesis-balance{background:radial-gradient(circle at 50% 45%,#1d3d55,#080e14 60%)}.thesis-balance h1{font-size:62px;margin:18px 0 55px}.thesis-balance section{display:grid;grid-template-columns:1fr 250px 1fr;gap:25px;align-items:center}.thesis-balance article{min-height:360px;padding:44px;border:1px solid #486579;background:rgba(8,20,30,.82);animation:balanceCard .75s ease both}.thesis-balance .restrained{animation-delay:.4s}.thesis-balance small{font:800 21px Menlo,monospace;color:#d6a84e}.thesis-balance b{display:block;font-size:54px;margin:65px 0 35px}.thesis-balance span{font-size:25px;line-height:1.45;color:#b8c3ca}.balance-beam{height:250px;position:relative}.balance-beam i{position:absolute;left:0;right:0;top:110px;height:8px;background:#d6a84e;transform:rotate(-5deg);animation:beamSettle 1.4s ease both}.balance-beam em{position:absolute;left:50%;top:118px;width:0;height:0;border-left:55px solid transparent;border-right:55px solid transparent;border-bottom:120px solid #718696;transform:translateX(-50%)}
@keyframes balanceCard{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:none}}@keyframes beamSettle{0%{transform:rotate(12deg)}55%{transform:rotate(-8deg)}100%{transform:rotate(-5deg)}}
""")


def render_evidence_meter(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    columns = variables.get("columns") if isinstance(variables.get("columns"), list) else [
        {"label": "公开披露", "value": "直接引用", "tone": "high"},
        {"label": "文章情景", "value": "明确标注", "tone": "mid"},
        {"label": "仍待验证", "value": "不包装成事实", "tone": "low"},
    ]
    blocks = "".join(
        f'<article class="evidence-level {esc(item.get("tone"))}" style="--delay:{index * .25:.2f}s"><small>{esc(item.get("label"))}</small><b>{esc(item.get("value"))}</b><div><i></i></div></article>'
        for index, item in enumerate(columns[:3]) if isinstance(item, dict)
    )
    return scene_shell(scene, f"""
<main class="frame evidence-meter"><div class="kicker mono">EVIDENCE DISCIPLINE</div><h1>{esc(scene.get('title'))}</h1><section>{blocks}</section><div class="evidence-rule">数字可以用于分析，但必须同时展示它属于“披露、情景还是待验证”。</div><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.evidence-meter{background:#f1ede4;color:#161a1e}.evidence-meter h1{font-size:58px;margin:18px 0 58px}.evidence-meter section{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}.evidence-level{min-height:310px;padding:34px;background:#fff;border:1px solid #c7c1b4;animation:evidenceLevel .7s ease var(--delay) both}.evidence-level small{font:800 21px Menlo,monospace;color:#697680}.evidence-level b{display:block;font-size:38px;margin:70px 0 45px}.evidence-level div{height:18px;background:#ddd8cd}.evidence-level i{display:block;height:100%;width:92%;background:#2f8a66;animation:meterGrow 1.1s ease .4s both}.evidence-level.mid i{width:62%;background:#c89232}.evidence-level.low i{width:28%;background:#b13a3a}.evidence-rule{margin-top:36px;border-left:7px solid #17344a;padding:18px 28px;font-size:27px;background:rgba(23,52,74,.07)}
@keyframes evidenceLevel{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:none}}@keyframes meterGrow{from{width:0}}
""")


def render_revenue_streams(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else ["卫星通信", "遥感数据", "导航增强", "行业应用"]
    spokes = "".join(f'<article class="stream stream-{index}"><b>{index + 1:02d}</b><span>{esc(item)}</span></article>' for index, item in enumerate(items[:4]))
    return scene_shell(scene, f"""
<main class="frame revenue-streams"><div class="kicker mono">RECURRING REVENUE</div><h1>{esc(scene.get('title'))}</h1><section><svg viewBox="0 0 1000 560"><line x1="500" y1="280" x2="170" y2="110"/><line x1="500" y1="280" x2="830" y2="110"/><line x1="500" y1="280" x2="170" y2="450"/><line x1="500" y1="280" x2="830" y2="450"/></svg><div class="network-core">卫星网络<br><strong>持续服务</strong></div>{spokes}</section><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.revenue-streams{background:#071016}.revenue-streams h1{font-size:58px;margin:18px 0}.revenue-streams section{position:absolute;left:260px;right:260px;top:185px;bottom:110px}.revenue-streams svg{position:absolute;inset:0;width:100%;height:100%}.revenue-streams line{stroke:#d4a54a;stroke-width:5;stroke-dasharray:12 10;animation:streamLine 1.2s ease both}.network-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:250px;height:250px;border-radius:50%;background:#eee6d5;color:#14212a;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;font-size:28px;line-height:1.25}.network-core strong{font-size:35px}.stream{position:absolute;width:245px;min-height:125px;padding:22px;background:#17344a;border:1px solid #506b7e;animation:streamPop .65s ease both}.stream b{display:block;color:#d4a54a;font:800 18px Menlo,monospace;margin-bottom:12px}.stream span{font-size:28px;font-weight:850}.stream-0{left:0;top:20px}.stream-1{right:0;top:20px;animation-delay:.25s}.stream-2{left:0;bottom:20px;animation-delay:.5s}.stream-3{right:0;bottom:20px;animation-delay:.75s}
@keyframes streamLine{from{stroke-dashoffset:500;opacity:0}to{stroke-dashoffset:0;opacity:1}}@keyframes streamPop{from{opacity:0;transform:scale(.85)}to{opacity:1;transform:scale(1)}}
""")


def render_model_compare(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    left = variables.get("left") if isinstance(variables.get("left"), list) else ["发射", "卫星", "服务收入"]
    right = variables.get("right") if isinstance(variables.get("right"), list) else ["发射供应", "集中客户", "体系分润"]
    left_items = "".join(f'<li>{esc(item)}</li>' for item in left[:5])
    right_items = "".join(f'<li>{esc(item)}</li>' for item in right[:5])
    return scene_shell(scene, f"""
<main class="frame model-compare"><div class="kicker mono">BUSINESS MODEL SPLIT</div><h1>{esc(scene.get('title'))}</h1><section><article class="closed-loop"><small>SpaceX</small><b>闭环运营者</b><ol>{left_items}</ol><span>利润跨环节留存</span></article><div class="versus">VS</div><article class="supplier-model"><small>国内火箭公司</small><b>体系供应商</b><ol>{right_items}</ol><span>利润受采购与分工约束</span></article></section><p class="safe-bottom caption">{esc(short(scene.get('narration'),120))}</p></main>
""", """
.model-compare{background:#f1ede3;color:#15191d}.model-compare h1{font-size:58px;margin:18px 0 42px}.model-compare section{display:grid;grid-template-columns:1fr 120px 1fr;gap:20px;align-items:center}.model-compare article{min-height:430px;padding:38px;border:1px solid #c8c1b3;background:#fff;animation:modelReveal .75s ease both}.model-compare .supplier-model{background:#17344a;color:#fff;animation-delay:.35s}.model-compare small{font:800 21px Menlo,monospace;color:#c89232}.model-compare b{display:block;font-size:44px;margin:35px 0}.model-compare ol{list-style:none;padding:0;display:grid;gap:13px}.model-compare li{padding:15px 18px;background:#eee9de;font-size:25px;font-weight:800}.supplier-model li{background:#29485d}.model-compare article>span{display:block;margin-top:25px;font-size:24px;color:#8c2f2f;font-weight:800}.supplier-model>span{color:#f2c86f}.versus{text-align:center;font:900 42px Menlo,monospace;color:#c89232}
@keyframes modelReveal{from{opacity:0;transform:translateX(-35px)}to{opacity:1;transform:none}}.supplier-model{animation-name:modelRevealRight!important}@keyframes modelRevealRight{from{opacity:0;transform:translateX(35px)}to{opacity:1;transform:none}}
""")


def render_value_chain_bridge(scene: dict[str, Any]) -> str:
    variables = scene.get("variables") or {}
    items = variables.get("items") if isinstance(variables.get("items"), list) else [
        {"title": "上游稀缺", "detail": "材料 · 芯片 · 核心部件"},
        {"title": "火箭与总装", "detail": "制造 · 集成 · 发射服务"},
        {"title": "下游应用", "detail": "通信 · 遥感 · 数据服务"},
    ]
    classes = ["upstream", "midstream", "downstream"]
    blocks = "".join(
        f'<article class="{classes[index]}" style="--delay:{index * .28:.2f}s">'
        f'<b>{esc(item.get("title"))}</b><span>{esc(item.get("detail"))}</span></article>'
        for index, item in enumerate(items[:3])
        if isinstance(item, dict)
    )
    return scene_shell(scene, f"""
<main class="frame chain-bridge"><div class="kicker mono">{esc(variables.get('kicker') or 'CHAPTER · CAPITALIZATION CHAIN')}</div><h1>{esc(scene.get('title'))}</h1><section>{blocks}</section><div class="bridge-thesis">{esc(variables.get('thesis') or '稳定的资本市场，把融资、产业化和下一轮投入连成一条链。')}</div></main>
""", """
.chain-bridge{background:#091118}.chain-bridge h1{font-size:68px;max-width:1500px;margin:24px 0 48px}.chain-bridge section{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.chain-bridge article{position:relative;min-height:310px;padding:35px;border:1px solid #435e71;background:#102332;animation:bridgeBlock .7s ease var(--delay) both;overflow:hidden}.chain-bridge article:after{content:"";position:absolute;left:0;right:0;bottom:0;height:14px;background:#d3a248}.chain-bridge .midstream{background:#17344a}.chain-bridge .midstream:after{background:#8797a4}.chain-bridge .downstream{background:#15352f}.chain-bridge .downstream:after{background:#4da681}.chain-bridge b{display:block;font-size:42px;margin:38px 0 60px}.chain-bridge span{font-size:25px;line-height:1.45;color:#c3cdd4}.bridge-thesis{margin-top:30px;border-left:7px solid #d3a248;padding:17px 25px;font-size:27px;color:#dce3e8;background:rgba(255,255,255,.04)}
@keyframes bridgeBlock{from{opacity:0;transform:translateY(42px)}to{opacity:1;transform:none}}
""")


def render_outro(scene: dict[str, Any]) -> str:
    return scene_shell(
        scene,
        f"""
<main class="frame outro">
  {motion_layer(scene)}
  <div class="logo">大</div>
  <h1>Newma 财经</h1>
  <p>{esc(short(scene.get('narration'), 80))}</p>
  <div class="safe-bottom mono">SIGNAL · NOT NOISE</div>
</main>
""",
        """
.outro{background:#08090c;text-align:center}.logo{width:220px;height:220px;border-radius:48px;margin:430px auto 54px;background:linear-gradient(135deg,#d8aa55,#7a4b19);display:flex;align-items:center;justify-content:center;font-size:130px;font-weight:950;box-shadow:0 0 70px rgba(216,170,85,.25);animation:rise .9s ease both}
.outro h1{font-size:76px;margin:0 0 26px}.outro p{font-size:32px;line-height:1.5;color:#cfd3dc;max-width:760px;margin:0 auto}
""",
    )


def render_generic(scene: dict[str, Any]) -> str:
    return scene_shell(
        scene,
        f"""
<main class="frame generic">
  {motion_layer(scene)}
  <p class="kicker mono">MARKET NOTE</p>
  <h1>{esc(scene.get('title'))}</h1>
  <p>{esc(short(scene.get('narration'), 180))}</p>
</main>
""",
        """
.generic{background:#111827}.generic h1{font-size:72px;line-height:1.12;margin:360px 0 38px}.generic p{font-size:32px;line-height:1.55;color:#cfd3dc}
""",
    )


def render_scene(scene: dict[str, Any]) -> str:
    part = scene.get("content_part")
    template_id = scene.get("template_id")
    if template_id == "route-map-seven":
        return render_route_map(scene)
    if template_id == "source-web-evidence":
        return render_source_web_evidence(scene)
    if template_id == "business-flywheel":
        return render_business_flywheel(scene)
    if template_id == "customer-concentration-funnel":
        return render_customer_funnel(scene)
    if template_id == "valuation-waterfall":
        return render_valuation_waterfall(scene)
    if template_id == "commercial-proof-ladder":
        return render_proof_ladder(scene)
    if template_id == "value-chain-profit-map":
        return render_value_chain(scene)
    if template_id == "investment-signal-gate":
        return render_signal_gate(scene)
    if template_id == "direction-price-balance":
        return render_thesis_balance(scene)
    if template_id == "evidence-discipline-meter":
        return render_evidence_meter(scene)
    if template_id == "recurring-revenue-streams":
        return render_revenue_streams(scene)
    if template_id == "business-model-split":
        return render_model_compare(scene)
    if template_id == "value-chain-chapter-bridge":
        return render_value_chain_bridge(scene)
    if template_id == "tree-rescue-metaphor":
        return render_tree_rescue(scene)
    if (scene.get("variables") or {}).get("chart_kind"):
        return render_article_chart(scene)
    if template_id in {"frame-data-rollup"}:
        return render_rollup(scene)
    if template_id in {"frame-pentagram-stat"}:
        return render_stat(scene)
    if template_id in {"frame-nyt-graph"}:
        return render_line_graph(scene)
    if template_id in {"dashboard", "live-dashboard", "finance-report"} and part != "data_table":
        return render_dashboard(scene)
    if template_id in {"frame-swiss-grid", "deck-swiss-international"}:
        return render_swiss_grid(scene)
    if template_id in {"social-x-post-card", "card-twitter"}:
        return render_social(scene)
    if template_id in {"frame-takram-organic", "deck-graphify-dark"}:
        return render_takram(scene)
    if part == "article_title" or template_id == "frame-liquid-bg-hero":
        return render_liquid_hero(scene)
    if part in {"opening_hook", "transition"} or template_id == "frame-glitch-title":
        return render_glitch(scene)
    if part == "chapter_divider" or template_id == "frame-light-leak-cinema":
        return render_cinema(scene)
    if part in {"overall_outline", "logic_chain", "timeline"} or template_id == "frame-flowchart-sticky":
        return render_flowchart(scene)
    if part in {"data_chart", "financial_chart", "kpi_card"}:
        return render_data(scene)
    if part == "data_table":
        return render_data(scene, table_mode=True)
    if part == "warning_or_risk":
        return render_alert(scene)
    if part in {"quote", "pull_quote"}:
        return render_quote(scene)
    if part in {"article_image", "news_or_document", "source_citation"}:
        return render_document(scene)
    if part in {"closing_outro", "brand_mark"} or template_id == "frame-logo-outro":
        return render_outro(scene)
    return render_generic(scene)


def build_preview(manifest: dict[str, Any]) -> str:
    cards = []
    for scene in manifest["scenes"]:
        cards.append(
            f"""
<article>
  <iframe src="{esc(scene['relative_html'])}"></iframe>
  <div><b>{esc(scene['id'])}</b><span>{esc(scene['content_part'])}</span><code>{esc(scene['template_id'])}</code><em>{scene['start_sec']}s → {scene['end_sec']}s</em></div>
</article>
"""
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{esc(manifest['title'])}</title>
<style>
body{{margin:0;padding:28px;background:#10131a;color:#f5f2e9;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}
h1{{margin:0 0 8px;font-size:34px}}p{{color:#aab2c2}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}
article{{background:#171c27;border:1px solid #30394a;border-radius:18px;overflow:hidden}}iframe{{width:100%;aspect-ratio:{manifest['width']}/{manifest['height']};border:0;background:#000}}
article div{{padding:12px 14px;display:grid;gap:5px}}span,em,code{{color:#aab2c2;font-style:normal}}code{{color:#d8aa55}}
</style></head><body>
<h1>{esc(manifest['title'])}</h1>
<p>{manifest['scene_count']} scenes · {manifest['duration_estimate_sec']}s · HTML Anything routed preview</p>
<section class="grid">{''.join(cards)}</section>
</body></html>
"""


def build_pack(timeline_path: Path, output_dir: Path) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    scenes = timeline.get("timeline") or timeline.get("scenes") or []
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = output_dir / "scenes"
    rendered = []
    for index, scene in enumerate(scenes, 1):
        scene = dict(scene)
        variables = dict(scene.get("variables") or {})
        asset_path = clean_text(scene.get("asset_path"))
        if asset_path and variables.get("src") in {None, "", "bound_article_asset"}:
            variables["src"] = asset_path
        scene["variables"] = variables
        file_name = f"{index:03d}_{scene.get('content_part','scene')}_{scene.get('template_id','template')}.html"
        safe_name = re.sub(r"[^0-9A-Za-z_.-]+", "_", file_name)
        html_path = scene_dir / safe_name
        write_text(html_path, render_scene(scene))
        rendered.append(
            {
                "id": scene.get("id"),
                "index": index,
                "content_part": scene.get("content_part"),
                "beat_class": scene.get("beat_class"),
                "director_state": scene.get("director_state"),
                "driver_scores": scene.get("driver_scores"),
                "driver_score": scene.get("driver_score"),
                "template_id": scene.get("template_id"),
                "start_sec": scene.get("start_sec"),
                "end_sec": scene.get("end_sec"),
                "duration_sec": scene.get("duration_sec"),
                "title": scene.get("title"),
                "narration": scene.get("narration"),
                "variables": scene.get("variables") or {},
                "qc_notes": scene.get("qc_notes") or [],
                "original_refs": scene.get("original_refs") or [],
                "motion_policy": motion_policy(scene),
                "transition_to_next": scene.get("transition_to_next"),
                "audio": scene.get("audio"),
                "html": str(html_path.resolve()),
                "relative_html": str(html_path.relative_to(output_dir)),
            }
        )
    manifest = {
        "schema_version": "dasheng.html_anything_scene_pack.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_timeline": str(timeline_path.resolve()),
        "title": timeline.get("title"),
        "aspect": "16:9" if WIDTH > HEIGHT else "9:16" if HEIGHT > WIDTH else "1:1",
        "width": WIDTH,
        "height": HEIGHT,
        "scene_count": len(rendered),
        "duration_estimate_sec": timeline.get("duration_estimate_sec")
        or round(sum(float(scene.get("duration_sec") or 0) for scene in rendered), 3),
        "template_usage": dict(Counter(scene["template_id"] for scene in rendered)),
        "director_usage": dict(Counter(clean_text(scene.get("director_state")) for scene in rendered)),
        "beat_usage": dict(Counter(clean_text(scene.get("beat_class")) for scene in rendered)),
        "transition_usage": dict(Counter(clean_text(scene.get("transition_to_next")) for scene in rendered)),
        "motion_runtime": {
            "mode": MOTION_RUNTIME_MODE,
            "gsap_inline": bool(read_motion_lib("gsap")) and MOTION_RUNTIME_MODE != "lite",
            "lottie_inline": bool(read_motion_lib("lottie")) and MOTION_RUNTIME_MODE != "lite",
            "lottie_asset_policy": "Generated lightweight Lottie JSON per scene; replace with searched/designed assets when available.",
        },
        "scenes": rendered,
        "render_next": {
            "preview_html": str((output_dir / "preview.html").resolve()),
            "policy": "Render each scene HTML to video/image segment, align to audio master, then stitch.",
        },
    }
    write_text(output_dir / "scene_pack_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "preview.html", build_preview(manifest))
    narration = "\n".join(f"{idx:02d}. {scene['narration']}" for idx, scene in enumerate(rendered, 1))
    write_text(output_dir / "narration_script.txt", narration + "\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render HTML Anything routed timeline into standalone scene HTML pack.")
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--motion-runtime", choices=["auto", "lite"], default="auto")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global MOTION_RUNTIME_MODE, WIDTH, HEIGHT
    MOTION_RUNTIME_MODE = args.motion_runtime
    WIDTH = args.width
    HEIGHT = args.height
    manifest = build_pack(Path(args.timeline).expanduser().resolve(), Path(args.output_dir).expanduser().resolve())
    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(Path(args.output_dir).expanduser().resolve()),
                "scene_count": manifest["scene_count"],
                "preview_html": manifest["render_next"]["preview_html"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
