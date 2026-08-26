# B-roll provider routing

| Need | Preferred route | External candidate | Guardrail |
| --- | --- | --- | --- |
| filing, chart, product UI, real event | sourced evidence | none | preserve source and citation |
| VOX editorial paper collage B-roll | Codex reference image + signed-in Chrome Gemini Omni | internal Remotion assembly | one flat background, 4-6 separable groups, one 10s clip per shot |
| cinematic cutaway or sticker animation | internal motion asset | Seedance/Jimeng official model | no factual impersonation; record provider/model |
| recurring conceptual character | dasheng-lemon-illustrations | none | keep channel visual identity |
| title, number, diagram, transition | Remotion/HyperFrames | none | build data-native animation |

Provider routing follows `configs/video/tool_registry.json`:

- Keep official model providers available: OpenAI/GPT/Codex, Moonshot/Kimi, Google/Gemini, ByteDance Seedance/Jimeng/Seedream, and MiniMax/MMX.
- Treat their API keys, CLI login, or model access as normal optional configuration, not as a reason to delete the Skill.
- Never auto-route through AtlasCloud, OpenRouter, Replicate, RunPod, Modal, ElevenLabs, Higgsfield, or another third-party service provider.
- Exclude candidates that require an additional desktop App or local App backend.
- Record `provider`, `model`, credential state, output path and fallback in the shot manifest; never record credential values.
