#!/usr/bin/env python3
"""Small stdlib helper for TaskRadar Web Agent API calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".config" / "taskradar-skill" / "env"
DEFAULT_BASE_URL = "https://taskradar.uydyun.com/app-api/taskradar"
DEFAULT_AGENT_NAME = "Codex"
DEFAULT_AGENT_PROVIDER = "codex"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        values[key.strip()] = value
    return values


def load_config() -> dict[str, str]:
    values = parse_env_file(CONFIG_PATH)
    for key, value in os.environ.items():
        if key.startswith("TASKRADAR_"):
            values[key] = value
    return values


def normalize_base_url(url: str) -> str:
    base = (url or DEFAULT_BASE_URL).rstrip("/")
    for suffix in ("/api", "/agent"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def missing_token_message() -> str:
    return f"""TaskRadar Agent Token is not configured.

Get one from:
1. Open https://taskradar.uydyun.com
2. Log in
3. Click "Agent Token"
4. Click "Generate Token"
5. Copy the one-time tr_pat_ token
6. Do not paste it into chat
7. Save it in {CONFIG_PATH}

Setup:
mkdir -p ~/.config/taskradar-skill
chmod 700 ~/.config/taskradar-skill
touch ~/.config/taskradar-skill/env
chmod 600 ~/.config/taskradar-skill/env
${{EDITOR:-nano}} ~/.config/taskradar-skill/env

File contents:
TASKRADAR_BASE_URL=https://taskradar.uydyun.com/app-api/taskradar
TASKRADAR_AGENT_TOKEN=tr_pat_xxx
"""


def require_token(config: dict[str, str]) -> str:
    token = config.get("TASKRADAR_AGENT_TOKEN", "")
    if not token:
        raise SystemExit(missing_token_message())
    if not token.startswith("tr_pat_"):
        raise SystemExit("TASKRADAR_AGENT_TOKEN must be a tr_pat_ Agent Token.")
    return token


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return text[:80] or "task"


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def envelope_error(status: int, body: Any) -> str | None:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("code")
        code = body.get("code")
        if isinstance(code, int) and code != 0:
            return body.get("msg") or f"code {code}"
        if status >= 400:
            return body.get("msg") or f"HTTP {status}"
    if status >= 400:
        return f"HTTP {status}"
    return None


def api_call(config: dict[str, str], method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = require_token(config)
    root = normalize_base_url(config.get("TASKRADAR_BASE_URL", DEFAULT_BASE_URL))
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{root}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as error:
        raise SystemExit(f"TaskRadar request failed: {error.reason}") from error

    try:
        parsed: Any = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw}

    message = envelope_error(status, parsed)
    if message:
        raise SystemExit(f"TaskRadar request failed: {message}")
    return parsed


def data_from(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data", response)
    if not isinstance(data, dict):
        raise SystemExit("TaskRadar response did not contain an object data payload.")
    return data


def project_payload(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    title = args.project_title or config.get("TASKRADAR_PROJECT_TITLE") or Path.cwd().name
    return {
        "external_project_key": args.project_key or config.get("TASKRADAR_PROJECT_KEY") or slug(title),
        "title": title,
        "description": args.project_description or f"Tracked by TaskRadar Skill for {title}",
        "priority": args.project_priority or config.get("TASKRADAR_PROJECT_PRIORITY") or "normal",
    }


def agent_payload(
    args: argparse.Namespace,
    config: dict[str, str],
    project_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "name": args.agent_name or config.get("TASKRADAR_AGENT_NAME") or DEFAULT_AGENT_NAME,
        "provider": args.agent_provider
        or config.get("TASKRADAR_AGENT_PROVIDER")
        or DEFAULT_AGENT_PROVIDER,
        "session_name": args.session_name or config.get("TASKRADAR_SESSION_NAME") or conversation_id,
        "external_session_id": args.session_id or config.get("TASKRADAR_SESSION_ID") or conversation_id,
    }


def ensure_project(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload = project_payload(args, config)
    if args.dry_run:
        return {"request": {"method": "POST", "path": "/agent/projects/ensure", "body": payload}}
    return api_call(config, "POST", "/agent/projects/ensure", payload)


def ensure_agent(
    args: argparse.Namespace,
    config: dict[str, str],
    project_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    if not project_id:
        project_id = str(data_from(ensure_project(args, config)).get("id", "__PROJECT_ID__"))
    if not conversation_id:
        conversation_id = args.conversation_id or config.get("TASKRADAR_CONVERSATION_ID") or "local"
    payload = agent_payload(args, config, project_id, conversation_id)
    if args.dry_run:
        return {"request": {"method": "POST", "path": "/agent/agents/ensure", "body": payload}}
    return api_call(config, "POST", "/agent/agents/ensure", payload)


def task_payload(
    args: argparse.Namespace,
    project_id: str,
    agent_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "agent_id": agent_id,
        "external_conversation_id": conversation_id,
        "title": args.title,
        "description": args.description or "",
        "status": args.status,
        "urgency": args.urgency,
        "next_action": args.next_action or "",
        "needs_user_attention": args.needs_user_attention,
    }


def ensure_task(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    conversation_id = (
        args.conversation_id
        or config.get("TASKRADAR_CONVERSATION_ID")
        or f"manual:{slug(args.title)}"
    )
    requests = []
    if args.project_id:
        project_id = args.project_id
    else:
        project_response = ensure_project(args, config)
        requests.append(project_response["request"] if args.dry_run else project_response)
        project_id = str(data_from(project_response).get("id", "__PROJECT_ID__"))

    if args.agent_id:
        agent_id = args.agent_id
    else:
        agent_response = ensure_agent(args, config, project_id, conversation_id)
        requests.append(agent_response["request"] if args.dry_run else agent_response)
        agent_id = str(data_from(agent_response).get("id", "__AGENT_ID__"))

    payload = task_payload(args, project_id, agent_id, conversation_id)
    if args.dry_run:
        requests.append({"method": "POST", "path": "/agent/tasks/ensure", "body": payload})
        return {
            "requests": requests
        }
    return api_call(config, "POST", "/agent/tasks/ensure", payload)


def patch_status(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": args.status}
    if args.next_action:
        payload["next_action"] = args.next_action
    if args.needs_user_attention is not None:
        payload["needs_user_attention"] = args.needs_user_attention
    if args.dry_run:
        return {"request": {"method": "PATCH", "path": f"/agent/tasks/{args.task_id}", "body": payload}}
    return api_call(config, "PATCH", f"/agent/tasks/{args.task_id}", payload)


def write_event(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload = {"event_type": args.event_type, "message": args.message}
    if args.dry_run:
        return {
            "request": {
                "method": "POST",
                "path": f"/agent/tasks/{args.task_id}/events",
                "body": payload,
            }
        }
    return api_call(config, "POST", f"/agent/tasks/{args.task_id}/events", payload)


def parse_remind_at(value: str) -> int:
    if value.isdigit():
        return int(value)
    text = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int(parsed.timestamp() * 1000)


def write_reminder(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload = {"remind_at": parse_remind_at(args.remind_at), "message": args.message}
    if args.dry_run:
        return {
            "request": {
                "method": "POST",
                "path": f"/agent/tasks/{args.task_id}/reminders",
                "body": payload,
            }
        }
    return api_call(config, "POST", f"/agent/tasks/{args.task_id}/reminders", payload)


def self_test(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    assert normalize_base_url("https://x/app-api/taskradar/api") == "https://x/app-api/taskradar"
    assert normalize_base_url("https://x/app-api/taskradar/agent") == "https://x/app-api/taskradar"
    assert slug("TaskRadar Web!") == "taskradar-web"
    assert parse_remind_at("1782963000000") == 1782963000000

    args.dry_run = True
    args.project_title = "TaskRadar Web"
    args.project_key = "taskradar-web"
    args.project_description = None
    args.project_priority = None
    args.agent_name = None
    args.agent_provider = None
    args.session_name = None
    args.session_id = None
    args.project_id = None
    args.agent_id = None
    args.conversation_id = "self-test"
    args.title = "Self test task"
    args.description = None
    args.status = "active"
    args.urgency = "normal"
    args.next_action = "Verify dry-run payload"
    args.needs_user_attention = False
    result = ensure_task(args, config)
    assert len(result["requests"]) == 3
    assert result["requests"][0]["path"] == "/agent/projects/ensure"
    assert result["requests"][1]["body"]["external_session_id"] == "self-test"
    assert result["requests"][2]["body"]["external_conversation_id"] == "self-test"
    return {"ok": True}


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-title")
    parser.add_argument("--project-key")
    parser.add_argument("--project-description")
    parser.add_argument("--project-priority")


def add_agent_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent-name")
    parser.add_argument("--agent-provider")
    parser.add_argument("--session-name")
    parser.add_argument("--session-id")


def add_common_write_args(parser: argparse.ArgumentParser) -> None:
    add_project_args(parser)
    add_agent_args(parser)
    parser.add_argument("--project-id")
    parser.add_argument("--agent-id")
    parser.add_argument("--conversation-id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write agent task state to TaskRadar Web.")
    parser.add_argument("--dry-run", action="store_true", help="Print requests without using a token.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    project = subparsers.add_parser("ensure-project")
    add_project_args(project)

    agent = subparsers.add_parser("ensure-agent")
    add_common_write_args(agent)

    task = subparsers.add_parser("ensure-task")
    add_common_write_args(task)
    task.add_argument("--title", required=True)
    task.add_argument("--description")
    task.add_argument("--status", default="active")
    task.add_argument("--urgency", default="normal")
    task.add_argument("--next-action")
    task.add_argument("--needs-user-attention", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("--task-id", required=True)
    status.add_argument("--status", required=True)
    status.add_argument("--next-action")
    status.add_argument("--needs-user-attention", action=argparse.BooleanOptionalAction)

    event = subparsers.add_parser("event")
    event.add_argument("--task-id", required=True)
    event.add_argument("--message", required=True)
    event.add_argument("--event-type", default="progress")

    reminder = subparsers.add_parser("reminder")
    reminder.add_argument("--task-id", required=True)
    reminder.add_argument("--message", required=True)
    reminder.add_argument("--remind-at", required=True, help="Epoch millis or ISO datetime.")

    subparsers.add_parser("self-test")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config()
    args.dry_run = bool(args.dry_run)

    handlers = {
        "ensure-project": ensure_project,
        "ensure-agent": ensure_agent,
        "ensure-task": ensure_task,
        "status": patch_status,
        "event": write_event,
        "reminder": write_reminder,
        "self-test": self_test,
    }
    result = handlers[args.command](args, config)
    print_json(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
