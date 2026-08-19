#!/usr/bin/env bash
# Load ASP automation env from macOS Keychain (rootgrove/*). No .env required.
#
# Usage (from any asp-infra shell wrapper):
#   source "$(dirname "$0")/load_asp_env.sh"
#   # or: source "$REPO_ROOT/scripts/load_asp_env.sh"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export ASP_WORKTREE_ROOT="${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}"
export WORKSPACE_ROOT="${WORKSPACE_ROOT:-$ASP_WORKTREE_ROOT}"

_LOAD_SECRETS="$ASP_WORKTREE_ROOT/tools/secrets/load_secrets.sh"
if [[ -f "$_LOAD_SECRETS" ]]; then
  # shellcheck source=/dev/null
  source "$_LOAD_SECRETS"
else
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: load_secrets.sh not found at $_LOAD_SECRETS" >&2
fi

# Align legacy OPENCODE_HOST/PORT/USER/PASS with Keychain OPENCODE_BASE_URL / USERNAME / PASSWORD
# Use parameter expansion (not BASH_REMATCH) so sourcing works under zsh and bash.
if [[ -n "${OPENCODE_BASE_URL:-}" && -z "${OPENCODE_HOST:-}" ]]; then
  case "$OPENCODE_BASE_URL" in
    http://*|https://*)
      _opencode_rest="${OPENCODE_BASE_URL#*://}"
      OPENCODE_HOST="${_opencode_rest%%[:/]*}"
      _opencode_hostport="${_opencode_rest%%/*}"
      if [[ "$_opencode_hostport" == *:* ]]; then
        OPENCODE_PORT="${_opencode_hostport#*:}"
      elif [[ "$OPENCODE_BASE_URL" == https://* ]]; then
        OPENCODE_PORT=443
      else
        OPENCODE_PORT=4096
      fi
      export OPENCODE_HOST OPENCODE_PORT
      ;;
  esac
  unset _opencode_rest _opencode_hostport
fi
export OPENCODE_USER="${OPENCODE_USER:-${OPENCODE_USERNAME:-opencode}}"
export OPENCODE_PASS="${OPENCODE_PASS:-${OPENCODE_PASSWORD:-}}"
export OPENCODE_USERNAME="${OPENCODE_USERNAME:-$OPENCODE_USER}"
export OPENCODE_PASSWORD="${OPENCODE_PASSWORD:-$OPENCODE_PASS}"

# gh CLI / GitHub API (GraphQL: triage, lead-tick, observer) need outbound HTTPS.
# When mihomo is up on :7890 and no proxy is already set (launchd has a bare env),
# point HTTP(S)_PROXY at it. Skip if the port is down so we do not force a dead
# proxy onto jobs (fall back to direct). Pattern parity: tools/feishu_inbound/load_personal_env.sh.
if [[ -z "${HTTPS_PROXY:-}${HTTP_PROXY:-}${https_proxy:-}${http_proxy:-}" ]]; then
  if (echo >/dev/tcp/127.0.0.1/7890) >/dev/null 2>&1; then
    export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7890}"
    export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7890}"
    export ALL_PROXY="${ALL_PROXY:-http://127.0.0.1:7890}"
  fi
fi
