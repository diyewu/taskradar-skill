#!/usr/bin/env python3
"""Small stdlib helper for TaskRadar Web Agent API calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "taskradar-skill"
CONFIG_PATH = CONFIG_DIR / "env"
REGISTRY_PATH = CONFIG_DIR / "projects.json"
LOCAL_CONTEXT_DIR = ".taskradar"
LOCAL_CONTEXT_FILE = "project.json"
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


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        backup = path.with_name(f"{path.name}.bak.{dt.datetime.now().strftime('%Y%m%d%H%M%S')}")
        path.replace(backup)
        raise SystemExit(f"{path} is invalid JSON. Backed up to {backup}.") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object.")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_git(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or Path.cwd(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def git_root(cwd: Path | None = None) -> Path | None:
    root = run_git(["rev-parse", "--show-toplevel"], cwd)
    return Path(root) if root else None


def project_root(cwd: Path | None = None) -> Path:
    return git_root(cwd) or (cwd or Path.cwd())


def normalize_project_key(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^ssh://", "", text)
    text = re.sub(r"^[^@/\s]+@", "", text)
    text = re.sub(r"^https?://", "", text)
    text = text.replace(":", "/", 1) if ":" in text.split("/", 1)[0] else text
    text = re.sub(r"\.git$", "", text)
    return text.strip("/")


def git_project_key(cwd: Path | None = None) -> str | None:
    remote = run_git(["remote", "get-url", "origin"], cwd)
    return normalize_project_key(remote) if remote else None


def local_context_path(root: Path | None = None) -> Path:
    return (root or project_root()) / LOCAL_CONTEXT_DIR / LOCAL_CONTEXT_FILE


def find_local_context(cwd: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    current = (cwd or Path.cwd()).resolve()
    for path in [current, *current.parents]:
        candidate = path / LOCAL_CONTEXT_DIR / LOCAL_CONTEXT_FILE
        if candidate.exists():
            return candidate, read_json(candidate)
    return None


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = read_json(path)
    projects = registry.get("projects", [])
    if not isinstance(projects, list):
        raise SystemExit(f"{path} must contain a projects list.")
    return {"projects": [item for item in projects if isinstance(item, dict)]}


def save_registry(registry: dict[str, Any], path: Path = REGISTRY_PATH) -> None:
    write_json(path, registry)


def find_registry_project(
    project_key: str | None,
    project_title: str | None = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    projects = registry.get("projects", [])
    if project_key:
        for item in projects:
            if item.get("project_key") == project_key:
                return dict(item)
    if project_title:
        for item in projects:
            if item.get("project_title") == project_title:
                return dict(item)
    return {}


def upsert_registry_project(context: dict[str, Any], workspace: Path | None = None) -> None:
    project_key = context.get("project_key")
    if not project_key:
        return
    registry = load_registry()
    projects = [
        item for item in registry["projects"] if item.get("project_key") != project_key
    ]
    projects.append(
        {
            "project_key": project_key,
            "project_title": context.get("project_title") or project_key,
            **optional_id("project_id", context.get("project_id")),
            "last_workspace": str(workspace or project_root()),
            "updated_at": now_iso(),
        }
    )
    save_registry({"projects": projects})


def ensure_gitignore_entry(root: Path, entry: str = f"{LOCAL_CONTEXT_DIR}/") -> None:
    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if entry not in lines:
        lines.append(entry)
        gitignore.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_local_project_context(
    context: dict[str, Any],
    root: Path | None = None,
    update_gitignore: bool = True,
) -> Path:
    root = root or project_root()
    value = {
        "project_key": context.get("project_key"),
        "project_title": context.get("project_title"),
        **optional_id("project_id", context.get("project_id")),
        "project_description": context.get("project_description"),
        "project_priority": context.get("project_priority") or "normal",
        "updated_at": now_iso(),
    }
    write_json(local_context_path(root), {k: v for k, v in value.items() if v})
    if update_gitignore:
        ensure_gitignore_entry(root)
    return local_context_path(root)


def load_handoff(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    raw = getattr(args, "handoff_file", None) or config.get("TASKRADAR_HANDOFF_FILE")
    if not raw:
        return {}
    value = read_json(Path(raw).expanduser())
    return {
        "project_key": value.get("project_key"),
        "project_title": value.get("project_title"),
        "project_id": value.get("project_id"),
        "parent_agent_id": value.get("parent_agent_id"),
        "parent_task_id": value.get("parent_task_id"),
        "spawned_by_agent_id": value.get("spawned_by_agent_id"),
        "agent_role": "subagent",
    }


def apply_handoff(args: argparse.Namespace, config: dict[str, str]) -> dict[str, str]:
    handoff = load_handoff(args, config)
    if not handoff:
        return config
    values = dict(config)
    mapping = {
        "project_key": "TASKRADAR_PROJECT_KEY",
        "project_title": "TASKRADAR_PROJECT_TITLE",
        "project_id": "TASKRADAR_PROJECT_ID",
        "parent_agent_id": "TASKRADAR_PARENT_AGENT_ID",
        "parent_task_id": "TASKRADAR_PARENT_TASK_ID",
        "spawned_by_agent_id": "TASKRADAR_SPAWNED_BY_AGENT_ID",
        "agent_role": "TASKRADAR_AGENT_ROLE",
    }
    for source, target in mapping.items():
        if handoff.get(source) and target not in values:
            values[target] = str(handoff[source])
    return values


def project_context(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    local = find_local_context()
    local_values = local[1] if local else {}
    git_key = git_project_key()
    explicit_key = getattr(args, "project_key", None) or config.get("TASKRADAR_PROJECT_KEY")
    explicit_title = getattr(args, "project_title", None) or config.get("TASKRADAR_PROJECT_TITLE")
    registry_key = explicit_key or local_values.get("project_key") or git_key
    registry_values = find_registry_project(registry_key, explicit_title)

    title = (
        explicit_title
        or local_values.get("project_title")
        or registry_values.get("project_title")
        or Path.cwd().name
    )
    key = explicit_key or local_values.get("project_key") or registry_values.get("project_key")
    project_id = (
        registry_values.get("project_id")
        if explicit_key or explicit_title
        else local_values.get("project_id") or registry_values.get("project_id")
    )
    return {
        "project_key": key or git_key or slug(title),
        "project_title": title,
        "project_id": project_id,
        "project_description": getattr(args, "project_description", None)
        or config.get("TASKRADAR_PROJECT_DESCRIPTION")
        or local_values.get("project_description")
        or f"Tracked by TaskRadar Skill for {title}",
        "project_priority": getattr(args, "project_priority", None)
        or config.get("TASKRADAR_PROJECT_PRIORITY")
        or local_values.get("project_priority")
        or "normal",
        "source": (
            "cli"
            if explicit_key or explicit_title
            else "local-context"
            if local_values
            else "global-registry"
            if registry_values
            else "git-remote"
            if git_key
            else "cwd"
        ),
    }


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
    context = project_context(args, config)
    return {
        "external_project_key": context["project_key"],
        "title": context["project_title"],
        "description": context["project_description"],
        "priority": context["project_priority"],
    }


def agent_payload(
    args: argparse.Namespace,
    config: dict[str, str],
    project_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    role = args.agent_role or config.get("TASKRADAR_AGENT_ROLE") or "main"
    parent_agent_id = args.parent_agent_id or config.get("TASKRADAR_PARENT_AGENT_ID")
    if role not in ("main", "subagent"):
        raise SystemExit("TASKRADAR_AGENT_ROLE must be main or subagent.")
    if role == "subagent" and not parent_agent_id:
        raise SystemExit("Subagent writes require TASKRADAR_PARENT_AGENT_ID or --parent-agent-id.")
    if role != "subagent" and parent_agent_id:
        raise SystemExit("parent_agent_id is only valid when agent role is subagent.")

    return {
        "project_id": project_id,
        "name": args.agent_name or config.get("TASKRADAR_AGENT_NAME") or DEFAULT_AGENT_NAME,
        "provider": args.agent_provider
        or config.get("TASKRADAR_AGENT_PROVIDER")
        or DEFAULT_AGENT_PROVIDER,
        "session_name": args.session_name or config.get("TASKRADAR_SESSION_NAME") or conversation_id,
        "external_session_id": args.session_id or config.get("TASKRADAR_SESSION_ID") or conversation_id,
        "role": role,
        **optional_id("parent_agent_id", parent_agent_id),
    }


def ensure_project(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload = project_payload(args, config)
    if args.dry_run:
        return {"request": {"method": "POST", "path": "/agent/projects/ensure", "body": payload}}
    response = api_call(config, "POST", "/agent/projects/ensure", payload)
    persist_project_context(args, payload, response)
    return response


def project_context_from_response(
    payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    data = data_from(response)
    return {
        "project_key": payload.get("external_project_key"),
        "project_title": payload.get("title"),
        "project_id": str(data.get("id")) if data.get("id") is not None else None,
        "project_description": payload.get("description"),
        "project_priority": payload.get("priority"),
    }


def should_write_local_context(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "write_local_context", True))


def persist_project_context(
    args: argparse.Namespace,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    context = project_context_from_response(payload, response)
    written: dict[str, Any] = {}
    if should_write_local_context(args):
        written["local_context"] = str(write_local_project_context(context))
    upsert_registry_project(context)
    written["registry"] = str(REGISTRY_PATH)
    return written


def join_project(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    payload = project_payload(args, config)
    if args.dry_run:
        return {"request": {"method": "POST", "path": "/agent/projects/ensure", "body": payload}}
    response = api_call(config, "POST", "/agent/projects/ensure", payload)
    context = project_context_from_response(payload, response)
    written = persist_project_context(args, payload, response)
    return {"project": context, **written}


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
    config: dict[str, str],
    project_id: str,
    agent_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    parent_task_id = args.parent_task_id or config.get("TASKRADAR_PARENT_TASK_ID")
    spawned_by_agent_id = args.spawned_by_agent_id or config.get("TASKRADAR_SPAWNED_BY_AGENT_ID")
    if bool(parent_task_id) != bool(spawned_by_agent_id):
        raise SystemExit(
            "Child task writes require both TASKRADAR_PARENT_TASK_ID and "
            "TASKRADAR_SPAWNED_BY_AGENT_ID, or both CLI flags."
        )

    return {
        "project_id": project_id,
        "agent_id": agent_id,
        **optional_id("parent_task_id", parent_task_id),
        **optional_id("spawned_by_agent_id", spawned_by_agent_id),
        "external_conversation_id": conversation_id,
        "title": args.title,
        "description": args.description or "",
        "status": args.status,
        "urgency": args.urgency,
        "next_action": args.next_action or "",
        "needs_user_attention": args.needs_user_attention,
    }


def optional_id(key: str, value: str | None) -> dict[str, str]:
    return {key: value} if value else {}


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

    payload = task_payload(args, config, project_id, agent_id, conversation_id)
    if args.dry_run:
        requests.append({"method": "POST", "path": "/agent/tasks/ensure", "body": payload})
        return {
            "requests": requests
        }
    return api_call(config, "POST", "/agent/tasks/ensure", payload)


def list_projects(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    return load_registry()


def current_project(args: argparse.Namespace, config: dict[str, str]) -> dict[str, Any]:
    context = project_context(args, config)
    return {
        "source": context["source"],
        "project_key": context["project_key"],
        "project_title": context["project_title"],
        **optional_id("project_id", context.get("project_id")),
    }


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
    assert normalize_project_key("https://gitlab.udyun.net/opc/taskradar-web.git") == (
        "gitlab.udyun.net/opc/taskradar-web"
    )
    assert normalize_project_key("git@gitlab.udyun.net:opc/taskradar-web.git") == (
        "gitlab.udyun.net/opc/taskradar-web"
    )
    test_config: dict[str, str] = {}

    args.dry_run = True
    args.project_title = "TaskRadar Web"
    args.project_key = "taskradar-web"
    args.project_description = None
    args.project_priority = None
    args.write_local_context = True
    args.agent_name = None
    args.agent_provider = None
    args.session_name = None
    args.session_id = None
    args.agent_role = None
    args.parent_agent_id = None
    args.handoff_file = None
    args.project_id = None
    args.agent_id = None
    args.conversation_id = "self-test"
    args.parent_task_id = None
    args.spawned_by_agent_id = None
    args.title = "Self test task"
    args.description = None
    args.status = "active"
    args.urgency = "normal"
    args.next_action = "Verify dry-run payload"
    args.needs_user_attention = False
    result = ensure_task(args, test_config)
    assert len(result["requests"]) == 3
    assert result["requests"][0]["path"] == "/agent/projects/ensure"
    assert result["requests"][1]["body"]["external_session_id"] == "self-test"
    assert result["requests"][1]["body"]["role"] == "main"
    assert result["requests"][2]["body"]["external_conversation_id"] == "self-test"

    args.agent_role = "subagent"
    args.parent_agent_id = "100"
    args.agent_id = None
    args.parent_task_id = "200"
    args.spawned_by_agent_id = "100"
    result = ensure_task(args, test_config)
    assert result["requests"][1]["body"]["role"] == "subagent"
    assert result["requests"][1]["body"]["parent_agent_id"] == "100"
    assert result["requests"][2]["body"]["parent_task_id"] == "200"
    assert result["requests"][2]["body"]["spawned_by_agent_id"] == "100"

    args.agent_role = None
    args.parent_agent_id = None
    args.parent_task_id = None
    args.spawned_by_agent_id = None
    subagent_config = {
        **test_config,
        "TASKRADAR_AGENT_ROLE": "subagent",
        "TASKRADAR_PARENT_AGENT_ID": "100",
        "TASKRADAR_PARENT_TASK_ID": "200",
        "TASKRADAR_SPAWNED_BY_AGENT_ID": "100",
    }
    result = ensure_task(args, subagent_config)
    assert result["requests"][1]["body"]["role"] == "subagent"
    assert result["requests"][1]["body"]["parent_agent_id"] == "100"
    assert result["requests"][2]["body"]["parent_task_id"] == "200"
    assert result["requests"][2]["body"]["spawned_by_agent_id"] == "100"

    args.agent_role = "subagent"
    try:
        ensure_agent(args, test_config, "__PROJECT_ID__", "self-test")
    except SystemExit as exc:
        assert "parent-agent-id" in str(exc)
    else:
        raise AssertionError("subagent without parent_agent_id should fail")

    with tempfile.TemporaryDirectory() as raw_tmp:
        root = Path(raw_tmp)
        path = write_local_project_context(
            {
                "project_key": "example.test/repo",
                "project_title": "Example Repo",
                "project_id": "123",
                "project_priority": "normal",
            },
            root,
        )
        assert path.exists()
        assert ".taskradar/" in (root / ".gitignore").read_text(encoding="utf-8")
        context = read_json(path)
        assert context["project_key"] == "example.test/repo"
    return {"ok": True}


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-title")
    parser.add_argument("--project-key")
    parser.add_argument("--project-description")
    parser.add_argument("--project-priority")
    parser.add_argument(
        "--write-local-context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write .taskradar/project.json and add .taskradar/ to .gitignore.",
    )


def add_agent_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent-name")
    parser.add_argument("--agent-provider")
    parser.add_argument("--session-name")
    parser.add_argument("--session-id")
    parser.add_argument("--agent-role", choices=("main", "subagent"))
    parser.add_argument("--parent-agent-id")


def add_common_write_args(parser: argparse.ArgumentParser) -> None:
    add_project_args(parser)
    add_agent_args(parser)
    parser.add_argument("--project-id")
    parser.add_argument("--agent-id")
    parser.add_argument("--conversation-id")
    parser.add_argument("--handoff-file", help="Read same-machine subagent context JSON.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write agent task state to TaskRadar Web.")
    parser.add_argument("--dry-run", action="store_true", help="Print requests without using a token.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    project = subparsers.add_parser("ensure-project")
    add_project_args(project)

    join = subparsers.add_parser("join-project")
    add_project_args(join)

    subparsers.add_parser("list-projects")
    subparsers.add_parser("current-project")

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
    task.add_argument("--parent-task-id")
    task.add_argument("--spawned-by-agent-id")

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
    config = apply_handoff(args, load_config())
    args.dry_run = bool(args.dry_run)

    handlers = {
        "ensure-project": ensure_project,
        "join-project": join_project,
        "list-projects": list_projects,
        "current-project": current_project,
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
