#!/usr/bin/env bash
# Shadow compare — ASP instance. Appends JSON diff to dated log under logs/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/tools/feishu_inbound/config.yaml"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/shadow_compare_$(date +%Y%m%d).log"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"

# shellcheck source=load_asp_env.sh
source "$SCRIPT_DIR/load_asp_env.sh"

mkdir -p "$LOG_DIR"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing venv: $VENV_PYTHON — run bash launchd/install.sh first" >&2
  exit 1
fi

{
  echo "=== shadow-compare asp $(date -Iseconds) ==="
  echo "config: $CONFIG"
  echo "legacy-root: $REPO_ROOT"
  "$VENV_PYTHON" -m feishu_inbound.cli shadow-compare \
    --legacy-root "$REPO_ROOT" \
    --config "$CONFIG" \
    --python "$VENV_PYTHON"
  echo "exit: $?"
  echo
} 2>&1 | tee -a "$LOG_FILE"

echo "Log: $LOG_FILE"
