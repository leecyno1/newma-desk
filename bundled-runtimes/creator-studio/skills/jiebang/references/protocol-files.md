# Protocol Files

## Runtime Layout

```text
.jiebang/
  manifest.yml
  templates/
  runtime/
    project.md
    current-task.md
    decision-log.md
    handoffs/
      cc.md
      cx.md
      ag.md
    sessions/
      cc.md
      cx.md
      ag.md
```

## Handoff Schema

Each `handoffs/{agent}.md` should use this shape:

```markdown
---
agent: cc|cx|ag
status: active|paused|done
updated_at: YYYY-MM-DD HH:MM
task: short task name
mode: manual|auto
---

# Handoff

## Goal
[The current objective]

## Done
- [Completed item]

## In Progress
- [Partial work]

## Changed Files
- [path]

## Risks
- [Risk or caveat]

## Next Step
[The first action for the receiving agent]
```

## Usage Policy

- `project.md` should change rarely
- `current-task.md` should represent only the active task
- `decision-log.md` should hold durable decisions, not chat fragments
- `handoffs/*.md` should be short and actionable
- `sessions/*.md` can be noisy and detailed because they are fallback context
- `handoffs/*.md` may be updated by both manual `交棒` and automatic snapshots
- automatic snapshots should include a timestamp and clear marker when the summary is machine-generated
