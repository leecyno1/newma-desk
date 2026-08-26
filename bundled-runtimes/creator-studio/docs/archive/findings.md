# Findings

- Existing canonical docs live under 引擎/03_全链路SOP工作流 and skills/dasheng-daily-shared/runtime.
- `run_stage1_intake.py` already writes intake outputs to 产物/01_内容采集 and uses env-configured endpoints.
- `phase2_rebuilder.py` currently scores mostly by heat/template rules and needs TopicCard writability signals.
- No clean `build_stage3_draft.py` currently exists.
- `feishu-plan.js` stage order and intake matching are inconsistent with the canonical chain.
- Added canonical schema set for TopicCard / SelectedTopic / Claim / EvidenceItem / AssetItem / ChannelPack / ReasoningSheet.
- Intake now emits entity rankings, event clusters, source quality report, and Intake Gate seed file.
- Brief now emits TopicCard objects, research brief, and Brief Gate files with required selection state.
- Draft now has an executable builder that refuses to run without approved selected_topics.json.
- Feishu planner now uses canonical stage order and refills draft docs instead of rewrite docs.
