---
name: dasheng-video-vox
description: Direct question-led VOX explainers through content distillation, conversational script rewriting, retention design, review storyboards, approved production-shot splitting, evidence footage, paper-collage visual grammar, image-to-video generation, Remotion composition, and governed QC. Use for investigative faceless videos that must be distinct from ordinary article-led explainers.
---

# Newma VOX Video

Build an independent `vox_explainer_video` lane. Do not restyle `explainer_html_video` or recite article chapters. For complete production and provider routing, use `dasheng-vox-skills`; this Skill remains its director and visual-grammar component.

Read [references/director-workflow.md](references/director-workflow.md) before any new script or storyboard. Read [references/visual-grammar.md](references/visual-grammar.md) only after the review storyboard is approved.

## Workflow

1. Build `video_content_brief.md`: lock one central question, one-sentence answer, 3-5 progressive claims, 4-8 decisive evidence items, one counterargument or boundary, one qualified forecast and 3-5 monitoring indicators.
2. Separate fact, opinion, inference, forecast, rumor and unknown before writing narration.
3. Rewrite the source into `narration_script.rewritten.md`. The article is a research dossier, not a teleprompter. Use a conversational creator or podcast voice and explain what every important number means.
4. Design the first-8-second hook, a one-sentence creator introduction after the first useful information, one meaningful audience interaction every 45-60 seconds, at least two retention refreshes and a promised payoff.
5. Use this narrative order as a flexible investigation spine, not an article-chapter map:

   `cold_open -> central_question -> evidence_map -> historical_context -> mechanism_explainer -> field_or_human_evidence -> counterargument -> data_resolution -> qualified_conclusion`

6. Create `storyboard_review.md` with 10-25 second `story_segment` rows. Each row contains complete narration, claim/evidence references, main visual, real inserts, emphasis text, entity labels and its interaction or retention function.
7. Obtain explicit approval for the rewritten narration and review storyboard. Do not generate assets or detailed image prompts before approval.
8. After approval, split each story segment into director shots averaging 8-12 seconds and optional 2.5-5 second Remotion micro-beats. Every shot must trace back to its story segment, core claim and evidence.
9. Create one `vox_visual_bible.json` after content approval and before drawing scenes. Lock the paper/material system, palette, typography, hero objects, spatial world, camera grammar and sound vocabulary.
10. Pass Claim/Evidence before asset production.
11. Search exact entities, events, people, dates and claims. Prefer direct news, interviews, speeches, archival footage, on-site footage, source documents and real data over generic B-roll.
12. Run `scripts/video_vox_omni_pack.py` to create one reference-image prompt and one Omni motion prompt for every approved director shot. Generate the first approved scene still as the master style reference.
13. Generate every complete 16:9 reference still with Codex built-in `imagegen`, save it to the declared project path, and never use Chrome or Gemini for reference-image generation. Keep it flat and separable: one matte background, optional torn base panel, and 4-6 major movable groups with generous gaps. It is the object map Omni must assemble, not a photorealistic scene or the final edited video.
14. Crop every still into 16:9, 1:1 and 9:16 using the declared focus and shot scale. Review the source image and all three crops in `storyboard_contact_sheet.jpg`; reject cut faces, evidence objects, charts or motion paths.
15. Use `dasheng-video-omni-browser` as the default shot generator. Upload the complete reference image and matching prompt to the signed-in Chrome Gemini Omni page; download one approximately 10-second MP4 per shot.
16. Omni must begin on the persistent background/base layer, assemble named paper groups independently, finish by 9 seconds and hold the supplied composition for the final second. Reject full-poster openings followed by deconstruction, uniform push-ins, camera drift, morphing and newly invented objects.
17. Inspect every generated clip. Reject cut edges, baked-in authoritative text, object drift, broken collage geometry, flashes or an unstable final hold.
18. Import approved Omni clips into the dedicated `vox-editorial-collage` Remotion family. Add real evidence, exact text, charts, captions, audio and any local layer animation during this second edit.
19. Pass renderer asset, renderer contract, full render QC and final delivery identity gates.

## Director rules

- Default to `1920x1080`, `16:9`, `30fps`. Create square or vertical adaptations separately.
- Default to core alignment: preserve the source's decisive arguments and evidence without mapping every paragraph. A paragraph-aligned draft is an optional omission audit, never the production storyboard.
- Review at the `story_segment` level; generate at the `director_shot` level; edit motion and overlays at the `micro_beat` level.
- Open with real footage plus animated title, central question/evidence map, data or rule layer, and full captions.
- The default visual world is editorial paper collage: a flat bold paper background, torn base panels, halftone cut-outs, taped source screens, red-thread relationships and physicalized charts. Depth belongs to short paper shadows and later Remotion compositing, not a generated 3D diorama.
- Change the canvas only when narrative responsibility changes. Inside a scene, move through evidence with object transforms and camera choreography.
- Use the motion vocabulary visible in the reference samples: slide, collide, hinge, page-turn, stack, connect, converge and dismantle. Smooth whole-frame drift is not VOX motion.
- During final Remotion editing, put overlays and real footage at distinct Z depths. Do not ask Omni to fake a cinematic 3D world or camera move inside a reference-poster shot.
- Target one 10-second Omni clip per director shot; trim the downloaded clip to the narration beat only during the final edit.
- Use one master reference frame per visual world to constrain palette, materials, typography and object identity. Generate it first and make later Image2 jobs depend on it. Do not let every shot invent a new style.
- Let the script splitter produce paired reference-image and Omni prompts. The narration beat controls the final trim; Omni generation remains 10 seconds.
- Treat crop design as shot design: wide, medium, close and detail shots must produce visibly different framing, not identical full-frame images with different labels.
- Generated text is never authoritative. Headlines, numbers, dates, citations and chart labels must be overlaid exactly in Remotion.
- Treat central news anchors as PIP or split-screen unless the original statement or lower third is direct evidence.
- Keep source charts complete with `contain` before magnification. Do not show a reconstructed chart beside the original chart.
- Include at least one counterargument, failure mode, or boundary condition.
- End with a qualified conclusion that states what is known, inferred, and still unknown.
- Keep new high-salience techniques to a few key shots.
- Keep a visible base layer across cuts. Do not use black curtains, white flashes, or per-caption fade-outs.
- Prefer a clean match cut. If a dissolve is necessary, prelap the incoming shot for only 3-4 frames while the outgoing shot stays opaque; longer dissolves create double-evidence ghosting.
- Reserve blank paper or negative space for Remotion text with a visible inner margin. Reject titles that touch the paper edge, sit outside the generated label, or compete with captions.

## Provider policy

- Use `media-downloader` for real material and provenance.
- Use MiniMax CLI for production narration/music by default.
- Use Codex built-in `imagegen` as the only reference-image provider for the VOX Omni lane. Chrome/Gemini begins only after the approved local PNG exists.
- Use the user's signed-in Chrome Gemini Omni page as the default image-to-video route; no Gemini API key is required.
- Keep MiniMax/MMX and Seedance as shot-level reserves only. They must not silently replace Omni for the whole film.
- Never route production through the removed `vox-director`, AtlasCloud, OpenRouter, Replicate, or another third-party service key.

## Required outputs

- `video_content_brief.md`
- `script.json`
- `narration_script.rewritten.md`
- `script_rewrite_gate.json`
- `narrative_storyboard.json`
- `storyboard_review.md`
- `storyboard_review.html`
- `storyboard_review_gate.json`
- `scene_plan.json`
- `vox_visual_bible.json`
- `tool_routing_plan.json`
- `claim_evidence_ledger.json`
- `asset_manifest.json`
- `image2_shot_manifest.json`
- `vox_layer_manifest.json`
- `storyboard_contact_sheet.jpg`
- `edit_decisions.json`
- `video_render_qc.json`
- `final_delivery_manifest.json`

## 两段式导演入口

首次运行只生成内容提炼、重写口播和审核分镜，不生成生产镜或视觉资产：

```bash
python scripts/dasheng_video_director.py \
  --lane vox_explainer_video \
  --article-html <article.html> \
  --output-dir <project>/director
```

审核页导出决定后生成门禁：

```bash
python scripts/validate_storyboard_review_gate.py \
  --storyboard <project>/director/narrative_storyboard.json \
  --decision <project>/director/storyboard_review_decision.json \
  --output <project>/director/storyboard_review_gate.json
```

门禁通过后，第二次运行才生成 `scene_plan.json`、8–12 秒生产镜、2.5–5 秒微节拍、视觉圣经和工具路由：

```bash
python scripts/dasheng_video_director.py \
  --lane vox_explainer_video \
  --article-html <article.html> \
  --output-dir <project>/director \
  --storyboard-review-gate <project>/director/storyboard_review_gate.json
```

Write runtime media under `~/Desktop/自媒体创作`, never inside this Skill.
