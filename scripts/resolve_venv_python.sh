#!/usr/bin/env bash
# Resolve Python for ASP feishu-inbound pipeline (Pipeline B–F).
# Prefers rootgrove venv (cursor_sdk + pinned feishu_inbound wheel) over asp-infra venv.
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

report_feishu_inbound_runtime() {
  local req="${REPO_ROOT:-}/requirements-feishu-inbound.txt"
  local expected=""
  if [ -f "$req" ]; then
    expected="$(sed -n 's/^feishu-inbound==//p' "$req" | head -1 | tr -d '[:space:]')"
  fi

  local runtime
  runtime="$($VENV_PYTHON -c 'import feishu_inbound; print(feishu_inbound.__version__); print(feishu_inbound.__file__)')"
  local actual="${runtime%%$'\n'*}"
  local module_path="${runtime#*$'\n'}"
  echo "feishu-inbound runtime: version=${actual} expected=${expected:-untracked} python=${VENV_PYTHON} module=${module_path}"

  if [ -n "$expected" ] && [ "$actual" != "$expected" ]; then
    echo "WARN: feishu-inbound runtime version ${actual} != instance pin ${expected}" >&2
    if [ "${FEISHU_INBOUND_STRICT_VERSION:-0}" = "1" ]; then
      return 1
    fi
  fi
}
