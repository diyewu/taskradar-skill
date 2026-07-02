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
- Current backend idempotency is `user_id + title`.
- `external_project_key` is accepted but is not the unique key yet.
- Use `data.id` as `project_id`.

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
  "external_session_id": "codex-session-abc"
}
```

Use `external_session_id`. Do not send `external_agent_id`.

Use `data.id` as `agent_id`.

## Task Ensure

```text
POST /agent/tasks/ensure
```

```json
{
  "project_id": "123",
  "agent_id": "456",
  "external_conversation_id": "codex-session-abc",
  "title": "Implement task workspace",
  "description": "Track the implementation and verification",
  "status": "active",
  "urgency": "normal",
  "next_action": "Run smoke test"
}
```

Use `external_conversation_id`. One conversation should usually map to one task.

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
