#!/usr/bin/env bash
# Load ASP automation env from macOS Keychain (rootgrove/*). No .env required.
#
# Usage (from any asp-infra shell wrapper):
#   source "$(dirname "$0")/load_asp_env.sh"
#   # or: source "$REPO_ROOT/scripts/load_asp_env.sh"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export ASP_WORKTREE_ROOT="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}"

_LOAD_SECRETS="$ASP_WORKTREE_ROOT/tools/secrets/load_secrets.sh"
if [[ -f "$_LOAD_SECRETS" ]]; then
  # shellcheck source=/dev/null
  source "$_LOAD_SECRETS"
else
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: load_secrets.sh not found at $_LOAD_SECRETS" >&2
fi

# Align legacy OPENCODE_HOST/PORT/USER/PASS with Keychain OPENCODE_BASE_URL / USERNAME / PASSWORD
if [[ -n "${OPENCODE_BASE_URL:-}" && -z "${OPENCODE_HOST:-}" ]]; then
  if [[ "$OPENCODE_BASE_URL" =~ ^https?://([^:/]+)(:([0-9]+))? ]]; then
    OPENCODE_HOST="${BASH_REMATCH[1]}"
    if [[ -n "${BASH_REMATCH[3]:-}" ]]; then
      OPENCODE_PORT="${BASH_REMATCH[3]}"
    elif [[ "$OPENCODE_BASE_URL" == https://* ]]; then
      OPENCODE_PORT=443
    else
      OPENCODE_PORT=4096
    fi
    export OPENCODE_HOST OPENCODE_PORT
  fi
fi
export OPENCODE_USER="${OPENCODE_USER:-${OPENCODE_USERNAME:-opencode}}"
export OPENCODE_PASS="${OPENCODE_PASS:-${OPENCODE_PASSWORD:-}}"
export OPENCODE_USERNAME="${OPENCODE_USERNAME:-$OPENCODE_USER}"
export OPENCODE_PASSWORD="${OPENCODE_PASSWORD:-$OPENCODE_PASS}"
