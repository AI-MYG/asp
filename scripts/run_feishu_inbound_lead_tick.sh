#!/usr/bin/env bash
# Lead tick — Pipeline C+D+E (+F) chain (feishu-inbound engine)
#
# Scheduled via launchd: com.asp.feishu-inbound-lead-tick
# Schedule: launchd_schedules.lead_tick in config.yaml
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=load_asp_env.sh
source "$SCRIPT_DIR/load_asp_env.sh"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
  VENV_PYTHON="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/venv/bin/python"
fi

# shellcheck source=pipeline_skip_if_weekend.sh
source "$SCRIPT_DIR/pipeline_skip_if_weekend.sh"
pipeline_skip_if_weekend lead_tick

cd "$REPO_ROOT"

if ! host -W 3 api.github.com >/dev/null 2>&1 && \
   ! curl -sf --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping: no network connectivity (offline)"
  exit 0
fi

exec "$VENV_PYTHON" -m feishu_inbound.cli lead-tick --config "$REPO_ROOT/tools/feishu_inbound/config.yaml"
