# TaskRadar Web Agent API

Default root:

```text
https://taskradar.uydyun.com/app-api/taskradar
```

Use `Authorization: Bearer <tr_pat-token>` for every `/agent/**` request.

Do not use a normal Web access token for Agent APIs.

## Project Ensure

```text
POST /agent/projects/ensure
```

```json
{
  "external_project_key": "repo-or-workspace-key",
  "title": "TaskRadar Web",
  "description": "Created or reused by Agent Token",
  "priority": "normal"
}
```

Notes:

- Token is user-level, not project-level.
- Backend idempotency prefers `user_id + external_project_key`.
- If `external_project_key` is omitted, backend falls back to `user_id + title`.
- Use `data.id` as `project_id`.

The skill stores non-secret project join context locally:

```text
.taskradar/project.json
~/.config/taskradar-skill/projects.json
```

Cross-machine main agents should join with a non-secret command:

```bash
taskradar join-project \
  --project-key "repo-or-workspace-key" \
  --project-title "TaskRadar Web"
```

This command does not contain a token. Each machine must configure its own
user-level `tr_pat_` token locally.

## Agent Ensure

```text
POST /agent/agents/ensure
```

```json
{
  "project_id": "123",
  "name": "Codex",
  "provider": "codex",
  "session_name": "Local session",
  "external_session_id": "codex-session-abc",
  "role": "subagent",
  "parent_agent_id": "123"
}
```

Use `external_session_id`. Do not send `external_agent_id`.

Use `data.id` as `agent_id`.

`role` defaults to `main`. Use `role=subagent` with `parent_agent_id` to link a child agent to a parent agent in the same project. The helper script rejects `subagent` writes without `parent_agent_id`.

## Task Ensure

```text
POST /agent/tasks/ensure
```

```json
{
  "project_id": "123",
  "agent_id": "456",
  "parent_task_id": "789",
  "spawned_by_agent_id": "123",
  "external_conversation_id": "codex-session-abc",
  "title": "Implement task workspace",
  "description": "Track the implementation and verification",
  "status": "active",
  "urgency": "normal",
  "next_action": "Run smoke test"
}
```

Use `external_conversation_id`. One conversation should usually map to one task.

`parent_task_id` links a child task to its parent task. `spawned_by_agent_id` records the agent that spawned the child task. Both must belong to the same user and project. In the helper script, set both together with CLI flags or local env:

```bash
TASKRADAR_PARENT_TASK_ID=789
TASKRADAR_SPAWNED_BY_AGENT_ID=123
```

Subagent handoff is same-machine only. A handoff file may provide
`project_key`, `project_title`, `project_id`, `parent_agent_id`,
`parent_task_id`, and `spawned_by_agent_id`; it must not contain a token.

## Task Status

```text
PATCH /agent/tasks/{taskId}
```

```json
{
  "status": "waiting_user",
  "next_action": "Waiting for user confirmation",
  "needs_user_attention": true
}
```

Allowed statuses:

- `active`
- `waiting_user`
- `waiting_agent`
- `blocked`
- `done`
- `archived`

## Event

```text
POST /agent/tasks/{taskId}/events
```

```json
{
  "event_type": "progress",
  "message": "Build passed"
}
```

Common event types:

- `progress`
- `status_changed`
- `waiting_user`
- `waiting_agent`
- `blocked`
- `completed`

## Reminder

```text
POST /agent/tasks/{taskId}/reminders
```

```json
{
  "remind_at": 1782963000000,
  "message": "Follow up with user"
}
```

`remind_at` is epoch milliseconds.
