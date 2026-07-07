---
name: taskradar-web
description: Record and update long-running agent work in TaskRadar Web. Use when the user asks to track a task, add a task to TaskRadar, update TaskRadar status, record progress/blockers/reminders, or when a conversation becomes multi-step and the user confirms it should be tracked.
---

# TaskRadar Web

Use this skill to write durable task state to TaskRadar Web after the user confirms.

TaskRadar Web is only a task tracker. Do not write knowledge-base records, source documents, secrets, or ordinary chat into TaskRadar.

## Hard Rules

- Ask before creating a TaskRadar task.
- Create at most one TaskRadar task per conversation unless the user explicitly asks to split work.
- Use one user-level `tr_pat_` Agent Token for all projects under that user.
- Never ask the user to paste a token into chat.
- Never print, log, commit, or store a token in task titles, events, README examples, or git.
- If the user pastes a `tr_pat_` token into chat, refuse to use it and tell them to revoke it and generate a new one.
- Call the Agent API, not the TaskRadar Web frontend.

## Token Setup

If `TASKRADAR_AGENT_TOKEN` is missing, stop and tell the user:

```text
TaskRadar Agent Token is not configured.

Get one from:
1. Open https://taskradar.uydyun.com
2. Log in
3. Click "Agent Token"
4. Click "Generate Token"
5. Copy the one-time tr_pat_ token
6. Do not paste it into chat
7. Save it in ~/.config/taskradar-skill/env
```

Give only placeholder commands:

```bash
mkdir -p ~/.config/taskradar-skill
chmod 700 ~/.config/taskradar-skill
touch ~/.config/taskradar-skill/env
chmod 600 ~/.config/taskradar-skill/env
${EDITOR:-nano} ~/.config/taskradar-skill/env
```

Expected local file:

```bash
TASKRADAR_BASE_URL=https://taskradar.uydyun.com/app-api/taskradar
TASKRADAR_AGENT_TOKEN=tr_pat_xxx
```

The helper script reads environment variables first, then `~/.config/taskradar-skill/env`.

For a subagent session, configure the parent context locally instead of asking
the user for it in chat:

```bash
TASKRADAR_AGENT_ROLE=subagent
TASKRADAR_PARENT_AGENT_ID=123
TASKRADAR_PARENT_TASK_ID=789
TASKRADAR_SPAWNED_BY_AGENT_ID=123
```

`TASKRADAR_PARENT_TASK_ID` and `TASKRADAR_SPAWNED_BY_AGENT_ID` must be set
together for child task writes.

## Workflow

1. Decide whether the conversation is task-worthy.
2. Ask the user to confirm before creating a task.
3. Load token configuration without asking for the token in chat.
4. Ensure the project with `/agent/projects/ensure`.
5. Ensure the agent with `/agent/agents/ensure`.
6. Ensure the task with `/agent/tasks/ensure`.
7. Store the returned `task_id` in the current conversation context.
8. Update the same task for progress, waiting, blockers, reminders, and completion.

Read `references/api.md` when you need exact fields.

## Helper Script

Use `scripts/taskradar_agent.py` for reliable API calls.

Dry-run a task payload without a token:

```bash
python3 taskradar-web/scripts/taskradar_agent.py --dry-run ensure-task \
  --project-title "TaskRadar Web" \
  --project-key "taskradar-web" \
  --title "Implement email verification countdown" \
  --next-action "Run frontend smoke"
```

Dry-run a subagent child task:

```bash
python3 taskradar-web/scripts/taskradar_agent.py --dry-run ensure-task \
  --project-title "TaskRadar Web" \
  --project-key "taskradar-web" \
  --agent-role subagent \
  --parent-agent-id 123 \
  --parent-task-id 789 \
  --spawned-by-agent-id 123 \
  --title "Verify child task write" \
  --next-action "Write child event"
```

If the subagent context is already configured in env, omit the parent flags and
only pass the task fields.

Create or reuse a real task after token setup:

```bash
python3 taskradar-web/scripts/taskradar_agent.py ensure-task \
  --project-title "TaskRadar Web" \
  --project-key "taskradar-web" \
  --title "Implement email verification countdown" \
  --next-action "Run frontend smoke"
```

Update an existing task:

```bash
python3 taskradar-web/scripts/taskradar_agent.py status \
  --task-id 123 \
  --status waiting_user \
  --next-action "Waiting for manual verification"
```

Write an event:

```bash
python3 taskradar-web/scripts/taskradar_agent.py event \
  --task-id 123 \
  --message "Frontend build passed"
```

## Status Mapping

- Active work: `active`
- Waiting for user: `waiting_user`
- Waiting for another agent/tool: `waiting_agent`
- Blocked: `blocked`
- Finished: `done`
- Archived: `archived`

Use `waiting_user` or `blocked` when `needs_user_attention` should be true.

## Noise Control

Skip TaskRadar for:

- One-off questions
- Casual chat
- Simple explanations
- Work the user explicitly says not to track

Track TaskRadar for:

- Multi-step implementation
- Work that may span sessions
- Work waiting on user confirmation or another system
- Work with a concrete deliverable and acceptance check
