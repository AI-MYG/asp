#!/usr/bin/env bash
# Pipeline D — Auto-execute analyzed issues via worktree agents + Smart PR
#
# Scans AI-MYG org for open assigned issues (all repos) with execution gates,
# spawns AgentClient to implement the plan, then creates Smart PR.
#
# Scheduled via launchd: com.asp.issue-executor
# Schedule: launchd_schedules.issue_executor in config.yaml
#   (offset from Pipeline C by +15 min to ensure analysis is posted first)
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=load_asp_env.sh
source "$SCRIPT_DIR/load_asp_env.sh"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"

# Fallback: use rootgrove venv if ASP venv doesn't exist
if [ ! -f "$VENV_PYTHON" ]; then
  VENV_PYTHON="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/venv/bin/python"
fi

# shellcheck source=pipeline_skip_if_weekend.sh
source "$SCRIPT_DIR/pipeline_skip_if_weekend.sh"
pipeline_skip_if_weekend executor

cd "$REPO_ROOT"

# Network check
if ! host -W 3 api.github.com >/dev/null 2>&1 && \
   ! curl -sf --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping: no network connectivity (offline)"
  exit 0
fi

exec "$VENV_PYTHON" "$REPO_ROOT/tools/feishu_inbound/issue_executor.py" --batch 3 --parallel
