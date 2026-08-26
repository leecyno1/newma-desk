# VOX Visual Grammar

## Default visual system

VOX is not a white infographic theme. The default is one continuous editorial evidence world:

- torn newsprint, cardboard depth, paper cutouts, tape, stamps and red-thread relationships;
- one style board locks palette, material, typography, hero objects and depth before scene generation;
- each scene has a start frame, end frame and motion description, even when Remotion generates the motion locally;
- the camera moves through a shared world while objects transform, connect, split, stack or resolve;
- charts become physical evidence objects inside the world instead of replacing the world with a clean dashboard page.

Reference workflow learned from the 2026-08-10 XiaoHongShu samples:

`voiceover -> style board -> micro-shot design -> Image2 scene prompt -> full scene still -> crop storyboard -> director approval -> one-shot image-to-video -> Remotion evidence composite`

The generated scene still is mandatory for every approved micro-shot. It locks composition and style, but the Omni reference itself should contain only 4-6 clearly separated major groups on a persistent flat background. The final Remotion composite may add more evidence, text and chart layers. Never animate the approved still as one flat plate.

## Layered scene contract

Each production micro-shot declares:

- `scene_layers`: at least eight independent layers in the final Remotion composite; the Omni reference image itself stays within 4-6 major movable groups;
- `depth` and `occlusion_order`: real foreground, midground and background separation;
- `entry_path`, `motion_path`, `exit_path`: object-specific trajectories, not a shared canvas drift;
- `camera_keyframes`: at least two camera states with a visible X/Y/Z change;
- `stepped_fps`: normally 8-12fps for tactile paper motion while delivery remains 30fps.

Use at least three motion dimensions in each normal shot: translation, Z travel, rotation or hinge, scale, opacity, route draw, chart growth. At least one foreground layer should cross another object or the lens. Exact text, maps, routes and charts remain separate Remotion/SVG layers.

The whole-scene still has one permitted role: layout reference. Independent assets can be generated separately on chroma key, segmented from the approved still, cropped as torn-paper islands, or sourced as real evidence.

The 2026-08-10 `AIGC 图生视频 VOX` sample adds a useful production shortcut:

`script segment -> image prompt + motion prompt -> master reference frame + front prompt -> generated full scene -> focal crop and shot-size review -> image-to-video prompt + target duration + sound cue -> Remotion exact-text composite`

Borrow the prompt-packet design, not the sample's black-frame transitions. Its measured visual density was high, but it contained one 0.37-second black run and repeated dark-entry pulses.

## Image2 shot contract

- Generate the first micro-shot first. Use it as the master visual reference when no approved external reference exists.
- Generate one complete 2048x1152 scene per micro-shot. Use one flat matte background, at most one base panel and 4-6 bold paper groups with visible gaps. Keep the main evidence action inside the central 45% for downstream aspect crops.
- Declare `shot_size`, normalized `focus`, `crop_scale`, `image_prompt`, `video_prompt`, `duration_sec` and `sound_cue` before generation.
- Produce SOURCE, 16:9, 1:1 and 9:16 previews. Approve the storyboard from these real images, not from text descriptions or template screenshots.
- Use crop scale to create real wide, medium, close and detail framing. Changing a label without changing the crop is a failed shot design.
- Use the approved crop as the image-to-video object map and final target. Ask Omni to start with the background/base layer only, assemble once, and hold a stable final frame; reject a full-poster opening followed by deconstruction.
- Add authoritative text, numbers, dates, citations and chart labels only in Remotion.

## Narrative responsibility

| State | Visual responsibility |
| --- | --- |
| cold_open | Direct or topic-specific real footage, one contradiction, kinetic title, question cue |
| central_question | Reduce the topic to one visible question map |
| evidence_map | Show 3-6 evidence pillars and how they relate |
| historical_context | Archive, timeline, newspaper, document, map, dated labels |
| mechanism_explainer | Nodes, paths, layers, causal arrows, spatial transformation |
| field_or_human_evidence | Interview, speech, news, on-site footage, original audio, source lower third |
| counterargument | Claim vs evidence split, competing timeline, failed case, boundary condition |
| data_resolution | Verified data-native chart, full source reading state, annotated conclusion |
| qualified_conclusion | Resolve the evidence map into known, inferred, conditional, unknown |

## Composition

- Use archive collage, maps, timelines, labels, arrows, masks, circles, and shared elements as explanation, not decoration.
- Let real footage be full-screen, PIP, split, masked, or adjacent to a chart. Keep faces, original lower thirds, axes, legends, and source labels readable.
- Use scene-space footage such as factories, markets, crowds, cities, machines, and interview environments as backgrounds. Do not bury a central anchor behind a dark chart layer.
- Reuse a coherent footage family across the film with different time ranges, crops, masks, and overlays.

## Evidence language

- `direct`: visible material directly supports the spoken claim.
- `context`: material establishes place, industry, time, or mood but does not prove the claim.
- `illustrative`: generated or schematic material explains a mechanism.
- `assumption`: scenario or estimate that must be disclosed on screen.

Never upgrade context or illustration to direct evidence.

## Motion and sound

- Prefer semantic motion: a timeline grows, a route travels, layers separate, documents align, values resolve.
- Use clean cuts, shared elements, object transforms, and audio bridges. Keep a visible base layer across every transition.
- Preserve interview or event ambience briefly before and after narration enters. Duck music under speech and source audio.
- Keep high-salience effects to the opening, a chapter turn, or a decisive data shot.
- Use 2.5-5 second micro-shots. A 15-second narration scene normally contains 3-5 camera or object beats.
- Motion prompts describe camera action, object action, assembly order and sound cue. "Make it dynamic" is not a valid motion plan.
- Prefer a start/end-frame transformation over unconstrained text-to-video when a shared object or layout must survive the shot.
- A single reference frame may replace the start/end pair only when the whole composition is already locked and the requested motion is local: camera push, object activation, line growth, smoke, light, page turn or small assembly.
- Each generated micro-shot packet contains `image_prompt`, `motion_prompt`, `duration_sec` and `sound_cue`. Exact factual text remains a Remotion overlay.

## Measured Image2 production rules

The 2026-08-11 20-second gold test established these defaults:

- Preflight MiniMax with an explicit China base URL. `https://api.minimaxi.com/v1` causes a doubled `/v1/v1` route in current CLI behavior; use `mmx --base-url https://api.minimaxi.com ...`.
- Treat model output duration as source material, not final timing. Inspect frames near 5%, 50% and 95%; keep the semantic action and trim before late flare, object drift or text mutation.
- Normalize approved clips before Remotion. The tested Hailuo output was 1364x768 at 24fps; the delivery lane remained 1920x1080 at 30fps.
- Use clean cuts when the evidence world and palette already match. If a dissolve helps continuity, limit the incoming prelap to 3-4 frames and keep the outgoing frame opaque until the cut. Do not create an alpha dip or a long double-image blend.
- Fit exact titles only after video generation. Keep at least one visible text-safe inset inside blank paper labels and review the final rendered frame, not only the source still.
- Scan scene boundaries for black frames, white frames and freezes after the final audio/video encode. A storyboard pass does not replace encoded-file QC.

## QC blockers

- No central question.
- No counterargument or boundary.
- Article chapter recitation.
- Generic B-roll presented as proof.
- Cropped source chart before full reading.
- Static screenshot slideshow or zoompan.
- No visual bible or no shared continuity anchor.
- Dense photorealistic diorama used as an Omni reference frame.
- More than six major movable groups with no explicit split into another shot.
- Missing Image2 scene still for any approved micro-shot.
- Complete scene still used as the only moving visual layer.
- Fewer than eight independent production layers, fewer than three motion dimensions, or no camera/depth change.
- Storyboard approved without reviewing SOURCE and aspect crops.
- Image-to-video started before crop approval.
- One large white chart/card held for an entire narration scene.
- Fewer than three designed micro-shots in a normal VOX scene.
- Black/white single-frame flash at cuts or subtitle endings.
- Absolute conclusion that hides uncertainty or conflicting evidence.
