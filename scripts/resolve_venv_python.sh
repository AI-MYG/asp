#!/usr/bin/env bash
# Resolve Python for ASP feishu-inbound pipeline (Pipeline B–F).
# Prefers rootgrove venv (cursor_sdk + editable feishu_inbound) over asp-infra venv.
#
# Usage (after load_asp_env.sh):
#   source "$SCRIPT_DIR/resolve_venv_python.sh"
#   resolve_venv_python
#   exec "$VENV_PYTHON" ...

resolve_venv_python() {
  local rootgrove="${WORKSPACE_ROOT:-${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}}"
  if [ -x "$rootgrove/venv/bin/python" ]; then
    VENV_PYTHON="$rootgrove/venv/bin/python"
  elif [ -n "${REPO_ROOT:-}" ] && [ -x "$REPO_ROOT/venv/bin/python" ]; then
    VENV_PYTHON="$REPO_ROOT/venv/bin/python"
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: no venv at $rootgrove/venv or ${REPO_ROOT:-<unset>}/venv" >&2
    return 1
  fi
  export VENV_PYTHON
}

ensure_feishu_inbound_imports() {
  if ! "$VENV_PYTHON" -c "import feishu_inbound" 2>/dev/null; then
    local req="${REPO_ROOT:-}/requirements-feishu-inbound.txt"
    if [ -f "$req" ]; then
      "$VENV_PYTHON" -m pip install -r "$req"
    fi
  fi
  if ! "$VENV_PYTHON" -c "import cursor_sdk" 2>/dev/null; then
    local tools_req="${WORKSPACE_ROOT:-${ASP_WORKTREE_ROOT:-$HOME/CursorWorks/rootgrove}}/tools/requirements.txt"
    if [ -f "$tools_req" ]; then
      "$VENV_PYTHON" -m pip install -r "$tools_req"
    fi
  fi
}
