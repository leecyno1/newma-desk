export type SceneAudio = {
  duck_bgm?: boolean;
  sfx?: string | null;
  sfx_src?: string;
  sfx_start_sec?: number;
  sfx_volume?: number;
  voice_priority?: string;
};

export type PipItem = {
  src: string;
  type?: 'image' | 'video';
  caption?: string;
  start_sec?: number;
  object_fit?: 'cover' | 'contain';
  object_position?: string;
};

export type TimedCaption = {
  text: string;
  startMs: number;
  endMs: number;
  confidence?: number;
  timingSource?: string;
};

export type VoxTextCue = {
  text: string;
  startMs: number;
  endMs: number;
  x?: number;
  y?: number;
  tone?: 'red' | 'gold' | 'cream' | 'ink';
};

export type VoxEntityLabel = VoxTextCue & {
  entityType?: 'person' | 'organization' | 'place' | 'object';
};

export type VoxMotionKeyframe = {
  at: number;
  x?: number;
  y?: number;
  z?: number;
  scale?: number;
  rotation?: number;
  rotate_x?: number;
  rotate_y?: number;
  opacity?: number;
  blur?: number;
};

export type VoxSceneLayer = {
  id: string;
  asset_type: 'image' | 'video' | 'text' | 'paper' | 'shape' | 'route' | 'bar_chart';
  src?: string;
  text?: string;
  label?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  anchor?: {x?: number; y?: number};
  mask?: string;
  object_fit?: 'cover' | 'contain' | 'fill';
  object_position?: string;
  color?: string;
  background?: string;
  border?: string;
  border_radius?: number;
  font_size?: number;
  font_weight?: number;
  font_family?: string;
  line_height?: number;
  text_align?: 'left' | 'center' | 'right';
  padding?: number;
  shadow?: string;
  mix_blend_mode?: React.CSSProperties['mixBlendMode'];
  entry_path?: VoxMotionKeyframe[];
  motion_path?: VoxMotionKeyframe[];
  exit_path?: VoxMotionKeyframe[];
  rotation_keyframes?: Array<{at: number; value: number}>;
  scale_keyframes?: Array<{at: number; value: number}>;
  occlusion_order?: number;
  stepped_fps?: number;
  route_path?: string;
  route_width?: number;
  route_color?: string;
  route_fill?: string;
  chart_values?: number[];
  chart_labels?: string[];
};

export type VisualPayload = {
  asset_id?: string;
  evidence_relation?: string;
  evidence_confidence?: string;
  disclosure?: string;
  display_mode?: 'clean' | 'keyword_only' | 'card';
  eyebrow?: string;
  headline?: string;
  source?: string;
  chart_type?: 'line' | 'bar';
  series?: Array<{name: string; color?: string; values: number[]}>;
  labels?: string[];
  metrics?: Array<{label: string; value: number; peer?: string; peer_value?: number}>;
  unit?: string;
  document_src?: string;
  document_detail_src?: string;
  disable_highlight?: boolean;
  document_title?: string;
  callouts?: string[];
  columns?: string[];
  rows?: string[][];
  nodes?: string[];
  tasks?: string[];
  broll_src?: string;
  broll_start_sec?: number;
  background_video_src?: string;
  background_video_start_sec?: number;
  background_video_opacity?: number;
  background_video_scrim?: number;
  pip_video_src?: string;
  pip_video_start_sec?: number;
  pip_video_object_position?: string;
  pip_image_src?: string;
  pip_image_caption?: string;
  secondary_pip_image_src?: string;
  secondary_pip_image_caption?: string;
  pip_items?: PipItem[];
  pip_expand_to_next?: boolean;
  pip_expand_index?: number;
  pip_expand_target?: 'fullscreen' | 'document';
  linked_entry_src?: string;
  linked_entry_type?: 'image' | 'video';
  linked_entry_start_sec?: number;
  linked_entry_object_fit?: 'cover' | 'contain';
  motion_plate_src?: string;
  keyframe_start_src?: string;
  keyframe_end_src?: string;
  collage_style?: string;
  world_id?: string;
  scene_layers?: VoxSceneLayer[];
  camera_keyframes?: VoxMotionKeyframe[];
  camera_perspective?: number;
  stepped_fps?: number;
  micro_shots?: Array<{
    id: string;
    action?: string;
    phase?: string;
    visual_mechanism?: string;
    camera_move?: string;
    start_ratio?: number;
    end_ratio?: number;
  }>;
  context?: string;
  left?: {title: string; value: string};
  right?: {title: string; value: string};
  points?: string[];
  keywords?: string[];
  emphasis_cues?: VoxTextCue[];
  entity_labels?: VoxEntityLabel[];
};

export type DirectorScene = {
  id: string;
  type?: string;
  narrative_function?: string;
  vox_state?: string;
  title: string;
  narration?: string;
  captions?: TimedCaption[];
  subtitle_timing_source?: string;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  beat_class: string;
  template_id: string;
  speaker_state: string;
  material_state: string;
  pip_shape: string;
  transition_in: string;
  transition_out: string;
  html_animation_behavior: string;
  audio: SceneAudio;
  visual?: VisualPayload;
  speaker_object_position?: string;
  camera?: {scale?: number; x?: number; y?: number};
};

export type DirectorPlan = {
  title?: string;
  fps?: number;
  width?: number;
  height?: number;
  source_video?: string;
  bgm_src?: string;
  voice_gain?: number;
  speaker_object_position?: string;
  scenes: DirectorScene[];
};

export type FamilyProps = {
  scene: DirectorScene;
  motionBehavior: string;
};
