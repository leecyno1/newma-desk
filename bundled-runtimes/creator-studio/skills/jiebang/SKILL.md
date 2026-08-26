---
name: jiebang
description: "当用户说“接棒cc/cx/ag”“交棒”“同步上下文”“跨代理切换开发”“自动交棒”时使用。用于 Claude Code、Codex、Antigravity 在同一项目中通过 `.jiebang/runtime/` 共享进度和决策，而不是依赖私有聊天记忆。"
---

# Jiebang

## When To Use

Use this skill when the user wants to:

- switch work between `cc`, `cx`, and `ag`
- import another agent's latest persisted project state
- export the current agent's progress for another agent
- stabilize cross-agent context so future turns do not depend on private chat history

## Mandatory Rules

1. Load `.jiebang/manifest.yml` first.
2. Never claim to know another agent's private chat history unless it was persisted in `.jiebang/runtime/`.
3. Treat `.jiebang/runtime/handoffs/*.md` as the source of truth for agent-to-agent transfer.
4. Keep root instruction files stable; write dynamic progress into runtime files instead.
5. Never rewrite existing `CLAUDE.md`, `AGENTS.md`, or other project instruction files. Only append a bounded hook when the user explicitly asks for `bootstrap --update-agents`.
6. When bootstrapping a project, use the templates bundled in this skill's `assets/` directory and never overwrite existing `.jiebang` files.

## Command Handling

### `接棒cc` / `接棒cx` / `接棒ag`

1. Read `.jiebang/manifest.yml`
2. Read `.jiebang/runtime/project.md`
3. Read `.jiebang/runtime/current-task.md`
4. Read `.jiebang/runtime/decision-log.md`
5. Read the source agent handoff file
6. If the handoff is too thin, read the source session log
7. Read `AGENTS.md` only when project-level rules are needed or the manifest declares it as a project context file
8. Respond with:
   - imported goal
   - imported current state
   - risks or missing context
   - the next concrete action

If the source handoff file is missing, say that no persisted source context is available yet.

### `交棒`

Update the current agent's own handoff file with the template in `references/protocol-files.md`.

Minimum required sections:

- Goal
- Done
- In Progress
- Changed Files
- Risks
- Next Step

Also update `.jiebang/runtime/current-task.md` when the active objective or success criteria changed.

The `交棒` command does not need an agent suffix. The active agent identity determines which handoff file to write.

### `自动交棒`

When the user asks for automatic handoff:

1. Configure a local snapshot mechanism that writes to the active agent's handoff file
2. Use periodic snapshots as the baseline
3. Keep the last manual `交棒` higher quality than automatic snapshots
4. Never depend on network availability for the snapshot itself

## Files To Read

- `references/command-contract.md` for exact behavior of `接棒xx` and `交棒`
- `references/protocol-files.md` for the runtime file layout and handoff schema

## CLI Helper

If shell access is useful, use:

```bash
skills/jiebang/scripts/jiebang.sh bootstrap
skills/jiebang/scripts/jiebang.sh bootstrap --update-agents
skills/jiebang/scripts/jiebang.sh remove-agents-hook
skills/jiebang/scripts/jiebang.sh validate
skills/jiebang/scripts/jiebang.sh brief cc
skills/jiebang/scripts/jiebang.sh autosave cc
skills/jiebang/scripts/jiebang.sh daemon-start cc 180
skills/jiebang/scripts/jiebang.sh daemon-status
skills/jiebang/scripts/jiebang.sh daemon-stop
```

`brief <agent>` prints a compact import pack for manual or tool-assisted transfer.

For globally installed skills, resolve the script from the installed skill directory. The script can bootstrap any target project from its bundled `assets/` templates.
