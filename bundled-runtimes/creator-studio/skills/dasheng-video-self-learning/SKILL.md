---
name: dasheng-video-self-learning
description: Use when continuously tracking target creators, discovering new videos, learning director/design/storyboard/transition/chart DNA, and maintaining a versioned video-production knowledge base.
---

# Newma Video Self Learning

## Role

Run an optional, continuous learning loop around `dasheng-video-style-trainer`.
It discovers new creator videos, deduplicates them by platform video ID, and
reads them locally with `claude-real-video`. It then prepares a Codex review
packet containing every contact sheet, transcript, manifest, and output schema.
Codex reads that evidence directly and writes candidate rules into the knowledge
base.

It does not replace the director and it does not silently mutate approved DNA.

## Storage

All media and learning outputs must stay under:

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/每日博主自学习/
```

Never store downloaded videos, frames, contact sheets, transcripts, or notes in
the repository or any Skill directory.

## Daily Run

```bash
python3 scripts/run_mainline_stage.py video-self-learn
```

Manual discovery without downloading:

```bash
python3 scripts/run_video_creator_self_learning.py --discover-only
```

Analyze the latest item for every tracked creator even when it was baselined:

```bash
python3 scripts/run_video_creator_self_learning.py --backfill-latest 1
```

Install the macOS schedule:

```bash
python3 scripts/install_video_self_learning_schedule.py
```

Default schedule: every day at `22:00 Asia/Shanghai`. The scheduled process only
discovers videos, downloads them, runs local CRV preprocessing, and creates the
Codex review queue. It must not send contact sheets, transcripts, or manifests to
MiniMax or another external analysis model. Director analysis is completed by
Codex reading the review packet directly.

## Learning Contract

Each completed video produces:

- CRV manifest, keyframes, grids, and report;
- `codex_review_packet.json` while the item is awaiting direct Codex review;
- `analysis.json` following the creator-learning schema;
- `analysis.md` written in director, design, storyboard, transition, production,
  chart, and aesthetic terminology;
- a creator-level rolling candidate profile;
- updates to the global director, aesthetic, technical-stack, and evolution notes.

## Technical Stack Mapping

The Agent may recommend ways to reproduce an observed expression using:

- Hyperframes;
- HTML Anything;
- Remotion;
- GSAP;
- Lottie;
- html-video;
- FFmpeg.

These are reproduction recommendations, not claims about what the original
creator used.

## Safety And Quality Rules

- Use persistent Chrome cookies through `yt-dlp --cookies-from-browser chrome`;
  never create a temporary browser login profile.
- Never use MiniMax for video reading, visual interpretation, transcript
  interpretation, JSON repair, or director analysis. MiniMax remains available
  only to downstream media-generation stages such as voice, music, and images.
- Only new or retryable video IDs enter the heavy analysis path.
- Successful analysis deletes the downloaded source cache while retaining CRV
  evidence and knowledge notes.
- Preserve approved historical profiles. New rules remain
  `candidate_not_approved` until human review.
- Do not copy scripts, creator footage, logos, subtitles, or exclusive packaging.
- Do not optimize for maximum cut count. Record core-scene integrity, evidence
  readability, and semantic cut triggers.

## Source Files

- Watchlist: `configs/video/creator_learning_watchlist.json`
- Taxonomy: `configs/video/creator_learning_taxonomy.json`
- Analysis schema: `configs/video/artifact_schemas/creator_learning_analysis.schema.json`
- Runner: `scripts/run_video_creator_self_learning.py`
- Schedule installer: `scripts/install_video_self_learning_schedule.py`
