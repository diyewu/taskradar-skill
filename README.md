# TaskRadar Skill

Codex Skill for recording confirmed long-running agent work in TaskRadar Web.

TaskRadar Web:

```text
https://taskradar.uydyun.com
```

## Install

Copy or symlink the skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/taskradar-web" ~/.codex/skills/taskradar-web
```

Then invoke it as `$taskradar-web`.

Optional CLI wrapper:

```bash
mkdir -p ~/.local/bin
ln -s "$(pwd)/taskradar-web/bin/taskradar" ~/.local/bin/taskradar
```

## Configure Token

Do not paste your `tr_pat_` token into chat.

Get a token:

1. Open `https://taskradar.uydyun.com`
2. Log in
3. Click `Agent Token`
4. Click `Generate Token`
5. Copy the one-time `tr_pat_` token
6. Save it locally

Local config:

```bash
mkdir -p ~/.config/taskradar-skill
chmod 700 ~/.config/taskradar-skill
touch ~/.config/taskradar-skill/env
chmod 600 ~/.config/taskradar-skill/env
${EDITOR:-nano} ~/.config/taskradar-skill/env
```

File contents:

```bash
TASKRADAR_BASE_URL=https://taskradar.uydyun.com/app-api/taskradar
TASKRADAR_AGENT_TOKEN=tr_pat_xxx
```

Environment variables override the config file.

## Join A Project

Join or refresh the current project without exposing your token:

```bash
taskradar join-project \
  --project-key "gitlab.udyun.net/opc/paid-items/taskradar-web" \
  --project-title "TaskRadar Web"
```

This writes non-sensitive context to `.taskradar/project.json`, adds
`.taskradar/` to `.gitignore`, and refreshes
`~/.config/taskradar-skill/projects.json`.

## Dry Run

```bash
taskradar --dry-run ensure-task \
  --title "Example tracked task" \
  --next-action "Run smoke test"
```

## Self Check

This does not need a token and does not call the network:

```bash
taskradar self-test
```

## Real Write

After token setup and `join-project`:

```bash
taskradar ensure-task \
  --title "Example tracked task" \
  --next-action "Run smoke test"
```

The skill asks before creating tasks. One conversation should usually map to one TaskRadar task.
