# Task Plan

## Goal
Implement the Dasheng Daily workflow product upgrade so the repo has one canonical stage chain, explicit object/gate contracts, stronger intake/brief logic, a real draft stage, and Feishu sync aligned to canonical artifacts.

## Phases
- [complete] Inspect current workflow files and determine canonical change points
- [complete] Add shared object and gate contracts
- [complete] Upgrade intake outputs and quality signals
- [complete] Upgrade brief scoring and outputs
- [complete] Add canonical draft stage with Reasoning Sheet
- [complete] Fix Feishu stage order and artifact discovery
- [in_progress] Validate scripts and summarize changes

## Constraints
- Keep canonical main chain: intake -> brief -> draft -> material -> rewrite -> publish -> postmortem
- Feishu remains collaboration view, not source of truth
- Human gate files are mandatory contracts
