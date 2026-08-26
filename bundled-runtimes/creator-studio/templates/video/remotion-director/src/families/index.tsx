import React from 'react';
import {
  Easing,
  Img,
  interpolate,
  OffthreadVideo,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {FamilyProps} from '../types';
import {VoxEditorialCollageFamily} from './VoxEditorialCollageFamily';

const P = {
  ink: '#14211d',
  paper: '#f5f2e9',
  green: '#0d766e',
  coral: '#d65c45',
  gold: '#c6933a',
  blue: '#396b88',
  muted: '#67716d',
  line: '#c9cec7',
};
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const ease = Easing.bezier(0.16, 1, 0.3, 1);
const progress = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, end], [0, 1], {...clamp, easing: ease});
const motionStage = (frame: number, duration: number, startRatio: number, endRatio: number) =>
  progress(frame, Math.round(duration * startRatio), Math.max(Math.round(duration * endRatio), Math.round(duration * startRatio) + 1));
const pipSafeRight = (speakerState?: string, hasEvidencePip = false) => {
  if (hasEvidencePip) return 535;
  if (speakerState === 'rounded_rect_pip') return 535;
  if (speakerState === 'circle_pip') return 405;
  if (speakerState === 'vertical_strip' || speakerState === 'half_right') return 525;
  return 150;
};
const hasEvidencePip = (scene: FamilyProps['scene']) => Boolean(
  scene.template_id === 'broll-fullscreen' && (scene.visual?.pip_items?.length || scene.visual?.pip_video_src || scene.visual?.pip_image_src || scene.visual?.secondary_pip_image_src),
);

const SourceTag: React.FC<{text?: string}> = ({text}) => {
  if (!text) return null;
  return (
    <div style={{position: 'absolute', left: 72, bottom: 150, maxWidth: 1180, padding: '6px 10px', borderRadius: 9, background: 'rgba(245,242,233,.84)', fontSize: 17, color: P.ink, letterSpacing: '0.04em'}}>
      来源：{text}
    </div>
  );
};

const SceneTitle: React.FC<{eyebrow: string; title: string; align?: 'left' | 'center'}> = ({eyebrow, title, align = 'left'}) => {
  const frame = useCurrentFrame();
  const titleProgress = 0.55 + progress(frame, 0, 18) * 0.45;
  return (
    <div style={{position: 'absolute', left: 72, right: 72, top: 58, textAlign: align, opacity: titleProgress, transform: `translateY(${(1 - titleProgress) * 18}px)`}}>
      <div style={{fontSize: 17, fontWeight: 800, color: P.green, letterSpacing: '0.16em'}}>{eyebrow}</div>
      <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 52, lineHeight: 1.08, fontWeight: 800, marginTop: 10}}>{title}</div>
    </div>
  );
};

export const SpeakerAnchorFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const keywords = scene.visual?.keywords?.length ? scene.visual.keywords : ['问题', '证据', '结论'];
  const settle = spring({frame, fps, config: {damping: 160, stiffness: 105}});
  const keywordStep = motionBehavior.includes('constellation') ? 0.1 : 0.12;
  const displayMode = scene.visual?.display_mode || 'card';
  if (scene.beat_class === 'hook') {
    return (
      <>
        <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(90deg,rgba(9,24,21,.84),rgba(9,24,21,.42) 48%,rgba(9,24,21,0) 76%)'}} />
        <div style={{position: 'absolute', left: 84, top: 120, width: 870, color: 'white', transform: `translateX(${(1 - settle) * -58}px)`, opacity: 0.5 + settle * 0.5}}>
          <div style={{fontSize: 19, color: '#9ed4c7', fontWeight: 900, letterSpacing: '0.18em'}}>{scene.visual?.eyebrow || '商业航天估值'}</div>
          <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 76, lineHeight: 1.04, fontWeight: 900, marginTop: 20}}>{scene.title}</div>
          <div style={{width: 150 * settle, height: 8, borderRadius: 999, background: P.coral, marginTop: 34}} />
        </div>
        <div style={{position: 'absolute', left: 86, bottom: 92, display: 'flex', gap: 12}}>
          {keywords.map((keyword, index) => {
            const p = motionStage(frame, duration, 0.12 + index * keywordStep, 0.34 + index * keywordStep);
            return <div key={keyword} style={{padding: '12px 18px', borderRadius: 999, background: index === keywords.length - 1 ? P.green : 'rgba(255,255,255,.92)', color: index === keywords.length - 1 ? 'white' : P.ink, fontSize: 23, fontWeight: 800, transform: `translateY(${(1 - p) * 22}px)`, opacity: p}}>{keyword}</div>;
          })}
        </div>
      </>
    );
  }
  if (displayMode === 'clean') return null;
  if (displayMode === 'keyword_only') {
    return (
      <div style={{position: 'absolute', left: 76, bottom: 94, display: 'flex', gap: 12}}>
        {keywords.map((keyword, index) => {
          const p = motionStage(frame, duration, 0.12 + index * keywordStep, 0.34 + index * keywordStep);
          return <div key={keyword} style={{padding: '12px 18px', borderRadius: 999, background: index === keywords.length - 1 ? P.green : 'rgba(245,242,233,.90)', color: index === keywords.length - 1 ? 'white' : P.ink, fontSize: 23, fontWeight: 750, boxShadow: '0 12px 36px rgba(20,33,29,.12)', transform: `translateY(${(1 - p) * 22}px)`, opacity: p}}>{keyword}</div>;
        })}
      </div>
    );
  }
  return (
    <>
      <div style={{position: 'absolute', left: 70, top: 70, width: 620, padding: '30px 34px', borderRadius: 30, background: 'rgba(245,242,233,.90)', boxShadow: '0 20px 70px rgba(20,33,29,.18)', transform: `translateX(${(1 - settle) * -50}px)`}}>
        <div style={{fontSize: 18, color: P.green, fontWeight: 850, letterSpacing: '0.14em'}}>{scene.visual?.eyebrow || '核心判断'}</div>
        <div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 54, lineHeight: 1.08, fontWeight: 850, marginTop: 16}}>{scene.title}</div>
      </div>
      <div style={{position: 'absolute', left: 76, bottom: 94, display: 'flex', gap: 12}}>
        {keywords.map((keyword, index) => {
          const p = motionStage(frame, duration, 0.12 + index * keywordStep, 0.34 + index * keywordStep);
          return <div key={keyword} style={{padding: '12px 18px', borderRadius: 999, background: index === keywords.length - 1 ? P.green : 'rgba(245,242,233,.88)', color: index === keywords.length - 1 ? 'white' : P.ink, fontSize: 23, fontWeight: 750, transform: `translateY(${(1 - p) * 22}px)`, opacity: p}}>{keyword}</div>;
        })}
      </div>
    </>
  );
};

const chartPoints = (values: number[], width: number, height: number, min: number, max: number) => {
  const range = Math.max(1, max - min);
  return values.map((value, index) => ({
    x: values.length === 1 ? width / 2 : (index / (values.length - 1)) * width,
    y: height - ((value - min) / range) * height,
  }));
};

export const DataLineChartFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const series = scene.visual?.series?.length
    ? scene.visual.series
    : [{name: '待接入真实数据', color: P.green, values: [100, 102, 101, 105, 104, 108]}];
  const labels = scene.visual?.labels ?? series[0].values.map((_, index) => String(index + 1));
  const allChartValues = series.flatMap((item) => item.values);
  const chartMin = Math.min(...allChartValues);
  const chartMax = Math.max(...allChartValues);
  const labelTickCount = Math.min(6, labels.length);
  const labelTickIndexes = Array.from({length: labelTickCount}, (_, index) =>
    Math.round((index / Math.max(1, labelTickCount - 1)) * Math.max(0, labels.length - 1)),
  ).filter((value, index, values) => values.indexOf(value) === index);
  const axisP = motionStage(frame, duration, 0.04, 0.22);
  const annotationEnabled = motionBehavior.includes('annotation') || motionBehavior.includes('endpoint');
  const chartLateCue = motionStage(frame, duration, 0.72, 0.9);
  const primarySeries = series[0];
  const primaryStart = primarySeries.values[0] || 0;
  const primaryEnd = primarySeries.values[primarySeries.values.length - 1] || 0;
  const primaryChange = primaryStart === 0 ? 0 : ((primaryEnd / primaryStart) - 1) * 100;
  const safeRight = pipSafeRight(scene.speaker_state, hasEvidencePip(scene));
  if (scene.visual?.chart_type === 'bar') {
    const plotMin = Math.min(0, ...allChartValues);
    const plotMax = Math.max(0, ...allChartValues);
    const plotRange = Math.max(1, plotMax - plotMin);
    const plotWidth = 1360;
    const plotHeight = 500;
    const baselineY = ((plotMax - 0) / plotRange) * plotHeight + 55;
    const groupWidth = plotWidth / Math.max(1, labels.length);
    const barWidth = Math.min(82, Math.max(28, (groupWidth - 44) / Math.max(1, series.length)));
    return (
      <>
        <SceneTitle eyebrow={scene.visual?.eyebrow || '真实数据'} title={scene.visual?.headline || scene.title} />
        <svg viewBox="0 0 1500 650" style={{position: 'absolute', left: 120, top: 250, width: `calc(100% - ${120 + safeRight}px)`, height: 650, overflow: 'visible'}}>
          {[0, 1, 2, 3, 4].map((row) => <line key={row} x1={70} y1={55 + row * 125} x2={1435} y2={55 + row * 125} stroke={P.line} strokeWidth={1} />)}
          <line x1={70} y1={baselineY} x2={1435 * axisP} y2={baselineY} stroke={P.ink} strokeWidth={3} />
          {labels.map((label, labelIndex) => {
            const groupX = 80 + labelIndex * groupWidth;
            return <g key={label}>
              {series.map((item, seriesIndex) => {
                const value = item.values[labelIndex] ?? 0;
                const reveal = motionStage(frame, duration, 0.14 + labelIndex * 0.055 + seriesIndex * 0.03, 0.48 + labelIndex * 0.055 + seriesIndex * 0.03);
                const valueHeight = Math.abs(value) / plotRange * plotHeight * reveal;
                const x = groupX + (groupWidth - barWidth * series.length) / 2 + seriesIndex * barWidth;
                const y = value >= 0 ? baselineY - valueHeight : baselineY;
                const color = item.color ?? [P.green, P.coral, P.blue, P.gold][seriesIndex % 4];
                return <g key={`${item.name}-${label}`}>
                  <rect x={x} y={y} width={barWidth - 8} height={Math.max(2, valueHeight)} rx={10} fill={value < 0 ? P.coral : color} />
                  <text x={x + (barWidth - 8) / 2} y={value >= 0 ? y - 14 : y + valueHeight + 30} textAnchor="middle" fill={value < 0 ? P.coral : P.ink} fontSize={23} fontWeight={850}>{value.toFixed(Math.abs(value) < 10 ? 2 : 1)}</text>
                </g>;
              })}
              <text x={groupX + groupWidth / 2} y={610} textAnchor="middle" fill={P.muted} fontSize={23}>{label}</text>
            </g>;
          })}
          {series.length > 1 ? series.map((item, index) => <g key={item.name} transform={`translate(${90 + index * 235},18)`}><rect width={22} height={8} rx={4} fill={item.color ?? [P.green, P.coral, P.blue][index % 3]} /><text x={32} y={10} fill={P.muted} fontSize={19}>{item.name}</text></g>) : null}
        </svg>
        <SourceTag text={scene.visual?.source} />
      </>
    );
  }
  const chartSeries = series.map((item, seriesIndex) => {
    const points = chartPoints(item.values, 1300, 470, chartMin, chartMax).map((point) => ({x: point.x + 100, y: point.y + 70}));
    return {
      item,
      seriesIndex,
      points,
      endpoint: points[points.length - 1],
      color: item.color ?? [P.green, P.coral, P.blue][seriesIndex % 3],
      labelY: points[points.length - 1].y,
    };
  });
  const labelsByY = [...chartSeries].sort((left, right) => left.endpoint.y - right.endpoint.y);
  const minLabelY = 74;
  const maxLabelY = 535;
  const labelGap = 44;
  labelsByY.forEach((entry, index) => {
    entry.labelY = Math.max(entry.endpoint.y, index === 0 ? minLabelY : labelsByY[index - 1].labelY + labelGap);
  });
  const overflow = labelsByY.length ? Math.max(0, labelsByY[labelsByY.length - 1].labelY - maxLabelY) : 0;
  if (overflow > 0) labelsByY.forEach((entry) => { entry.labelY -= overflow; });
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '真实行情'} title={scene.visual?.headline || scene.title} />
      <svg viewBox="0 0 1500 650" style={{position: 'absolute', left: 120, top: 250, width: `calc(100% - ${120 + safeRight}px)`, height: 650, overflow: 'visible'}}>
        <line x1={80} y1={560} x2={1450 * axisP} y2={560} stroke={P.ink} strokeWidth={3} />
        <line x1={80} y1={560} x2={80} y2={560 - 500 * axisP} stroke={P.ink} strokeWidth={3} />
        {[0, 1, 2, 3, 4].map((row) => <line key={row} x1={80} y1={60 + row * 125} x2={1450} y2={60 + row * 125} stroke={P.line} strokeWidth={1} />)}
        {chartSeries.map(({item, seriesIndex, points, endpoint, color, labelY}) => {
          const lineP = motionStage(frame, duration, 0.2 + seriesIndex * 0.08, 0.62 + seriesIndex * 0.08);
          const annotationP = annotationEnabled
            ? motionStage(frame, duration, 0.64 + seriesIndex * 0.06, 0.84 + seriesIndex * 0.06)
            : lineP;
          const d = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
          return <g key={item.name}>
            <path d={d} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - lineP} />
            <circle cx={endpoint.x} cy={endpoint.y} r={12 * annotationP} fill={color} />
            <path d={`M ${endpoint.x - 8} ${endpoint.y} L ${endpoint.x - 42} ${labelY}`} fill="none" stroke={color} strokeWidth={3} opacity={annotationP} />
            <text x={endpoint.x - 52} y={labelY + 8} textAnchor="end" fill={color} fontSize={27} fontWeight={850} opacity={annotationP}>{item.name}</text>
          </g>;
        })}
        {labelTickIndexes.map((index) => <text key={`${labels[index]}-${index}`} x={100 + index * (1300 / Math.max(1, labels.length - 1))} y={610} textAnchor="middle" fill={P.muted} fontSize={20}>{labels[index]}</text>)}
        <text x={65} y={82} textAnchor="end" fill={P.muted} fontSize={20}>{chartMax.toFixed(1)}</text>
        <text x={65} y={555} textAnchor="end" fill={P.muted} fontSize={20}>{chartMin.toFixed(1)}</text>
      </svg>
      <div style={{position: 'absolute', right: 90, top: 82, minWidth: 250, padding: '18px 22px', borderRadius: 20, background: P.ink, color: 'white', opacity: chartLateCue, transform: `translateY(${(1 - chartLateCue) * 22}px)`}}>
        <div style={{fontSize: 16, color: '#b8c7c1', letterSpacing: '0.08em'}}>{primarySeries.name} 区间变化</div>
        <div style={{fontSize: 42, fontWeight: 900, marginTop: 4}}>{primaryChange >= 0 ? '+' : ''}{primaryChange.toFixed(1)}%</div>
      </div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const ValuationCompareFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const metrics = scene.visual?.metrics?.length
    ? scene.visual.metrics
    : [{label: '公司 A', value: 14, peer: '可比公司', peer_value: 24}];
  const max = Math.max(...metrics.flatMap((metric) => [metric.value, metric.peer_value ?? 0]), 1);
  const metricStep = motionBehavior.includes('peer') ? 0.1 : 0.08;
  const valuationLateCue = motionStage(frame, duration, 0.7, 0.9);
  const leadMetric = metrics[0];
  const valueSuffix = scene.visual?.unit || 'x';
  const leadPeerValue = leadMetric.peer_value ?? 0;
  const relativeGap = leadPeerValue === 0 ? 0 : (1 - leadMetric.value / leadPeerValue) * 100;
  const safeRight = pipSafeRight(scene.speaker_state, hasEvidencePip(scene));
  if (metrics.length === 1) {
    const ownP = motionStage(frame, duration, 0.12, 0.48);
    const peerP = motionStage(frame, duration, 0.28, 0.64);
    return (
      <>
        <SceneTitle eyebrow={scene.visual?.eyebrow || '估值对比'} title={scene.visual?.headline || scene.title} />
        <div style={{position: 'absolute', left: 150, right: safeRight, top: 270, bottom: 150, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28}}>
          {[
            {label: leadMetric.label, value: leadMetric.value, color: P.green, p: ownP, eyebrow: '当前估值'},
            {label: leadMetric.peer ?? '可比公司', value: leadPeerValue, color: P.coral, p: peerP, eyebrow: '可比估值'},
          ].map((item) => <div key={item.label} style={{padding: '42px 46px', borderRadius: 32, background: '#fff', borderTop: `12px solid ${item.color}`, boxShadow: '0 26px 80px rgba(20,33,29,.12)', opacity: item.p, transform: `translateY(${(1 - item.p) * 34}px)`}}>
            <div style={{fontSize: 18, color: item.color, fontWeight: 900, letterSpacing: '0.14em'}}>{item.eyebrow}</div>
            <div style={{fontSize: 34, fontWeight: 850, marginTop: 28}}>{item.label}</div>
            <div style={{fontFamily: 'Iowan Old Style, Georgia, serif', fontSize: 104, lineHeight: 1, fontWeight: 900, marginTop: 42, color: item.color}}>{item.value.toFixed(1)}{valueSuffix}</div>
            <div style={{height: 12, borderRadius: 999, background: '#e6eae5', marginTop: 54, overflow: 'hidden'}}><div style={{height: '100%', width: `${Math.min(100, (item.value / Math.max(leadMetric.value, leadPeerValue, 1)) * 100) * item.p}%`, background: item.color}} /></div>
          </div>)}
        </div>
        <div style={{position: 'absolute', left: 150, bottom: 82, padding: '14px 20px', borderRadius: 16, background: P.ink, color: 'white', opacity: valuationLateCue, transform: `translateY(${(1 - valuationLateCue) * 20}px)`, fontSize: 25, fontWeight: 850}}>
          {leadMetric.label} 相对 {leadMetric.peer ?? '同业'} {relativeGap >= 0 ? '低' : '高'} {Math.abs(relativeGap).toFixed(0)}%
        </div>
        <SourceTag text={scene.visual?.source} />
      </>
    );
  }
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '估值对比'} title={scene.visual?.headline || scene.title} />
      <div style={{position: 'absolute', left: 150, right: safeRight, top: 260, bottom: 120, display: 'grid', alignContent: 'center', gap: 34}}>
        {metrics.map((metric, index) => {
          const ownP = motionStage(frame, duration, 0.16 + index * metricStep, 0.5 + index * metricStep);
          const peerP = motionStage(frame, duration, 0.28 + index * metricStep, 0.66 + index * metricStep);
          const ownWidth = (metric.value / max) * 1050 * ownP;
          const peerWidth = ((metric.peer_value ?? 0) / max) * 1050 * peerP;
          return <div key={`${metric.label}-${index}`} style={{display: 'grid', gridTemplateColumns: '190px 1fr', gap: 28, alignItems: 'center'}}>
            <div style={{fontSize: 31, fontWeight: 850}}>{metric.label}<div style={{fontSize: 18, color: P.muted, marginTop: 4}}>vs {metric.peer ?? 'peer'}</div></div>
            <div style={{display: 'grid', gap: 10}}>
              <div style={{height: 46, width: ownWidth, minWidth: 2, borderRadius: 12, background: P.green, color: 'white', padding: '7px 14px', fontSize: 24, fontWeight: 850, whiteSpace: 'nowrap'}}>{metric.value}</div>
              <div style={{height: 36, width: peerWidth, minWidth: 2, borderRadius: 10, background: P.coral, color: 'white', padding: '4px 12px', fontSize: 20, fontWeight: 800, whiteSpace: 'nowrap'}}>{metric.peer_value}</div>
            </div>
          </div>;
        })}
      </div>
      <div style={{position: 'absolute', left: 170, bottom: 88, padding: '14px 20px', borderRadius: 16, background: 'rgba(13,118,110,.12)', border: `1px solid ${P.green}`, color: P.green, opacity: valuationLateCue, transform: `translateX(${(1 - valuationLateCue) * -24}px)`, fontSize: 24, fontWeight: 850}}>
        {leadMetric.label} 相对 {leadMetric.peer ?? '同业'} {relativeGap >= 0 ? '低' : '高'} {Math.abs(relativeGap).toFixed(0)}%
      </div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const DocumentExactCropFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const p = spring({frame, fps, config: {damping: 170, stiffness: 100}});
  const focusStart = motionBehavior.includes('marker_focus') ? 0.34 : 0.28;
  const focus = motionStage(frame, duration, focusStart, 0.64);
  const calloutP = motionStage(frame, duration, 0.58, 0.82);
  const documentLateCue = motionStage(frame, duration, 0.68, 0.9);
  const detailP = scene.visual?.document_detail_src ? motionStage(frame, duration, 0.46, 0.68) : 0;
  const callouts = scene.visual?.callouts ?? ['精确页码', '精确行列'];
  const safeRight = pipSafeRight(scene.speaker_state, hasEvidencePip(scene));
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '公开资料'} title={scene.visual?.document_title || scene.visual?.headline || scene.title} />
      <div style={{position: 'absolute', left: 165, right: safeRight, top: 230, height: 690, borderRadius: 28, overflow: 'hidden', background: '#fff', boxShadow: '0 30px 90px rgba(20,33,29,.22)', transform: `translateY(${(1 - p) * 30}px)`}}>
        {scene.visual?.document_src ? <Img src={staticFile(scene.visual.document_src)} style={{width: '100%', height: '100%', objectFit: 'contain', objectPosition: '50% 50%', background: '#fff', opacity: 1 - detailP}} /> : <div style={{padding: 70}}><div style={{fontFamily: 'Georgia, serif', fontSize: 28, color: P.muted}}>OFFICIAL DOCUMENT / DEMO</div><div style={{fontFamily: 'Georgia, serif', fontSize: 58, fontWeight: 800, marginTop: 24}}>{scene.visual?.document_title ?? 'Exact source region'}</div><div style={{height: 2, background: P.line, margin: '36px 0'}} />{[0, 1, 2, 3, 4].map((row) => <div key={row} style={{height: 34, width: `${88 - row * 7}%`, background: row === 2 ? 'rgba(13,118,110,.16)' : '#e7e9e5', marginBottom: 20, borderRadius: 8}} />)}</div>}
        {scene.visual?.document_detail_src ? <Img src={staticFile(scene.visual.document_detail_src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', objectPosition: '50% 50%', background: '#fff', opacity: detailP}} /> : null}
        {!scene.visual?.disable_highlight ? <div style={{position: 'absolute', left: 120, right: 150, top: 335, height: 105, border: `5px solid ${P.coral}`, borderRadius: 18, opacity: focus, boxShadow: '0 0 0 999px rgba(20,33,29,.18)'}} /> : null}
        {!scene.visual?.disable_highlight ? <div style={{position: 'absolute', left: 120, top: 280, padding: '10px 16px', borderRadius: 12, background: P.coral, color: 'white', fontSize: 20, fontWeight: 850, opacity: documentLateCue, transform: `translateY(${(1 - documentLateCue) * 18}px)`}}>定位到当前命题的关键区域</div> : null}
        <div style={{position: 'absolute', right: 40, top: 40, display: 'grid', gap: 10}}>{callouts.map((callout, index) => <div key={callout} style={{padding: '10px 14px', borderRadius: 12, background: index === 0 ? P.green : P.ink, color: 'white', fontSize: 19, transform: `translateX(${(1 - calloutP) * 28}px)`, opacity: calloutP}}>{callout}</div>)}</div>
      </div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const EvidenceTableFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const columns = scene.visual?.columns ?? ['指标', '数值', '来源'];
  const rows = scene.visual?.rows?.length ? scene.visual.rows : [['待补', '待补', '待核验']];
  const safeRight = pipSafeRight(scene.speaker_state, hasEvidencePip(scene));
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '关键数据'} title={scene.visual?.headline || scene.title} />
      <div style={{position: 'absolute', left: 120, right: safeRight, top: 250, borderRadius: 28, overflow: 'hidden', border: `1px solid ${P.line}`, background: 'rgba(255,255,255,.90)', boxShadow: '0 25px 75px rgba(20,33,29,.12)'}}>
        <div style={{display: 'grid', gridTemplateColumns: `repeat(${columns.length}, 1fr)`, background: P.ink, color: 'white'}}>{columns.map((column) => <div key={column} style={{padding: '20px 24px', fontSize: 23, fontWeight: 850}}>{column}</div>)}</div>
        {rows.map((row, rowIndex) => {
          const rowStep = Math.min(0.12, 0.45 / Math.max(1, rows.length));
          const p = motionStage(frame, duration, 0.14 + rowIndex * rowStep, 0.38 + rowIndex * rowStep);
          const emphasis = motionBehavior.includes('cell_emphasis') ? motionStage(frame, duration, 0.66, 0.86) : 1;
          return <div key={rowIndex} style={{display: 'grid', gridTemplateColumns: `repeat(${columns.length}, 1fr)`, borderTop: `1px solid ${P.line}`, opacity: p, transform: `translateX(${(1 - p) * 32}px)`, background: rowIndex % 2 ? '#f0f3ee' : '#fff'}}>{columns.map((_, colIndex) => <div key={colIndex} style={{padding: '22px 24px', fontSize: 24, fontWeight: colIndex === 1 ? 850 : 550, color: colIndex === 1 ? P.green : P.ink, transform: colIndex === 1 ? `scale(${0.96 + emphasis * 0.04})` : undefined, transformOrigin: 'left center'}}>{row[colIndex] ?? '-'}</div>)}</div>;
        })}
      </div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const LogicFlowFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const nodes = scene.visual?.nodes?.length ? scene.visual.nodes : ['条件', '机制', '结果'];
  const conclusionLock = motionBehavior.includes('conclusion_lock') ? motionStage(frame, duration, 0.68, 0.88) : 0;
  const logicLateCue = motionStage(frame, duration, 0.72, 0.9);
  const safeRight = pipSafeRight(scene.speaker_state, hasEvidencePip(scene));
  const nodeWidth = nodes.length >= 5 ? 180 : nodes.length === 4 ? 230 : 300;
  const arrowWidth = nodes.length >= 5 ? 70 : nodes.length === 4 ? 85 : 120;
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '逻辑链条'} title={scene.title} />
      <div style={{position: 'absolute', left: 110, right: safeRight, top: 380, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20}}>
        {nodes.map((node, index) => {
          const nodeStep = Math.min(0.14, 0.48 / Math.max(1, nodes.length));
          const p = motionStage(frame, duration, 0.12 + index * nodeStep, 0.34 + index * nodeStep);
          return <React.Fragment key={node}>
            <div style={{width: nodeWidth, minHeight: 150, padding: 24, borderRadius: 28, display: 'grid', placeItems: 'center', textAlign: 'center', background: index === nodes.length - 1 ? P.green : '#fff', color: index === nodes.length - 1 ? 'white' : P.ink, border: `2px solid ${index === nodes.length - 1 ? P.green : P.line}`, boxShadow: index === nodes.length - 1 ? `0 0 ${50 * conclusionLock}px rgba(13,118,110,.38)` : undefined, fontSize: nodes.length >= 5 ? 25 : 29, fontWeight: 850, transform: `translateY(${(1 - p) * 36}px)`, opacity: p}}>{node}</div>
            {index < nodes.length - 1 ? <svg width={arrowWidth} height="60" viewBox="0 0 120 60"><path d="M4 30 H104" stroke={P.coral} strokeWidth={6} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} /><path d="M88 14 L108 30 L88 46" fill="none" stroke={P.coral} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" opacity={p} /></svg> : null}
          </React.Fragment>;
        })}
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 150, textAlign: 'center', opacity: logicLateCue, transform: `translateY(${(1 - logicLateCue) * 18}px)`, fontSize: 26, fontWeight: 850, color: P.green}}>链条最终落到：{nodes[nodes.length - 1]}</div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const ProductUiFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const tasks = scene.visual?.tasks?.length ? scene.visual.tasks : ['输入任务', 'Agent 执行', '返回结果'];
  const device = spring({frame, fps, config: {damping: 170, stiffness: 105}});
  const resultLock = motionBehavior.includes('result_confirmation') ? motionStage(frame, duration, 0.72, 0.9) : 1;
  const productLateCue = motionStage(frame, duration, 0.74, 0.92);
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '交互演示'} title={scene.title} />
      <div style={{position: 'absolute', left: 540, top: 235, width: 840, height: 700, borderRadius: 56, border: `12px solid ${P.ink}`, background: '#fbfcfa', overflow: 'hidden', boxShadow: '0 35px 100px rgba(20,33,29,.22)', transform: `translateY(${(1 - device) * 50}px) rotate(${(1 - device) * -2}deg)`}}>
        <div style={{height: 70, background: P.ink, color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', fontSize: 20}}><span>AI WORKSPACE</span><span>LIVE TASK</span></div>
        <div style={{padding: 40, display: 'grid', gap: 22}}>{tasks.map((task, index) => {
          const taskStep = Math.min(0.15, 0.48 / Math.max(1, tasks.length));
          const p = motionStage(frame, duration, 0.18 + index * taskStep, 0.4 + index * taskStep);
          const scale = index === tasks.length - 1 ? 0.98 + resultLock * 0.02 : 1;
          return <div key={task} style={{display: 'grid', gridTemplateColumns: '54px 1fr', alignItems: 'center', gap: 18, padding: '22px 24px', borderRadius: 20, background: index === tasks.length - 1 ? 'rgba(13,118,110,.12)' : '#eef1ec', transform: `translateX(${(1 - p) * 38}px) scale(${scale})`, opacity: p}}><div style={{width: 48, height: 48, display: 'grid', placeItems: 'center', borderRadius: '50%', background: index === tasks.length - 1 ? P.green : P.ink, color: 'white', fontWeight: 900}}>{index + 1}</div><div style={{fontSize: 27, fontWeight: 750}}>{task}</div></div>;
        })}</div>
      </div>
      <div style={{position: 'absolute', right: 470, bottom: 86, padding: '14px 22px', borderRadius: 16, background: P.green, color: 'white', opacity: productLateCue, transform: `translateY(${(1 - productLateCue) * 20}px)`, fontSize: 23, fontWeight: 850}}>✓ {tasks[tasks.length - 1]} 已完成</div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const BrollFullscreenFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const driftScale = motionBehavior.includes('subject_return') ? 1.25 : 1;
  const drift = Math.sin(frame / 24) * 24 * driftScale;
  const reveal = motionStage(frame, duration, 0.08, 0.34);
  return (
    <>
      {scene.visual?.broll_src ? <OffthreadVideo src={staticFile(scene.visual.broll_src)} startFrom={Math.round((scene.visual.broll_start_sec || 0) * fps)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: 'linear-gradient(135deg,#173b37,#365f59 48%,#9b684d)'}}><div style={{position: 'absolute', width: 760, height: 760, borderRadius: '50%', left: 130 + drift, top: 150, background: 'rgba(255,255,255,.10)'}} /><div style={{position: 'absolute', width: 680, height: 330, right: 100 - drift, bottom: 130, borderRadius: 80, border: '2px solid rgba(255,255,255,.32)', transform: 'rotate(-8deg)'}} /></div>}
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(90deg,rgba(10,20,18,.72),rgba(10,20,18,.18) 62%,rgba(10,20,18,.05))'}} />
      <div style={{position: 'absolute', left: 90, top: 260, width: 1150, color: 'white', opacity: reveal, transform: `translateY(${(1 - reveal) * 30}px)`}}><div style={{fontSize: 18, letterSpacing: '0.17em', fontWeight: 800}}>{scene.visual?.eyebrow || '现场画面'}</div><div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: scene.title.length > 20 ? 60 : 72, fontWeight: 850, lineHeight: 1.05, marginTop: 18}}>{scene.title}</div><div style={{fontSize: 26, lineHeight: 1.5, marginTop: 24, maxWidth: 850}}>{scene.visual?.context ?? ''}</div></div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const SplitComparisonFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const left = scene.visual?.left ?? {title: '事实', value: '可核验数据'};
  const right = scene.visual?.right ?? {title: '判断', value: '作者推演'};
  const leftP = motionStage(frame, duration, 0.08, 0.34);
  const rightP = motionStage(frame, duration, 0.26, 0.54);
  const verdictP = motionBehavior.includes('verdict') ? motionStage(frame, duration, 0.64, 0.88) : 1;
  const splitLateCue = motionStage(frame, duration, 0.72, 0.92);
  return (
    <>
      <SceneTitle eyebrow={scene.visual?.eyebrow || '结构对比'} title={scene.title} align="center" />
      {scene.visual?.context ? <div style={{position: 'absolute', left: '50%', top: 185, transform: 'translateX(-50%)', padding: '9px 16px', borderRadius: 999, background: 'rgba(20,33,29,.82)', color: 'white', fontSize: 18, fontWeight: 750}}>{scene.visual.context}</div> : null}
      <div style={{position: 'absolute', left: 100, right: 100, top: 245, bottom: 105, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24}}>
        {[{...left, p: leftP, color: P.green, x: -70}, {...right, p: rightP, color: P.coral, x: 70}].map((item) => <div key={item.title} style={{borderRadius: 34, padding: 54, background: '#fff', borderTop: `12px solid ${item.color}`, boxShadow: '0 24px 70px rgba(20,33,29,.12)', opacity: item.p, transform: `translateX(${(1 - item.p) * item.x}px)`}}><div style={{fontSize: 21, fontWeight: 850, color: item.color, letterSpacing: '0.14em'}}>{item.title}</div><div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 62, lineHeight: 1.08, fontWeight: 850, marginTop: 48}}>{item.value}</div><div style={{height: 8, borderRadius: 999, background: '#e7eae5', marginTop: 70, overflow: 'hidden'}}><div style={{height: '100%', width: `${verdictP * 100}%`, background: item.color}} /></div></div>)}
      </div>
      <div style={{position: 'absolute', left: '50%', bottom: 60, transform: `translateX(-50%) scale(${0.92 + splitLateCue * 0.08})`, padding: '12px 22px', borderRadius: 999, background: P.ink, color: 'white', opacity: splitLateCue, fontSize: 22, fontWeight: 850}}>{left.title}不等于{right.title}</div>
      <SourceTag text={scene.visual?.source} />
    </>
  );
};

export const RecapOutroFamily: React.FC<FamilyProps> = ({scene, motionBehavior}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const duration = Math.max(1, Math.round(scene.duration_sec * fps));
  const points = scene.visual?.points?.length ? scene.visual.points : ['事实', '机制', '赔率'];
  const pointStep = motionBehavior.includes('progressive') ? 0.16 : 0.13;
  return (
    <div style={{position: 'absolute', inset: 0, background: P.ink, color: 'white'}}>
      <div style={{position: 'absolute', left: 110, top: 105, right: 110}}><div style={{fontSize: 19, color: '#9ec9bd', letterSpacing: '0.18em', fontWeight: 850}}>{scene.visual?.eyebrow || '结论回顾'}</div><div style={{fontFamily: 'Iowan Old Style, Songti SC, serif', fontSize: 75, lineHeight: 1.03, fontWeight: 850, marginTop: 20}}>{scene.title}</div></div>
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 150, display: 'grid', gridTemplateColumns: `repeat(${points.length},1fr)`, gap: 20}}>{points.map((point, index) => {
        const p = motionStage(frame, duration, 0.14 + index * pointStep, 0.38 + index * pointStep);
        return <div key={point} style={{minHeight: 220, padding: 32, borderRadius: 28, border: '1px solid rgba(255,255,255,.18)', background: index === points.length - 1 ? P.green : 'rgba(255,255,255,.07)', opacity: p, transform: `translateY(${(1 - p) * 36}px)`}}><div style={{fontSize: 19, color: '#b8c7c1'}}>0{index + 1}</div><div style={{fontSize: 33, fontWeight: 850, lineHeight: 1.2, marginTop: 48}}>{point}</div></div>;
      })}</div>
    </div>
  );
};

export const FAMILY_COMPONENTS: Record<string, React.FC<FamilyProps>> = {
  'speaker-anchor': SpeakerAnchorFamily,
  'data-line-chart': DataLineChartFamily,
  'valuation-compare': ValuationCompareFamily,
  'document-exact-crop': DocumentExactCropFamily,
  'evidence-table': EvidenceTableFamily,
  'logic-flow': LogicFlowFamily,
  'product-ui': ProductUiFamily,
  'broll-fullscreen': BrollFullscreenFamily,
  'split-comparison': SplitComparisonFamily,
  'recap-outro': RecapOutroFamily,
  'vox-editorial-collage': VoxEditorialCollageFamily,
};
