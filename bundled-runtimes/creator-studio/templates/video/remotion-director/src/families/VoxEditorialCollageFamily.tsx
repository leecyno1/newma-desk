import React from 'react';
import {
  Img,
  interpolate,
  OffthreadVideo,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {FamilyProps, VoxMotionKeyframe, VoxSceneLayer} from '../types';

const C = {
  ink: '#181410',
  paper: '#e7d8b8',
  light: '#f4ead4',
  red: '#cf3f32',
  teal: '#1f756d',
  gold: '#bd8c34',
  muted: '#776a59',
};

const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};

const Paper: React.FC<React.PropsWithChildren<{
  style?: React.CSSProperties;
  tone?: 'light' | 'paper' | 'ink' | 'red' | 'teal';
  rotate?: number;
}>> = ({children, style, tone = 'light', rotate = 0}) => {
  const colors = {light: C.light, paper: C.paper, ink: C.ink, red: C.red, teal: C.teal};
  return (
    <div style={{
      position: 'relative',
      color: tone === 'ink' || tone === 'red' || tone === 'teal' ? C.light : C.ink,
      background: colors[tone],
      clipPath: 'polygon(1% 3%,98% 0,100% 94%,96% 100%,3% 98%,0 7%)',
      boxShadow: '0 18px 42px rgba(0,0,0,.30)',
      transform: `rotate(${rotate}deg)`,
      ...style,
    }}>
      {children}
    </div>
  );
};

const Tape: React.FC<{left?: number; right?: number; top?: number; rotate?: number}> = ({left, right, top = -12, rotate = -4}) => (
  <div style={{position: 'absolute', left, right, top, width: 112, height: 28, background: 'rgba(222,202,151,.78)', transform: `rotate(${rotate}deg)`, boxShadow: '0 2px 4px rgba(0,0,0,.12)'}} />
);

const Stamp: React.FC<{children: React.ReactNode; color?: string}> = ({children, color = C.red}) => (
  <span style={{display: 'inline-block', border: `3px solid ${color}`, color, padding: '7px 12px 5px', fontSize: 18, fontWeight: 950, letterSpacing: '.13em', transform: 'rotate(-2deg)', textTransform: 'uppercase'}}>{children}</span>
);

const SourceStamp: React.FC<{text?: string}> = ({text}) => text ? (
  <div style={{position: 'absolute', right: 38, top: 32, zIndex: 8, maxWidth: 600, padding: '8px 12px', background: 'rgba(244,234,212,.88)', color: C.ink, fontSize: 15, fontWeight: 750, lineHeight: 1.35, transform: 'rotate(.5deg)', boxShadow: '0 8px 20px rgba(0,0,0,.18)'}}>
    SOURCE · {text}
  </div>
) : null;

const RedThread: React.FC<{progress: number}> = ({progress}) => (
  <svg style={{position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible', pointerEvents: 'none'}} viewBox="0 0 1920 1080">
    <path d="M300 760 C560 570 630 340 920 510 C1180 660 1390 350 1650 470" fill="none" stroke={C.red} strokeWidth="8" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - progress} />
    <path d="M1630 448 L1660 470 L1628 488" fill="none" stroke={C.red} strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" opacity={progress} />
  </svg>
);

const TitleBlock: React.FC<{eyebrow?: string; title: string; progress: number; compact?: boolean}> = ({eyebrow, title, progress, compact = false}) => (
  <div style={{position: 'absolute', left: 82, top: 58, width: compact ? 900 : 1180, zIndex: 6, opacity: progress, transform: `translateY(${(1 - progress) * 28}px)`}}>
    <Stamp color={C.gold}>{eyebrow || 'VOX EXPLAINER'}</Stamp>
    <Paper rotate={-1} style={{display: 'inline-block', maxWidth: compact ? 880 : 1150, padding: compact ? '13px 22px 16px' : '18px 28px 22px', marginTop: 15}}>
      <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', color: C.ink, fontSize: compact ? 54 : 70, lineHeight: 1.04, fontWeight: 900}}>{title}</div>
    </Paper>
  </div>
);

const EvidenceMap: React.FC<{items: string[]; progress: number; activeIndex: number; shotCount: number}> = ({items, progress, activeIndex, shotCount}) => {
  const positions = [
    {left: 160, top: 320, rotate: -3},
    {left: 560, top: 510, rotate: 2},
    {left: 1010, top: 300, rotate: -1},
    {left: 1390, top: 570, rotate: 3},
  ];
  return (
    <>
      <RedThread progress={interpolate(progress, [.12, .72], [0, 1], clamp)} />
      {items.slice(0, 4).map((item, index) => {
        const p = interpolate(progress, [index * .16, .42 + index * .16], [0, 1], clamp);
        const pos = positions[index];
        const focusIndex = Math.min(items.length - 1, Math.floor(activeIndex * items.length / Math.max(1, shotCount)));
        const focused = index === focusIndex;
        return (
          <Paper key={item} rotate={pos.rotate} style={{position: 'absolute', left: pos.left, top: pos.top, width: 330, minHeight: 168, padding: '34px 30px', opacity: p * (focused ? 1 : .68), zIndex: focused ? 3 : 1, transform: `translateY(${(1 - p) * 70}px) scale(${focused ? 1.07 : .98}) rotate(${pos.rotate}deg)`}}>
            <Tape left={108} rotate={index % 2 ? 4 : -5} />
            <div style={{fontSize: 17, color: C.red, fontWeight: 900}}>EVIDENCE 0{index + 1}</div>
            <div style={{fontSize: 34, fontWeight: 900, lineHeight: 1.15, marginTop: 24}}>{item}</div>
          </Paper>
        );
      })}
    </>
  );
};

const MechanismBoard: React.FC<{items: string[]; progress: number; activeIndex: number; shotCount: number}> = ({items, progress, activeIndex, shotCount}) => (
  <div style={{position: 'absolute', left: 120, right: 120, top: 310, bottom: 150, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 44}}>
    {items.slice(0, 4).map((item, index) => {
      const p = interpolate(progress, [.05 + index * .13, .36 + index * .13], [0, 1], clamp);
      const focusIndex = Math.min(items.length - 1, Math.floor(activeIndex * items.length / Math.max(1, shotCount)));
      const focused = index === focusIndex;
      return (
        <React.Fragment key={item}>
          <Paper tone={index === items.length - 1 ? 'teal' : 'light'} rotate={index % 2 ? 2 : -2} style={{width: 330, minHeight: 230, padding: '38px 30px', display: 'grid', alignContent: 'center', textAlign: 'center', opacity: p * (focused ? 1 : .62), zIndex: focused ? 3 : 1, transform: `translateY(${(1 - p) * 80}px) scale(${focused ? 1.08 : .96}) rotate(${index % 2 ? 2 : -2}deg)`}}>
            <div style={{fontSize: 54}}>{['◉', '↯', '▰', '◎'][index]}</div>
            <div style={{fontSize: 31, fontWeight: 900, lineHeight: 1.18, marginTop: 25}}>{item}</div>
          </Paper>
          {index < Math.min(items.length, 4) - 1 ? <div style={{fontSize: 70, color: C.red, fontWeight: 300, opacity: p}}>→</div> : null}
        </React.Fragment>
      );
    })}
  </div>
);

const DataBoard: React.FC<{labels: string[]; values: number[]; unit?: string; progress: number; reserveRight?: boolean; activeIndex: number; shotCount: number}> = ({labels, values, unit, progress, reserveRight, activeIndex, shotCount}) => {
  const max = Math.max(1, ...values.map((value) => Math.abs(value)));
  return (
    <Paper rotate={-1} style={{position: 'absolute', left: 90, right: reserveRight ? 540 : 90, top: 250, bottom: 120, padding: '38px 48px 28px'}}>
      <Tape left={160} rotate={-4} /><Tape right={150} rotate={5} />
      <div style={{position: 'absolute', left: 52, right: 52, top: 325, height: 4, background: C.ink, opacity: .75}} />
      <div style={{position: 'absolute', left: 52, right: 52, top: 90, bottom: 42, display: 'flex', alignItems: 'stretch', justifyContent: 'space-around', gap: 18}}>
        {values.map((value, index) => {
          const p = interpolate(progress, [.08 + index * .08, .46 + index * .08], [0, 1], clamp);
          const height = Math.abs(value) / max * 210 * p;
          const positive = value >= 0;
          const focusIndex = Math.min(values.length - 1, Math.floor(activeIndex * values.length / Math.max(1, shotCount)));
          const focused = index === focusIndex;
          return (
            <div key={`${labels[index]}-${index}`} style={{position: 'relative', flex: 1, minWidth: 70, opacity: focused ? 1 : .58, transform: `scale(${focused ? 1.08 : .97})`, transformOrigin: '50% 72%'}}>
              <div style={{position: 'absolute', left: '50%', width: '56%', transform: 'translateX(-50%)', bottom: positive ? 145 : undefined, top: positive ? undefined : 235, height, background: positive ? C.gold : C.red, boxShadow: '5px 7px 0 rgba(24,20,16,.18)', clipPath: 'polygon(5% 0,96% 2%,100% 96%,2% 100%)'}} />
              <div style={{position: 'absolute', left: 0, right: 0, top: positive ? 105 - height * .05 : 242 + height, textAlign: 'center', fontSize: 22, fontWeight: 950, color: positive ? C.ink : C.red, opacity: p}}>{value > 0 ? '+' : ''}{value}{unit ? ` ${unit}` : ''}</div>
              <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, textAlign: 'center', fontSize: 20, fontWeight: 850}}>{labels[index]}</div>
            </div>
          );
        })}
      </div>
    </Paper>
  );
};

const CounterBoard: React.FC<{left: {title: string; value: string}; right: {title: string; value: string}; progress: number; activeIndex: number}> = ({left, right, progress, activeIndex}) => (
  <div style={{position: 'absolute', left: 100, right: 100, top: 270, bottom: 140, display: 'grid', gridTemplateColumns: '1fr 110px 1fr', alignItems: 'center'}}>
    {[left, right].map((item, index) => {
      const p = index === 0 ? interpolate(progress, [0, .22], [0, 1], clamp) : interpolate(activeIndex, [1, 2], [0, 1], clamp);
      return (
        <Paper key={item.title} tone={index ? 'paper' : 'light'} rotate={index ? 2 : -2} style={{minHeight: 480, padding: '48px 44px', opacity: p, transform: `translateX(${(1 - p) * (index ? 90 : -90)}px) rotate(${index ? 2 : -2}deg)`}}>
          <Stamp color={index ? C.red : C.teal}>{item.title}</Stamp>
          <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 54, lineHeight: 1.12, fontWeight: 900, marginTop: 86}}>{item.value}</div>
        </Paper>
      );
    }).flatMap((item, index) => index === 0 ? [item, <div key="tear" style={{fontSize: 82, textAlign: 'center', color: C.red, fontWeight: 950, opacity: interpolate(activeIndex, [0, 1], [0, 1], clamp), transform: `scale(${activeIndex === 1 ? 1.22 : 1})`}}>≠</div>] : [item])}
  </div>
);

const ConclusionBoard: React.FC<{points: string[]; progress: number; activeIndex: number}> = ({points, progress, activeIndex}) => (
  <div style={{position: 'absolute', left: 100, right: 100, top: 300, bottom: 120, display: 'grid', gridTemplateColumns: `repeat(${Math.min(3, points.length)},1fr)`, gap: 34, alignItems: 'center'}}>
    {points.slice(0, 3).map((point, index) => {
      const p = interpolate(progress, [.08 + index * .18, .42 + index * .18], [0, 1], clamp);
      const focused = Math.min(points.length - 1, activeIndex) === index;
      return (
        <Paper key={point} tone={index === 2 ? 'teal' : index === 1 ? 'paper' : 'light'} rotate={index - 1} style={{minHeight: 380, padding: '42px 34px', opacity: p * (focused ? 1 : .65), transform: `translateY(${(1 - p) * 90}px) scale(${focused ? 1.06 : .97}) rotate(${index - 1}deg)`}}>
          <div style={{fontSize: 18, color: index === 2 ? C.light : C.red, fontWeight: 950, letterSpacing: '.14em'}}>0{index + 1}</div>
          <div style={{fontSize: 34, lineHeight: 1.25, fontWeight: 900, marginTop: 70}}>{point}</div>
        </Paper>
      );
    })}
  </div>
);

const MicroShotRibbon: React.FC<{label?: string; index: number; count: number; enter: number}> = ({label, index, count, enter}) => label ? (
  <div style={{position: 'absolute', left: 88, top: 238, zIndex: 9, opacity: enter, transform: `translateX(${(1 - enter) * -34}px) rotate(-1deg)`}}>
    <Paper tone="ink" style={{display: 'flex', alignItems: 'center', gap: 18, padding: '11px 18px 12px', boxShadow: '7px 9px 0 rgba(207,63,50,.72)'}}>
      <span style={{fontSize: 16, color: C.gold, fontWeight: 950, letterSpacing: '.12em'}}>{String(index + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}</span>
      <span style={{fontSize: 22, fontWeight: 850}}>{label}</span>
    </Paper>
  </div>
) : null;

const EvidenceVideoScrap: React.FC<{src?: string; startFrom: number; enter: number}> = ({src, startFrom, enter}) => src ? (
  <Paper rotate={2} style={{position: 'absolute', right: 86, bottom: 118, width: 432, height: 252, zIndex: 8, overflow: 'hidden', opacity: enter, transform: `translateY(${(1 - enter) * 48}px) scale(${.92 + enter * .08}) rotate(2deg)`}}>
    <Tape left={150} rotate={5} />
    <OffthreadVideo src={staticFile(src)} startFrom={startFrom} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
    <div style={{position: 'absolute', left: 14, bottom: 12, padding: '6px 10px', background: 'rgba(24,20,16,.82)', color: C.light, fontSize: 15, fontWeight: 850}}>SOURCE FOOTAGE</div>
  </Paper>
) : null;

const keyframesFor = (layer: VoxSceneLayer) => [
  ...(layer.entry_path || []),
  ...(layer.motion_path || []),
  ...(layer.exit_path || []),
].sort((a, b) => a.at - b.at);

const sampleKeyframes = (
  keyframes: VoxMotionKeyframe[],
  progress: number,
  field: keyof VoxMotionKeyframe,
  fallback: number,
) => {
  const rawPoints = keyframes
    .filter((item) => typeof item[field] === 'number')
    .map((item) => ({at: item.at, value: item[field] as number}))
    .sort((a, b) => a.at - b.at);
  const pointMap = new Map<number, number>();
  rawPoints.forEach((item) => pointMap.set(item.at, item.value));
  const points = [...pointMap.entries()].map(([at, value]) => ({at, value})).sort((a, b) => a.at - b.at);
  if (!points.length) return fallback;
  if (points.length === 1) return points[0].value;
  return interpolate(progress, points.map((item) => item.at), points.map((item) => item.value), clamp);
};

const sampleSimpleKeyframes = (
  keyframes: Array<{at: number; value: number}> | undefined,
  progress: number,
  fallback: number,
) => {
  if (!keyframes?.length) return fallback;
  if (keyframes.length === 1) return keyframes[0].value;
  const sorted = [...keyframes].sort((a, b) => a.at - b.at);
  return interpolate(progress, sorted.map((item) => item.at), sorted.map((item) => item.value), clamp);
};

const steppedProgress = (frame: number, duration: number, fps: number, targetFps?: number) => {
  if (!targetFps || targetFps >= fps) return frame / Math.max(1, duration - 1);
  const stride = Math.max(1, fps / targetFps);
  return Math.floor(frame / stride) * stride / Math.max(1, duration - 1);
};

const routeReveal = (layer: VoxSceneLayer, progress: number) => {
  const entry = layer.entry_path || [];
  const start = entry.length ? Math.min(...entry.map((item) => item.at)) : 0;
  const end = entry.length ? Math.max(...entry.map((item) => item.at)) : .35;
  return interpolate(progress, [start, Math.max(start + .001, end)], [0, 1], clamp);
};

const LayerContent: React.FC<{layer: VoxSceneLayer; progress: number; fps: number}> = ({layer, progress, fps}) => {
  const fit = layer.object_fit || 'contain';
  const common: React.CSSProperties = {width: '100%', height: '100%', objectFit: fit, objectPosition: layer.object_position || '50% 50%'};
  if (layer.asset_type === 'image' && layer.src) return <Img src={staticFile(layer.src)} style={common} />;
  if (layer.asset_type === 'video' && layer.src) return <OffthreadVideo src={staticFile(layer.src)} muted style={common} />;
  if (layer.asset_type === 'route') {
    const draw = routeReveal(layer, progress);
    return (
      <svg viewBox={`0 0 ${layer.width || 1920} ${layer.height || 1080}`} style={{width: '100%', height: '100%', overflow: 'visible'}}>
        <path
          d={layer.route_path || 'M40 180 C260 20 520 300 760 120'}
          pathLength={1}
          fill={layer.route_fill || 'none'}
          stroke={layer.route_color || C.red}
          strokeWidth={layer.route_width || 9}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={1}
          strokeDashoffset={1 - draw}
        />
      </svg>
    );
  }
  if (layer.asset_type === 'bar_chart') {
    const values = layer.chart_values || [];
    const max = Math.max(1, ...values.map(Math.abs));
    const reveal = routeReveal(layer, progress);
    return (
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'flex-end', gap: 20, padding: 24}}>
        {values.map((value, index) => {
          const bar = interpolate(reveal, [index / Math.max(1, values.length + 1), (index + 2) / Math.max(2, values.length + 1)], [0, 1], clamp);
          return (
            <div key={`${layer.id}-${index}`} style={{flex: 1, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'center', gap: 10}}>
              <div style={{fontSize: 22, fontWeight: 950, color: C.ink, opacity: bar}}>{value}</div>
              <div style={{width: '72%', height: `${Math.abs(value) / max * 76 * bar}%`, minHeight: 2, background: index === values.length - 1 ? C.red : C.gold, boxShadow: '6px 6px 0 rgba(24,20,16,.18)', clipPath: 'polygon(4% 0,96% 2%,100% 96%,0 100%)'}} />
              <div style={{height: 28, fontSize: 18, fontWeight: 850, color: C.ink}}>{layer.chart_labels?.[index] || ''}</div>
            </div>
          );
        })}
      </div>
    );
  }
  if (layer.asset_type === 'shape') return <div style={{width: '100%', height: '100%', background: layer.background || layer.color || C.red, border: layer.border, borderRadius: layer.border_radius ?? 0}} />;
  const isPaper = layer.asset_type === 'paper';
  return (
    <div style={{
      width: '100%',
      height: '100%',
      boxSizing: 'border-box',
      display: 'flex',
      alignItems: 'center',
      justifyContent: layer.text_align === 'left' ? 'flex-start' : layer.text_align === 'right' ? 'flex-end' : 'center',
      padding: layer.padding ?? (isPaper ? 28 : 0),
      color: layer.color || C.ink,
      background: isPaper ? (layer.background || C.light) : layer.background,
      border: layer.border,
      borderRadius: layer.border_radius,
      clipPath: isPaper ? 'polygon(1% 4%,98% 0,100% 94%,96% 100%,3% 98%,0 8%)' : undefined,
      fontFamily: layer.font_family || 'Avenir Next, PingFang SC, sans-serif',
      fontSize: layer.font_size || 42,
      fontWeight: layer.font_weight || 900,
      lineHeight: layer.line_height || 1.08,
      textAlign: layer.text_align || 'center',
      whiteSpace: 'pre-line',
    }}>{layer.text || layer.label || ''}</div>
  );
};

const LayeredStage: React.FC<{
  scene: FamilyProps['scene'];
  frame: number;
  duration: number;
  fps: number;
}> = ({scene, frame, duration, fps}) => {
  const visual = scene.visual || {};
  const sceneProgress = steppedProgress(frame, duration, fps, visual.stepped_fps || 12);
  const cameraKeys = visual.camera_keyframes || [{at: 0, x: 0, y: 0, z: 0}, {at: 1, x: 0, y: 0, z: 0}];
  const cameraX = sampleKeyframes(cameraKeys, sceneProgress, 'x', 0);
  const cameraY = sampleKeyframes(cameraKeys, sceneProgress, 'y', 0);
  const cameraZ = sampleKeyframes(cameraKeys, sceneProgress, 'z', 0);
  const cameraRotateX = sampleKeyframes(cameraKeys, sceneProgress, 'rotate_x', 0);
  const cameraRotateY = sampleKeyframes(cameraKeys, sceneProgress, 'rotate_y', 0);
  const cameraRotation = sampleKeyframes(cameraKeys, sceneProgress, 'rotation', 0);
  const cameraScale = sampleKeyframes(cameraKeys, sceneProgress, 'scale', 1);
  const layers = [...(visual.scene_layers || [])].sort((a, b) => (a.occlusion_order ?? a.depth ?? 0) - (b.occlusion_order ?? b.depth ?? 0));

  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: C.paper, perspective: visual.camera_perspective || 1200, perspectiveOrigin: '50% 50%'}}>
      <div style={{position: 'absolute', inset: -120, backgroundColor: C.paper, backgroundImage: 'repeating-linear-gradient(0deg,rgba(72,50,28,.055) 0,rgba(72,50,28,.055) 1px,transparent 1px,transparent 5px),radial-gradient(circle at 22% 18%,rgba(255,255,255,.5),transparent 38%),radial-gradient(circle at 80% 72%,rgba(84,49,20,.16),transparent 44%)'}} />
      <div style={{position: 'absolute', inset: 0, transformStyle: 'preserve-3d', transformOrigin: '50% 50%', transform: `translate3d(${-cameraX}px,${-cameraY}px,${cameraZ * .35}px) rotateX(${-cameraRotateX}deg) rotateY(${-cameraRotateY}deg) rotateZ(${-cameraRotation}deg) scale(${cameraScale})`}}>
        {layers.map((layer) => {
          const progress = steppedProgress(frame, duration, fps, layer.stepped_fps || visual.stepped_fps || 12);
          const keys = keyframesFor(layer);
          const x = sampleKeyframes(keys, progress, 'x', 0);
          const y = sampleKeyframes(keys, progress, 'y', 0);
          const z = ((layer.depth || 0) + sampleKeyframes(keys, progress, 'z', 0)) * .45;
          const rotation = sampleSimpleKeyframes(layer.rotation_keyframes, progress, sampleKeyframes(keys, progress, 'rotation', 0));
          const rotateX = sampleKeyframes(keys, progress, 'rotate_x', 0);
          const rotateY = sampleKeyframes(keys, progress, 'rotate_y', 0);
          const scale = sampleSimpleKeyframes(layer.scale_keyframes, progress, sampleKeyframes(keys, progress, 'scale', 1));
          const opacity = sampleKeyframes(keys, progress, 'opacity', 1);
          const blur = sampleKeyframes(keys, progress, 'blur', 0);
          return (
            <div key={layer.id} style={{
              position: 'absolute',
              left: layer.x || 0,
              top: layer.y || 0,
              width: layer.width || 320,
              height: layer.height || 240,
              overflow: layer.mask ? 'hidden' : 'visible',
              clipPath: layer.mask || undefined,
              transformOrigin: `${(layer.anchor?.x ?? .5) * 100}% ${(layer.anchor?.y ?? .5) * 100}%`,
              transformStyle: 'preserve-3d',
              transform: `translate3d(${x}px,${y}px,${z}px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) rotateZ(${rotation}deg) scale(${scale})`,
              opacity,
              filter: blur ? `blur(${blur}px)` : undefined,
              boxShadow: layer.shadow,
              mixBlendMode: layer.mix_blend_mode,
              backfaceVisibility: 'hidden',
            }}>
              <LayerContent layer={layer} progress={progress} fps={fps} />
            </div>
          );
        })}
      </div>
      <SourceStamp text={visual.source} />
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: .13, backgroundImage: 'repeating-radial-gradient(circle at 0 0,transparent 0,rgba(0,0,0,.42) 1px,transparent 2px)', backgroundSize: '5px 5px', mixBlendMode: 'multiply'}} />
    </div>
  );
};

export const VoxEditorialCollageFamily: React.FC<FamilyProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const progress = interpolate(frame, [0, duration - 1], [0, 1], clamp);
  const enter = spring({frame, fps, config: {damping: 180, stiffness: 105, mass: .8}});
  const state = scene.vox_state || scene.narrative_function || scene.type || 'mechanism_explainer';
  const visual = scene.visual || {};
  if (visual.scene_layers?.length) {
    return <LayeredStage scene={scene} frame={frame} duration={duration} fps={fps} />;
  }
  const shots = visual.micro_shots?.length ? visual.micro_shots : [{id: `${scene.id}_01`, action: '建立证据'}, {id: `${scene.id}_02`, action: '推进机制'}, {id: `${scene.id}_03`, action: '锁定结论'}];
  const shotCount = shots.length;
  const shotFloat = Math.min(shotCount - .001, progress * shotCount);
  const shotIndex = Math.floor(shotFloat);
  const shotLocal = shotFloat - shotIndex;
  const shotEnter = interpolate(shotLocal, [0, .22], [0, 1], clamp);
  const activeShot = shots[shotIndex];
  const nodes = visual.nodes?.length ? visual.nodes : visual.points?.length ? visual.points : ['事实', '机制', '结论'];
  const values = visual.series?.[0]?.values || [];
  const labels = visual.labels || values.map((_, index) => String(index + 1));
  const cameraAnchors = [
    {x: -28, y: 20, scale: 1.035},
    {x: 42, y: -18, scale: 1.12},
    {x: -20, y: 28, scale: 1.08},
    {x: 26, y: -10, scale: 1.145},
  ];
  const currentAnchor = cameraAnchors[shotIndex % cameraAnchors.length];
  const previousAnchor = shotIndex === 0 ? {x: 0, y: 0, scale: 1} : cameraAnchors[(shotIndex - 1) % cameraAnchors.length];
  const cameraMove = interpolate(shotLocal, [0, .32], [0, 1], clamp);
  const cameraX = previousAnchor.x + (currentAnchor.x - previousAnchor.x) * cameraMove;
  const cameraY = previousAnchor.y + (currentAnchor.y - previousAnchor.y) * cameraMove;
  const cameraScale = previousAnchor.scale + (currentAnchor.scale - previousAnchor.scale) * cameraMove;
  const thread = interpolate(progress, [.08, .62], [0, 1], clamp);
  const hasVideo = Boolean(visual.background_video_src || visual.motion_plate_src);
  const title = visual.headline || scene.title;
  const bigNumber = title.match(/\d[\d,.]*/)?.[0];
  const pipStart = Math.max(0, Math.round((visual.pip_video_start_sec || 0) * fps));

  let content: React.ReactNode;
  if (state === 'cold_open') {
    const numberIn = interpolate(shotFloat, [.7, 1.15], [0, 1], clamp);
    const titleIn = interpolate(shotFloat, [1.45, 2.05], [0, 1], clamp);
    const verdictIn = interpolate(shotFloat, [2.55, 3.08], [0, 1], clamp);
    content = (
      <>
        <div style={{position: 'absolute', left: 90, bottom: 150, zIndex: 5, transform: `translateY(${(1 - enter) * 54}px)`}}>
          {bigNumber ? <Paper tone="red" rotate={-3} style={{display: 'inline-block', padding: '22px 34px', fontSize: 102, lineHeight: 1, fontWeight: 950, opacity: numberIn, transform: `translateX(${(1 - numberIn) * -130}px) rotate(-3deg)`}}>{bigNumber}</Paper> : null}
          <Paper rotate={1} style={{width: 980, marginTop: -6, padding: '28px 36px', opacity: titleIn, transform: `translateY(${(1 - titleIn) * 54}px) rotate(1deg)`}}>
            <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 66, lineHeight: 1.04, fontWeight: 950}}>{title}</div>
          </Paper>
          <div style={{marginTop: 22, opacity: verdictIn, transform: `translateX(${(1 - verdictIn) * 55}px)`}}><Stamp>不是一句“避险”就能解释</Stamp></div>
        </div>
        <RedThread progress={interpolate(shotFloat, [1.7, 3.2], [0, 1], clamp)} />
      </>
    );
  } else if (state === 'central_question') {
    content = (
      <>
        <TitleBlock eyebrow={visual.eyebrow} title="把问题缩成一句话" progress={enter} compact />
        <Paper rotate={-1} style={{position: 'absolute', left: 260, right: 260, top: 350, padding: '66px 72px', textAlign: 'center', opacity: enter, transform: `scale(${.9 + enter * .1}) rotate(-1deg)`}}>
          <Tape left={260} /><Tape right={240} rotate={5} />
          <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 70, lineHeight: 1.12, fontWeight: 950}}>{title}</div>
          <div style={{height: 10, width: `${thread * 86}%`, margin: '45px auto 0', background: C.red}} />
        </Paper>
      </>
    );
  } else if (state === 'evidence_map') {
    content = <><TitleBlock eyebrow={visual.eyebrow} title={title} progress={enter} compact /><EvidenceMap items={nodes} progress={progress} activeIndex={shotIndex} shotCount={shotCount} /></>;
  } else if (state === 'historical_context' || state === 'field_or_human_evidence' || state === 'data_resolution') {
    content = <><TitleBlock eyebrow={visual.eyebrow} title={title} progress={enter} compact />{values.length ? <DataBoard labels={labels} values={values} unit={visual.unit} progress={progress} reserveRight={Boolean(visual.pip_video_src)} activeIndex={shotIndex} shotCount={shotCount} /> : <EvidenceMap items={nodes} progress={progress} activeIndex={shotIndex} shotCount={shotCount} />}</>;
  } else if (state === 'counterargument') {
    content = <><TitleBlock eyebrow={visual.eyebrow} title={title} progress={enter} compact /><CounterBoard left={visual.left || {title: '短期解释', value: '价格会回撤'}} right={visual.right || {title: '长期结构', value: '机制仍需验证'}} progress={progress} activeIndex={shotIndex} /></>;
  } else if (state === 'qualified_conclusion') {
    content = <><TitleBlock eyebrow={visual.eyebrow} title={title} progress={enter} compact /><ConclusionBoard points={visual.points || nodes} progress={progress} activeIndex={shotIndex} /></>;
  } else {
    content = <><TitleBlock eyebrow={visual.eyebrow} title={title} progress={enter} compact /><MechanismBoard items={nodes} progress={progress} activeIndex={shotIndex} shotCount={shotCount} /></>;
  }

  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: hasVideo ? 'rgba(24,20,16,.20)' : C.ink}}>
      <div style={{position: 'absolute', inset: -70, opacity: hasVideo ? .18 : .96, backgroundColor: C.paper, backgroundImage: 'repeating-linear-gradient(0deg,rgba(82,64,36,.06) 0,rgba(82,64,36,.06) 1px,transparent 1px,transparent 5px),radial-gradient(circle at 20% 20%,rgba(255,255,255,.42),transparent 38%),radial-gradient(circle at 80% 70%,rgba(93,57,24,.16),transparent 42%)', transform: `translate(${cameraX}px,${cameraY}px) scale(${cameraScale}) rotate(${Math.sin(frame / 80) * .25}deg)`}} />
      {visual.motion_plate_src ? (
        <Paper rotate={state === 'cold_open' ? 0 : -1} style={state === 'cold_open' ? {position: 'absolute', inset: 0, overflow: 'hidden', opacity: .82, boxShadow: 'none'} : {position: 'absolute', left: 110, right: 110, top: 170, bottom: 110, overflow: 'hidden', opacity: .72}}>
          <OffthreadVideo src={staticFile(visual.motion_plate_src)} startFrom={Math.max(0, Math.round((visual.background_video_start_sec || 0) * fps))} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </Paper>
      ) : visual.keyframe_start_src ? (
        <>
          <Img src={staticFile(visual.keyframe_start_src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: visual.keyframe_end_src ? interpolate(progress, [.55, .9], [.42, 0], clamp) : .42}} />
          {visual.keyframe_end_src ? <Img src={staticFile(visual.keyframe_end_src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: interpolate(progress, [.55, .9], [0, .42], clamp)}} /> : null}
        </>
      ) : null}
      <div style={{position: 'absolute', inset: 0, transform: `translate(${cameraX}px,${cameraY}px) scale(${cameraScale})`, transformOrigin: '50% 52%'}}>{content}</div>
      {state !== 'cold_open' ? <MicroShotRibbon label={activeShot.action || activeShot.phase} index={shotIndex} count={shotCount} enter={shotEnter} /> : null}
      <EvidenceVideoScrap src={visual.pip_video_src} startFrom={pipStart} enter={interpolate(shotFloat, [1.2, 1.7], [0, 1], clamp)} />
      <SourceStamp text={visual.source} />
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity: .16, backgroundImage: 'repeating-radial-gradient(circle at 0 0,transparent 0,rgba(0,0,0,.35) 1px,transparent 2px)', backgroundSize: '5px 5px', mixBlendMode: 'multiply'}} />
    </div>
  );
};
