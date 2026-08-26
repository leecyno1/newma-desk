# Prompt Templates

## Full Canvas

```text
Generate one standalone 16:9 horizontal Chinese editorial illustration for a finance/explainer video.

Visual language:
Pure white background. Minimal black hand-drawn line art with slightly wobbly pen lines. Large quiet blank areas. Sparse orange/red/blue handwritten Chinese annotations. Clean, absurd product-sketch feeling. No gradient, shadow, paper texture, commercial vector style, PPT infographic, cute poster, children's illustration, realistic UI, or complex background.

Recurring character:
柠檬人, an irregular lemon-yellow anthropomorphic systems operator with one small dark-green leaf, two tiny black dot eyes, extremely thin black arms and legs, no mouth or one tiny straight-line mouth, and a blank serious expression. It must perform the core conceptual action. It is deadpan and hardworking, not cute and not a mascot.

Theme: {theme}
Core idea: {one idea only}
Character action: {one concrete action}
Composition: {character position, main prop, information movement, blank-space position}
Suggested elements: {3-5 elements}
Chinese labels: {0-5 short labels}

Color:
Lemon yellow and dark green only for the character. Black for structure and main text. Orange for the main path. Red only for warning/result. Blue only for secondary system feedback.

Constraints:
Main subject occupies 40%-60% of the canvas; preserve at least 35% white space. No title in the top-left. Do not write the structure type. One image explains one action. Invent a new metaphor for this narration beat. No factual chart, number, logo, source page, or document unless supplied as verified input.
```

## Transparent Overlay

```text
Create one isolated transparent-overlay source asset for a talking-head finance video.

Subject:
The same recurring 柠檬人 identity: irregular lemon-yellow body, one small dark-green leaf, two tiny black dot eyes, thin black stick limbs, no smile, deadpan serious expression. The character performs exactly one action: {action}. Include only the one required prop: {prop}.

Style:
Minimal hand-drawn black line art, slightly imperfect contour, restrained yellow and dark green, readable silhouette, generous padding, no text, no title, no extra characters, no decorative background, no cast shadow.

Background:
Perfectly flat solid #ff00ff chroma-key background from edge to edge. No gradient, texture, floor, lighting variation, reflection, or magenta in the subject.
```

## Production Commands

Generate with the project-standard MiniMax CLI. The explicit base URL avoids the current `/v1` image-route mismatch:

```bash
mmx image generate \
  --prompt "<prompt>" \
  --aspect-ratio 16:9 \
  --subject-ref "type=character,image=$HOME/Desktop/自媒体创作/00_品牌资产/柠檬卡通人/lemon-person-master-reference-v2.jpg" \
  --base-url "https://api.minimaxi.com" \
  --out "<task-output-path>"
```

For transparent output:

```bash
python "$HOME/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py" \
  --input "<chroma-source>" \
  --out "<alpha-output.png>" \
  --auto-key border \
  --soft-matte \
  --transparent-threshold 12 \
  --opaque-threshold 220 \
  --despill
```

Use the single-character master as the subject reference. The action sheet is only a pose vocabulary reference and must not be cropped directly into production video.
