import React from 'react';
import {Composition} from 'remotion';
import {DirectorVideo} from './DirectorVideo';
import type {DirectorPlan} from './types';

const plan = require('../data/scene_plan.json') as DirectorPlan;
const fps = plan.fps ?? 30;
const durationSec = Math.max(...plan.scenes.map((scene) => scene.end_sec), 1);

export const RemotionRoot: React.FC = () => (
  <Composition
    id="DirectorVideo"
    component={DirectorVideo}
    durationInFrames={Math.ceil(durationSec * fps)}
    fps={fps}
    width={plan.width ?? 1920}
    height={plan.height ?? 1080}
    defaultProps={plan}
  />
);
