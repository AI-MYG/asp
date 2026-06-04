#!/usr/bin/env bash
# Pipeline E — Gate-review executed surface PRs (review only; never edits/merges)
#
# Scans AI-MYG org for open assigned issues with `executed` + open linked PR and
# no `review-dev-pass`, runs a gate review with a model != executor model, then
# passes (label) or rejects (remove `executed` + Gate Review comment for D).
#
# Scheduled via launchd: com.asp.issue-pr-reviewer
# Schedule: launchd_schedules.issue_pr_reviewer in config.yaml
#   (offset from Pipeline D executor :05/:35 by +10 min so PRs exist first)
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
pipeline_skip_if_weekend reviewer

cd "$REPO_ROOT"

# Network check
if ! host -W 3 api.github.com >/dev/null 2>&1 && \
   ! curl -sf --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping: no network connectivity (offline)"
  exit 0
fi

exec "$VENV_PYTHON" "$REPO_ROOT/tools/feishu_inbound/issue_pr_reviewer.py" --batch 3 --parallel
