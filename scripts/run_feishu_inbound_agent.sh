#!/usr/bin/env bash
# Pipeline C — Per-developer issue scanner with difficulty-aware analysis
#
# Scans AI-MYG/asp-backend for open issues assigned to GITHUB_ASSIGNEE,
# runs deep code analysis via OpenCode AgentClient, posts analysis comment.
#
# Scheduled via launchd: com.asp.feishu-inbound-agent
# Schedule: weekdays at :20 and :50 past each hour (9-18)
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"

# Fallback: use rootgrove venv if ASP venv doesn't exist
if [ ! -f "$VENV_PYTHON" ]; then
  VENV_PYTHON="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/venv/bin/python"
fi

# Skip weekends
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping on weekend (day=$DOW)"
  exit 0
fi

# Load .env
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE"
  set +a
fi

# Load secrets from macOS Keychain
LOAD_SECRETS="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}/tools/secrets/load_secrets.sh"
# shellcheck source=/dev/null
[ -f "$LOAD_SECRETS" ] && . "$LOAD_SECRETS"

cd "$REPO_ROOT"

# Network check
if ! host -W 3 api.github.com >/dev/null 2>&1 && \
   ! curl -sf --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping: no network connectivity (offline)"
  exit 0
fi

exec "$VENV_PYTHON" "$REPO_ROOT/tools/feishu_inbound/issue_scanner.py" --batch 3 --parallel
