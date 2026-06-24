#!/usr/bin/env bash
# Dev acceptance — wrap feishu-inbound accept (Pipeline post-F).
#
# Usage:
#   bash scripts/run_accept.sh pass --issue 148 --repo AI-MYG/asp-backend [--note "..."]
#   bash scripts/run_accept.sh fail --issue 148 --repo AI-MYG/asp-backend --reason "..."
#   bash scripts/run_accept.sh scan [--dry-run]
#
# Bootstrap first: bash scripts/bootstrap_inbound_cli.sh
# Docs: docs/onboarding_inbound_skills.md
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${ASP_INBOUND_CONFIG:-$REPO_ROOT/tools/feishu_inbound/config.yaml}"

# shellcheck source=load_asp_env.sh
source "$SCRIPT_DIR/load_asp_env.sh"

CLI="$REPO_ROOT/venv/bin/feishu-inbound"
if [[ ! -x "$CLI" ]]; then
  echo "error: $CLI not found — run: bash scripts/bootstrap_inbound_cli.sh" >&2
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "error: config not found: $CONFIG" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated — run 'gh auth login' as issue requester/assignee" >&2
  exit 1
fi

cd "$REPO_ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: run_accept.sh pass|fail|scan [feishu-inbound accept args...]" >&2
  exit 1
fi

MODE="$1"
shift

case "$MODE" in
  pass|fail)
  if [[ $# -lt 4 ]] || [[ "$1" != "--issue" ]] || [[ "$3" != "--repo" ]]; then
    echo "usage: run_accept.sh $MODE --issue N --repo owner/repo [--note ...] [--reason ...] [--dry-run]" >&2
    exit 1
  fi
  exec "$CLI" accept "$MODE" --config "$CONFIG" "$@"
  ;;
  scan)
  exec "$CLI" accept --config "$CONFIG" --scan-only "$@"
  ;;
  *)
  echo "usage: run_accept.sh pass|fail|scan ..." >&2
  exit 1
  ;;
esac
