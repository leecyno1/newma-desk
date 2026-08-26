---
name: dasheng-video-style-trainer
description: Use when learning reusable video style DNA from many sample videos, training a blogger/channel editing style, or applying a learned style profile to Newma talking-head and no-human explainer video workflows.
---

# Newma Video Style Trainer

## Role

Build an optional video-learning asset before production. It analyzes user-provided reference videos and produces a reusable `style_profile.json` for later video generation.

This is not a mainline gate. The canonical chain remains:

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

Video training is an optional asset generator like article paradigm learning. Use it when the user provides many sample videos, names a target creator style, or asks future videos to follow a learned editing/visual rhythm.

For continuous creator monitoring and daily incremental learning, delegate to
`dasheng-video-self-learning`. The trainer owns one training run; the
self-learning module owns discovery, deduplication, scheduling, knowledge-base
updates, and rolling candidate profiles.

## Storage Rule

All videos, upload caches, training reports, rendered previews, audio, subtitles, and other generated media must stay outside the repo.

Default output root:

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/
```

Never write source videos or training outputs to:

- `skills/`
- project root
- `openclaw-skill-exports/`
- any skill package directory

Source videos may stay wherever the user provided them. The training manifest records their paths; it does not copy them into the repo.

## Train Style DNA

Default command:

```bash
python3 scripts/run_mainline_stage.py video-train \
  --video-dir <sample_video_dir> \
  --style-id <style_id> \
  --blogger-name "<name>" \
  --blogger-platform "<platform>"
```

Direct command:

```bash
python3 scripts/learn_blogger_video_style_local.py \
  --video-dir <sample_video_dir> \
  --style-id <style_id> \
  --blogger-name "<name>" \
  --blogger-platform "<platform>" \
  --output-dir ~/Desktop/自媒体创作/00_范式学习/视频训练
```

Requirements:

- Prefer local `claude-real-video` for first-pass video reading: scene-aware keyframes, contact sheets, manifest, and optional transcript.
- Do not upload reference videos to model providers in this stage.
- Use `ffprobe` and `ffmpeg` for metadata and oversized-video compression.
- Keep compressed upload copies under `<style_id>/_upload_cache/`.
- Use `--skip-aggregate` only for debugging single-video analysis.

Local video reading command:

```bash
python3 scripts/read_video_with_crv.py <video_or_url> \
  --output-dir ~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/crv/<video_stem> \
  --why "提取剪辑节奏、镜头构图、证据画面、转场和风格 DNA" \
  --report
```

Use `--transcribe` only when local Whisper is installed and transcription is needed. Do not store `crv-out` in the repo.

## Output Contract

Training must emit:

- `training_manifest.json`
- optional `crv/<video_stem>/dasheng_video_reading_manifest.json`
- `per_video/<video_stem>/analysis.json`
- `style_profile.json` unless `--skip-aggregate` is used
- `style_profile.md` unless `--skip-aggregate` is used
- `_upload_cache/*.upload.mp4` only when a source video exceeds upload limits

`training_manifest.json` must record:

- `stage: video-style-training`
- `style_id`
- sample video paths
- output paths
- model name
- status
- whether source videos were copied
- where compressed upload cache lives

## Apply Style

Before selecting a profile, read `configs/video/reference_video_dna_registry.json`.
Use `style_profile.curated.json` when the registry points to one; the automatically
aggregated `style_profile.json` is only the statistical fallback.

The registry distinguishes:

- fixed user-approved standard samples;
- rolling "latest creator video" samples with an explicit `checked_at` date;
- classic benchmarks that must not be silently replaced by a creator's latest format.

When refreshing a rolling sample, create a new dated training directory and registry
entry. Do not overwrite an approved historical profile in place.

Use a learned `style_profile.json` to drive HTML Anything and html-video timelines:

```bash
python3 scripts/apply_blogger_style_to_timeline.py \
  --style-profile ~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json \
  --storyboard ~/Desktop/自媒体创作/<run_id>/04_转写/<topic>/video_storyboard.json \
  --article-html ~/Desktop/自媒体创作/<run_id>/03_初稿/<topic>/03_HTML草稿_<topic>.html \
  --output-timeline ~/Desktop/自媒体创作/<run_id>/04_转写/<topic>/html_anything_video_timeline.style.json
```

End-to-end preview:

```bash
python3 scripts/run_blogger_style_video_pipeline.py \
  --style-profile ~/Desktop/自媒体创作/00_范式学习/视频训练/<style_id>/style_profile.json \
  --storyboard ~/Desktop/自媒体创作/<run_id>/04_转写/<topic>/video_storyboard.json \
  --article-html ~/Desktop/自媒体创作/<run_id>/03_初稿/<topic>/03_HTML草稿_<topic>.html \
  --output-dir ~/Desktop/自媒体创作/<run_id>/04_转写/<topic>/blogger_style_video
```

## Consumption Rules

- Talking-head videos use learned pacing, evidence interval, subtitle density, return-to-speaker rhythm, transition signature, and overlay placement.
- No-human explainer videos use learned template preferences, motion style, color palette, title/opening/outro patterns, and B-roll/data-scene density.
- Draft remains the fact source. Style training must not invent market data, charts, or claims.
- Style DNA controls form; article paradigm controls structure; account DNA controls voice.

## Quality Gate

Before using a style profile downstream, check:

- At least 3 representative sample videos unless the user explicitly requests a one-shot experiment.
- `style_profile.json` has `visual_dna`, `editing_dna`, and `template_preferences`.
- `talking_head_policy.blank_placeholder` is true for reference creators; user footage replaces the placeholder later.
- No generated media exists in repo root or any skill folder.
- The style profile describes reusable patterns rather than copying exact copyrighted frames, scripts, or slogans.
- The selected profile's scope matches the production lane. A sponsored interview must not replace a classic finance-explainer benchmark.
- A curated profile records both `strengths_to_reuse` and `limitations_not_to_copy`.
