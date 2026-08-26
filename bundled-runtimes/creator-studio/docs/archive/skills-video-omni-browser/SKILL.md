---
name: dasheng-video-omni-browser
description: Turn approved VOX reference images into one approximately 10-second clip per director shot by operating the user's signed-in Gemini Omni page in Chrome, then return the downloaded clips for Remotion editing. Use when Gemini API access is unavailable but the Chrome session is already signed in.
---

# Newma Omni Browser Shots

Use this as the signed-in-browser executor inside `dasheng-vox-skills`. The unified Skill owns provider selection, attempt history and fallback; this component only generates and downloads the requested shots. `dasheng-video-vox` decides the story, evidence and composition.

## Input

- `omni_shot_manifest.json`
- One complete 16:9 reference image for every shot
- One Omni motion prompt for every shot
- Target clip path under `~/Desktop/自媒体创作`

Build or refresh the packet with:

```bash
python scripts/video_vox_omni_pack.py build --shots <shots.json> --output-dir <omni_pipeline>
python scripts/video_vox_omni_pack.py refresh --manifest <omni_shot_manifest.json>
```

## Workflow

1. Make each director shot about 10 seconds. Gemini generates one 10-second clip per shot; trim only in the final edit.
2. Codex designs and generates the completed reference composition with built-in `imagegen`, then saves the result to the declared project path. Do not use Chrome or Gemini to generate reference images. If the normal generated-image path is unavailable, persist the latest built-in `image_generation_call.result` from the active Codex rollout into the declared PNG path. Keep one visual bible across all shots.
3. The reference is Omni's target composition. Make it a flat, separable object map: one matte background, optionally one torn base panel, and only 4-6 major movable groups with generous gaps. Reject photorealistic dioramas, rooms, desks, miniature cities and dense newspaper worlds.
4. Open the user's existing Chrome Gemini tab. Use the signed-in session; do not read cookies, local storage, passwords or profile files.
5. Select Gemini video generation with Omni and horizontal 16:9 output.
6. Upload one reference image, paste its matching prompt and generate. Never ask Omni to create the whole film.
7. Download the resulting MP4 to the shot's declared `clip_path`. A failed shot is regenerated alone.
8. Inspect the opening, middle and final frame. Reject a completed poster shown before assembly, any object that disappears after arriving, unexpected objects, morphing, camera drift, broken cut-outs, readable fake text, flashes or an end frame that no longer matches the reference.
9. Return approved clips to Remotion. Remotion adds exact titles, figures, charts, citations, subtitles, real footage, audio and transitions.

If a CAPTCHA appears, stop and ask the user to complete it. Keep browser work in the existing window and avoid taking over the main display.

## Omni motion grammar

Use the supplied image as the target composition. Start with the matte background and optional base panel, then make each named group appear once in the director's order. Keep every group visible after it arrives. Keep the camera locked, finish by 9 seconds and hold the completed composition for the final second. If a shot repeatedly deconstructs or mutates, switch only that shot to `motion_mode: in_place` and use `motion_beats`.

Always require:

- flat 2D editorial paper collage, 4-6 major groups, halftone cut-outs, crisp paper edges, tactile grain and short physical shadows;
- fixed camera, no pan, zoom, cut or whole-frame drift;
- persistent base background; once an object arrives it stays visible; no dissolve, fade or blank flash;
- no new objects, no morphing, no alternate composition and no realistic 3D;
- no readable text, letters, numbers, logos, watermark, UI or sound.

## Routing

- Primary: Chrome signed-in Gemini Omni.
- Reserve only: MiniMax/MMX, Seedance or programmatic Remotion motion.
- Never use AtlasCloud, OpenRouter, Replicate or another third-party service key.

Runtime media belongs under `~/Desktop/自媒体创作`, never inside this Skill.

Provider boundary: `Codex imagegen -> local reference PNG -> Chrome Gemini Omni video`. Never collapse the first two stages into Gemini.
