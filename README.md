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

## Dry Run

```bash
python3 taskradar-web/scripts/taskradar_agent.py --dry-run ensure-task \
  --project-title "TaskRadar Web" \
  --project-key "taskradar-web" \
  --title "Example tracked task" \
  --next-action "Run smoke test"
```

## Self Check

This does not need a token and does not call the network:

```bash
python3 taskradar-web/scripts/taskradar_agent.py self-test
```

## Real Write

After token setup:

```bash
python3 taskradar-web/scripts/taskradar_agent.py ensure-task \
  --project-title "TaskRadar Web" \
  --project-key "taskradar-web" \
  --title "Example tracked task" \
  --next-action "Run smoke test"
```

The skill asks before creating tasks. One conversation should usually map to one TaskRadar task.
